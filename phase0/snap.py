#!/usr/bin/env python3
"""Grab a handful of 4K frames so the output can actually be looked at.

Two series: one across exposure, one across focus. The focus one matters
because the module has a motorised lens whose default position is 1, and
nothing has yet told it where infinity is — which for a cityscape is the whole
ball game.

    ./snap.py [output-dir]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2
from PIL import Image, ImageFilter, ImageStat

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Pictures/arducam"
EXPOSURES = [18, 51, 144, 407, 1200]
FOCUS = [1, 100, 200, 350, 500, 700, 831]
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


def main():
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
