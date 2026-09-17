#!/usr/bin/env python3
"""Grab a handful of 4K frames so the output can actually be looked at.

Two series: one across exposure, one across focus. The focus one matters
because the module has a motorised lens whose default position is 1, and
nothing has yet told it where infinity is — which for a cityscape is the whole
ball game.

    ./snap.py [output-dir]
    ./snap.py --dark [output-dir]    # long exposures and a gain ladder
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2
from PIL import Image, ImageFilter, ImageStat

OUT = Path.home() / "Pictures/arducam"
EXPOSURES = [18, 51, 144, 407, 1200]
FOCUS = [1, 100, 200, 350, 500, 700, 831]

# A dark scene lives at the far end of the range, where shutter alone runs out
# and gain has to take over. Both ladders matter: the handover between them is
# what ramp.py will be doing through the last of a sunset.
DARK_EXPOSURES = [500, 1000, 2000, 3500, 5000]
DARK_GAINS = [0, 25, 50, 75, 100]
LAG = 8                                   # measured at 6; a margin costs nothing
WHITE_BALANCE_K = 5000                    # daylight-ish; locked, never automatic
FOCUS_SETTLE_S = 1.0                      # the lens is a motor, not a register


def find():
    return str(next(Path("/dev/v4l/by-id").glob("*Arducam*index0")))


def grab(cam, n=LAG):
    for _ in range(n):
        frame = cam.grab()
    return frame


def detail(jpeg_path):
    """Edge energy on a centre crop — a rough sharpness proxy, enough to tell
    one focus position from another."""
    with Image.open(jpeg_path) as im:
        w, h = im.size
        crop = im.crop((w // 3, h // 3, 2 * w // 3, 2 * h // 3)).convert("L")
        return ImageStat.Stat(crop.filter(ImageFilter.FIND_EDGES)).stddev[0]


def dark_series(cam, out):
    print("exposure ladder at gain 0 (shutter only)")
    cam.set(v4l2.CID_GAIN, 0)
    for e in DARK_EXPOSURES:
        cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, e)
        p = out / f"dark_exp{e:04d}_{e/10:.0f}ms_gain00.jpg"
        p.write_bytes(grab(cam, LAG + 6))
        with Image.open(p) as im:
            y = ImageStat.Stat(im.convert("L")).mean[0]
        print(f"  {p.name:<36} luma {y:6.2f}   {p.stat().st_size/1000:5.0f} kB")

    print("\ngain ladder at maximum shutter (500 ms)")
    cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, DARK_EXPOSURES[-1])
    for g in DARK_GAINS:
        cam.set(v4l2.CID_GAIN, g)
        p = out / f"dark_exp5000_500ms_gain{g:02d}.jpg"
        p.write_bytes(grab(cam, LAG + 6))
        with Image.open(p) as im:
            y = ImageStat.Stat(im.convert("L")).mean[0]
        # File size is a rough noise proxy here: at a fixed scene, more grain
        # compresses worse, so a size climbing faster than luma means the gain
        # is buying noise rather than signal.
        print(f"  {p.name:<36} luma {y:6.2f}   {p.stat().st_size/1000:5.0f} kB")
    cam.set(v4l2.CID_GAIN, 0)


def main():
    global OUT
    dark = "--dark" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        OUT = Path(args[0])
    OUT.mkdir(parents=True, exist_ok=True)
    with v4l2.Device(find()) as cam:
        fcc, w, h, _ = cam.configure("MJPG", 3840, 2160)
        cam.set(v4l2.CID_EXPOSURE_AUTO, v4l2.EXPOSURE_MANUAL)
        # Disabling AWB without also fixing a temperature leaves the ISP in an
        # uninitialised gain state - on this module the green channel collapses
        # to zero. Locking white balance means setting it, not just switching
        # the automatic off.
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 0)
        cam.set(v4l2.CID_WHITE_BALANCE_TEMPERATURE, WHITE_BALANCE_K)
        cam.start()

        print(f"{fcc} {w}x{h} -> {OUT}\n")

        if dark:
            dark_series(cam, OUT)
            cam.stop()
            print(f"\n{len(list(OUT.glob('*.jpg')))} frames in {OUT}")
            return

        print("exposure series (focus left at default)")
        for e in EXPOSURES:
            cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, e)
            p = OUT / f"exposure_{e:04d}_{e/10:.1f}ms.jpg"
            p.write_bytes(grab(cam))
            print(f"  {p.name:<34} {p.stat().st_size/1000:5.0f} kB")

        print("\nfocus series at a mid exposure")
        cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, 144)
        best = (None, -1)
        for f in FOCUS:
            cam.set(v4l2.CID_FOCUS_ABSOLUTE, f)
            time.sleep(FOCUS_SETTLE_S)
            p = OUT / f"focus_{f:03d}.jpg"
            p.write_bytes(grab(cam, LAG + 8))
            d = detail(p)
            if d > best[1]:
                best = (f, d)
            print(f"  {p.name:<34} {p.stat().st_size/1000:5.0f} kB   detail {d:6.2f}")

        print(f"\nsharpest at focus={best[0]} (detail {best[1]:.2f})")
        cam.set(v4l2.CID_FOCUS_ABSOLUTE, best[0])
        cam.stop()

    print(f"\n{len(list(OUT.glob('*.jpg')))} frames in {OUT}")


if __name__ == "__main__":
    main()
