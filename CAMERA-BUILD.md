# Pocket Timelapse Camera — the consumer-camera build

**Status: exploration, but the most promising one here.** Nothing measured. This is the architecture
the project started from, revisited after Phase 0 established that the module path's problem is
exposure range rather than sensor quality.

The premise: **stop trying to find a camera module that behaves like a camera, and use a camera.**

## The build, in one paragraph

**A used Panasonic GX7, a cheap manual wide lens, a dummy battery, two 18650s and a timer.** The
camera's own intervalometer runs the session, its electronic shutter means no mechanical wear, its
ISP is tuned by people who make cameras, and it writes to its own SD card. **The MCU does nothing but
switch the rail on at dusk and off again** — which is the DS3231 + P-FET latch already designed in
[PI-BUILD.md](PI-BUILD.md), sitting at microamps in between.

| | |
|---|---|
| Sensor | **+2.74 stops** over the IMX678 measured in Phase 0 |
| Exposure range | the camera's own — **~17 stops**, against 4.91 |
| Software to write | **the timer. That is all** |
| Cost | **~€320** complete |
| Power | ~1.6 W shooting, **2 cells for a sunset** |

No demosaic, no ISP tuning, no `ramp.py`, no `storage.py`, no V4L2, no PTP, no USB host. Every piece
of the problem this repository has been solving is already solved inside a camera that costs €150
second-hand.

**Not the good camera.** An R7 left in a wood is a bad trade, and the R-line is poorly suited anyway —
high power, no on-camera scripting, quirky `gphoto2` support. It appears below only to show what the
*format* buys.

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

### Interchangeable-lens bodies, used

Sensor area against the IMX678's 33.6 mm², at equal field of view and f-number.

| Body | Mount | Sensor | Area | vs IMX678 | E-shutter | Built-in interval | DC coupler | Used |
|---|---|---|---|---|---|---|---|---|
| **Panasonic GX85 / GX80** | MFT | 17.3×13.0 | 225 mm² | **+2.74 st** | **yes** | **yes** | DMW-DCC11 | ~€250 |
| **Panasonic G7** | MFT | 17.3×13.0 | 225 mm² | **+2.74 st** | **yes** | **yes** | DMW-DCC8 | ~€180 |
| **Panasonic GX7** | MFT | 17.3×13.0 | 225 mm² | **+2.74 st** | **yes** | **yes** | DMW-DCC11 | ~€150 |
| Olympus E-M10 II | MFT | 17.3×13.0 | 225 mm² | +2.74 st | yes | yes | via AC adapter | ~€180 |
| Canon EOS M | EF-M | 22.3×14.9 | 332 mm² | **+3.31 st** | no | via Magic Lantern | DR-E12 | ~€130 |
| Canon 100D / 650D | EF | 22.3×14.9 | 332 mm² | +3.31 st | no | via Magic Lantern | DR-E12 / E8 | ~€130 |
| Sony a6000 | E | 23.5×15.6 | 367 mm² | **+3.45 st** | no (EFCS only) | **no — app discontinued** | AC-PW20 | ~€250 |
| Sony NEX-5N / 6 | E | 23.5×15.6 | 367 mm² | +3.45 st | no | no | AC-PW20 | ~€120 |
| Nikon 1 J5 | Nikon 1 | 13.2×8.8 | 116 mm² | +1.79 st | yes | yes | EP-5 | ~€150 |

**The Panasonic MFT bodies are the answer for this build**, and it is not close:

- **Built-in intervalometer**, so the camera runs the whole session — the MCU is a timer switch.
- **Electronic shutter**, so there is *no mechanical wear at all*. This is the single biggest
  practical difference against every DSLR here: 8,640 actuations a session against a 100,000 rating
  makes a mechanical shutter a consumable, and an electronic one makes that number irrelevant.
- **DC couplers are cheap and everywhere** — DMW-DCC8 and DCC11 are commodity parts.
- 16 MP at 4592×3448, so a 16:9 crop is 4592×2583 — above 4K with room spare.

The **GX7 at ~€150** is the value pick; the **G7** adds an articulating screen; the **GX85** adds IBIS
and drops the AA filter.

**Watch the Sony trap.** The a6000's interval shooting came from a PlayMemories app, and Sony shut
that store down — so a used a6000 has *no* built-in intervalometer today despite what old reviews
say. It needs external triggering, which works but gives up the "camera does everything" advantage.

### Lens mounts, and why old glass is technically better here

**Aperture flicker is a real and documented timelapse failure**, not a preference. An electronic lens
re-actuates its diaphragm for every frame and does not land in exactly the same place twice; the
result is visible brightness stepping through the sequence. The standard fixes are the "lens twist
trick" — partially unmounting the lens to break the electrical contacts so the blades stay put — or,
simply, **a lens with a real aperture ring, which cannot flicker because nothing moves.**

So a manual vintage lens is **cheaper *and* better** for this application. It also cannot hunt,
cannot drift on power-up, and has one less thing to fail in a box on a hillside.

#### What each mount can adapt

Short flange distance is what buys adaptability — the mount must sit *closer* to the sensor than the
lens was designed for.

| Mount | Flange | What adapts onto it |
|---|---|---|
| **Fuji X** | 17.7 mm | everything below |
| **Sony E** | 18 mm | everything below |
| **Canon EF-M** | 18 mm | everything below |
| **Micro Four Thirds** | 19.25 mm | **M42, OM, MD/MC, FD, C/Y, PK, Nikon F, Leica R, EF…** |
| Canon EF | 44 mm | M42, Leica R, C/Y — a short list |
| Nikon F | 46.5 mm | almost nothing |

**Any of the mirrorless mounts adapts essentially every vintage SLR lens ever made**, with a dumb
mechanical adapter at €10–25. The DSLR mounts do not, which is another mark against the Canon DSLRs.

#### Vintage families worth buying, cheapest first

| Family | Typical 50 mm price | Notes |
|---|---|---|
| **M42 screw** | €20–60 | Takumar, Zeiss Jena, Praktica. Enormous supply, the cheapest route in |
| **Minolta MD / MC** | €25–70 | Orphaned mount, so excellent glass at low prices |
| **Canon FD** | €25–80 | Also orphaned when Canon moved to EF — bargains |
| **Olympus OM** | €40–100 | Compact, well made |
| **Pentax K** | €30–80 | Still mountable on modern Pentax, so slightly dearer |
| **Nikon F (AI/AI-S)** | €50–150 | Still usable natively, so the priciest |
| C-mount (16 mm cine) | €20–60 | **Image circle too small** — vignettes on MFT and above |

#### The catch: vintage is not wide

For a cityscape you want roughly 75–90° diagonal, which means:

| Format | Diagonal | 90° needs | 75° needs |
|---|---|---|---|
| MFT | 21.6 mm | **10.8 mm** | 14 mm |
| APS-C | 28.2 mm | **14 mm** | 18 mm |

**Cheap vintage glass is 28 mm, 50 mm and 135 mm.** A €40 vintage 28 mm becomes a 56 mm-equivalent on
MFT — a short telephoto, not a landscape lens. Vintage wide-angles are exactly the expensive
exception, and on MFT the 2× crop makes it worse.

**The fix is a modern manual lens**, which keeps the aperture-ring advantage and costs little:

| Lens | Format | Mount | ≈ Price |
|---|---|---|---|
| 7artisans 7.5 mm f/2.8 fisheye | MFT | native MFT | €130 |
| Meike / 7artisans 12 mm f/2.8 | MFT & APS-C | native MFT / E / EF-M | €150 |
| TTArtisan 11 mm f/2.8 | APS-C | native E / EF-M / X | €200 |
| Laowa 7.5 mm f/2 | MFT | native MFT | €450 |

All fully manual with real aperture rings, native mount, no adapter. **Buy one modern manual wide for
the actual work, and adapt vintage glass when a longer view is wanted** — which for a timelapse box
is a genuinely useful second option, since a 50 mm equivalent view of a distant skyline is a
different and often better picture than a wide one.

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
sensor rather than a 1/1.8″ module.

### Two power cycles, and only one of them applies here

**Between sessions** — the box sits for days or weeks, wakes at a scheduled time, shoots, and shuts
down. This is the DS3231 + P-FET latch from [PI-BUILD.md](PI-BUILD.md) sitting at microamps in
between, and it is what makes weeks of standby possible. **Essential, and independent of the
interval.**

**Between frames** — cutting the camera's rail between individual shots. **Not worth it at the
intervals this project actually uses.**

| Interval | Stay on (1.6 W) | Cycle (~3 s boot at ~2.5 W) | |
|---|---|---|---|
| 2 s | 3.2 J | 7.5 J | **impossible** — boot exceeds the interval |
| 5 s | 8.0 J | 7.5 J | break-even |
| 10 s | 16.0 J | 7.5 J | ~2× on paper |
| 60 s | 96.0 J | 7.5 J | clearly worth it |

The naive break-even is **4.7 s**, but the practical threshold is far higher. A camera needs more
than three seconds to boot *and* be ready — metering, card mount, autofocus, lens init on a compact.
Auto-power-off minimums are typically 30 s, so the camera will not help. And 4,320 power cycles in a
single 12 h session is wear on hardware not designed for it, with a dropped frame every time a boot
runs slow and no way to know until you get home.

**So at 2–10 s intervals the MCU closes the rail once at the start of the session and opens it once
at the end.** That is the whole of its power role, and it simplifies everything downstream: the
power budget is simply idle × session length, the trigger logic is "fire" with no wake-first
handshake, and there is no boot-timing race to lose frames to.

> **Correction, 2026-09-21.** An earlier version of this section claimed level 0 "might be
> dramatically better than anything else in this repository, because it is the only architecture
> where both the host and the camera can sleep". That is true only above ~30 s intervals. At the 2 s
> interval actually used it is false — the camera cannot sleep at all, and the power budget is the
> straightforward one already sized below.

---

## Battery sizing — an estimate, and how to replace it with a measurement

**These are estimates with roughly ±50 % on the dominant term.** Nobody publishes the standing power
of a camera in timelapse mode, and the CIPA shot rating does not model it — CIPA assumes flash,
image review, zooming and a power cycle every ten frames, none of which a timelapse does, while
ignoring the thing that actually drains the battery: **the camera sitting awake between frames.**

### The model

Same shape as everywhere else in this project — a static floor plus a per-frame cost:

    E_total = P_idle × T  +  E_frame × N

Working backwards from the widely reported figure that a DSLR yields roughly 1,500 timelapse frames
from an 8 Wh battery gives **P_idle ≈ 1.6 W and E_frame ≈ 3 J** for an APS-C body. A compact should
be gentler; call it **1.2 W and 2 J**.

Sanity check in the other direction: 7 Wh of camera battery at 1.6 W is **about 4 hours**, which
matches the common experience that one battery gets you a few hours of timelapse and no more.

### What that means at a 5 s interval

| Session | Compact (G1X II class) | APS-C (EOS M class) |
|---|---|---|
| 6 h — 4,320 frames | 9.6 Wh | 13.2 Wh |
| 8 h — 5,760 frames | 12.8 Wh | 17.6 Wh |
| 12 h — 8,640 frames | 19.2 Wh | 26.4 Wh |

Through a converter at 88 % and with the usual 25 % derate for cold, ageing and not running flat,
in 3500 mAh 18650s at 12.6 Wh each:

| Session | Compact | APS-C |
|---|---|---|
| 6 h | **2 cells** | **2 cells** |
| 8 h | **2 cells** | **2–3 cells** |
| 12 h | **3 cells** | **3–4 cells** |

**Two cells covers a sunset comfortably, three covers a long session.** Note the interval barely
matters below ~10 s: at 5 s the static floor is 70–75 % of the total, so halving the interval to 2 s
adds only about a quarter to the budget.

### Against the other builds

| Build | Shooting power | 12 h |
|---|---|---|
| [Pi build](PI-BUILD.md) | ~1.1 W | 2 cells |
| [UVC build](UVC-BUILD.md), tier C | ~1 W | 2 cells |
| **This build, compact** | **~1.6 W avg** | **3 cells** |
| **This build, APS-C** | **~2.2 W avg** | **3–4 cells** |
| [Astro build](ASTRO-BUILD.md) | ~4.0–4.5 W | 6 cells |

**It sits between the module builds and the Linux builds**, which is a good place to be given it
brings a sensor three stops larger and deletes the entire software pipeline.

### Would sleeping between frames help? At 5 s, barely

Tempting, since CHDK and Magic Lantern can power down between shots on some bodies. But waking a
camera costs energy and several seconds, and at a 5 s interval there is almost no idle left to
reclaim — the saving arrives around **20–30 s intervals** and is large only beyond that. Worth
configuring for long-interval sessions; not worth designing the build around.

### The free experiment that replaces all of this

Two unknowns, so two runs, and **no hardware at all**:

1. Charge a battery fully, run the camera's own intervalometer at **5 s** until it dies, record
   frames and elapsed time.
2. Repeat at **30 s**.

Two equations, two unknowns, and `P_idle` and `E_frame` fall out directly — for the actual body, in
the actual mode, which is worth more than any estimate above. It costs two evenings and a battery
cycle, and it can be done before buying anything else.

## Hardware around the camera

### The recommended build — Panasonic MFT

| # | Part | Role | ≈ EUR |
|---|---|---|---|
| 1 | **Panasonic GX7**, used | body — e-shutter, built-in intervalometer | **150** |
| 2 | **7artisans / Meike 12 mm f/2.8**, native MFT | manual aperture ring: **cannot flicker** | **150** |
| 3 | **DMW-DCC11 DC coupler** | replaces DMW-BLG10, takes external ~7.4 V | 20 |
| 4 | Boost/buck to 7.4 V | from the 18650 pack | 15 |
| 5 | 2 × 18650 + sled | ~25 Wh — a sunset with margin | 20 |
| 6 | DS3231 + P-FET latch *or* Witty Pi | **the only electronics that do anything** | 15 |
| 7 | Bay charger | charge outside the box | 25 |
| 8 | 52 mm filter as the optical window | small front element, so a small window | 20 |
| 9 | IP65 case ≈ 180 × 130 × 110 mm | enclosure | 25 |
| 10 | Vent plug, desiccant, O-rings, 1/4″ inserts | sealing and mount | 25 |
| | | **total** | **≈ 465** |
| | | **…excluding lens and body** | **≈ 165** |

Against ~€175 for the Pi build, ~€350 for the UVC build, ~€470 for the Basler variant and ~€800 for
the ZWO astro build — and this is the only one of them that can actually photograph a sunset today.

**Storage is the camera's own SD card.** No microSD on the host, no fuel gauge, no boost for a Pi, no
storage code, no corruption handling.

**The optical window is small**, because a 12 mm MFT lens has a 46 mm filter thread — so a 52 mm
filter works as the window and the original enclosure thinking survives, rather than the 77 mm plate
an interchangeable-lens full-frame body would need.

### If the MCU is to do more than switch power

Optional, and only if the camera's own Av + Auto ISO ramp proves unsatisfactory:

| Part | Role | ≈ EUR |
|---|---|---|
| Optocoupler + 2.5 mm remote lead | external trigger, level 0 | 5 |
| ESP32-P4 with USB host | PTP control, level 1 | 15 |

The Panasonic remote socket is a 2.5 mm jack, so external triggering is a transistor and two wires.

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

0. **Borrow or buy a GX7 and run its own intervalometer through one real sunset**, on its own
   battery, Av with Auto ISO, before building anything at all. That answers the only question that
   matters — does the camera's own exposure ramp look acceptable — and it needs no hardware, no
   firmware and no enclosure.
1. **Measure the power** with the two-run battery experiment above. This decides the cell count and
   whether this is the best architecture here or merely a good one.
2. **Verify PTP control of the exact body** on a laptop with `gphoto2` first. Canon R-series support
   is **partial and quirky**: ISO and aperture work on the R7, `exposurecompensation` is a known open
   bug, and gphoto2 has reported shutter/aperture inconsistencies across the R line. Confirm that
   shutter and ISO can be set reliably *before* writing any firmware.
3. **Run a heat test** — sealed box, in the sun, for a full session.
4. **Then port the subset to the MCU**, using `felis/PTP_2.0`'s Canon layer as the reference.

Step 2 costs nothing and can be done this evening with the camera already owned and a USB cable.
