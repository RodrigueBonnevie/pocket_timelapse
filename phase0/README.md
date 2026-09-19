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
./focus_preview.py      # live view in a browser while you turn the barrel
./focus_assist.py       # the same metric as a terminal bar, no video
./exposure_sweep.py     # test 1
./snap.py               # a few 4K frames to look at, into ~/Pictures/arducam
./timelapse.py          # shoot a real sunset — see below
```

**Focus first.** The lens ships out of focus and there is no software control
for it, so every other measurement is taken through a blurred image until the
barrel has been set.

### Focusing the M12 lens

There is no focus ring and no control to find — on an M12 (S-mount) lens the
whole barrel screws in and out of the holder on a 0.5 mm-pitch thread, and that
movement *is* the focus. `Focus, Absolute` in the UVC descriptor drives nothing.

**It will feel seized, and on this unit it was: Arducam put glue on the thread**
so focus survives shipping. Before applying more force, check for a set screw in
the side of the lens holder (usually 1.5 mm hex) and for a lock ring under the
lens — either will hold it solid. Then break the glue with steady torque on the
knurled base, gripping the holder rather than the PCB so the load does not go
through the sensor's solder joints.

Turn it **very little**. A quarter turn is 0.125 mm of back focus, which at 100°
is most of the range from close-up to infinity. Aim at something 100 m away with
hard edges, keep that detail near the centre of frame (the metric only looks at
the middle half), and re-lock the thread afterwards — a box that travels in a
pocket will drift.

`focus_preview.py` serves the camera's own MJPEG frames to a browser at
`http://localhost:8080` with the sharpness number beside them, so you can see
*what* is sharp rather than only *how* sharp. Exposure and white balance are
left automatic there so it stays usable at dusk; that is the opposite of every
other script here, and deliberate. It holds the camera open, so stop it before
running a capture.

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

### A trap worth knowing about — and a correction

**Switching auto white balance off can leave the green channel at zero**, so
every frame comes out magenta:

| | R | G | B |
|---|---|---|---|
| AWB off from a cold plug-in | 131.5 | **0.0** | 102.0 |
| AWB on | 85.6 | 90.9 | 86.7 |
| AWB off after AWB has run | 86.8 | 93.0 | 81.0 |

It looks exactly like a missing IR-cut filter, which would have been a much
worse problem and would have decided which lens variant to buy. It isn't.

**The original entry here concluded that setting `white_balance_temperature`
was the fix. That was too confident.** Setting a temperature did make the fault
go away, but so did simply having run AWB at some point earlier in the session:
once the ISP has computed white-balance gains it keeps them until the camera
loses power. The fault therefore only appears on the **first session after
plugging in** — which is exactly when an unattended capture starts, and exactly
why it is easy to convince yourself it has gone away. It could not be
reproduced again on 2026-09-17 without a replug, so the precise mechanism
remains unconfirmed.

**What `timelapse.py` does instead**, which is robust under either explanation:
let the ISP's own AWB converge for ~40 frames, freeze it by switching AWB off,
then **verify the green channel is alive** and abort with a clear message if it
is not. Locking after convergence is also the right thing for a sunset — a live
AWB would spend the whole session neutralising the colour shift being filmed.

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

## The shutter ceiling — the important negative result (2026-09-17)

**`exposure_time_absolute` advertises 1..5000 (0.1–500 ms). Only about 1..144
(0.1–14.4 ms) does anything.** Above that the module accepts the value, reports
it back verbatim, and ignores it; ten times the exposure yields an identical
frame.

| | |
|---|---|
| Shutter, 0.9 – 14.4 ms | **3.80 stops** |
| Gain, 0 – 100 | **1.10 stops** |
| **Total** | **4.91 stops** |
| A sunset spans | **~10 stops** |

Eliminated as explanations: the frame period (a 200 ms frame at 5 fps still
caps at 14.4 ms), `Backlight Compensation` a.k.a. "Ultra Low Light Mode"
(0..2 here, all three plateau), and `Exposure, Dynamic Framerate` (brightens
~2.7×, extends nothing). 14.4 ms ÷ 2160 lines ≈ 6.7 µs/line — one sensor
readout. The cap is the sensor's internal frame length, which never changes
because **USB 2.0 bandwidth**, not the sensor, is what holds this camera at
25 fps.

See [../UVC-BUILD.md](../UVC-BUILD.md) for the full write-up including the
Sonix extension unit and why unlocking it is not worth attempting. **Parked,
not resolved** — `timelapse.py` is here to find out whether ~4.9 stops ruins a
sunset or merely shortens it.

## The exposure floor — the other end, and it also bites (2026-09-18)

Pointed at an ordinary daylit scene at the **minimum** the camera offers —
`exposure_time_absolute` = 1 (0.1 ms), gain 0 — the frame was still **2.3 stops
overexposed, 48 % of it blown**. The lens is fixed-aperture, so exposure time is
the only lever and it is already at the stop.

```
acquired rung 0/105: exposure 1 gain 0
  0  exp 1 gain 0  luma 179.64  blown 48.40%  err -2.30 st  PINNED
PINNED for 8/8 frames (100 % of the session)
worst shortfall 2.32 stops beyond the camera's range
```

**Fit an ND filter for anything brighter than dusk.** ND4–ND8 to be merely
correct; ND32–ND64 to also land above 0.9 ms, where the ramp is smooth rather
than steppy. It screws onto the same 37 mm window the enclosure already uses.

The window between the two limits is narrow: too sensitive for daylight, capped
at 14.4 ms at the dark end. Dusk is what is left, which is the subject — but ND
is a per-shoot decision, and a fixed ND cannot come off mid-session, so
sunset-to-night either starts clipped or ends pinned.

### Two things this changed in timelapse.py

**The ladder used to start at exposure 9, not 1**, on the reasoning that below
~0.9 ms one integer count is a bigger change than the ramp's whole per-frame
budget. True, but it silently discarded **3.17 stops at exactly the end daylight
needs**. The floor is now 1; frames below 9 are flagged `coarse` in the log and
counted in the summary, because the steps there really are visible. Lumpy beats
having no range.

**Metering the mean is wrong for this subject.** A bright sky over darker ground
pulls the mean down, the ramp exposes for the ground, and the sky burns off the
top of the histogram — which is what "the whole sky is overexposed" turned out
to be, on top of the floor. It now measures the fraction of the frame above 250
and lets highlights override the mean when that exceeds `--max-blown`
(default 2 %, `100` disables). Default 2 % is strict when half the frame is
legitimately near-white; for a sunset try 5, and tune from the `blown_pct`
column in `frames.csv`.

## Shooting a sunset

```bash
./timelapse.py --interval 5 --until 21:30
./timelapse.py --interval 2 --duration 45m --target 110
./timelapse.py --max-blown 5              # looser highlight guard, for bright skies
./timelapse.py --shutter-ceiling 5000     # pretend the cap is not there
```

Frames land in `~/Pictures/timelapse/<date>_<time>/` as `NNNNNN.jpg`, written
atomically, alongside a `frames.csv` logging exposure, gain, ladder rung,
luma, blown percentage, error in stops, and per-channel means for every
frame.

**The number to read afterwards is `PINNED`.** It marks frames where the ramp
was already at one end of its range and the scene kept going that way — too
dark at the top, too bright at the bottom — and the summary reports the worst
shortfall in stops. That is the measurement that decides whether the camera's
range is enough:

- never pinned → the range was enough for this sunset
- pinned at the *start* → too bright; fit an ND filter
- pinned for the last few minutes → shorten the session, or start later
- pinned for half the run → the cap is fatal for this use and the fallbacks in
  UVC-BUILD.md apply

Exposure is placed by bisection before the first frame is written — about
seven probes, none of them recorded — so frame 0 is already correct and there
is no run-in to discard.

## Tests 2–4

Need a USB power meter (`P_cam`, `t_on`, suspend current) and a
`uhubctl`-compatible hub (scripted power cycling). They decide how *good* the
build is, not whether it works, so they wait until the power design starts.
