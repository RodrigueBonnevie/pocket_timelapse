# Pocket Timelapse Camera — the consumer-camera build

**Status: exploration.** Nothing measured. This is the architecture the project started from, revisited
after Phase 0 established that the module path's problem is exposure range rather than sensor quality.

The premise: **stop trying to find a camera module that behaves like a camera, and use a camera.**

**Not the good camera.** An R7 left in a wood is a bad trade, and the R-line is poorly suited anyway.
See *The cheap-body shortlist* below — the answer is an old body running CHDK or Magic Lantern, where
the MCU does nothing but switch the power.

---

## Why it looks good on the numbers

Against the Arducam B0587 that Phase 0 measured, at the same field of view and f-number:

| | Arducam B0587 | **Canon EOS R7** (owned) |
|---|---|---|
| Sensor | IMX678, 1/1.8″, 33 mm² | **APS-C, 22.3×14.8 mm, 330 mm²** |
| Pixel | 2.0 µm | **3.2 µm** — +1.36 stops per pixel |
| Total light at equal FOV and f-number | — | **10× the area = +3.3 stops** |
| Resolution | 3840×2160 | **6960×4640** — 32.5 MP, crop room to spare |
| **Exposure range** | **4.91 stops, measured** | **30 s – 1/16000 ≈ 18.9 stops**, plus bulb |
| Output | 8-bit JPEG | 14-bit RAW **or** in-camera JPEG |
| Storage | host's problem | **the camera's own SD card** |
| ISP and tuning | Arducam's | **Canon's, which is the point of buying a Canon** |
| Cost | ~Skr 1,000 | already owned |

**+3.3 stops of light and fourteen more stops of exposure range**, with an ISP tuned by a company
whose entire business is that tuning. No demosaic to write, no flat frames, no colour matrix.

---

## Can the USB control be distilled onto an MCU? Yes — and it has been done on an ATmega

Cameras speak **PTP** (Picture Transfer Protocol) over USB: a simple container-based request/response
protocol over bulk endpoints. Canon extends it with vendor opcodes in the 0x9xxx range. The
operations this project needs are few — `OpenSession`, `GetDevicePropDesc`, `SetDevicePropValue` for
shutter/ISO/aperture, `InitiateCapture`.

**The prior art is unambiguous.** [`felis/PTP_2.0`](https://github.com/felis/PTP_2.0) is a PTP camera
control library for the USB Host Shield 2.0, with a Canon EOS layer in `canoneos.h`, supporting Canon
EOS, PowerShot and Nikon DSLRs — and it runs on an **ATmega**, an 8-bit part with kilobytes of RAM.
An ESP32-P4 has a USB 2.0 High Speed host and is orders of magnitude more capable.

### The move that makes this architecture collapse to nothing

**Do not transfer the images.** Let the camera write to its own SD card.

That single decision deletes the entire data path that every other architecture in this repository
struggles with — no 16 MB raw frames over USB, no demosaic, no JPEG encode, no storage subsystem, no
`storage.py`, no card-corruption handling. **The MCU sends a few hundred bytes per frame and the
camera does everything else**, including being good at photography.

What is left for the host: an RTC, a power switch, and a handful of PTP commands.

### Three levels, cheapest first

| Level | Mechanism | Hardware | Exposure ramp | Cost |
|---|---|---|---|---|
| **0 — intervalometer** | optocoupler shorts the remote-release contacts | ~€5 | **camera's own AE** — will flicker frame to frame | trivial |
| **1 — PTP on an MCU** | ESP32-P4 USB host speaking PTP | ~€15 | **explicit, capped per frame** — the real thing | a firmware project |
| **2 — `gphoto2` on Linux** | SBC running libgphoto2 | ~€30 + 2 W | explicit, and everything works | loses tier C |

**Level 0 is a legitimate build.** A camera in aperture priority with Auto ISO, triggered every five
seconds, is how a great many timelapses are made. Its weakness is exactly the one this project has
been solving for — frame-to-frame exposure flicker with no cap on the step — but `ffmpeg`'s
deflicker and the existing `frames.csv` discipline mitigate it, and modern metering is not bad.

**Level 1 is the interesting one**, and it is what the project's MCU preference points at.

---

## The cheap-body shortlist — and how far the architecture collapses

Leaving an R7 on a hillside is a bad trade, and the R-line is the wrong tool anyway: high power, no
on-camera scripting, and quirky `gphoto2` support. The right answer is an old body that already does
the work on board.

**Because once CHDK or Magic Lantern is running, the MCU stops needing to set settings or trigger at
all.** Its job reduces to *switching the rail on at the scheduled time and off again hours later* —
which is exactly the DS3231 + P-FET latch already designed in [PI-BUILD.md](PI-BUILD.md), at
microamps. No USB host, no PTP, no V4L2, no image handling, no storage code, no `ramp.py`.

**This is the simplest architecture in this repository by a wide margin.**

### The two on-camera firmwares

**CHDK** (Canon PowerShot) runs Lua/uBASIC scripts on the camera: intervalometer, exposure ramping,
RAW, full manual. It also has the neatest control channel found anywhere in this project — **apply
3–5 V to the USB power pin and the camera acts**, with `get_usb_power` returning the pulse length to
about 10 ms, so **pulse width encodes commands**. One GPIO, one transistor, no protocol stack, no USB
host peripheral. An ESP32-C3 would do.

**Magic Lantern** (Canon DSLRs and EOS M) has a built-in intervalometer and **bulb ramping that
"adjusts shutter and ISO automatically by analyzing image brightness of previous shots"** — which is
`ramp.py`, already written and debugged by other people, running on the camera.

### Candidate bodies

Sensor area against the IMX678's 33.6 mm², at equal field of view and f-number:

| Body | Sensor | Area | vs IMX678 | Resolution | Firmware | Used price |
|---|---|---|---|---|---|---|
| **PowerShot G1 X Mark II** | **1.5″**, 18.7×14.0 | **262 mm²** | **+2.96 st** | 4352×3264 | **CHDK** (120a) | ~€250 |
| PowerShot G7 X | 1″, 13.2×8.8 | 116 mm² | +1.79 st | 5472×3648 | **CHDK** | ~€200 |
| PowerShot G16 | 1/1.7″ | 41.5 mm² | +0.31 st | 4000×3000 | **CHDK** (DIGIC 6) | ~€120 |
| **Canon EOS M** | APS-C | **332 mm²** | **+3.31 st** | 5184×3456 | **Magic Lantern** | ~€130 |
| Canon EOS 100D / 650D | APS-C | 332 mm² | +3.31 st | 5184×3456 | **Magic Lantern** | ~€130 |

All of them clear 4K after a 16:9 crop, with room spare.

### The two that matter

**PowerShot G1 X Mark II** is the interesting one. A 1.5″ sensor is **+3 stops over the module already
owned** — as much as APS-C — in a compact body with the lens built in. That last point is worth more
than it sounds: **no lens to buy, and a small front element means a small optical window**, so the
37 mm filter from the original enclosure plan still works rather than a 77 mm plate. The lens also
retracts, protecting itself. CHDK's USB-pulse channel makes the electronics trivial.

**Canon EOS M** is the cheapest route to APS-C, at around €130. Mirrorless, so no mirror slap and
lower power than a DSLR, tiny, and Magic Lantern does the ramping. Against it: an interchangeable
lens means buying glass and a much larger window, and it has a **mechanical shutter**.

### Shutter wear is the deciding constraint for the DSLRs

One 12 h session at 5 s is **8,640 actuations**. Against a 100,000-rated shutter that is **twelve
sessions**. This is a consumable, and it is why the compacts win: many use a leaf or electronic
shutter with no comparable wear. **Check the shutter type before buying any body for this.**

### Three gotchas that will otherwise waste a weekend

**Buy a genuine Canon DC coupler, not an aftermarket dummy battery.** The distinction matters exactly
here: an original coupler identifies itself as a coupler rather than impersonating a battery, and
cameras that see a coupler can be **powered on and off freely** — which is the entire premise of an
MCU-switched rail. Aftermarket units that masquerade as batteries can behave differently.

**Verify the camera boots when the rail is applied**, with its physical switch left on, and that
CHDK's autostart script or ML's intervalometer starts unattended after a cold power-up. If it needs a
button press, the whole design fails and it fails silently at 3 a.m.

**Decide what happens to a retracting lens on power loss.** Cutting the rail mid-session may leave
the lens extended. Inside a sealed box that is harmless — and arguably better, since it avoids a
retract/extend cycle per session — but confirm the camera does not sulk on the next boot.

## The catch that decides the power budget

**A USB-connected camera generally will not sleep.** Level 0 lets the camera auto-power-off between
frames and wake on a half-press, which is how commercial intervalometers get weeks out of a battery.
Level 1 keeps a PTP session open, and the camera stays awake at perhaps 2–4 W.

| | Camera | Host | Total |
|---|---|---|---|
| Level 0, camera sleeping between frames | low, unmeasured | ~30 µA | **potentially very low** |
| Level 1, PTP session held open | ~3 W estimated | ~30 µA | **~3 W** |
| Level 2, Linux + gphoto2 | ~3 W estimated | ~2 W | ~5 W |

Level 1 at ~3 W is comparable to the astro and machine-vision builds — but it buys a 32 MP APS-C
sensor rather than a 1/1.8″ module. **Level 0 might be dramatically better than anything else in this
repository**, because it is the only architecture where *both* the host and the camera can sleep.

That makes the power measurement the single most valuable unknown on this path.

---

## Hardware around the camera

| Part | Role | ≈ EUR |
|---|---|---|
| **DC coupler (dummy battery)** — Canon DR-E6NH | replaces LP-E6NH, takes external 7.4–8.4 V | 40 |
| Boost/buck to 8.4 V | from the 18650 pack | 15 |
| 4 × 18650 + sled | ~52 Wh, ~14 h at 3 W | 40 |
| **ESP32-P4** (level 1) *or* optocoupler + 2.5 mm remote lead (level 0) | control | 15 / 5 |
| DS3231 + P-FET latch, or Witty Pi | scheduled wake, switched rail | 15 |
| **Large flat optical window** | 77 mm+ filter or a flat port | 40 |
| Weatherproof case, ~250×180×150 mm | enclosure | 40 |
| Vent plug, desiccant, O-rings, inserts | sealing | 25 |
| | **total, excluding the camera** | **≈ 230** |

The camera's own SD card is the storage. No microSD on the host, no boost for a Pi, no fuel gauge.

---

## Four things that could sink it

**Heat.** A mirrorless camera sealed in a box in the sun will overheat — these bodies are already
thermally limited when recording, and a sealed enclosure removes the convection they rely on. This is
the most likely failure mode and the hardest to design around. Mitigations: shade, a light-coloured
case, thermal mass, a bigger box, and possibly a session that does not run through midday. **Test
before trusting it.**

**The optical window.** A camera lens looking through flat glass needs that glass to be good — a
cheap window in front of an RF lens throws away exactly what you paid for. A large multi-coated
filter costs real money, and the front element sits far from the window, which invites internal
reflections from bright skies. Budget for a proper one and a deep matte hood inside.

**Shutter wear, if the camera has a mechanical one.** DSLR shutters are rated 100k–300k actuations;
one 12 h session at 5 s is **8,640 frames**, so a rated life is **12 to 35 sessions**. This is a
consumable cost, not a footnote. **The R7's fully electronic shutter has no mechanical wear at all**,
which is decisive — and it is silent and vibration-free, which matters inside a box.

**The camera is worth more than everything else combined.** Leaving an R7 and a lens on a hillside is
a different risk calculation from leaving a €90 module. That argues for a **cheap second-hand body
for the box** — a used EOS RP, R10 or M50 at €300–500 keeps the same ecosystem, the same `gphoto2`
and PTP support, and the same DC coupler family, while the R7 stays for handheld work.

---

## Compact cameras, and the CHDK shortcut

Most compacts have weak PTP control — many will trigger but not accept exposure settings. But there
is a better route that needs **no external controller at all**:

- **CHDK** (Canon Hack Development Kit) runs scripts *on* older Canon PowerShots: intervalometer,
  exposure ramping, RAW output, full manual control. Load it from the SD card, non-destructively.
- **Magic Lantern** does the same for many Canon DSLRs, adding intervalometers and bulb ramping.

So a CHDK-capable compact plus power plus a weatherproof box is **the simplest possible version of
this entire project** — no MCU, no USB, no firmware to write, and the ramp runs on the camera. The
price is a small old sensor and a model-specific dependency on a community project.

Worth knowing about. Not obviously better than using the camera already owned.

---

## DSLR with the mirror up?

Mirror lockup helps vibration and mirror wear, but it does not help the thing that matters. In Live
View the mirror is up *and the sensor is live*, which is the high-power, high-heat state — the worst
combination for a sealed battery-powered box. And the mechanical shutter still actuates per frame.

**Mirrorless with an electronic shutter dominates a DSLR here on every axis that matters**: no mirror,
no shutter wear, no vibration, no noise, lower power in the states this build uses. An old DSLR is
cheap, and a shutter replacement is ~€150 — but it is a wear item that a mirrorless simply does not
have.

---

## What to find out, in order

1. **Measure the power** in all three levels, especially level 0 with the camera asleep between
   frames. This is the number that decides whether this is the best architecture here or merely a
   good one.
2. **Verify PTP control of the exact body** on a laptop with `gphoto2` first. Canon R-series support
   is **partial and quirky**: ISO and aperture work on the R7, `exposurecompensation` is a known open
   bug, and gphoto2 has reported shutter/aperture inconsistencies across the R line. Confirm that
   shutter and ISO can be set reliably *before* writing any firmware.
3. **Run a heat test** — sealed box, in the sun, for a full session.
4. **Then port the subset to the MCU**, using `felis/PTP_2.0`'s Canon layer as the reference.

Step 2 costs nothing and can be done this evening with the camera already owned and a USB cable.
