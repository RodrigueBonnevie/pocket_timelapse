#!/usr/bin/env python3
"""Ask the camera to describe itself.

Read-only. Answers, in one run: whether MJPEG is offered, what resolutions and
frame rates exist, whether manual exposure is exposed, the real exposure range
on this unit, and whether a compression-quality control exists for storage.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2

BY_ID = Path("/dev/v4l/by-id")


def find():
    for link in sorted(BY_ID.glob("*video-index0")):
        if "Arducam" in link.name:
            return str(link)
    sys.exit("No Arducam found under /dev/v4l/by-id — pass the device path.")


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else find()
    print(f"device: {dev}\n")

    with v4l2.Device(dev) as cam:
        cap = cam.capability()
        print(f"driver   {cap.driver.decode()}")
        print(f"card     {cap.card.decode()}")
        print(f"bus      {cap.bus_info.decode()}\n")

        print("formats and frame rates")
        for fcc, desc in cam.formats():
            print(f"  {fcc}  {desc}")
            for w, h in cam.frame_sizes(fcc):
                fps = cam.frame_intervals(fcc, w, h)
                rates = ", ".join(f"{f:g}" for f in fps) if fps else "?"
                mark = "   <-- 4K" if w >= 3840 else ""
                print(f"      {w:>5} x {h:<5} {rates:>22} fps{mark}")

        print("\ncontrols")
        for c in cam.controls():
            rng = f"{c['min']}..{c['max']} step {c['step']} default {c['default']}"
            ro = "  [read-only]" if c["flags"] & 0x0002 else ""
            print(f"  {c['name']:<34} {c['type']:<6} {rng}{ro}")
            for idx, label in c.get("menu", {}).items():
                print(f"       {idx}: {label}")


if __name__ == "__main__":
    main()
