# Pocket Timelapse Camera — the astro build

**Status: exploration, not a recommendation.** Nothing here has been measured on hardware. Power
figures are vendor maxima, timings are estimates, and the enclosure has not been drawn. This
document exists so the path can be judged before anything is bought — the previous architecture was
chosen on published specifications and [that went badly](UVC-BUILD.md).

---

## Context

[PI-BUILD.md](PI-BUILD.md) solves this with a Raspberry Pi and its tuned ISP; it is blocked on a
board that has been unobtainable through 2026. [UVC-BUILD.md](UVC-BUILD.md) buys the tuning inside
a USB camera so the host needs no ISP; Phase 0 then measured its total usable exposure range at
**4.91 stops against a sunset's ~10**, capped at both ends, and established that this is structural
rather than a defect of the particular module: a camera whose ISP somebody else tuned is a camera
whose sensor registers somebody else owns.

This document takes the other exit. **It gives the ISP up deliberately** and buys a camera whose
entire purpose is manual control of long exposures.

The consequence that makes it worth writing down: **the only reason this project ever needed a
Raspberry Pi specifically was the Pi's tuned ISP.** An astronomy camera needs no tuning, so this
path dissolves the dependency that created the whole problem. Any capable Linux SBC will do, and
unlike the Zero 2 W those are in stock.

---

## What this costs against the original brief

The brief is not set in stone, but it should be clear which parts this path pushes on.

| Requirement | Status under this build |
|---|---|
| ≥4K stills with crop room | **Met** — 3840×2160, and 12-bit rather than 8-bit JPEG |
| Decent image quality | **Met, but earned in post** rather than out of the camera |
| Weeks of idle standby | **Met** — same switched-rail approach as the other builds |
| 6–12 h shooting | **Pressured** — roughly double the power, so 6 h is comfortable and 12 h is heavy |
| Field-configurable, no laptop | **Met** — WiFi AP, unchanged |
| Scheduled / timer starts | **Met** — unchanged |
| MCU-based control | **Lost.** Not negotiable — see Decision 3 |
| Swappable camera module | **Met differently** — M42/C-mount, a much wider lens and body ecosystem |
| SD card of stills, no video encode | **Met** — and arguably better, since raw frames keep grading latitude |
| **Pocketable** | **This is the one that breaks.** See the enclosure section |

---

## Decision 1 — give the tuned ISP up, on purpose

The UVC build's first decision was to buy the tuning, because doing it yourself is a lab job. That
was correct, and the bill arrived as the product category: tuned ISPs are sold inside webcams and
surveillance cameras, and those stream.

Astronomy cameras invert every term. There is no ISP at all — deliberately, because the market wants
linear uncalibrated data and an ISP would destroy the photometry. What crosses the cable is Bayer.

**What is lost:** lens shading correction, a colour matrix, a noise model. Frames are flatter and
less accurate in colour than the Arducam's, and a wide lens will visibly vignette.

**Why the loss is smaller than it looks:** all three are corrected **once, not per frame**. A flat
frame fixes the vignetting, a colour profile fixes the matrix, and a timelapse applies the identical
correction to every frame of the sequence. That is routine practice in both astronomy and
photography, it happens in post on a laptop, and it is a vastly smaller job than tuning an ISP in
firmware.

**What is gained** is the thing the UVC build could not have at any price:

| | UVC build (measured) | This build (published) |
|---|---|---|
| Usable exposure range | **4.91 stops** | **~26 stops** (32 µs – 2000 s) |
| Bit depth | 8-bit, post-ISP | **12-bit** |
| Who owns exposure | the vendor's firmware | **you** |

The SDK is also less bare than "raw Bayer" suggests. From `ASICamera2.h`, image types are
`ASI_IMG_RAW8`, `ASI_IMG_RGB24`, `ASI_IMG_RAW16` and `ASI_IMG_Y8` — **RGB24 exists**, debayered by
the library on the host — and the controls include `ASI_GAIN`, `ASI_EXPOSURE`, `ASI_GAMMA`,
`ASI_WB_R`, `ASI_WB_B`, `ASI_OFFSET`, `ASI_HARDWARE_BIN` and `ASI_HIGH_SPEED_MODE`. So there is a
rudimentary colour pipeline: white balance gains and a gamma curve, simply not a tuned one.

---

## Decision 2 — the camera

**Chosen for costing: ZWO ASI585MC (uncooled).** Player One's Uranus-C uses the same sensor and QHY
are a third source; all three have free Linux SDKs with aarch64 builds and INDI support.

| | ZWO ASI585MC | Arducam B0587 (owned) |
|---|---|---|
| Sensor | Sony IMX585, 1/1.2″ BSI | IMX678, 1/1.8″ |
| Resolution | 3840×2160, 8.29 MP | 3840×2160, 8.3 MP |
| Pixel | **2.9 µm** | 2.0 µm — **+1.07 stops per pixel** for the IMX585 |
| ADC | 12-bit | 8-bit out of the ISP |
| Read noise | 0.8 e⁻ | unpublished |
| Full well | 40 ke⁻ | unpublished |
| Peak QE | 91 % | unpublished |
| Exposure | **32 µs – 2000 s** | 0.1–14.4 ms usable |
| Buffer | 256 MB DDR3 | none |
| Power | 2.5 W max, uncooled | unmeasured |
| Mount | M42 + 1.25″ nosepiece | M12 |
| Back focus | 6.5 mm | — |
| Weight | ~136 g | a few grams |
| Price | ~€440 | ~€90 |

**Take the uncooled version.** The cooled "Pro" draws up to 22.6 W with the TEC running, which is
absurd on a battery, and thermal noise is irrelevant at the sub-second exposures a sunset needs.

### The trap: there is no IR-cut filter

The ASI585MC ships with an **AR (anti-reflection) window**, not an IR-cut. Astronomers want infrared;
landscape photography emphatically does not. Without a UV/IR-cut filter, daylight foliage goes
milky-pink and the colour matrix cannot rescue it.

**A UV/IR-cut filter is a mandatory BOM item, not an accessory.** A 1.25″ screw-in filter fits the
supplied nosepiece, or an M42 filter sits in front of the sensor window.

This is the direct equivalent of the `A650` vs `ANIR` question in the UVC build, and it is easy to
miss precisely because the astronomy market considers the AR window the desirable option.

---

## Decision 3 — the host must run Linux, and this is not negotiable

**An ESP32 cannot do this, and the blocker is not compute.**

A small preview is genuinely cheap. A half-scale debayer collapses each Bayer 2×2 quad into one RGB
pixel — four reads, no interpolation — so 1920×1080 of sensor becomes 960×540 of RGB with no
filtering. An ESP32-P4 has a hardware JPEG encoder and enough PSRAM for the buffers. On compute
grounds a composition-and-focus preview would be comfortable.

The blocker is the **driver**. `libASICamera2` is a **closed-source binary**, shipped for Linux
x86_64 and aarch64, macOS and Windows. There is no MCU build, no source, and no published USB
protocol. An ESP32 cannot talk to the camera *at all* — not at reduced resolution, not for a
preview, not for anything. The same is true of QHY and Player One; machine-vision cameras are better
off only in that USB3 Vision is an open standard with an open implementation in `aravis`, which
still needs a Linux userspace.

**So tier C dies here, and with it the microamp idle floor that was this project's most attractive
property.** That is the single biggest loss on this path, and it should be weighed against the 21
stops of exposure range it buys.

### Bandwidth is not a constraint, which widens the host choice

A 16-bit 8.3 MP frame is 16.6 MB. At a 5 s interval that is **3.3 MB/s**, against roughly 35 MB/s
of real-world USB 2.0 High Speed. **USB 3.0 is not required for timelapse**, and the camera's
256 MB DDR3 buffer absorbs readout while the host is busy writing. USB 3.0 only matters for the
46.9 fps video the camera is otherwise sold for.

### Candidate host

**Radxa Zero 3W** — RK3566, quad Cortex-A55 at 1.6 GHz, **65×30 mm (the Pi Zero footprint)**,
1–8 GB RAM, optional eMMC, and both USB 2.0 OTG and a USB 3.0 host port. Crucially it is
**aarch64**, which is what the ZWO binary needs, and it is purchasable. Idle is ~1.8–2.3 W headless
with WiFi up — no better than a Pi, so standby still means cutting the rail entirely, exactly as in
the other two builds.

Orange Pi Zero 3W is the alternative; note its idle is reported higher, 2–3.1 W.

**Verify the SDK runs on the chosen board before buying the camera.** A closed binary against an
unfamiliar libc is a real risk, and it is free to test with any ZWO camera, borrowed or otherwise.

---

## Decision 4 — develop on the box, or store raw

| | **Store raw** | **Develop on the box** |
|---|---|---|
| Per frame | 16.6 MB (RAW16) | ~1–2 MB JPEG |
| 12 h at 5 s | ~143 GB | ~9–17 GB |
| Host work per frame | write only | demosaic + colour + encode, ~0.3–0.6 s on A55 |
| Energy | lower | higher — CPU awake and working |
| Grading latitude | **full, 12-bit linear** | 8-bit, baked |
| Card | 256 GB per session | 64 GB is plenty |

**Store raw.** It is the better photographic answer for sunsets, it keeps the host doing nothing but
I/O, and it moves all the colour work to a laptop that has power and a screen. A 256 GB card holds a
session; the card is sized to one charge, exactly as in the Pi build.

Develop-on-box only becomes attractive if card cost or offload time becomes the annoyance, and it
can be added later without changing anything else.

---

## Bill of materials

| # | Part | Role | ≈ EUR |
|---|---|---|---|
| 1 | ZWO ASI585MC, uncooled | camera | 440 |
| 2 | **UV/IR-cut filter, 1.25″** | **mandatory — the camera has an AR window** | 35 |
| 3 | C-mount lens, ~6 mm, covering 1/1.2″ | ~90° diagonal; see below | 80–200 |
| 4 | M42 → C-mount adapter | 6.5 mm back focus makes both reachable | 20 |
| 5 | Radxa Zero 3W, 2 GB | host | 30 |
| 6 | 256 GB A2 microSD | one session of raw | 25 |
| 7 | Pololu U3V50F5 5 V step-up | 3.7 V pack → 5 V | 18 |
| 8 | Witty Pi 4 Mini *or* DS3231 + P-FET latch | scheduled wake, switched rail | 15–22 |
| 9 | 4 × 18650 (Samsung 35E) + holder | 14 Ah / 51 Wh | 40 |
| 10 | Bay charger | charge outside the box | 25 |
| 11 | IP65 enclosure, ~160×120×90 mm | bigger than the other builds | 25 |
| 12 | Optical window, O-ring, vent plug, desiccant | weatherproofing | 25 |
| 13 | 1/4″-20 inserts | mount | 5 |
| | | **total** | **≈ 780–900** |

Against ~€350 for the UVC build and ~€175 for the Pi build. **This is a materially more expensive
machine**, and most of it is the camera and its optics.

### The lens is a real problem, not a line item

A 1/1.2″ sensor has a **12.8 mm diagonal**. Most cheap CCTV and machine-vision lenses cover 1/2.8″
to 1/1.8″ and will vignette hard on this format. You need a lens explicitly rated for 1/1.2″ or
larger, and at ~6 mm focal length for a ~90° diagonal view those are Computar/Fujinon-class parts,
not €20 M12 units.

This is the hidden cost of the larger sensor, and it partly offsets the +1.07 stops it buys.

---

## Power budget

**All figures are vendor maxima or estimates. This section is the one most likely to be wrong.**

| | |
|---|---|
| Camera, streaming, uncooled | ≤2.5 W (vendor max; likely less at long intervals) |
| Radxa Zero 3W, idle headless | ~2.0 W |
| **Design point while shooting** | **~4.5 W at the 5 V rail** |

The host cannot sleep between frames: SDK init and USB enumeration cost seconds, and boot costs
~20 s, so at any sensible interval it stays awake. This is the UVC build's `always_on` case with no
alternative.

| Session | Energy at the rail | From the cells (÷0.88) | Ah at 3.7 V | +25 % derate |
|---|---|---|---|---|
| 6 h | 27 Wh | 30.7 Wh | 8.3 Ah | **10.4 Ah** |
| 12 h | 54 Wh | 61.4 Wh | 16.6 Ah | **20.7 Ah** |

So **6 h needs three 18650s and 12 h needs six** — against the Pi build's two for 12 h. Four cells
(14 Ah) gives a comfortable 8 h, which is the figure the BOM above is built around and probably the
honest answer for a sunset box.

Standby is unchanged from the other builds: the rail is cut, and the DS3231 latch or Witty Pi holds
the clock at microamps to single milliamps.

**Roughly double the shooting power of the UVC build.** That is the price of an awake Linux host
plus a camera built for 47 fps rather than for sleeping.

---

## Storage

RAW16 at 3840×2160 is **16.6 MB per frame**.

| Interval | Frames in 8 h | Storage | Video at 24 fps |
|---|---|---|---|
| 2 s | 14,400 | 239 GB | 10:00 |
| 5 s | 5,760 | 96 GB | 4:00 |
| 10 s | 2,880 | 48 GB | 2:00 |
| 30 s | 960 | 16 GB | 0:40 |

A 256 GB card covers everything except 8 h at 2 s. The same sizing principle as the Pi build holds:
**the card holds one charge's worth of frames.**

RAW8 halves this and is worth considering for bright sequences, but it throws away most of the
reason for choosing a 12-bit camera.

---

## Enclosure — the requirement this breaks

The optical assembly is a **62 mm diameter barrel** plus a C-mount lens, so call it 100 mm long and
62 mm across before the enclosure. Add a 65×30 mm board, four 18650s and a boost converter and the
box lands near **160×120×90 mm**.

That is a small camera bag, not a jacket pocket. **If "pocketable" is a hard requirement, this path
fails it** and the decision is whether the exposure range is worth more than the size. That is a
judgement, not a calculation, and it is the main thing to decide before spending anything.

Mechanically it is otherwise easier than the other builds: M42 and C-mount are rigid, standard, and
designed to be held by a barrel clamp rather than a PCB. The optical window can be a proper
screw-in filter as before — and here the **UV/IR-cut filter can double as the window**, which
removes a part rather than adding one.

---

## Software outline

Most of the existing work carries over; only the camera layer changes.

- **`camera.py`** — `libASICamera2.so` through **ctypes**, in the same spirit as
  [`phase0/v4l2.py`](phase0/v4l2.py): the header is small, the project already has the habit, and it
  avoids a dependency on an embedded host. `ASIGetNumOfConnectedCameras`, `ASIOpenCamera`,
  `ASIInitCamera`, `ASISetROIFormat`, `ASISetControlValue(ASI_EXPOSURE, µs)`, `ASIStartExposure`,
  `ASIGetDataAfterExp`.
- **`ramp.py` gets much simpler.** With 26 stops and exposure commanded directly in microseconds,
  the ladder gymnastics the UVC build needed — one ordered axis, the shutter-to-gain handover, a
  learned stops-per-rung — largely evaporate. Keep the capped per-frame step and the highlight
  guard; drop the rest. Gain stays at unity until the light genuinely runs out.
- **`preview.py`** — port [`phase0/focus_preview.py`](phase0/focus_preview.py) almost unchanged. Use
  `ASISetROIFormat` to run small and short, collapse Bayer quads to half-scale RGB, JPEG-encode, and
  serve over the same HTTP endpoint. Composition and focus only; no need for full resolution.
- **`storage.py`** — write raw frames plus a metadata sidecar. Same atomic write, fsync, rename
  discipline. FITS is the astronomy-native container and gets metadata for free; DNG is friendlier to
  photographic tools. Either beats a bare binary dump.
- **`calibrate.py`** (laptop side) — build the flat frame and the colour matrix once, apply to the
  whole sequence. This is where the ISP went.
- `scheduler.py`, `power.py`, `status.py`, `web.py` — unchanged from the UVC build.

---

## Phase 0 for this path

In order, and the first one is free.

1. **Does the SDK run on the intended host?** Put `libASICamera2.so` (aarch64) on a Radxa Zero 3W
   and open any ZWO camera. A closed binary against an unfamiliar libc is the single biggest
   technical risk and it can be retired before the expensive purchase.
2. **Verify the exposure range by measurement, not specification.** The lesson of the UVC build is
   that the advertised range and the effective range are different numbers. Run the equivalent of
   [`phase0/exposure_sweep.py`](phase0/exposure_sweep.py) and confirm the image actually responds
   across the claimed 32 µs – 2000 s.
3. **Measure power** at the 5 V rail: camera idle, camera exposing, host idle, host writing.
4. **Time the frame cycle** — expose, transfer, write 16.6 MB to SD. This sets the minimum interval.
5. **Judge untuned colour.** Shoot a daylight scene with and without the UV/IR-cut filter, build a
   flat frame, and see how close a single colour matrix gets. This decides whether "earned in post"
   is acceptable or merely theoretical.
6. **Fit the barrel to a box** on paper before buying the enclosure.

---

## Known risks

| Risk | Mitigation |
|---|---|
| **Closed binary driver** | Verify on the actual host first; INDI and `aravis` exist as escapes, both still Linux |
| **No IR-cut filter fitted** | Mandatory BOM item; easy to miss because astronomy prefers the AR window |
| **Pocketability lost** | Accept or reject before spending — the barrel sets the box size |
| Power roughly doubles | Four cells for 8 h; 12 h needs six and is probably not worth it |
| Lens for 1/1.2″ is expensive | Budget €80–200; cheap CCTV lenses will vignette on this format |
| Untuned colour disappoints | Phase 0 step 5, before committing |
| Tier C and its microamp idle are gone | Structural. This is the cost of the path |
| ZWO drop aarch64 support | Unlikely but unrecoverable; INDI community would likely carry it |
| Raw storage fills the card | 256 GB per session; card sized to one charge |
| Vendor lock-in on a hobby project | Player One and QHY use the same sensors with similar SDKs |

---

## Relationship to the other builds

| | [Pi build](PI-BUILD.md) | [UVC build](UVC-BUILD.md) | **Astro build** |
|---|---|---|---|
| Cost | ~€175 | ~€350 | **~€800** |
| Exposure range | full sensor control | **4.91 stops, measured** | ~26 stops, published |
| ISP | Pi's, tuned | camera's, tuned | **none — done in post** |
| Host | Pi Zero 2 W | SBC or MCU | **SBC only** |
| Idle floor | ~1.5 W | ~30 µA in tier C | ~2 W |
| Shooting power | ~1.1 W | ~2.5 W | **~4.5 W** |
| Pocketable | yes | yes | **no** |
| Sourceable today | **no** | yes | yes |

The honest summary: **the Pi build is the best design and cannot be bought; the UVC build can be
bought and cannot make the picture; this build can do both and is twice the size, twice the power
and four times the price.**

Nothing here should be bought until the two free questions from
[UVC-BUILD.md](UVC-BUILD.md) are answered — whether Arducam can lift the 14.4 ms cap in firmware,
and what e-con's 4K STARVIS parts actually do across their exposure range. Either answer would make
this document unnecessary, and both cost an email.
