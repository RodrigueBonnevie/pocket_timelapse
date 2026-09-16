#!/usr/bin/env python3
"""Live focus helper — turn the lens barrel until the number peaks.

The B0587's `Focus, Absolute` control is advertised by the UVC descriptor but
drives nothing: stepping it from 1 to 831 changes the image by about the
frame-to-frame noise floor. It is a fixed M12 lens, focused by rotating the
barrel, so focusing needs a human hand and a number to aim at.

Aim at whatever the timelapse will actually watch — for a cityscape, something
at infinity. Grip the barrel, turn slowly, watch the bar.

    ./focus_assist.py            # Ctrl-C when peaked

Exposure is locked so the number reflects focus and nothing else.
"""

import io
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2
from PIL import Image, ImageFilter, ImageStat

EXPOSURE = 60
WHITE_BALANCE_K = 5000
WIDTH, HEIGHT = 1920, 1080     # 1080p: enough detail to focus by, fast enough to feel live


def sharpness(jpeg):
    im = Image.open(io.BytesIO(jpeg))
    im.draft("L", (960, 540))
    im = im.convert("L")
    w, h = im.size
    centre = im.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
    return ImageStat.Stat(centre.filter(ImageFilter.FIND_EDGES)).stddev[0]


def main():
    signal.signal(signal.SIGINT, lambda *_: (print("\n"), sys.exit(0)))
    dev = str(next(Path("/dev/v4l/by-id").glob("*Arducam*index0")))

    with v4l2.Device(dev) as cam:
        fcc, w, h, _ = cam.configure("MJPG", WIDTH, HEIGHT)
        cam.set(v4l2.CID_EXPOSURE_AUTO, v4l2.EXPOSURE_MANUAL)
        cam.set(v4l2.CID_EXPOSURE_ABSOLUTE, EXPOSURE)
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 0)
        cam.set(v4l2.CID_WHITE_BALANCE_TEMPERATURE, WHITE_BALANCE_K)
        cam.start()
        for _ in range(10):
            cam.grab()

        print(f"{fcc} {w}x{h}, exposure locked at {EXPOSURE/10:.1f} ms")
        print("Turn the lens barrel slowly. Higher is sharper. Ctrl-C when peaked.\n")

        best, smooth = 0.0, None
        while True:
            s = sharpness(cam.grab())
            smooth = s if smooth is None else 0.7 * smooth + 0.3 * s
            best = max(best, smooth)
            # Scale the bar to the best seen so far, so it stays readable
            # whatever the scene's absolute detail level happens to be.
            filled = int(40 * smooth / best) if best else 0
            mark = "  <-- best" if smooth >= best - 1e-9 else ""
            print(f"\r  {smooth:7.2f}  [{'#' * filled}{'.' * (40 - filled)}]"
                  f"  best {best:6.2f}{mark}   ", end="", flush=True)
            time.sleep(0.05)


if __name__ == "__main__":
    main()
