# Phase 0 — the tests that decide the UVC build

Run these before buying anything beyond the camera. See
[../UVC-BUILD.md](../UVC-BUILD.md) §8 for what each one determines.

**Only test 1 is binary.** If exposure control cannot be driven finely and
repeatably, the sunset ramp is impossible and no other result matters.

## Requirements

```bash
sudo apt install v4l-utils python3-pil     # Debian/Ubuntu
```

Nothing else — no SBC, no battery, no load switch. A laptop and the camera.

## Test 1 — exposure linearity

```bash
./exposure_sweep.py                 # auto-detects via /dev/v4l/by-id
./exposure_sweep.py /dev/video0     # or name the device
```

Point the camera at a **static, evenly lit surface** that will not change for
the duration — a blank wall under steady artificial light. Daylight drifts, and
the drift reads as non-linearity.

The script sweeps `exposure_time_absolute` up a half-stop ladder, captures a
frame at each step, and repeats the whole sweep to test repeatability.

### What it produces

| File | Contents |
|---|---|
| `phase0-results/formats.txt` | supported formats and frame rates — **confirm MJPEG is present** |
| `phase0-results/controls.txt` | every UVC control with real ranges — check for a compression-quality control |
| `phase0-results/sweep.csv` | commanded value, readback, measured luma, per run |
| `phase0-results/run*_exp*.jpg` | the frames themselves — **look at them** |

### Reading the result

| Signal | Meaning |
|---|---|
| **slope ≈ 1.0, R² > 0.98** | exposure is linear in log-log, as it should be |
| **monotonic** | every step raised luma; a plateau means quantisation or an ignored command |
| **repeatability < 3 %** | the same command gives the same exposure on a second pass |
| **readback matches** | the camera accepted the value rather than clamping it |

Curvature alone is survivable — a calibration table fixes it. **Plateaus, poor
repeatability, or commands that report as set but do not change the image are
fatal**, and the last of those is documented as occurring on Arducam UVC
hardware.

## Also worth doing by hand

- **Open a captured frame as `.jpg`.** Some MJPEG variants omit the Huffman
  table and will not open standalone.
- **Shoot a real sunset** out of a window at a fixed exposure and look at the
  files. This is the image-quality judgement, and it needs no hardware.
- **Check the corners** for vignetting — Arducam's ISP has no lens shading
  correction, so what you see is what you get until you correct it in post.
- **Twenty manual replugs**, checking whether enumeration stays reliable and the
  `by-id` path stays stable. A crude stand-in for test 4.

## Tests 2–4

These need a USB power meter (`P_cam`, `t_on`, suspend current) and a
`uhubctl`-compatible hub (scripted power cycling). They decide how *good* the
build is, not whether it works, so they can wait until the power design starts.
