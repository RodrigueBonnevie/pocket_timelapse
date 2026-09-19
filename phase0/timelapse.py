#!/usr/bin/env python3
"""Shoot a real sunset from a laptop, and find out what the camera runs out of.

Phase 0 measured the module against walls and lamps. That answers whether the
controls behave, but not the question that actually decides the build: over a
real sunset, does this camera have enough range, and where does it give up?

So this writes 4K JPEGs on a monotonic schedule while a closed loop ramps
exposure, and logs enough per frame to answer afterwards:

  * how many stops the scene moved through
  * how many of them the camera could follow
  * when it pinned at the top of its range, and by how much it fell short

Being pinned is not a crash. The frames keep coming, they just go dark. That
shortfall, in stops, is the number this is here to produce.

    ./timelapse.py --interval 5 --until 21:30
    ./timelapse.py --interval 2 --duration 45m --target 110
    ./timelapse.py --shutter-ceiling 5000     # pretend the cap is not there

Needs nothing installed beyond python3 and Pillow.
"""

import argparse
import io
import math
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2
from PIL import Image, ImageStat

WIDTH, HEIGHT = 3840, 2160
WHITE_BALANCE_K = 5000      # locked, never automatic - see the magenta trap in README
# The control bottoms out at 1, and starting the ladder at 9 threw away 3.2
# stops at exactly the end daylight needs. Below COARSE_BELOW one integer step
# is bigger than the whole per-frame budget, so the ramp gets lumpy down there -
# lumpy beats having no range at all, and an ND filter is the real fix.
SHUTTER_MIN = 1
COARSE_BELOW = 9
SHUTTER_CEILING = 144       # measured 2026-09-17: above this the module ignores it
GAIN_MAX = 100
GAIN_STEP = 2

STEP_LIMIT = 1 / 6          # max stops of correction per frame; more than this strobes
# Rung spacing is deliberately finer than STEP_LIMIT. They are different things:
# STEP_LIMIT bounds how fast the ramp may chase the sun, while the rung is the
# smallest brightness change the ladder can express - and therefore the size of
# the jump every correction makes. At 1/6 stop per rung the loop settles with up
# to half a rung of standing error and then closes it in one visible 11 % step.
# At 1/12 it tracks the same speed with half the quantisation.
RUNG_STOPS = 1 / 12
DEADBAND = 0.02             # stops; below this, leave it alone rather than hunt
MAX_RUNGS = 6               # a bound on a bad stops-per-rung estimate, not on the ramp
TARGET_LUMA = 100.0
CLIP_LEVEL = 250            # counted as blown
MAX_BLOWN = 2.0             # percent of frame allowed above CLIP_LEVEL
# The driver fills all its buffers within ~160 ms of a control change and then
# stalls for want of a free one, so every queued frame predates the change. The
# drain therefore has to clear the queue AND outlast the measured 6-frame
# settling lag, not just one of the two.
DRAIN = 12
AWB_CONVERGE = 40           # frames of live AWB before the gains are frozen


def find():
    for link in sorted(Path("/dev/v4l/by-id").glob("*video-index0")):
        if "Arducam" in link.name:
            return str(link)
    sys.exit("No Arducam under /dev/v4l/by-id - pass --device explicitly.")


def build_ladder(shutter_min, shutter_ceiling, gain_max):
    """One ordered axis of light-gathering: shutter first, then gain.

    Keeping them on a single ladder is the whole point. A loop that treats
    exposure and gain as independent will happily wind exposure up to the
    control's advertised maximum, sit there having no effect, and never reach
    for gain at all - which is exactly what this module's silent shutter cap
    would cause."""
    rungs, v = [], shutter_min
    while v < shutter_ceiling:
        rungs.append((v, 0))
        # Near the bottom of the range one integer count is coarser than a rung,
        # which is the quantisation floor SHUTTER_MIN exists to keep us above.
        v = max(v + 1, round(v * 2 ** RUNG_STOPS))
    rungs.append((shutter_ceiling, 0))
    for g in range(GAIN_STEP, gain_max + 1, GAIN_STEP):
        rungs.append((shutter_ceiling, g))
    return rungs


class Ramp:
    """Closed loop on measured luma.

    It does not need to know the camera's transfer function, which is just as
    well: the ISP applies a tone curve, and gain buys far fewer stops than it
    nominally promises. Instead it learns stops-per-rung from what actually
    happened and sizes its next move from that."""

    def __init__(self, ladder, target, start, max_blown=MAX_BLOWN):
        self.ladder = ladder
        self.target = target
        self.max_blown = max_blown
        self.i = start
        self.stops_per_rung = RUNG_STOPS
        self._prev = None            # (index that luma belongs to, that luma)

    @property
    def setting(self):
        return self.ladder[self.i]

    def _learn(self, luma):
        if not self._prev:
            return
        prev_i, prev_luma = self._prev
        di = self.i - prev_i
        if di and prev_luma > 0.5 and luma > 0.5:
            observed = abs(math.log2(luma / prev_luma) / di)
            if 0.002 < observed < 1.0:
                self.stops_per_rung += 0.25 * (observed - self.stops_per_rung)

    def update(self, luma, blown):
        """Returns (error_stops, rungs_moved, pinned)."""
        self._learn(luma)
        err = math.log2(self.target / max(luma, 0.5))
        if blown > self.max_blown:
            # Metering the mean exposes for the ground and burns the sky off the
            # top of the histogram. Shadows can be lifted later; clipped sky is
            # gone for good, so highlights win the argument.
            err = min(err, -0.5 * math.log2(blown / self.max_blown))
        at_top, at_bottom = self.i == len(self.ladder) - 1, self.i == 0
        pinned = (err > DEADBAND and at_top) or (err < -DEADBAND and at_bottom)

        moved = 0
        if abs(err) > DEADBAND and not pinned:
            want = max(-STEP_LIMIT, min(STEP_LIMIT, err))
            # Round, and honour a rounded-down zero. Forcing a minimum move of
            # one rung instead makes the loop hunt forever whenever the error
            # sits below half a rung: it overshoots, reverses, overshoots back.
            # A rung of gain is ~0.05 stops, so that hunting is a visible
            # per-frame flicker - the exact artefact this ramp exists to avoid.
            n = int(round(want / max(self.stops_per_rung, 1e-3)))
            n = max(-MAX_RUNGS, min(MAX_RUNGS, n))
            if n:
                target_i = max(0, min(len(self.ladder) - 1, self.i + n))
                self._prev = (self.i, luma)
                moved = target_i - self.i
                self.i = target_i
        if not moved:
            self._prev = None        # nothing moved, so nothing to learn from
        return err, moved, pinned


def measure(jpeg):
    """Mean luma, blown percentage, per-channel means.

    DCT-scaled decode: a full 4K decode per frame would dominate a 2 s interval,
    and the loop needs a stable number rather than a sharp image."""
    im = Image.open(io.BytesIO(jpeg))
    im.draft("RGB", (480, 270))
    rgb = im.convert("RGB")
    r, g, b = ImageStat.Stat(rgb).mean
    h = rgb.convert("L").histogram()
    n = sum(h)
    luma = sum(v * c for v, c in enumerate(h)) / n
    return luma, 100.0 * sum(h[CLIP_LEVEL:]) / n, r, g, b


def acquire(cam, ramp, target, max_blown):
    """Place the exposure before the first frame is written.

    The per-frame step limit exists to keep the finished sequence from
    flickering. Applied to the initial acquisition it does the opposite of its
    job: starting several stops off, the ramp needs dozens of frames to crawl
    into range and every one of them lands in the sequence. A clipped frame
    makes it worse, because luma pins near 255 - however overexposed the frame
    really is, the error never reads worse than about -1.4 stops, so the crawl
    is slower than the true error warrants.

    Brightness is monotonic along the ladder, so bisect it instead: about seven
    probes to place the exposure, none of them recorded, no step limit.
    """
    lo, hi, probes = 0, len(ramp.ladder) - 1, 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        exp, gain = ramp.ladder[mid]
        cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, exp)
        cam.set(v4l2.CID_GAIN, gain)
        for _ in range(DRAIN):
            frame = cam.grab()
        probes += 1
        luma, blown, *_ = measure(frame)
        if luma <= target and blown <= max_blown:
            lo = mid                      # still short of target: go brighter
        else:
            hi = mid - 1
    ramp.i = lo
    exp, gain = ramp.setting
    cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, exp)
    cam.set(v4l2.CID_GAIN, gain)
    return probes


def write_frame(path, data):
    """Atomic: a power cut costs at most the frame in flight, never the
    sequence. The directory fsync is what makes the rename itself durable."""
    tmp = path.with_suffix(".jpg.tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.rename(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def parse_duration(s):
    total, num = 0, ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            if not num:
                raise argparse.ArgumentTypeError(f"bad duration: {s}")
            total += int(num) * {"s": 1, "m": 60, "h": 3600}[ch]
            num = ""
    if num:
        total += int(num)
    return total


def parse_until(s):
    hh, mm = (int(x) for x in s.split(":"))
    now = datetime.now()
    end = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if end <= now:
        end += timedelta(days=1)
    return (end - now).total_seconds()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between frames")
    ap.add_argument("--duration", type=parse_duration, help="e.g. 90m, 1h30m")
    ap.add_argument("--until", type=parse_until, dest="duration",
                    help="local clock time, e.g. 21:30")
    ap.add_argument("--target", type=float, default=TARGET_LUMA,
                    help=f"luma the ramp aims for, 0-255 (default {TARGET_LUMA:.0f})")
    ap.add_argument("--shutter-ceiling", type=int, default=SHUTTER_CEILING,
                    help=f"top of the useful shutter range (default {SHUTTER_CEILING}, measured)")
    ap.add_argument("--gain-max", type=int, default=GAIN_MAX)
    ap.add_argument("--max-blown", type=float, default=MAX_BLOWN,
                    help=f"%% of frame allowed above {CLIP_LEVEL} before highlights "
                         f"override the mean (default {MAX_BLOWN}; 100 disables)")
    ap.add_argument("--out", type=Path, help="session directory")
    ap.add_argument("--device", help="defaults to the Arducam under /dev/v4l/by-id")
    args = ap.parse_args()

    out = args.out or (Path.home() / "Pictures/timelapse" /
                       datetime.now().strftime("%Y-%m-%d_%H%M"))
    out.mkdir(parents=True, exist_ok=True)

    ladder = build_ladder(SHUTTER_MIN, args.shutter_ceiling, args.gain_max)
    dev = args.device or find()

    stop = False

    def handle(signum, frame):
        nonlocal stop
        stop = True
        print("\n  stopping after this frame...")

    signal.signal(signal.SIGINT, handle)

    print(f"camera   {dev}")
    print(f"session  {out}")
    print(f"ladder   {len(ladder)} rungs: shutter {SHUTTER_MIN}-{args.shutter_ceiling} "
          f"(x0.1 ms), then gain 0-{args.gain_max}")
    print(f"target   luma {args.target:.0f}   interval {args.interval:g} s", end="")
    print(f"   for {args.duration/60:.0f} min" if args.duration else "   until Ctrl-C")
    print()

    csv = (out / "frames.csv").open("w")
    csv.write("frame,unix,iso,exposure,gain,rung,luma,blown_pct,err_stops,moved,"
              "pinned,bytes,r,g,b\n")

    with v4l2.Device(dev) as cam:
        fcc, w, h, _ = cam.configure("MJPG", WIDTH, HEIGHT)
        cam.set(v4l2.CID_EXPOSURE_AUTO, v4l2.EXPOSURE_MANUAL)
        if cam.get(v4l2.CID_EXPOSURE_AUTO) != v4l2.EXPOSURE_MANUAL:
            sys.exit("Camera refused manual exposure - cannot ramp.")

        ramp = Ramp(ladder, args.target, 0, args.max_blown)

        # AWB runs live through acquisition so that it converges on a correctly
        # exposed image rather than a blown one, and is frozen once the exposure
        # has been placed. Switching AWB straight off from a cold plug-in can
        # leave the ISP with uninitialised gains - the green channel collapses
        # to zero and every frame comes out magenta. Those gains survive until
        # the camera loses power, which is why the fault only shows on the first
        # session after plugging in, and why it is easy to convince yourself it
        # has gone away.
        #
        # Freezing after convergence is also the right thing for a sunset: a
        # live AWB would spend the whole session neutralising exactly the colour
        # shift being filmed.
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 1)
        cam.start()

        probes = acquire(cam, ramp, args.target, args.max_blown)
        exp, gain = ramp.setting
        print(f"acquired rung {ramp.i}/{len(ladder) - 1}: exposure {exp} gain {gain} "
              f"({probes} probes, none recorded)")

        for _ in range(AWB_CONVERGE):
            cam.grab()
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 0)

        for _ in range(DRAIN):
            frame = cam.grab()
        _, _, r, g, b = measure(frame)
        if g < 1.0:
            cam.set(v4l2.CID_WHITE_BALANCE_TEMPERATURE, WHITE_BALANCE_K)
            for _ in range(DRAIN):
                frame = cam.grab()
            _, _, r, g, b = measure(frame)
        if g < 1.0:
            sys.exit("Green channel is dead - white balance never initialised.\n"
                     "Unplug the camera, plug it back in, and start again.")
        print(f"white balance locked at R{r:.0f} G{g:.0f} B{b:.0f}\n")

        t0 = time.monotonic()
        deadline = t0
        n = skipped = pinned_frames = stale = coarse = 0
        previous = None
        worst_deficit = 0.0
        pinned_since = None
        first_luma = last_luma = None

        try:
            while not stop:
                if args.duration and time.monotonic() - t0 >= args.duration:
                    break
                now = time.monotonic()
                if deadline > now:
                    time.sleep(deadline - now)

                for _ in range(DRAIN):
                    frame = cam.grab()
                # A frame identical to the last one is a stale buffer, not a
                # still scene: two real captures always differ in sensor noise.
                for _ in range(DRAIN):
                    if frame != previous:
                        break
                    frame = cam.grab()
                    stale += 1
                previous = frame
                luma, blown, r, g, b = measure(frame)
                exp, gain = ramp.setting
                wall = time.time()

                path = out / f"{n:06d}.jpg"
                write_frame(path, frame)

                err, moved, pinned = ramp.update(luma, blown)
                if pinned:
                    pinned_frames += 1
                    worst_deficit = max(worst_deficit, abs(err))
                    if pinned_since is None:
                        pinned_since = wall
                else:
                    pinned_since = None
                if first_luma is None:
                    first_luma = luma
                last_luma = luma

                csv.write(f"{n},{wall:.3f},{datetime.fromtimestamp(wall).isoformat()},"
                          f"{exp},{gain},{ramp.i},{luma:.3f},{blown:.3f},{err:+.4f},"
                          f"{moved},{int(pinned)},{len(frame)},{r:.2f},{g:.2f},"
                          f"{b:.2f}\n")
                csv.flush()
                os.fsync(csv.fileno())

                mark = "  PINNED" if pinned else ""
                if exp < COARSE_BELOW and not mark:
                    mark = "  coarse"
                print(f"  {n:>5}  {datetime.fromtimestamp(wall):%H:%M:%S}  "
                      f"exp {exp:>4} gain {gain:>3}  luma {luma:6.2f}  "
                      f"blown {blown:5.2f}%  err {err:+.2f} st  "
                      f"{len(frame)/1000:5.0f} kB{mark}")
                if exp < COARSE_BELOW:
                    coarse += 1

                # Apply the next setting immediately, so it has the whole
                # interval to settle instead of costing settling frames later.
                exp, gain = ramp.setting
                cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, exp)
                cam.set(v4l2.CID_GAIN, gain)

                n += 1
                deadline += args.interval
                while deadline <= time.monotonic():
                    deadline += args.interval    # fell behind: skip, never catch up
                    skipped += 1
        finally:
            cam.stop()
            csv.close()

    print("\n" + "=" * 68)
    print(f"{n} frames over {(time.monotonic()-t0)/60:.1f} min -> {out}")
    if skipped:
        print(f"{skipped} intervals missed (capture slower than the interval)")
    if stale:
        print(f"{stale} extra frames drained to clear stale buffers")
    if first_luma and last_luma:
        print(f"scene moved {abs(math.log2(max(last_luma,0.5)/max(first_luma,0.5))):.2f} "
              f"stops of measured luma, which is what was left AFTER the ramp "
              f"corrected - not the scene's own swing")
    if coarse:
        print(f"\n{coarse}/{n} frames sat below exposure {COARSE_BELOW}, where one "
              f"integer step\nexceeds the ramp's per-frame budget - expect visible "
              f"steps there.\nAn ND filter buys the same headroom smoothly.")
    if pinned_frames:
        print(f"\nPINNED for {pinned_frames}/{n} frames "
              f"({100*pinned_frames/max(n,1):.0f} % of the session)")
        print(f"worst shortfall {worst_deficit:.2f} stops beyond the camera's range")
        print("That shortfall is the answer to whether the shutter cap matters.")
    else:
        print("\nNever pinned - the ramp stayed inside the camera's range throughout.")
    print("=" * 68)
    print(f"\nassemble:\n  ffmpeg -framerate 24 -pattern_type glob -i '{out}/*.jpg' \\\n"
          f"    -vf deflicker=mode=pm:size=10,scale=3840:2160 -c:v libx264 -crf 18 "
          f"{out.name}.mp4")


if __name__ == "__main__":
    main()
