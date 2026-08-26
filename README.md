# Pocket Timelapse Camera

A pocketable, battery-powered, weatherproof timelapse box you set down at dusk and collect a day
or two later. Weeks of standby, 12+ hours of shooting, 4K stills with room to crop, configured
from a phone with no laptop in the field.

**Status: design complete, build not started.** Component selection is finished; construction
begins when the first parts arrive. No code written yet — by design, since the numbers that shape
the software all come from Phase 0 measurements on real hardware.

## Documents

| | |
|---|---|
| **[HARDWARE.md](HARDWARE.md)** | The decision document — every choice, why it was made, what was rejected, and the measurements that still need taking |
| **[IMAGE-PIPELINE.md](IMAGE-PIPELINE.md)** | Background: what happens between photons and a JPEG, and why the camera dictates the board |
| **[SENSORS.md](SENSORS.md)** | Background: the IMX range, why these sensors carry no ISP, and why a small sensor on a tripod is enough |

## The design in brief

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
| Parts | ≈ €175 |

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
pi/          capture application — Python + picamera2
post/        laptop-side assembly — ffmpeg, deflicker driven by frames.csv
hardware/    wiring notes, printed enclosure and cell sled
```

## License

Documentation and code are licensed **CC BY-SA 4.0** — see [LICENSE](LICENSE). Note the safety
disclaimer there: this describes a lithium-ion powered personal prototype, not a tested product.

## Build order

Phase 0 is deliberately first and deliberately cheap: buy only the Pi, camera, card and a USB
power meter, shoot one real sunset off a power bank, and find out whether the image quality is
acceptable before spending anything else. Every number in the documents is an estimate until that
phase replaces it.
