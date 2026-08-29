#!/usr/bin/env python3
"""Phase 0 test 1 — does manual exposure behave linearly and repeatably?

This is the binary test. If exposure cannot be commanded in fine, predictable,
repeatable steps then the sunset ramp is impossible and the UVC architecture is
dead, regardless of how good the sensor is.

Point the camera at a static, evenly lit surface that does not change over the
run — a blank wall under steady artificial light. Daylight drifts and will be
read as non-linearity.

    ./exposure_sweep.py                 # auto-detect the camera
    ./exposure_sweep.py /dev/video0     # or name it

Requires: v4l-utils (v4l2-ctl) and Pillow.
"""

import math
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageStat

OUT = Path("phase0-results")
SETTLE_S = 0.6          # after a control change, before the throwaway frame
STOPS = 6               # sweep range
STEPS_PER_STOP = 2      # half-stop ladder
RUNS = 2                # repeatability needs at least two

# The kernel renamed several of these; which pair exists tells us nothing about
# the camera, only about the running kernel, so accept either.
AUTO_EXPOSURE = ("auto_exposure", "exposure_auto")
EXPOSURE = ("exposure_time_absolute", "exposure_absolute")
AUTO_WB = ("white_balance_automatic", "white_balance_temperature_auto")


def v4l2(dev, *args, check=True):
    r = subprocess.run(["v4l2-ctl", "-d", dev, *args],
                       capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"v4l2-ctl {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def find_camera():
    """Prefer the by-id path — /dev/videoN moves across re-enumeration."""
    by_id = Path("/dev/v4l/by-id")
    if by_id.is_dir():
        for link in sorted(by_id.iterdir()):
            if "index0" in link.name:      # index0 is the capture node
                return str(link)
    out = v4l2("/dev/video0", "--list-devices", check=False)
    if out:
        return "/dev/video0"
    sys.exit("No camera found. Pass the device path explicitly.")


def controls(dev):
    """Map control name -> (min, max, step, default)."""
    found = {}
    for line in v4l2(dev, "--list-ctrls-menus").splitlines():
        m = re.match(r"\s*(\w+)\s+0x[0-9a-f]+\s+\((\w+)\)\s*:\s*(.*)", line)
        if not m:
            continue
        name, _, rest = m.groups()
        nums = dict(re.findall(r"(min|max|step|default)=(-?\d+)", rest))
        if nums:
            found[name] = {k: int(v) for k, v in nums.items()}
    return found


def pick(available, candidates, what):
    for c in candidates:
        if c in available:
            return c
    sys.exit(f"This camera exposes no {what} control (tried {', '.join(candidates)}).\n"
             f"That is a test-1 failure: the ramp cannot be driven.")


def capture(dev, path):
    """Two grabs, keep the second — the first covers pipeline settling."""
    for _ in range(2):
        v4l2(dev, "--stream-mmap", "--stream-count=1", f"--stream-to={path}")
    return path


def luma(path):
    with Image.open(path) as im:
        return ImageStat.Stat(im.convert("L")).mean[0]


def ladder(lo, hi):
    """Geometric ladder — the ramp works in ratios, so linear steps would
    cluster uselessly at the bright end."""
    start = max(lo, 9)   # below ~9 the integer step exceeds 1/6 stop
    vals, n = [], STOPS * STEPS_PER_STOP
    for i in range(n + 1):
        v = round(start * 2 ** (i / STEPS_PER_STOP))
        if v > hi:
            break
        if not vals or v != vals[-1]:
            vals.append(v)
    return vals


def sweep(dev, exp_ctl, values, run):
    result = []
    for v in values:
        v4l2(dev, "-c", f"{exp_ctl}={v}")
        time.sleep(SETTLE_S)
        readback = int(re.search(r": (-?\d+)", v4l2(dev, "-C", exp_ctl)).group(1))
        f = OUT / f"run{run}_exp{v:05d}.jpg"
        capture(dev, f)
        y = luma(f)
        result.append((v, readback, y))
        flag = "" if readback == v else f"  READBACK {readback}"
        print(f"  {v:>5} → luma {y:7.2f}{flag}")
    return result


def analyse(runs, values):
    print("\n" + "=" * 62)

    # Linearity: in log-log a perfect sensor gives slope 1.0.
    xs = [math.log2(v) for v, _, _ in runs[0]]
    ys = [math.log2(max(y, 1e-6)) for _, _, y in runs[0]]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sxy / sxx if sxx else 0
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    print(f"linearity        slope {slope:.3f} (ideal 1.000), R² {r2:.4f}")

    # Monotonicity: a plateau means the command was quantised or ignored.
    lumas = [y for _, _, y in runs[0]]
    flat = sum(1 for a, b in zip(lumas, lumas[1:]) if b <= a * 1.02)
    print(f"monotonic        {n - 1 - flat}/{n - 1} steps rose by >2 %")

    # Repeatability is what actually breaks a ramp: the same command must give
    # the same exposure on every pass or the sequence flickers.
    if len(runs) > 1:
        worst = max(abs(a[2] - b[2]) / max(a[2], 1e-6)
                    for a, b in zip(runs[0], runs[1]))
        print(f"repeatability    worst deviation between runs {worst * 100:.2f} %")
    else:
        worst = 0.0

    bad_readback = sum(1 for v, rb, _ in runs[0] if v != rb)
    print(f"readback         {n - bad_readback}/{n} commands accepted verbatim")

    print("=" * 62)
    ok = (0.85 <= slope <= 1.15 and r2 > 0.98 and flat == 0 and worst < 0.03)
    if ok:
        print("PASS — exposure is linear, monotonic and repeatable. Ramp is viable.")
    else:
        print("FAIL or MARGINAL. Curvature alone is survivable with a calibration")
        print("table; plateaus, poor repeatability or ignored commands are not.")
        print("Inspect phase0-results/ and the CSV before concluding.")
    return ok


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else find_camera()
    OUT.mkdir(exist_ok=True)
    print(f"camera: {dev}\n")

    # Capture the device's own description of itself — this answers several
    # open questions at once and is worth keeping regardless of the result.
    (OUT / "formats.txt").write_text(v4l2(dev, "--list-formats-ext"))
    (OUT / "controls.txt").write_text(v4l2(dev, "--list-ctrls-menus"))
    print(f"wrote {OUT}/formats.txt and {OUT}/controls.txt")

    ctrls = controls(dev)
    ae = pick(ctrls, AUTO_EXPOSURE, "auto-exposure")
    exp = pick(ctrls, EXPOSURE, "manual exposure")
    lo = ctrls[exp].get("min", 1)
    hi = ctrls[exp].get("max", 10000)
    print(f"controls: {ae}, {exp} (min={lo} max={hi})")

    v4l2(dev, "-c", f"{ae}=1")               # 1 = manual across both namings
    for name in AUTO_WB:
        if name in ctrls:
            v4l2(dev, "-c", f"{name}=0", check=False)

    values = ladder(lo, hi)
    print(f"ladder: {len(values)} half-stop steps, {values[0]}–{values[-1]}\n")

    runs = []
    for r in range(1, RUNS + 1):
        print(f"run {r}/{RUNS}")
        runs.append(sweep(dev, exp, values, r))

    with (OUT / "sweep.csv").open("w") as fh:
        fh.write("run,commanded,readback,luma\n")
        for i, run in enumerate(runs, 1):
            for v, rb, y in run:
                fh.write(f"{i},{v},{rb},{y:.4f}\n")
    print(f"\nwrote {OUT}/sweep.csv")

    sys.exit(0 if analyse(runs, values) else 1)


if __name__ == "__main__":
    main()
