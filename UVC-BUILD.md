# Pocket Timelapse Camera — the UVC build

*Status: design proposed, **three measurements outstanding** before the BOM can be trusted — see
§8. The sibling architecture is [PI-BUILD.md](PI-BUILD.md).*

## Context

A pocketable, battery-powered, weatherproof timelapse box you set down at dusk and collect a day or
two later. Weeks of standby, 6–12 h of shooting minimum, field-configurable without a laptop,
scheduled starts for sunsets, ≥4K stills. No on-device video encoding — it writes JPEGs to an SD
card and you assemble on a laptop.

Target form factor: a tight box with one waterproof button and one window for the lens, **no
external ports**, opened by hand for the SD card and to swap cells.

---

## Decision 1 — the tuned ISP lives in the camera

A raw sensor is useless on its own. Turning Bayer data into a photograph takes a hardware **ISP**,
and an ISP produces good images only with sensor-specific **tuning** — a measured calibration
dataset covering lens shading, colour matrices, noise profiles and white-balance response. Untuned,
the auto-exposure loop doesn't merely look wrong; it does not function at all. See
[SENSORS.md](SENSORS.md) §2 for what that involves and [IMAGE-PIPELINE.md](IMAGE-PIPELINE.md) for
what an ISP actually does.

That tuning is the scarce thing. Doing it yourself is a lab job with colour charts and calibrated
illuminants — months of specialist work, not a step in a hobby project.

**This architecture buys the tuning instead**, by choosing a camera that already contains a tuned
ISP and emits finished JPEGs.

The consequence is the whole design: **the host never touches an image.** No demosaic, no 3A, no
tuning files, no camera driver. It triggers a capture, receives compressed bytes, writes them to
SD, and sleeps. That is a job for almost anything — which is what makes the rest of this document
possible.

The product category is **UVC**: USB Video Class camera modules with an onboard ISP. e-con Systems
describe theirs as having *"a dedicated, in-built ISP… the ISP and sensor have been tuned for
achieving excellent image quality under various lighting conditions including near darkness."*
Standard interface, no vendor drivers.

---

## Decision 2 — the sensor

Most UVC modules are built for **surveillance**, which is a stroke of luck: those sensors are
designed for low light and wide dynamic range, exactly what a sunset needs. Sony's **STARVIS 2**
generation is the current best. Other industrial categories are surveyed further down — they have
genuinely different strengths, and one of them is worth watching.

| Sensor | Format | Resolution | Pixel area | Sensor area | vs IMX708 | Crop at 4K | Interface |
|---|---|---|---|---|---|---|---|
| IMX415 | 1/2.8" | 3864×2192 | 2.10 µm² | 17.8 mm² | −0.4 | 1.01× | USB 2.0 |
| AR1335 | 1/3.2" | 4208×3120 | 1.21 µm² | 15.9 mm² | −0.6 | 1.10× | USB 2.0/3.0 |
| **IMX678** | 1/1.8" | 3840×2160 | 4.00 µm² | 33.2 mm² | **+0.5** | 1.00× | **USB 2.0** or 3.0 |
| **IMX585** | **1/1.2"** | 3856×2180 | **8.41 µm²** | **70.7 mm²** | **+1.6** | 1.00× | USB 3.0 |
| **IMX283** | **1"** | 5472×3648 | 5.76 µm² | **115 mm²** | **+2.3** | **1.43×** | USB 3.0 |

**Chosen: IMX678 over USB 2.0**, in a board-level module with an M12 lens — the best sensor that
still permits the low-power host.

> **Worth chasing first:** if an **IMX283 module with MJPEG output** exists, it is arguably the
> better camera — +2.3 stops *and* 1.43× crop room, which is the combination nothing else offers.
> The known Arducam module is YUY2-only and USB 3.0, which rules out tier C, but the vendor
> landscape moves. Ask before settling for the IMX678.

**IMX415 is a trap.** It is the most common 4K UVC sensor and it is *worse than the IMX708 this
project started from* — high pixel density on a small optical format, weak in exactly the light
this device shoots in. Do not select by resolution.

**AR1335 is the same trap in a different costume** — 13 MP sounds generous until you notice it is
1/3.2" with 1.1 µm pixels, putting it *below* the IMX415. Resolution and light-gathering are
unrelated; see [SENSORS.md](SENSORS.md) §3.

**IMX585 is the low-light upgrade**: 8.4 µm² pixels, more than double the IMX678's sensor area.

**IMX283 is the crop-room upgrade**, and on paper the most interesting of all: **20 MP on a 1"
sensor, +2.3 stops, and 1.43× linear crop at 4K.** More total sensor area than the IMX585 *and*
real recomposing latitude. It has a catch — see the MJPEG requirement below.

### Crop room is a real axis, and only IMX283 offers it

The 8 MP STARVIS parts are 3840–3864 px wide, i.e. **4K exactly, with no margin** for cropping,
straightening or stabilising in post. That is a deliberate trade of crop latitude for low light.

The IMX283 breaks that trade — it gives both. If a still-higher-resolution module with a large
sensor appears, it inherits the same advantage: **crop room is the one spec that keeps paying off
as sensors improve**, because it lets you reframe a shot you can no longer revisit.

### Non-negotiable: the camera must output MJPEG

The whole architecture rests on the camera handing over *finished, compressed* frames. A module
that outputs only uncompressed YUY2 pushes the JPEG encode back onto the host — reintroducing
precisely the CPU cost this design exists to remove.

The numbers make it stark:

| Sensor | Uncompressed YUY2 frame |
|---|---|
| IMX585 | **17 MB** |
| IMX283 | **40 MB** |

A 40 MB frame does not fit an ESP32-P4's 32 MB of PSRAM, so a YUY2-only module **rules out tier C
outright** and makes tier B do the encoding. Arducam's IMX283 USB 3.0 module is documented as
YUY2-only, which is the catch mentioned above.

**Check the supported formats before ordering. MJPEG is a hard requirement, not a preference.**

### Beyond surveillance — the other industrial categories

Surveillance is not the only industrial camera market, and the others are built around genuinely
different priorities.

| Category | Best at | Why it doesn't win here |
|---|---|---|
| **Surveillance** (STARVIS) | low light, dynamic range, tuning aimed at *pleasing* images, cheap, 4K common | exposure control varies by vendor — the open question in §8 |
| **Machine vision** (Basler, FLIR, IDS) | **exposure control** — deterministic, repeatable, µs precision over GenICam | ISP tuned for *measurement*, not aesthetics; €300–800; USB 3.0; often mono |
| **Automotive** (OX03C10, OX08B40) | **140–150 dB HDR**, big pixels, LED flicker mitigation, −40 to +105 °C | the 4K parts are **GMSL2, not USB** — see below |
| **Scientific / astro** (ZWO, QHY) | very large sensors, cooling | raw only, no ISP, €600+, 2–5 W |
| **Broadcast / action** (Ambarella) | excellent ISP and encoding | closed SDKs, not sold as modules |

**The central tension: the two things this project needs most come from opposite ends of the
market.** Surveillance cameras give pleasing, tuned colour but inconsistent exposure control.
Machine vision cameras give immaculate exposure control but tune for measurement — Basler even
document turning colour processing *off* as the recommended setting. Neither category gives both.

That reframes the first test in §8: you are checking whether a *surveillance* camera happens to
have machine-vision-grade exposure control. If it doesn't, the fallback isn't giving up — it's
accepting a machine vision camera and doing your own colour transform in post, since the footage is
being post-processed anyway. Expensive, USB 3.0, and it forfeits the tuning advantage that motivated
this whole architecture, but it is a real backstop.

**The automotive category is the one to watch.** The OX03C10 has **140 dB of dynamic range** against
roughly 70–90 dB for a typical sensor, plus 3.0 µm pixels and an automotive temperature range that
suits a box left out through a Swedish winter. It is available as a UVC module today (Vadzo
Falcon-3C10CRS). A sunset is the highest-dynamic-range subject in photography, so this is close to
the ideal sensor for the job — except that at 2.5 MP it fails the resolution requirement outright.

#### The 4K automotive sensors exist — and you cannot use them

Chasing this down: **the sensors are real and they are close to ideal for this project.**

| Sensor | Res | Format | Sensor area | vs IMX708 | Dynamic range |
|---|---|---|---|---|---|
| **OX08B40** | 3840×2160 | 1/1.73" | 36.6 mm² | +0.6 | **140 dB** |
| **AR0823AT** | 4K | — | — | — | **150 dB** |
| *IMX678, for comparison* | 3840×2160 | 1/1.8" | 33.2 mm² | +0.5 | ~90 dB |

The OX08B40 has slightly more sensor area than the IMX678 **and roughly 50 dB more dynamic range**,
with an on-chip HALE engine holding both HDR and flicker mitigation across the full automotive
temperature range. For a sunset — the widest-dynamic-range subject in photography — that is close to
the perfect sensor.

**They are all GMSL2 or FPD-Link, not USB.** e-con's STURDeCAM88 (OX08B40) and NileCAM81 (AR0821)
are GMSL2 modules, built for automotive architecture where the camera streams over coax to a central
ECU that owns the ISP. Using one means a deserialiser board, a host with MIPI CSI-2 input, an ISP,
**and tuning for that sensor** — which lands you precisely back in the problem this architecture
exists to escape, with a Jetson-class power budget attached.

The 2.5 MP OX03C10 is available over UVC only because someone (Vadzo) deliberately integrated a
bridge and ISP onto it. Nobody has done that at 8 MP.

**Why the gap exists:** automotive sensors are sold to Tier 1 suppliers under NDA with automotive
qualification and volume commitments, into an architecture that assumes the ECU does the processing.
There is no commercial incentive to build a webcam out of one.

**So the automotive category has the best sensors for this job and the worst accessibility.** The
thing to watch for is a UVC module carrying an 8 MP automotive sensor — check Vadzo, e-con and
Leopard occasionally. If one appears it would likely be the best camera this project could use.

### Do not pay for a global shutter

Machine vision markets global shutter at a premium and it is worthless here. The camera is clamped
to a tripod photographing a static scene with long exposures; there is no motion to freeze. Global
shutter pixels carry more per-pixel circuitry, which costs fill factor and therefore **sensitivity —
the one thing this project actually needs.** Rolling shutter is the correct choice.

### The USB coupling — this decides more than it looks

**IMX585 modules are USB 3.0. IMX678 is available in USB 2.0.** That single fact couples the sensor
choice to the host choice:

| | USB 2.0 | USB 3.0 |
|---|---|---|
| Bus power ceiling | **500 mA = 2.5 W** | 900 mA = 4.5 W |
| Transfer, 2 MB frame | ~50 ms | ~5 ms |
| MCU host possible? | **yes** — ESP32-P4 has USB 2.0 HS host | **no** |

A timelapse needs *one frame at a time*, not video, so USB 3.0's bandwidth buys nothing here — the
transfer term is negligible either way. What it costs is real: **double the power ceiling, and it
rules out the low-power host entirely.**

So the trade is: **IMX585 (+1.6 stops) forces an SBC host and its ~1.5 W floor. IMX678 (+0.5 stops)
keeps the µA MCU host available.** Pick the sensor and the host together, not separately.

---

## Decision 3 — the host

Two viable hosts, and the choice is genuinely open.

| | **Tier B — SBC** | **Tier C — MCU** |
|---|---|---|
| Board | Radxa Zero 3W, Orange Pi Zero 2W | ESP32-P4 (+ ESP32-C6 for WiFi) |
| Idle floor | ~1.5 W | **~30 µA** |
| Camera options | IMX678 **or IMX585** | IMX678 only (USB 2.0) |
| Software | Linux, v4l2, Python | ESP-IDF, C |
| RTC + battery monitor | external (DS3231, MAX17048) | **onboard** — P4 has both |
| Effort | moderate — reuse most of the Pi build's Python | high — firmware from scratch |

**Tier B** is the pragmatic choice: Linux speaks UVC natively through v4l2, and `scheduler.py`,
`storage.py`, `ramp.py` and `web.py` carry over with only the capture module rewritten. It also
unlocks the IMX585.

**Tier C** is where the architecture's real advantage lives. With no operating system there is no
idle floor — the host sleeps at microamps between frames and the only energy spent is the camera's.
Past a ~10 s interval that is transformative. It also simplifies the BOM: the ESP32-P4 has its own
RTC, deep sleep and ADC, so the external RTC, load-switch latch and fuel gauge all disappear.

---

## Decision 4 — interface

Unchanged from the sibling build, and settled: **one illuminated IP65 pushbutton** carrying status
in blink codes, and configuration through a **WiFi AP with a web page** rather than a display. A
display sealed inside an opaque box needs a second window to be useful, which is enclosure
complexity bought for information the web page presents better.

| Signal | Meaning |
|---|---|
| dark | asleep, waiting for its alarm |
| solid, dim | booting |
| slow pulse | AP up, waiting for configuration |
| flash per frame | shooting — shows liveness and the interval |
| amber | battery low |
| red | error, card full |

---

## Bill of materials

### Shared platform

| # | Part | Role | ≈ EUR |
|---|---|---|---|
| 1 | 128 GB A2 microSD (Samsung Pro Plus / SanDisk Extreme) | frames | 15 |
| 2 | 2 × **protected** 18650 + quality hot-swap holder | 7.0 Ah / 25.9 Wh | 22 |
| 3 | 16 mm IP65 illuminated pushbutton + driver transistor | input and status in one hole | 10 |
| 4 | IP65 box ≈120×80×55 mm — or 3D printed | enclosure, designed to open | 18 |
| 5 | 37 mm screw-in UV filter + O-ring | optical window | 12 |
| 6 | PTFE vent plug + silica gel | condensation control | 8 |
| 7 | 1/4"-20 threaded inserts | tripod / clamp mount | 5 |
| | | **subtotal** | **≈ 90** |

### Camera

| Option | Sensor | Interface | ≈ EUR |
|---|---|---|---|
| **Default** | IMX678, M12 lens, board-level | USB 2.0 | **~110** |
| Upgrade | IMX585 + C-mount lens | USB 3.0 | ~220 |

> **Camera prices are estimates, not verified quotes.** Arducam and e-con both list these modules
> but pricing varies by region and lens. Confirm before budgeting — this is the single largest line
> in the build.

### Host

| Tier | Parts | ≈ EUR |
|---|---|---|
| **B** | Radxa Zero 3W (25) + Pololu U3V50F5 boost (18) + DS3231 & P-FET latch (15) + MAX17048 (12) | **70** |
| **C** | ESP32-P4 board with ESP32-C6 (35) + boost (18) + load switch and passives (5) | **58** |

### Totals

| Build | Total |
|---|---|
| **Tier C + IMX678** — lowest power | **≈ €258** |
| Tier B + IMX678 — easiest software | ≈ €270 |
| Tier B + IMX585 — best image quality | ≈ €380 |

**This is a more expensive build than the Pi architecture (~€175)**, and the camera is why. You are
paying for someone else's ISP tuning, in a box. Whether that is worth €80–150 depends entirely on
whether you can source a Raspberry Pi.

### Accessories — outside the box, reusable

| Item | Role | ≈ EUR |
|---|---|---|
| 4-bay 18650 charger (Nitecore / XTAR) | ~2 A per cell, ~2 h | 25 |
| Spare set of 2 protected 18650s | a second set is a second session | 22 |
| USB power meter with Wh/mAh totaliser | **not optional** — §8 depends on it | 15 |

### On lens choice

The default M12 module ships with a lens matched to the sensor. If you take the **IMX585 C-mount**
route, note that a 16 mm lens on a 1/1.2" sensor gives roughly **38° horizontal** — normal-to-tele,
about a 50 mm equivalent. For cityscapes and landscapes you likely want **6–8 mm** (~70°). Check the
focal length before ordering; the bundled 16 mm is aimed at machine vision, not scenery.

Fixed aperture and manual focus are *advantages* here — no focus breathing, no aperture flicker
between frames, both of which are real contributors to timelapse flicker.

---

## Power budget

### Shooting — the model

Per frame the camera is powered for `t_on`:

| Phase | Typical | Notes |
|---|---|---|
| ISP firmware boot | 0.5–1.5 s | **the dominant term** |
| USB enumeration | 0.1–0.5 s | descriptors, set configuration |
| Stream start + settle | 0.2–0.5 s | short, because exposure is locked |
| Frame transfer | ~0.05 s | 2 MB MJPEG over USB 2.0 HS — negligible |

```
P_avg  =  P_host_sleep  +  ( P_cam × t_on  +  E_host_active  +  E_write ) / T
```

For tier C, `P_host_sleep` ≈ 30 µA and vanishes. The energy per frame is essentially the camera's.

| Scenario | `P_cam` | `t_on` | `E_uvc` |
|---|---|---|---|
| Optimistic | 1.0 W | 1.0 s | 1.53 J |
| Plausible | 1.5 W | 1.5 s | 2.98 J |
| Pessimistic | 2.0 W | 1.8 s | 4.45 J |
| Worst case | 2.5 W | 2.5 s | 7.38 J |

> ### `P_cam` is the weakest number in this document
>
> No vendor publishes a figure for a 4K UVC module — e-con omit power from their datasheets
> entirely, and a vendor leaving out a spec is rarely because it flatters them. What exists is
> adjacent: Logitech C270 (720p) ~1.1 W; C920 (1080p) with its H.264 encoder quoted at ~1 W alone;
> FLIR Firefly (USB3 machine vision) 1.5 W; USB 2.0 hard ceiling 2.5 W.
>
> **The plausible range spans a factor of five in per-frame energy**, and every runtime figure below
> scales with it. Measure it first — §8.

### Static versus dynamic — why `t_on` is what matters

| Scales with frame rate | Fixed while powered |
|---|---|
| Row readout and ADC conversions | Sensor analog bias, column amplifiers, ADC references |
| ISP pixel throughput | PLLs and clock trees |
| JPEG encode | Regulator quiescent current, leakage |
| USB transfer | DDR refresh, where the bridge has a frame buffer |

The evidence points to **a substantial static floor**. One direct measurement found current
consumption did not vary between 352×288 and 640×480 capture — if tripling the pixel count doesn't
move the needle, the dynamic term isn't dominant. Structurally that fits: a webcam bridge ASIC is
designed to run 30 fps forever, with little incentive for aggressive clock gating, and sensor bias
circuits draw whenever powered regardless of readout rate.

> **The decimation trap.** Requesting a low frame rate over UVC often just makes the bridge *drop*
> frames while the sensor keeps reading out at full rate. You would save the USB transfer and
> nothing else. Whether a camera extends vertical blanking (a real saving) or decimates is not
> knowable from a datasheet.

**Consequence: the only lever that matters is shortening or eliminating `t_on`.** Frame rate is not
a useful knob here.

### The suspend lever

If the static floor dominates, the win is not running slower — it is **not booting at all**. Leave
the camera enumerated and **suspended** between frames rather than cutting its power:

| | Power-cycled | Suspended |
|---|---|---|
| Between frames | 0 W | **≤2.5 mA ≈ 12 mW** (USB spec cap) |
| Wake to first frame | 1–2.5 s (full ISP boot) | resume ≈ **20 ms** per spec |
| Per-frame energy | 1.5–7.4 J | potentially **~0.6 J** |

A 6× improvement, which would make this architecture comfortably the best option at every interval.

> **The catch is real.** Linux's `uvcvideo` enables autosuspend by default, but per the maintainers
> **"many cameras, including most Logitech UVC webcams, can't resume correctly from USB suspend"** —
> large stream-start delays or corrupted video. Device-dependent and frequently broken. Test it.

### Runtime

On 25.9 Wh of cells, 22.8 Wh at the rail, using the pessimistic `E_uvc` = 4.5 J:

| Interval | Tier C (MCU) | Tier B (SBC) |
|---|---|---|
| 2 s | 10.1 h | 6.9 h |
| 5 s | 25.3 h | 10.3 h |
| 10 s | 50.6 h | 12.3 h |
| 30 s | **151.9 h** | 14.1 h |
| 60 s | **303.9 h** | 14.6 h |

Two things to read off this. **Tier C scales with interval and tier B does not** — the SBC's idle
floor swamps everything, so it plateaus around 14 h no matter how long you wait between frames.
And on the optimistic `E_uvc` = 1.53 J, every tier C figure roughly **triples**: 74 h at 5 s, 894 h
at 60 s.

**Both comfortably clear the 6–12 h requirement.** The question is whether you want a device that
shoots for a day or one that shoots for a fortnight.

### Standby

| | Tier B | Tier C |
|---|---|---|
| RTC on backup | 1–3 µA (DS3231) | onboard, ~10 µA |
| Host | 0 — rail cut by P-FET | deep sleep, ~20 µA |
| Camera | 0 — rail cut | 0 — rail cut |
| Pack protection | ~5 µA | ~5 µA |
| **Total** | **≈ 10–30 µA** | **≈ 35 µA** |

Both are limited by the cells' own self-discharge (~2.5 %/month), not the circuit. Weeks of standby
is free provided the camera and host rails are genuinely switched off, not merely idle.

### Over-discharge

Three layers, and only one is useful:

| Layer | Trips at | Effect |
|---|---|---|
| **Software graceful shutdown** | ~3.1 V | clean halt, filesystem intact, cycle life preserved |
| Boost converter cutoff | ~2.9 V | nothing useful — it stops |
| Cell protection PCB | ~2.5 V | prevents cell damage |

The boost quits *above* the protection threshold, so in normal operation the cell protection never
activates. **Graceful shutdown is mandatory in software.** And whichever host you choose must clear
its wake alarm when halting on low battery, or it will wake onto a flat pack, discover the problem,
halt, and repeat until the cells reach protection cutoff.

---

## Storage

At 4K JPEG q80, roughly 2.2 MB a frame. The card is emptied at every recharge and the battery binds
within a charge, so it need only hold **one full charge's worth of frames**.

| Interval | Frames per charge (tier C) | at q80 |
|---|---|---|
| 2 s | 18,200 | 40 GB |
| 5 s | 18,200 | 40 GB |
| 10 s | 18,200 | 40 GB |
| 30 s | 18,200 | 40 GB |

Note the flat column: for tier C, energy per frame is constant, so **the number of frames per charge
is independent of interval** — roughly 22.8 Wh ÷ 4.5 J ≈ 18,200 frames. That is a different shape
from the Pi build, where a fixed idle floor makes short intervals cost more frames' worth of energy.

**128 GB is ample** — 40 GB at the pessimistic energy figure, or ~120 GB on the optimistic one where
you get 3× the frames. `storage.py` should still pick JPEG quality against a session budget so a
long deployment degrades gracefully rather than filling the card mid-run.

---

## Enclosure

- **Optical window: a screw-in 37 mm UV filter**, not cut acrylic. Flat, coated, cleanable,
  replaceable, already round. Bond over the hole with an O-ring.
- Lens close to the glass with a **black felt collar** in the gap, or internal reflections ghost
  across any bright sky.
- **One window only.** The illuminated button is the status indicator.
- **Silica gel plus a PTFE vent plug.** A sealed box that goes out warm and cools overnight fogs
  from the inside, and you find out on the footage.
- **No external ports.** The SD card already forces opening, so a charging port would mean
  maintaining a second sealing interface to avoid a step you still have to perform.
- **Design it to be opened:** captive fasteners rather than droppable screws, an O-ring in a groove
  rather than adhesive foam, a lid that only fits one way, reachable desiccant, and a lid that
  opens away from the lens window.
- 1/4"-20 insert in the base. A **clamp beats a tripod** for leaving something somewhere.

> **Size check before committing.** A USB camera module plus its lens is bulkier than a Pi camera,
> and the **IMX585 C-mount option is substantially bigger** — likely a ~40 mm board with a 30 mm
> lens barrel, which needs both a larger box and a larger window than the 37 mm filter. Model the
> chosen module before printing.

---

## Software outline

Python on tier B; C/ESP-IDF on tier C. The imaging layer is thin because the camera does the work.

- `camera.py` — open the UVC device, **disable auto-exposure and auto-white-balance**, set
  `exposure_time_absolute` explicitly, grab one MJPEG frame. No demosaic, no tuning, no 3A.
- `scheduler.py` — **monotonic deadlines, not `sleep(interval)`**, or capture time accumulates as
  drift. Model a session as a **list of windows**, not a single start/stop.
- `ramp.py` — a sunset spans ~10 stops; naive auto-exposure strobes. Measure mean luma, correct by
  a **capped step of ≤1/6 stop per frame**. Shutter first to a motion-blur cap, then gain.
- `storage.py` — write `NNNNNN.jpg.tmp`, fsync, rename, fsync the directory. Power loss costs at
  most one frame. Log exposure, gain and lux per frame to `frames.csv`. Owns the storage budget.
- `power.py` — RTC alarm, low-voltage threshold, recovery threshold, and clearing the alarm when
  halting flat.
- `status.py` — button press durations and LED blink codes.
- `web.py` — the settings page, served only while the AP is up.
- Laptop side: `ffmpeg` with `deflicker=mode=pm:size=10`, driven by `frames.csv`.

**The exposure ramp is the hard part and it depends entirely on §8's first test.** Everything else
is plumbing.

---

## The three open measurements

**Buy one camera module — €110 — and run these before anything else.** They cost an evening and
they determine whether this build is viable, competitive, or dead.

### 1. Exposure control — decides whether the path works at all

The entire sunset strategy needs fine, repeatable manual exposure with AE genuinely off. UVC defines
`CT_EXPOSURE_TIME_ABSOLUTE` in 100 µs units with a manual mode, so it is possible in principle —
but whether a module implements it, honours it repeatably, and doesn't let its ISP override you
varies enormously.

1. Disable auto-exposure and auto-white-balance via v4l2 controls.
2. Set `exposure_time_absolute` across a series of known values spanning several stops.
3. Photograph a static, evenly lit scene at each.
4. Plot mean luma against commanded exposure.

**You want a straight line, and the same value must give the same result on a repeat run.**
Curvature is survivable with a calibration table. Hysteresis, quantisation into a handful of steps,
or the ISP overriding you is fatal.

### 2. `P_cam` and `t_on` — decides whether it is competitive

Inline meter on the USB 5 V line. Measure steady draw while streaming, and time plug-in to first
valid frame. Five minutes, and it resolves the largest uncertainty in the power model.

### 3. USB suspend — decides whether it is clearly better

Let the driver autosuspend the device, measure the suspended current, then time resume-to-first-
valid-frame and inspect that frame for corruption. Clean suspend eliminates the dominant energy
term. Broken resume means falling back to power-cycling.

---

## Order of work

**Phase 0 — the three measurements above**, on one module, before buying anything else. If exposure
control fails, this architecture is dead and you have spent €110 finding out.

**Phase 1 — capture and ramp.** Interval accuracy, locked exposure, atomic writes, metadata log.

**Phase 2 — exposure ramping** against a real sunset.

**Phase 3 — power.** Host selection, rail switching, RTC wake, low-voltage and recovery thresholds.
Prove them by running a session to empty.

**Phase 4 — AP config page, button, blink codes.**

**Phase 5 — enclosure and an unattended overnight run in real weather.**

---

## Verification

| What | How |
|---|---|
| Exposure linearity | Luma vs commanded exposure, twice, looking for hysteresis |
| `P_cam`, `t_on` | Inline USB meter; plug-in to first valid frame |
| Suspend behaviour | Suspended current, resume time, first-frame integrity |
| Image quality | A real sunset sequence, at 100 % and as a 4K frame |
| Interval accuracy | `frames.csv` timestamps — stddev of deltas under 50 ms |
| Session power | Meter across 1 h at the real interval |
| Standby power | µA meter on the pack over 24 h with rails cut |
| Low-voltage shutdown | Run to threshold; must halt cleanly and not re-wake flat |
| Shutdown safety | 50 forced power-cuts mid-capture; card mounts clean every time |
| Weatherproofing | Overnight outdoors in rain; inspect the window for condensation |

---

## Known risks

| Risk | Mitigation |
|---|---|
| **Exposure control unusable** | Test 1, before any other spending. No workaround if it fails |
| `P_cam` far above estimate | Test 2; tier C degrades gracefully since energy scales with interval |
| USB suspend broken | Test 3; fall back to power-cycling, which is the assumed baseline anyway |
| No crop room at 4K | Deliberate trade for low light. Frame carefully in the field |
| IMX585 forces USB 3.0 and an SBC host | Choose sensor and host together; IMX678 keeps tier C open |
| Camera module bulk breaks the enclosure | Model the module before printing; C-mount especially |
| Flat pack re-wakes and drains to protection | Clear the wake alarm when halting on low battery |
| **Module outputs YUY2 only** | Check supported formats before ordering; kills tier C and adds host encode cost |
| UVC vendor quirks | Prefer documented vendors (e-con, Arducam, Vadzo) over generic modules |

---

## Relationship to the Pi build

[PI-BUILD.md](PI-BUILD.md) solves the same problem with a Raspberry Pi and its own tuned ISP. It is
cheaper (~€175), its numbers are settled, and at 2–5 s intervals it is probably more efficient. Its
weakness is that it depends on a board that spent much of 2026 unobtainable.

This build costs more and carries three open questions, but it sources today, offers a materially
better sensor, and — in tier C — scales to multi-week deployments the Pi cannot approach.

If a Raspberry Pi-compatible module with a STARVIS 2 sensor and Pi tuning ever appears, it would be
the best of both, and should be adopted immediately.

---

## Sources

- [e-con Systems — IMX415 4K STARVIS USB camera, in-built tuned ISP](https://www.e-consystems.com/usb-cameras/sony-imx415-4k-usb-camera.asp)
- [e-con Systems — IMX678 4K STARVIS 2 low-light module](https://www.e-consystems.com/camera-modules/4k-sony-starvis2-imx678-low-light-camera-module.asp)
- [Arducam — IMX678 STARVIS 2 USB 2.0 UVC module](https://www.arducam.com/ultra-low-light-usb2-0-camera-module-8-3mp-4k-wide-angle-sony-starvis-2-imx678-uvc-plug-n-play-ideal-for-surveillance-night-vision.html)
- [Arducam — IMX585 STARVIS 2 USB 3.0 module with C-mount](https://www.arducam.com/presalesarducam-8-3mp-imx585-manual-focus-usb-3-0-camera-module-with-16mm-c-mount-lens.html)
- [IMX678 vs IMX585 selection guide](https://www.cameramodule.com/info/two-giants-of-sony-starvis2-core-differences-103291125.html)
- [Linux UVC driver FAQ — autosuspend and resume problems](https://www.ideasonboard.org/uvc/faq/)
- [USB webcam power draw on a Raspberry Pi 4 — forum measurements](https://forums.raspberrypi.com/viewtopic.php?t=343144)
- [What is a UVC camera — Edge AI and Vision Alliance](https://www.edge-ai-vision.com/2022/08/what-is-a-uvc-camera-and-what-are-the-different-types-of-uvc-cameras/)
- [Vadzo Falcon-3C10CRS — OX03C10 140 dB HDR UVC module](https://www.accessnewswire.com/newsroom/en/electronics-and-engineering/vadzo-imaging-launches-falcon-3c10crs-2.5mp-omnivisionox03c10-hdr-usb-3-1172035)
- [OmniVision OX03C10 — 140 dB HDR with LED flicker mitigation](https://www.ovt.com/press-releases/omnivision-launches-worlds-first-image-sensor-for-automotive-viewing-cameras-with-140-db-hdr-and-top-led-flicker-mitigation-performance/)
- [Arducam 20 MP IMX283 USB 3.0 module with onboard ISP](https://www.arducam.com/arducam-20mp-usb-3-0-camera-module-with-16mm-c-mount-lens-b0477.html)
- [Basler — colour processing and calibration in machine vision cameras](https://www.baslerweb.com/en-us/learning/color-calibration/)
- [OmniVision OX08B40 — 8.3 MP, 140 dB HDR, LFM](https://www.ovt.com/products/ox08b40/)
- [e-con STURDeCAM88 — OX08B40 4K GMSL2 camera](https://www.e-consystems.com/gmsl-cameras/8mp-ox08b40-ip67-gmsl2-140db-hdr-camera.asp)
- [e-con STURDeCAM84 — AR0823AT 4K, 150 dB HDR, GMSL2](https://www.e-consystems.com/automotive-cameras/4k-ar0823at-ip69k-gmsl2-150db-hdr-camera.asp)
