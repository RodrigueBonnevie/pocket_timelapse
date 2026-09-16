# Phase 0 — the tests that decide the UVC build

See [../UVC-BUILD.md](../UVC-BUILD.md) §8 for what each test determines.
**Only test 1 is binary**: if exposure cannot be commanded finely and
repeatably, the sunset ramp is impossible and no other result matters.

## Requirements: none

`v4l2.py` talks to the kernel through `ioctl` directly, so Phase 0 needs
nothing installed beyond python3 and Pillow. The camera itself is handled by
the kernel's built-in `uvcvideo` driver — plug it in and it appears.

This is also why the bindings are written rather than shelling out to
`v4l2-ctl`: the eventual `camera.py` runs on a minimal embedded host where
adding packages is inconvenient.

```bash
./probe.py              # what the camera says it can do — read-only
./focus_assist.py       # turn the lens barrel until the number peaks
./exposure_sweep.py     # test 1
./snap.py               # a few 4K frames to look at, into ~/Pictures/arducam
```

**Focus first.** The lens ships out of focus and there is no software control
for it, so every other measurement is taken through a blurred image until the
barrel has been set.

## Setting up the shot

**This matters more than anything else in the procedure.** Aim at a surface
that is:

- **static** — nothing moving, no screens in frame
- **evenly lit by steady artificial light** — daylight drifts during the run and
  the drift reads as a camera fault
- **filling the frame**, mid-tone, not clipping

A blank wall under a lamp is ideal. The script selects the responsive part of
the exposure range automatically and will tell you if too little of it responds,
which almost always means the scene is clipping.

## Reading the result

| Check | Why it is the criterion |
|---|---|
| **monotonic** | every command must move the image the right way |
| **repeatable** | the same command twice must give the same exposure — hysteresis is what makes a ramp flicker |
| **commands honoured** | readback must match; a clamped or ignored value is a silent failure |

The reported power-law exponent is **informational only**. The ISP applies a
tone curve, and `ramp.py` is a closed loop that measures luma and corrects, so
the response does not need to be linear — only well-behaved.

## Results on the Arducam B0587 — 2026-09-16

**Test 1: PASS.**

| | |
|---|---|
| Monotonic | 8/8 steps |
| Repeatability | **0.80 %** worst gap between runs (threshold 3 %) |
| Commands honoured | 9/9 accepted verbatim |
| Response shape | luma ~ exposure^1.02 — near linear |
| Settling | **6 frames / ~225 ms** after a change |

### A trap worth knowing about

**Disabling auto white balance without also setting a temperature breaks the
image.** On this module the green channel collapses to zero and everything
comes out magenta:

| | R | G | B |
|---|---|---|---|
| AWB off, no temperature set | 131.5 | **0.0** | 102.0 |
| AWB on | 85.6 | 90.9 | 86.7 |
| AWB off, 2800 K set | 86.8 | 93.0 | 81.0 |

It looks exactly like a missing IR-cut filter, which would have been a much
worse problem and would have decided which lens variant to buy. It isn't.
**`camera.py` must set `white_balance_temperature` whenever it disables
`white_balance_automatic`** — locking white balance means setting it, not just
switching the automatic off.

Also established:

- **MJPEG at 3840×2160 @ 25 fps** is offered, and frames are valid standalone
  JPEGs (`ffd8ff` SOI, open directly in PIL). The Huffman-table concern does not
  apply to this module.
- **`Exposure Time, Absolute` is 1..5000 in 0.1 ms units** — the range from
  Arducam's general wiki does apply to this part.
- **No JPEG compression-quality control exists.** `storage.py` cannot adjust
  quality to fit a session budget and must budget by interval instead.
- **`Focus, Absolute` (1..831) does nothing.** It is advertised by the UVC
  descriptor and accepts values, but stepping it from 1 to 831 changes the
  image by 1.10x the frame-to-frame noise floor, and whole-frame edge energy is
  identical to two decimal places across the range. This is a **fixed M12
  lens** — focus it by turning the barrel, with `focus_assist.py`.

  Worth noting as a caution: comparing frame *hashes* suggested the control
  worked, because two captures of a static scene differ at the pixel level
  anyway. Any test for "did this control do something" has to measure the
  change against the noise floor, not against zero.
- **4K frames were ~500 kB** on an indoor scene, against the 2.2 MB the storage
  model assumes. A detailed daylight scene will be larger, but the budget looks
  conservative. (Measurements taken before the white-balance fix read ~320 kB —
  a zeroed channel compresses better, so discard those.)
- **Pipeline lag is 6 frames.** Queued buffers carry the previous exposure, so a
  fixed settle count is not enough — `measure_lag()` determines it at runtime.
  This is also the settling component of `t_on`.

## Tests 2–4

Need a USB power meter (`P_cam`, `t_on`, suspend current) and a
`uhubctl`-compatible hub (scripted power cycling). They decide how *good* the
build is, not whether it works, so they wait until the power design starts.
