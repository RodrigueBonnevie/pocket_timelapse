# Pocket Timelapse Camera — the UVC build

*The second architecture. Keeps 4K and image quality without depending on the Raspberry Pi, by
putting the tuned ISP inside the camera. **Three measurements stand between this and a buildable
BOM** — see §5. The sibling document is [PI-BUILD.md](PI-BUILD.md).*

The chosen design depends on the Raspberry Pi, and [SENSORS.md](SENSORS.md) §2 explains why: not
performance, not price, but that Raspberry Pi are close to the only vendor shipping **open, tooled,
validated ISP tuning** for cheap sensors. That dependency became a practical problem in 2026, when
substrate supply constraints from the AI hardware boom left the Zero 2 W unobtainable for months.

This document describes the one architecture found that keeps 4K and keeps image quality while
escaping that dependency entirely.

---

## 0. What this shares with the Pi build

The two architectures are siblings, not rivals: this is a different **host and camera**, not a
different product. Everything below the imaging layer
is inherited unchanged from [PI-BUILD.md](PI-BUILD.md) and is not repeated here:

| Shared, see PI-BUILD.md | |
|---|---|
| **Battery and power in** | 2 × protected 18650, hot-swap, external bay charger, matched-set discipline |
| **Enclosure** | designed to be opened, one 37 mm filter window, no external ports, vent and desiccant |
| **Interface** | one illuminated IP65 button with blink codes; WiFi AP config page |
| **Storage** | adaptive JPEG quality against a per-session budget, 128 GB card sizing |
| **Software** | `scheduler.py`, `storage.py`, `ramp.py`, `web.py`, `rtc.py`, and the post-processing pipeline |
| **Over-discharge** | three-layer cutoff; graceful shutdown required regardless of host |

What actually differs is the imaging layer and the power controller: `camera.py` swaps picamera2 for
v4l2, and the Witty Pi 4 L3V7 is a Raspberry Pi HAT, so tier C would need its own RTC and load
switch — the DS3231 + P-FET latch documented as path B in the Pi build applies directly.

---

## 1. The idea

**If the camera module contains its own tuned ISP and emits compressed frames, the host needs no
ISP at all.**

That single move dissolves the lock-in. The host stops being an imaging device and becomes a file
writer: trigger a capture, receive JPEG bytes, write to SD, sleep. No demosaic, no 3A, no tuning,
no libcamera — and therefore no reason it has to be a Raspberry Pi.

The product category that does this is **UVC**: USB Video Class camera modules with an onboard ISP.
e-con Systems describe their IMX415 module as having *"a dedicated, in-built ISP… the ISP and
sensor have been tuned for achieving excellent image quality under various lighting conditions
including near darkness"*, output as MJPEG, UVC compliant, no drivers required.

**You buy the tuning instead of doing it.** That is the whole insight.

---

## 2. Three tiers

| | Host | Camera | Idle floor | Availability | Work required |
|---|---|---|---|---|---|
| **A** | Pi Zero 2 W | Camera Module 3 | 0.39 W | ✗ scarce | none — the current design |
| **B** | any available SBC | UVC module | ~1.5 W | ✅ | rewrite `camera.py` only |
| **C** | **ESP32-P4** | UVC module | **~µA** | ✅ | full firmware rewrite |

**Tier B** answers *"the Pi isn't available"*. A Radxa Zero 3W or Orange Pi Zero 2W speaks UVC
natively through v4l2, needs no camera tuning because it's in the camera, and both boards are in
stock. `scheduler.py`, `storage.py`, `ramp.py`, `web.py` and the entire power architecture survive
untouched — only the capture module changes.

**Tier C** answers *"Linux costs 85 % of my energy"*. The ESP32-P4 has **USB 2.0 High Speed host**,
which is the specific capability that makes this possible; the ESP32-S3's USB is Full Speed only
and would take over a second just to transfer one frame. Note the P4 has **no radio** — it needs a
companion ESP32-C6 for the WiFi config AP.

---

## 3. The power model

### The terms

Per captured frame, the camera is powered for `t_on`, decomposed as:

| Phase | Typical | Notes |
|---|---|---|
| ISP firmware boot | 0.5–1.5 s | **the dominant term** |
| USB enumeration | 0.1–0.5 s | descriptors, set configuration |
| Stream start + settle | 0.2–0.5 s | short, because exposure is locked |
| Frame transfer | **~0.05 s** | 2 MB MJPEG over USB 2.0 HS (~40 MB/s) — negligible |

**`P_cam` has a hard ceiling: USB 2.0 supplies at most 500 mA at 5 V = 2.5 W by specification.**
USB 3.0 allows 900 mA = 4.5 W. So a bus-powered USB 2.0 module *cannot* exceed 2.5 W — but that is
a ceiling, not a typical draw, and the actual figure is the weakest number in this document (see
the callout below).

### The equation

```
P_avg  =  P_host_sleep  +  ( E_cam + E_host_active + E_write ) / T

E_cam  =  P_cam × t_on
```

With `P_host_sleep` ≈ 20 µA for an MCU, that first term vanishes — which is the entire point of
tier C. Against the Pi's `P = 0.39 + 1.25/T`, the crossover interval is:

```
T*  =  ( E_uvc − 1.25 J ) / 0.39 W
```

### The numbers

| Scenario | `P_cam` | `t_on` | `E_uvc` | **Crossover** |
|---|---|---|---|---|
| Optimistic | 1.0 W | 1.0 s | 1.53 J | **0.7 s** |
| Plausible | 1.5 W | 1.5 s | 2.98 J | **4.4 s** |
| Pessimistic | 2.0 W | 1.8 s | 4.45 J | **8.2 s** |
| Worst case | 2.5 W | 2.5 s | 7.38 J | **15.7 s** |

> ### `P_cam` is the weakest number in this document
>
> **The crossover spans a factor of twenty and the model is essentially unconstrained without
> measurement.** No vendor publishes a figure for a 4K UVC module; e-con omit power from their
> See3CAM datasheets entirely, and a vendor leaving out a spec is rarely because it flatters them.
> What exists is adjacent and imperfect:
>
> - Logitech **C270** (720p): ~220 mA ≈ **1.1 W**
> - Logitech **C920** (1080p): rated 500 mA; its *H.264 encoder alone* is quoted at **~1 W**
> - FLIR **Firefly** (USB3 machine vision, continuous streaming): **1.5 W**
> - USB 2.0 hard ceiling: 500 mA = **2.5 W**
>
> **A sanity check that cuts the other way:** the *entire* Pi Zero 2 W system — Linux, SoC, ISP
> doing demosaic and denoise, camera, SD, WiFi — peaks at 250–300 mA, i.e. **1.25–1.5 W**. A UVC
> module doing strictly less imaging work than that should not cost more.
>
> The reason it plausibly does is packaging, not physics. **Webcams are not power-optimised** —
> there is 500 mA on the bus and no battery anywhere. The Pi's ISP is a block inside an SoC that is
> *already powered*, so its **marginal** cost is small; a UVC module pays **full freight** for a
> standalone ISP/bridge ASIC on an older node, with its own PMIC, crystal and regulator losses.
>
> **Consequence: the qualitative conclusion below is directional, not settled.** At the optimistic
> end the MCU path wins at every interval including 2–5 s; at the pessimistic end it loses until
> past 15 s. Measure `P_cam` and `t_on` before believing either.

### Static versus dynamic — why `t_on` is the term that matters

A natural question: does `P_cam` scale with frame rate, or is there a large fixed cost to simply
having the camera powered? The evidence points to **a substantial static floor**.

| Scales with frame rate | Fixed while powered |
|---|---|
| Row readout and ADC conversions | Sensor analog bias, column amplifiers, ADC references |
| ISP pixel throughput | PLLs and clock trees |
| JPEG encode | Regulator quiescent current, leakage |
| USB transfer | DDR refresh, where the bridge has a frame buffer |

The one direct measurement found is suggestive: an older test reported **current consumption did not
vary between 352×288 and 640×480 capture**. If tripling the pixel count doesn't move the needle, the
dynamic term was not dominant on that device.

Structurally that is unsurprising. A webcam bridge ASIC is designed to run 30 fps video
indefinitely; there is little commercial incentive to implement aggressive clock gating, and sensor
analog bias circuits draw whenever the sensor is powered regardless of readout rate.

> **The decimation trap.** Even when you request a low frame rate over UVC, many bridges implement
> it by *dropping frames* — the sensor continues reading out at full rate. You would save the USB
> transfer and nothing else. Whether a given camera extends vertical blanking (a real saving) or
> simply decimates is not knowable from a datasheet.

**This is why the model is so sensitive to `t_on` and barely to anything else.** For a timelapse the
camera isn't run slowly, it's power-cycled — so frame rate only applies to the ~1–2 s window it is
awake, during which it boots and streams at its default rate while we keep one frame in forty. Boot
plus static cost *is* the per-frame energy.

### The lever this exposes: USB selective suspend

If the static floor dominates, the win is not running slower — it is **not booting at all**.

Leave the camera enumerated and **suspended** between frames rather than cutting its power:

| | Power-cycled | Suspended |
|---|---|---|
| Between frames | 0 W | **≤2.5 mA ≈ 12 mW** (USB spec cap) |
| Wake to first frame | `t_on` = 1–2.5 s (full ISP boot) | resume ≈ **20 ms** per spec |
| Per-frame energy | 1.5–7.4 J | potentially **~0.6 J** |

If resume-plus-capture were 0.3 s at 2 W, that is **0.6 J against 3.6 J — a 6× improvement**, which
would push the crossover below one second and make the MCU path win at *every* interval, sunsets
included. It would change this architecture from a long-interval specialist into the better option
outright.

> **The catch is real.** Linux's `uvcvideo` driver enables USB autosuspend by default, but per the
> maintainers, **"many cameras, including most Logitech UVC webcams, can't resume correctly from USB
> suspend"** — symptoms being large stream-start delays or corrupted video. Support is
> device-dependent and frequently broken.

That makes suspend behaviour the **third thing to test**, and arguably the highest-leverage of the
three: `P_cam` sets the crossover, exposure control decides whether the path is usable at all, and
suspend decides whether it is merely competitive or clearly better.

### Runtime, on the same 25.9 Wh pack

Using the **pessimistic** case (`E_uvc` = 4.5 J), against 22.8 Wh at the rail. Note this is the
column that flatters the Pi — the optimistic case moves every MCU figure up by roughly 3×:

| Interval | Pi Zero 2 W | Tier C (MCU) | Tier B (SBC) | Winner |
|---|---|---|---|---|
| 2 s | **22.5 h** | 10.1 h | 6.9 h | Pi, 2.2× |
| 5 s | **35.6 h** | 25.3 h | 10.3 h | Pi, 1.4× |
| 10 s | 44.3 h | **50.6 h** | 12.3 h | MCU, 1.1× |
| 15 s | 48.2 h | **76.0 h** | 13.1 h | MCU, 1.6× |
| 30 s | 52.8 h | **151.9 h** | 14.1 h | MCU, 2.9× |
| 60 s | 55.5 h | **303.9 h** | 14.6 h | **MCU, 5.5×** |

Two conclusions, the first heavily caveated by the `P_cam` uncertainty above:

**At 2–5 s the Pi probably wins — but this is the least certain claim here.** It holds if `P_cam`
is near 2 W; it reverses entirely if the module is closer to 1 W. The mechanism is sound in either
case: the camera's boot cost is paid every frame while the Pi's idle floor amortises across the
wait, which is the same shape as the ESP32-P4 and Luckfox analyses. Only the crossover point is in
doubt — but it is in doubt *precisely where this project operates*.

**Past ~10 s the MCU path wins, and by 60 s it wins by 5×** — twelve days of shooting on one pack.
That is a genuinely different device: multi-week deployments, seasonal timelapses, construction
sites.

**Tier B never wins on power** — it is strictly worse than the Pi at every interval. Its case is
availability, not efficiency.

---

## 4. Camera options

The UVC ecosystem is built around **surveillance** sensors, which is fortunate: they are designed
for low light and wide dynamic range, exactly the qualities a sunset needs. Sony's **STARVIS 2**
generation is the current best.

| Sensor | Format | Resolution | Pixel | Pixel area | Sensor area | vs IMX708 |
|---|---|---|---|---|---|---|
| IMX415 | 1/2.8" | 3864×2192 | 1.45 µm | 2.10 µm² | 17.8 mm² | **−0.4 stops** |
| *IMX708 (current)* | *1/2.43"* | *4608×2592* | *1.40 µm* | *1.96 µm²* | *23.4 mm²* | *—* |
| **IMX678** | 1/1.8" | 3840×2160 | 2.00 µm | 4.00 µm² | 33.2 mm² | **+0.5 stops** |
| **IMX585** | **1/1.2"** | 3856×2180 | **2.90 µm** | **8.41 µm²** | **70.7 mm²** | **+1.6 stops** |

**IMX585 is the standout.** It has **1.6 stops more sensor area and 4.3× the pixel area** of the
current choice — a larger jump than any option in [SENSORS.md](SENSORS.md) short of Micro Four
Thirds, and it comes pre-tuned in a box. For a device whose hardest problem is the dark end of a
sunset ramp, that is a serious upgrade.

**IMX415 is a trap.** It is the most common 4K UVC sensor and it is *worse* than what you already
have — higher pixel density, smaller optical format, weaker low light. Do not pick it by
resolution alone.

The cost is crop room: all of these are 3840–3864 px wide, i.e. **4K with nothing spare**, against
the IMX708's 4608 px and its ~20 % margin. Trading 20 % crop for 1.6 stops is defensible for sunset
work, but it is a real trade and it should be a deliberate one.

Modules exist from **Arducam** (IMX678 in both USB 2.0 and USB 3.0, IMX585 USB 3.0 with C-mount),
**e-con Systems** (IMX415, IMX678), and cheaper generic vendors.

### Pick USB 2.0, not USB 3.0

Counter-intuitive but important. USB 3.0 is needed for *4K video at high frame rates or
uncompressed*. **A timelapse needs one still frame at a time**, and MJPEG over USB 2.0 High Speed
moves a 2 MB frame in ~50 ms.

Choosing USB 2.0 buys three things: the power ceiling halves from 4.5 W to **2.5 W**, the transfer
term stays negligible, and **the ESP32-P4 remains a viable host** — its USB is 2.0 High Speed, so a
USB 3.0 camera would rule out tier C entirely.

---

## 5. The open risk — exposure control

This is the one thing that decides whether the architecture is real, and it cannot be resolved by
reading datasheets.

The entire sunset strategy depends on **fine, repeatable, manual exposure** with auto-exposure
genuinely disabled — capped steps of ≤1/6 stop per frame, applied predictably. UVC does define
`CT_EXPOSURE_TIME_ABSOLUTE` in 100 µs units along with a manual exposure mode, so it is possible in
principle. But whether a given module implements it, honours it repeatably, and doesn't let its ISP
quietly override it varies enormously between vendors.

**This is the same wall that disqualified the Arducam Mega and the generic UVC modules.** Reputable
vendors (e-con, Arducam) document their controls properly; cheap modules are a lottery.

### The test that decides it

Buy **one** module — €50–90 — and before anything else:

0. **Measure `P_cam` and `t_on` first** — inline meter on the USB 5 V line, from plug-in to first
   valid frame. Five minutes, and it resolves the largest uncertainty in the model.
0b. **Test USB suspend.** Let `uvcvideo` autosuspend the device, measure the suspended current, then
   time resume-to-first-valid-frame and inspect that frame for corruption. Clean suspend/resume is
   worth more than any other optimisation here; broken resume means falling back to power-cycling.
1. Disable auto-exposure and auto-white-balance via v4l2 controls.
2. Set `exposure_time_absolute` across a series of known values spanning several stops.
3. Photograph a static, evenly lit scene at each.
4. Plot mean luma against commanded exposure.

**You want a straight line, and you want the same value to give the same result on a repeat run.**
Curvature is survivable with a calibration table; hysteresis, quantisation into a handful of steps,
or the ISP overriding you is fatal.

That is an evening's work and it either opens this entire path or closes it.

---

## 6. Where each architecture wins

Neither is strictly better. They win in different places, and they are at different stages of
validation.

| | Pi build | UVC build |
|---|---|---|
| **Status** | numbers settled, BOM complete | **three measurements outstanding** |
| **Sourcing** | blocked by the Zero 2 W shortage | components in stock |
| **2–5 s intervals** | probably wins — but see the `P_cam` caveat | possibly wins if `P_cam` is low or suspend works |
| **>30 s intervals** | 53 h | **152–900 h** — no contest |
| **Best sensor available** | IMX708, or IMX477 for the lens mount | **IMX585, +1.6 stops** |
| **Crop room at 4K** | ~20 % margin | none |
| **Software** | picamera2, well-trodden | v4l2 (tier B) or ESP-IDF firmware (tier C) |

**Pick the Pi build** if you can source a Zero 2 W and shoot mostly at 2–5 s intervals. It is the
known quantity: every number in its document is either measured or has a documented path to being
measured, and the software is the well-trodden one.

**Pick the UVC build** if the Pi stays unobtainable, if you want multi-week deployments at long
intervals, or if the low-light gain matters more than crop room. **IMX585 offers 1.6 stops and 4.3×
the pixel area of the IMX708** — pre-tuned, in a box, and available today. That is the single
biggest image-quality upgrade identified anywhere in this project.

**What would settle it:** the three tests in §5, on one module, in one evening. `P_cam` fixes the
crossover, exposure control decides whether the path is usable at all, and suspend decides whether
it is merely competitive or clearly better. Until those are run, this document is a well-researched
hypothesis and the Pi build is a plan.

And regardless of which wins: **if a Raspberry Pi-compatible module with a STARVIS 2 sensor and Pi
tuning ever appears, it is the best of both** and should be adopted immediately.

---

## Sources

- [e-con Systems — IMX415 4K STARVIS USB camera, in-built tuned ISP](https://www.e-consystems.com/usb-cameras/sony-imx415-4k-usb-camera.asp)
- [e-con Systems — IMX678 4K STARVIS 2 low-light module](https://www.e-consystems.com/camera-modules/4k-sony-starvis2-imx678-low-light-camera-module.asp)
- [Arducam — IMX678 STARVIS 2 USB 2.0 UVC module](https://www.arducam.com/ultra-low-light-usb2-0-camera-module-8-3mp-4k-wide-angle-sony-starvis-2-imx678-uvc-plug-n-play-ideal-for-surveillance-night-vision.html)
- [Arducam — IMX585 STARVIS 2 USB 3.0 module with C-mount](https://www.arducam.com/presalesarducam-8-3mp-imx585-manual-focus-usb-3-0-camera-module-with-16mm-c-mount-lens.html)
- [IMX678 vs IMX585 selection guide](https://www.cameramodule.com/info/two-giants-of-sony-starvis2-core-differences-103291125.html)
- [What is a UVC camera — Edge AI and Vision Alliance](https://www.edge-ai-vision.com/2022/08/what-is-a-uvc-camera-and-what-are-the-different-types-of-uvc-cameras/)
- [USB webcam power draw on a Raspberry Pi 4 — forum measurements](https://forums.raspberrypi.com/viewtopic.php?t=343144)
- [Logitech H.264 encoding white paper (C920 encoder power)](https://www.logitech.com/assets/45120/logitechh.pdf)
