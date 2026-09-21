# Camera qualification — the experiments, and how to repeat them

**Why this exists.** A camera was chosen on published specifications, bought, and found unable to
photograph the subject it was bought for. None of the specifications were wrong; the one that
mattered was simply never published. These are the measurements that would have caught it in an
evening, written so they can be run against any candidate camera.

Every number below was measured on the **Arducam B0587 (IMX678)** between 2026-09-16 and 2026-09-21.
It is the baseline: a new camera is judged against this column.

Tooling lives in [`phase0/`](phase0/) and needs nothing installed beyond python3 and Pillow — the
V4L2 bindings are pure `ctypes`. For a non-UVC camera only the capture layer changes; the analysis
is format-agnostic.

---

## Run them in this order

The order is by cost and decisiveness: each one can kill the camera before you spend time on the
next.

| # | Experiment | Cost | Kills the camera if |
|---|---|---|---|
| 1 | What it claims | minutes | no 4K, no MJPEG, no manual exposure |
| 2 | **Effective exposure range** | 20 min | **< ~10 stops of shutter** |
| 3 | The exposure floor | 10 min | cannot get dark enough for daylight |
| 4 | Exposure behaviour | 20 min | not monotonic, not repeatable |
| 5 | Delivered dynamic range | 15 min | *informative rather than fatal* |
| 6 | Container utilisation | 10 min | *informative rather than fatal* |
| 7 | Colour sanity | 5 min | colour breaks when automatics are locked |
| 8 | Pipeline latency | 5 min | settling is longer than the interval |
| 9 | **A real sunset** | one evening | the integration test |

---

## 1. What the device claims

**Question:** what modes, controls and ranges does it advertise — and what does the USB descriptor
say that the driver does not expose?

**Method:** [`phase0/probe.py`](phase0/probe.py) walks formats, frame sizes, frame intervals and
every control via `VIDIOC_QUERYCTRL` with `V4L2_CTRL_FLAG_NEXT_CTRL`. Then parse
`/sys/bus/usb/devices/*/descriptors` for the VideoStreaming input header (`bStillCaptureMethod`,
`bmaControls`), the camera terminal's `bmControls`, and any extension units.

**B0587:** MJPG and YUYV, 15 modes, 4K at 25 fps. Sixteen controls. `bStillCaptureMethod = 0`, no
still-image path. One Sonix extension unit, `{28f03370-…}`, unit 3. A second video node exists and
is **metadata only**.

> **Record the advertised exposure range, then distrust it.** The B0587 advertises
> `exposure_time_absolute` 1–5000 and honours 1–144.

---

## 2. Effective exposure range — the decisive one

**Question:** across what range does commanding an exposure actually change the image?

**Method:** lit, static scene. Manual exposure, gain 0, white balance locked. Sweep the *whole*
advertised range geometrically and record mean luma at each step. The effective ceiling is where
luma stops rising. **Repeat for every advertised mode** — the ceiling can differ by mode.

**Criterion:** a sunset spans **10–13 stops** (measured: 13.01). Shutter alone should cover most of
that. Below ~10 stops of shutter, plan on being pinned.

**B0587:** advertised 0.1–500 ms = 12.3 stops. **Effective 0.1–14.4 ms = 7.17 stops.** Across all 15
modes the ceiling takes only two values — 14.4 ms (4K@25, YUYV 320×320@5) or 7.2 ms (the other
thirteen). **Fails.**

> **The scene must be lit.** Pointed at an unlit room the camera read luma 4.3 at maximum settings
> and the sweep returned pure noise, which briefly looked like a result.

---

## 3. The exposure floor

**Question:** at minimum exposure and gain, is the camera dark enough for daylight?

**Method:** same rig, set the minimum the control offers, point at a daylit scene, measure mean luma
and the percentage of pixels above 250.

**Criterion:** mean luma below target with < 1 % blown. A fixed-aperture lens has no other lever.

**B0587:** **2.3 stops too bright at minimum, 48 % of the frame blown.** ND4–ND8 brings daylight into
range, ND32–ND64 also clears the coarse bottom of the ladder.

> **But ND buys nothing overall.** It shifts the window without widening it, so the total unreachable
> range is unchanged — it only chooses which end of the sunset you lose. Treat this experiment as
> measuring *where* the window sits, and experiment 2 as measuring how wide it is. Only the width
> matters for whether the camera can do the job.

---

## 4. Exposure behaviour

**Question:** is the control monotonic, repeatable, and honoured?

**Method:** [`phase0/exposure_sweep.py`](phase0/exposure_sweep.py). Two runs over the *effective*
range, checking that every step raises luma, that the two runs agree, and that readback matches.

**Criterion:** monotonic; repeatability < 3 %; every command accepted.

**B0587:** monotonic 8/8, repeatability **0.80 %**, 9/9 accepted. **Passes.**

> **This test passing means very little on its own.** It passed on a camera with 4.91 usable stops,
> because it only exercises the range experiment 2 establishes. Run 2 first.

---

## 5. Delivered dynamic range

**Question:** how many stops survive to the file, as opposed to being captured by the sensor?

**Method:** N frames of a static lit scene at a fixed exposure. Point-sample pixels at full
resolution (`Image.NEAREST`, never a draft decode — downscaling averages noise away). Compute
per-pixel *temporal* standard deviation, bin by signal level.
**DR = 20·log₁₀(255 / σ at the noise floor).**

**Criterion:** compare against the sensor's engineering DR (full well ÷ read noise) from the
datasheet. A large gap means the output format is throwing range away.

**B0587:** **8.9 stops delivered** (8.5 at gain 50) from a sensor with **13.4 stops** engineering DR.
Roughly 4.5 stops lost to the 8-bit JPEG.

> Two things flatter the result and should be said aloud: JPEG smooths noise in flat dark areas, and
> on this camera σ *fell* from 2.51 in the shadows to 0.93 in the midtones, which shot noise cannot
> do — the ISP denoises unevenly by level.

---

## 6. Container utilisation

**Question:** is the file's bit depth being used well, or are the tones piled into a few levels?

**Method:** on a correctly exposed frame, histogram the luma. Count distinct levels used, gaps
inside the occupied span (posterisation), the share at level 0 and 255, and the share in the bottom
four levels.

**Criterion:** tones spread across the container; no comb pattern; shadows not piled at the floor.

**B0587:** all 256 levels used and no gaps — the ISP is not wasting the container — **but 31 % of a
correctly exposed frame occupies levels 0–3, while levels 250–255 hold nothing.** In 12-bit those
four levels would be 64. When pinned, a comb appears at levels 0/3/5/8: posterisation from gain
amplifying a starved signal.

**Also test the tone curve before blaming it.** Sweep gamma and contrast at fixed exposure and check
whether clipped highlights come back. On the B0587 they do not: pixels clipped to 255 at default
contrast span **184–192 at contrast 0, 0.06 stops** — saturated, not compressed.

---

## 7. Colour sanity

**Question:** does colour survive locking the automatics?

**Method:** measure per-channel means with auto white balance on, then off, **from a cold plug-in**.

**Criterion:** no channel collapses.

**B0587:** switching AWB off from a cold plug-in can leave **the green channel at zero** — every
frame magenta. The gains survive until the camera loses power, so the fault only appears on the
first session after plugging in, which is exactly when an unattended capture starts. Mitigation:
let AWB converge, freeze it, then **verify the green channel before recording.**

---

## 8. Pipeline latency

**Question:** how many frames after a control change still carry the old setting?

**Method:** `measure_lag()` in [`phase0/exposure_sweep.py`](phase0/exposure_sweep.py) — step between
two exposures and count frames until the image moves.

**Criterion:** shorter than the capture interval.

**B0587:** **6 frames.** But the driver fills every buffer within ~160 ms of a change and then
stalls, so the drain must clear the queue *and* outlast the settling lag — 12 frames in practice.

---

## 9. A real sunset — the integration test

**Question:** how does it hold up against the actual subject?

**Method:** [`phase0/timelapse.py`](phase0/timelapse.py) through a full sunset. Then analyse
`frames.csv`:

- **Scene range:** reconstruct demand as `stops(exposure, gain) + err_stops` — *not* from the `rung`
  column — and take first-to-last. This is the number the camera must cover.
- **Scene rate:** median frame-to-frame change in that demand.
- **Coverage:** percentage of frames pinned at either end.
- **Smoothness:** frame-to-frame luma change in stops. Anything above ~0.1 is visible.

**B0587, 3073 frames over 102 minutes:**

| | |
|---|---|
| Scene range | **+13.01 stops** (7.7 stops/hour) |
| Scene rate | 0.0043 stops/frame at 2 s |
| Camera ladder | 8.27 stops |
| **Frames pinned** | **53 %** — 17 min at the floor, 36 min at the ceiling |

> **Replaying the CSV is a free regression test.** Reconstruct the scene's demand and run a modified
> controller against it offline. That is how the ramp fix was validated without waiting for another
> sunset: median tracking error 0.610 → 0.103 stops, median step 1.000 → 0.078.

---

## The baseline to beat

| Measurement | B0587 | What a camera for this needs |
|---|---|---|
| Effective shutter range | **7.17 stops** | ~10+ |
| With gain | 8.27 stops | ~13 |
| Floor vs daylight | 2.3 stops too bright | in range, or ND |
| Delivered DR | **8.9 stops** | 11+, which means more than 8-bit out |
| Sensor DR | 13.4 stops | — |
| Shadows | 31 % in 4 levels | spread across the container |
| Repeatability | 0.80 % | < 3 % |
| Settling | 6 frames | < interval |
| Frame size at 4K | 550–620 kB | budget storage from this |
| **Sunset coverage** | **47 %** | 100 % |

---

## How not to fool yourself

Every one of these cost real time on this project.

- **Light the scene.** Noise looks like signal. A ceiling "measured" in an unlit room was nonsense.
- **A specification is not a measurement.** The advertised exposure range was wrong by 5 stops, and
  a bus power ceiling was twice mistaken for a power draw.
- **Readback proves nothing.** This camera echoes values it ignores.
- **Filter noise properly before diffing.** 150 of 4,096 registers here jitter between consecutive
  reads; a two-sample filter manufactured a convincing pattern out of them.
- **Look at distributions, not counts.** "Six distinct levels recovered" sounded like detail until
  the 10th, 50th and 90th percentiles all turned out to be 188.
- **The scene moves.** Two readings three minutes apart at sunset differed by 1.4 stops and briefly
  looked like a bug.
- **Check the log agrees with itself.** `exposure` was recorded before the ramp moved and `rung`
  after, so rows contradicted each other and corrupted an analysis before it was noticed.
