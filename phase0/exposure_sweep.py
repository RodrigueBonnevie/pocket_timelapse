#!/usr/bin/env python3
"""Phase 0 test 1 — does manual exposure behave predictably and repeatably?

The binary test. If exposure cannot be commanded in fine, consistent steps then
the sunset ramp is impossible and the architecture is dead regardless of sensor.

Point the camera at a static, evenly lit surface that will not change for the
duration — a blank wall under steady artificial light. Daylight drifts, and the
drift reads as a camera fault.

    ./exposure_sweep.py                  # auto-detects the Arducam
    ./exposure_sweep.py /dev/video4

Needs nothing installed beyond python3 and Pillow.
"""

import io
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2
from PIL import Image, ImageStat

OUT = Path("phase0-results")
WIDTH, HEIGHT = 3840, 2160     # test the configuration the build will actually use
SETTLE_TOL = 0.005             # frames agree to 0.5 % -> the change has landed
SETTLE_MAX = 40                # give up rather than hang on a drifting scene
RESPOND_MIN = 0.03             # a step must lift luma this much to count as responding
STOPS, PER_STOP, RUNS = 6, 2, 2
RAMP_STEP_LIMIT = 1 / 6        # the ramp's per-frame budget, from ramp.py


def find():
    for link in sorted(Path("/dev/v4l/by-id").glob("*video-index0")):
        if "Arducam" in link.name:
            return str(link)
    sys.exit("No Arducam under /dev/v4l/by-id — pass the device path explicitly.")


def ladder(lo, hi):
    """Geometric, because the ramp works in ratios. Starts where a single
    integer step first falls inside the ramp's budget — below that the control
    is too coarse to ramp through regardless of how well it behaves."""
    start = lo
    while math.log2((start + 1) / start) > RAMP_STEP_LIMIT:
        start += 1
    vals = []
    for i in range(STOPS * PER_STOP + 1):
        v = round(start * 2 ** (i / PER_STOP))
        if v > hi:
            break
        if not vals or v != vals[-1]:
            vals.append(v)
    return start, vals


def quick_luma(jpeg):
    """DCT-scaled decode - a 4K frame per settle frame is otherwise the
    bottleneck, and settling only needs a stable number, not a sharp one."""
    im = Image.open(io.BytesIO(jpeg))
    im.draft("L", (480, 270))
    return ImageStat.Stat(im.convert("L")).mean[0]


def measure_lag(cam, lo, hi):
    """How many frames the pipeline serves at the old exposure after a change.

    Queued buffers carry the previous exposure, so "two frames agree" is
    satisfied immediately by two stale frames. Rather than guess a drain depth,
    step between two exposures and count frames until the image actually moves.
    The answer is also the latency component of t_on."""
    cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, lo)
    for _ in range(SETTLE_MAX):
        cam.grab()
    base = quick_luma(cam.grab())

    cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, hi)
    for n in range(1, SETTLE_MAX + 1):
        if abs(quick_luma(cam.grab()) - base) > 0.2 * max(base, 1.0):
            return n
    return SETTLE_MAX


def settle(cam, lag):
    """Drain the known-stale frames, then wait for two to agree."""
    t0 = time.monotonic()
    for _ in range(lag):
        frame = cam.grab()
    prev = quick_luma(frame)
    for n in range(lag + 1, SETTLE_MAX + 1):
        frame = cam.grab()
        cur = quick_luma(frame)
        if abs(cur - prev) <= SETTLE_TOL * max(cur, 1e-6):
            return frame, cur, n, time.monotonic() - t0
        prev = cur
    return frame, prev, SETTLE_MAX, time.monotonic() - t0


def usable_range(cam, values, lag):
    """Keep the contiguous span where luma actually responds to exposure.

    A band check on absolute luma is not enough: once highlights clip, the mean
    sits at some plateau value that may well fall inside any sensible band, and
    a clipped step is indistinguishable from an ignored command. Responsiveness
    is the property that matters, so test for it directly."""
    probe = []
    for v in values:
        cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, v)
        _, luma, _, _ = settle(cam, lag)
        probe.append((v, luma))

    best, run = [], []
    for (v, y), (_, y_next) in zip(probe, probe[1:]):
        if y_next > y * (1 + RESPOND_MIN):
            run = run + [v] if run else [v]
        else:
            if len(run) > len(best):
                best = run + [v]      # the step that ended the run is still valid
            run = []
    if len(run) > len(best):
        best = run + [probe[-1][0]]

    if len(best) < 5:
        print(f"  only {len(best)} responsive steps - the scene is clipping or too "
              f"dark.\n  Aim at an evenly lit surface that fills the frame, then re-run.")
        lo_y, hi_y = probe[0][1], probe[-1][1]
        print(f"  (luma spanned {lo_y:.1f} to {hi_y:.1f} across {values[0]}-{values[-1]})")
        return [v for v, _ in probe]
    print(f"  responsive: {len(best)} of {len(values)} steps ({best[0]}-{best[-1]})")
    return best


def sweep(cam, values, run, lag):
    rows = []
    for v in values:
        cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, v)
        frame, luma, nframes, secs = settle(cam, lag)
        readback = cam.get(v4l2.CID_EXPOSURE_ABSOLUTE)
        path = OUT / f"run{run}_exp{v:05d}.jpg"
        path.write_bytes(frame)
        rows.append((v, readback, luma, len(frame), nframes, secs))
        flag = "" if readback == v else f"  READBACK {readback}"
        print(f"  {v:>5} -> luma {luma:6.2f}   {len(frame)/1000:5.0f} kB   "
              f"settled in {nframes:>2} frames / {secs*1000:4.0f} ms{flag}")
    return rows


def analyse(runs):
    a = runs[0]
    n = len(a)
    print("\n" + "=" * 64)

    # A power law, not a straight line: the ISP applies gamma, so the exponent
    # is whatever that curve is. Consistency is what matters, not its value.
    xs = [math.log2(v) for v, _, _, _, _, _ in a]
    ys = [math.log2(max(y, 1e-6)) for _, _, y, _, _, _ in a]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    print(f"response shape   luma ~ exposure^{slope:.3f}   R2 {r2:.4f}   [informational]")
    print("                 The ISP applies a tone curve, so a pure power law is not")
    print("                 expected. ramp.py is a closed loop measuring luma and")
    print("                 correcting, so shape does not need to be linear.")

    lumas = [y for _, _, y, _, _, _ in a]
    rises = sum(1 for p, q in zip(lumas, lumas[1:]) if q > p * 1.02)
    print(f"monotonic        {rises}/{n - 1} steps rose by >2 %")

    worst = 0.0
    if len(runs) > 1:
        worst = max(abs(p[2] - q[2]) / max(p[2], 1e-6) for p, q in zip(runs[0], runs[1]))
        print(f"repeatability    worst gap between runs {worst * 100:.2f} %")

    accepted = sum(1 for v, rb, _, _, _, _ in a if v == rb)
    print(f"readback         {accepted}/{n} commands accepted verbatim")

    sizes = [s for _, _, _, s, _, _ in a]
    print(f"frame size       {min(sizes)/1000:.0f}-{max(sizes)/1000:.0f} kB "
          f"(feeds the storage model; scene-dependent)")
    fr = [f for _, _, _, _, f, _ in a]
    ms = [s * 1000 for _, _, _, _, _, s in a]
    print(f"settling         {min(fr)}-{max(fr)} frames, {min(ms):.0f}-{max(ms):.0f} ms "
          f"(the settling component of t_on)")

    print("=" * 64)
    # What a closed-loop ramp actually requires: every command moves the image
    # in the right direction, the same command gives the same result twice, and
    # nothing is silently ignored.
    checks = {
        "monotonic": rises == n - 1,
        "repeatable": worst < 0.03,
        "commands honoured": accepted == n,
    }
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    ok = all(checks.values())
    print("-" * 64)
    if ok:
        print("PASS - the exposure ramp is viable on this camera.")
    else:
        print("FAIL.")
        print("  not monotonic -> plateaus mean clipping or ignored commands. If the")
        print("                   scene was clipping, re-aim and re-run before judging.")
        print("  not repeatable -> hysteresis. Fatal: this is what makes a ramp flicker.")
        print("  not honoured   -> the camera clamped or ignored values.")
    return ok


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else find()
    OUT.mkdir(exist_ok=True)
    print(f"camera: {dev}")

    with v4l2.Device(dev) as cam:
        fcc, w, h, _ = cam.configure("MJPG", WIDTH, HEIGHT)
        print(f"format: {fcc} {w}x{h}")

        cam.set(v4l2.CID_EXPOSURE_AUTO, v4l2.EXPOSURE_MANUAL)
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 0)
        if cam.get(v4l2.CID_EXPOSURE_AUTO) != v4l2.EXPOSURE_MANUAL:
            sys.exit("Camera refused manual exposure mode - that is a test-1 failure.")

        lo = hi = None
        for c in cam.controls():
            if c["id"] == v4l2.CID_EXPOSURE_ABSOLUTE:
                lo, hi = c["min"], c["max"]
        start, values = ladder(lo, hi)
        print(f"exposure range {lo}..{hi} (x0.1 ms); ramping from {start} "
              f"where one step first fits {RAMP_STEP_LIMIT:.3f} stops")
        print(f"ladder: {len(values)} half-stop steps, {values[0]}-{values[-1]}")

        cam.start()
        lag = measure_lag(cam, values[0], values[-1])
        print(f"pipeline lag: {lag} frames of stale exposure after a change")
        values = usable_range(cam, values, lag)
        print()
        runs = []
        for r in range(1, RUNS + 1):
            print(f"run {r}/{RUNS}")
            runs.append(sweep(cam, values, r, lag))
        cam.stop()

    with (OUT / "sweep.csv").open("w") as fh:
        fh.write("run,commanded,readback,luma,bytes,settle_frames,settle_s\n")
        for i, rows in enumerate(runs, 1):
            for v, rb, y, b, f, sec in rows:
                fh.write(f"{i},{v},{rb},{y:.4f},{b},{f},{sec:.4f}\n")
    print(f"\nwrote {OUT}/sweep.csv and {sum(len(r) for r in runs)} frames")

    sys.exit(0 if analyse(runs) else 1)


if __name__ == "__main__":
    main()
