# Pocket Timelapse Camera

A pocketable, battery-powered, weatherproof timelapse box you set down at dusk and collect a day
or two later. Weeks of standby, 12+ hours of shooting, 4K stills with room to crop, configured
from a phone with no laptop in the field.

**Status: Phase 0 under way, and it has already changed the design.** The UVC camera arrived, the
test tooling is written, and the measurements have been unkind — see *What Phase 0 found* below.
Construction has not started; the architecture is back under review.

## Documents

**Three architectures**, at different stages of validation, plus the camera survey, two background
papers and the Phase 0 results.

| | |
|---|---|
| **[PI-BUILD.md](PI-BUILD.md)** | **Architecture 1 — Raspberry Pi.** The more settled of the two. Every choice, why it was made, what was rejected, and the measurements that still need taking |
| **[UVC-BUILD.md](UVC-BUILD.md)** | **Architecture 2 — UVC camera.** Buys the ISP tuning in the camera, so the host needn't be a Pi. Sources today, better sensor, scales to multi-week runs — with four measurements standing between it and a trusted BOM |
| **[ASTRO-BUILD.md](ASTRO-BUILD.md)** | **Architecture 3 — give the ISP up on purpose.** Own the exposure register instead of buying tuning: an astronomy camera (~26 stops against 4.91) or a board-level machine-vision camera. Removes the Raspberry Pi dependency entirely. Costs twice the power and colour earned in post. An exploration, not a recommendation |
| **[CAMERAS.md](CAMERAS.md)** | **Every camera considered, in one table.** Thirty-odd modules across ten sensors, grouped by whether they keep the low-power MCU host; sensors ranked by light per pixel; and a status column saying which claims are measured, which are vendor-stated and which are guesses |
| **[phase0/README.md](phase0/README.md)** | **The measurements**, the tooling that took them, and the traps found along the way |
| **[IMAGE-PIPELINE.md](IMAGE-PIPELINE.md)** | Background: what happens between photons and a JPEG, and why the camera dictates the board |
| **[SENSORS.md](SENSORS.md)** | Background: the IMX range, why these sensors carry no ISP, what ISP *tuning* is and why it — not hardware — is the real constraint, and why a small sensor on a tripod is enough |

## Architecture 1 in brief — the Raspberry Pi build

| | |
|---|---|
| Compute | Raspberry Pi Zero 2 W |
| Sensor | Camera Module 3 — IMX708, 11.9 MP, 4608×2592, autofocus |
| Power control | Witty Pi 4 L3V7 — RTC, scheduling, 5 V/3 A boost, low-voltage shutdown |
| Battery | 2 × protected 18650, hot-swap, charged in an external bay charger |
| Storage | 128 GB microSD, adaptive JPEG quality |
| Interface | WiFi AP + web page to configure; one illuminated button, blink codes for status |
| Enclosure | IP65 or 3D printed — no external ports, designed to be opened |
| Runtime | ~20 h untuned, ~27 h tuned · standby limited by cell self-discharge, not the circuit |
| Parts | ≈ €175 (Pi) · ≈ €350 (UVC) · ≈ €800 (astro) |

## What Phase 0 found

The Arducam B0587 (IMX678) was bought, measured, and found wanting — in a way no datasheet would
have revealed.

**Its usable exposure range is 4.91 stops. A sunset spans about ten.** The control advertises
0.1–500 ms and reports every value back verbatim, but only 0.1–14.4 ms changes the image; above
that the camera silently ignores it. At the other end, the minimum exposure is still 2.3 stops too
bright for daylight, with 48 % of the frame blown and no iris to close.

**This is structural, not a faulty part.** The cap is one full sensor readout — a constant 6.67 µs
line time across every mode — because USB 2.0 bandwidth, not the sensor, sets the frame rate. And
the deeper cause is the architecture's own first decision: *a camera whose ISP somebody else tuned
is a camera whose sensor registers somebody else owns.* Tuned ISPs are sold inside webcams and
surveillance cameras, and those stream.

**No vendor publishes an exposure range**, which is exactly how this got past selection. Across
thirty-odd modules, ten sensors and a dozen vendors, **two manufacturers state the figure** — both
selling into microscopy. The one specification that decides whether the build works is not a
published specification. See [CAMERAS.md](CAMERAS.md) for the full survey and the buying heuristics
that did survive contact.

## Three things that shaped everything else

**4K forces a Linux board, not a microcontroller.** A raw frame is ~15 MB, which exceeds an MCU's
entire usable RAM, and demosaicing needs a hardware ISP. You aren't buying CPU — you're buying an
ISP block and enough memory to hold a frame.

**The Pi cannot manage its own standby.** A halted Pi Zero 2 W still draws 20–50 mA and has no RTC
at all, so it can neither survive weeks on a battery nor know when to wake. Something external has
to keep time and switch the rail.

**Idle dominates.** Roughly 85% of the battery goes to keeping Linux alive between frames rather
than to photography. That single fact drives the interval strategy, the tuning work, and the
decision to cut power entirely between sessions.

## Planned layout

```
phase0/      test tooling — pure-stdlib V4L2 via ctypes, no packages needed
             probe.py           enumerate formats, controls, frame rates
             exposure_sweep.py  test 1: is exposure monotonic and repeatable?
             timelapse.py       closed-loop ramp, atomic writes, frames.csv
             focus_preview.py   live view in a browser for focusing the lens
             snap.py            a few 4K frames to look at
post/        laptop-side assembly — ffmpeg, deflicker driven by frames.csv
hardware/    wiring notes, printed enclosure and cell sled
```

## License

Documentation and code are licensed **CC BY-SA 4.0** — see [LICENSE](LICENSE). Note the safety
disclaimer there: this describes a lithium-ion powered personal prototype, not a tested product.

## Build order

Phase 0 is deliberately first and deliberately cheap: buy one camera, shoot one real sunset, and
find out whether the picture is acceptable before spending anything else. Every number in the
documents is an estimate until that phase replaces it.

It earned its keep immediately. One €90 camera and a week of evenings established that the chosen
architecture cannot photograph the subject it was designed for — which is precisely what a cheap
first phase is for, and far better news now than after the enclosure was printed.
