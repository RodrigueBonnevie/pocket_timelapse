# Pocket Timelapse Camera — the Raspberry Pi build

*The Raspberry Pi architecture — the more settled of the two. Component selection complete; build
starts when the first parts arrive. The sibling document is [UVC-BUILD.md](UVC-BUILD.md), which
keeps 4K without depending on the Pi at all.*
*Last revised: 2026-08-24*

## Context

A pocketable, battery-powered, weatherproof timelapse box you can leave on a hillside or a
rooftop and collect a day or two later. Weeks of standby, 6–12 h of shooting, field-
configurable without a laptop, scheduled starts for sunsets, ≥4K stills for crop room. No
on-device video encoding — it writes JPEGs to a big SD card and you assemble on a laptop.

Target form factor: a tight box with one waterproof button and one window for the lens — **no
external ports**, opened by hand for the SD card and to swap cells.

---

## Decision 1 — 4K forces a Linux board, not an MCU

The best camera you can hang off an ESP32-class part is a 5 MP module (OV5640 / Arducam Mega,
2592×1944) with a fixed ISP. That's below 4K *before* you crop, and weak in exactly the light
you care about most. Real 4K-with-crop-room means a 12 MP sensor and a proper ISP, which in
practice means a small Linux board.

**Chosen: Raspberry Pi Zero 2 W + Camera Module 3 (IMX708, 11.9 MP, 4608×2592, autofocus).**
Mature libcamera/picamera2 stack, 65×30 mm board, and a whole family of swappable CSI cameras
behind one connector.

To be precise about *why*: the constraint is not processing power. A single raw frame is ~15 MB,
which exceeds an MCU's entire usable RAM, and the demosaic/denoise work needs a hardware ISP that
only comes packaged inside things that run Linux. **You're buying an ISP block and enough memory
to hold a frame — the CPU is almost incidental.** See
[IMAGE-PIPELINE.md](IMAGE-PIPELINE.md) for the full walkthrough; it also explains why ~85 % of the
battery goes to keeping Linux idle between frames rather than to photography, which drives several
decisions below.

### Why not something smaller that still runs Linux

The obvious next question, and the answer is that the small low-power Linux SoCs hit **the same
wall the ESP32 hit**, one step further up.

The Rockchip RV1106 (Luckfox Pico) has a genuinely good hardware ISP — HDR, 3A, lens shading, 3D
noise reduction, sharpening, all in silicon — but it is specced as a **maximum 5-megapixel ISP**,
with 128 MB (G2) or 256 MB (G3) of integrated DDR3L. The Milk-V / SG200x family sits in the same
class. A Luckfox would give you Linux, a real ISP and about half the Pi's draw, while capping you
at 5 MP: the identical compromise the Arducam Mega forces, reached by a different route and with a
toolchain tax on top.

| Board | ISP ceiling | RAM | Idle | Verdict |
|---|---|---|---|---|
| Luckfox Pico Max / Ultra (RV1106) | **5 MP** | 128–256 MB | ~0.5 W | fails 4K |
| Milk-V Duo S (SG2000) | ~5 MP | 512 MB | ~0.5 W | fails 4K |
| Pi Zero W (BCM2835) | 12 MP | 512 MB | ~120 mA | same idle, far slower software JPEG |
| **Pi Zero 2 W (BCM2710A1)** | **12 MP** | 512 MB | 77–120 mA | **chosen** |
| Radxa Zero 3W, Pi 5 | 4K+ | 1–8 GB | 1.5–2.5 W | more capable, much thirstier |

There is a real gap in the market here: nothing tiny combines a 12 MP-class ISP with sub-watt
idle. Everything that clears 5 MP (RV1126, RK3566, BCM2712) is *more* power-hungry, not less.
**The Pi Zero 2 W is close to the floor for what this project asks.** The way to spend less energy
is therefore to tune the stack, not to shop for a smaller board — see the power-tuning checklist
in the software outline.

## Decision 2 — the Pi cannot manage its own standby

Worth testing properly, because if it worked it would remove a whole subsystem. It doesn't, for
two independent reasons:

- **A halted Pi Zero 2 W still draws 20–50 mA.** `shutdown -h` is a low-power state, not off —
  it keeps enough alive to wake on GPIO3. At ~30 mA through the boost, a 7 Ah pack is flat in
  **≈6 days**. Weeks of standby is gone before a single frame is taken.
- **The Pi Zero 2 W has no RTC.** No battery-backed clock, nothing that knows the time while
  halted, no wake-on-alarm. A halted Pi can be woken by shorting GPIO3 to ground — that's a
  button, not a schedule. `rtcwake` has nothing to talk to.

(The Pi 5 *does* have an RTC and wake-from-halt, but idles around 2.5 W. Hopeless on battery.)

What's required is not a microcontroller but **two small things: something that keeps time while
the Pi is dead, and something that physically switches the Pi's power.**

### Options considered

| Approach | Standby | Firmware | Scheduled wake | Verdict |
|---|---|---|---|---|
| Pi alone | 20–50 mA, no clock | none | **impossible** | fails outright |
| **A — Witty Pi 4 L3V7** | **~0.3 mA** on battery | none (vendor scripts) | yes, ±2 ppm | **chosen** |
| **B — DS3231 + P-FET latch** | 5–30 µA | none | yes, ±2 ppm | alternative |
| nRF52840 supervisor | ~30 µA | a whole Rust project | yes | rejected |

**Path A is the choice.** Its standby figure — ~0.3 mA on battery, ~1 mA on USB-C — resolves the
question that was gating this decision, and it resolves it in path A's favour: see "Standby" under
the power budget. Path B remains documented as the alternative for anyone who needs *months* of
unattended standby rather than weeks. Neither needs firmware.

**Rejected: the nRF52840 supervisor.** It would have added BLE arming, a fuel gauge readable
while asleep, and a hardware watchdog — but it costs an entire Rust firmware sub-project to get
there. Since you're standing next to the box when you set it up, BLE saves you only a ~20 s Pi
boot. Revisit only if you later want to check battery state without waking the box.

### Path A — Witty Pi 4 L3V7

**The key distinction from the Witty Pi 4 Mini**, and the reason this variant is the one to buy:
the Mini has **no DC/DC converter**, so it needs 5 V in and an external boost must sit in front of
it. The **L3V7** — the name is literally "Li 3.7 V" — takes the pack **directly**. Its documented
power input is *"DC 5V (via USB-C connector) or 3.7V Lithium ion/polymer battery"*, and it carries
a **DC/DC step-up converter that outputs up to 5 V/3 A** onboard, shipping with an 8 cm PH2.0 cable
for the battery. So the Pololu U3V50F5 disappears into it rather than sitting alongside.

What one 65 × 30 × 7 mm board then does — **exactly the Pi Zero footprint**, 10 g:

| | |
|---|---|
| RTC | PCF85063A, ±2 ppm, firmware temperature compensation, supercap timekeeping |
| Scheduling | on/off via vendor scripts — nothing to design, nothing to debug on a hillside |
| **Boost** | 5 V / 3 A, fed straight from the 3.7 V pack |
| Charger | 1 A — redundant given the hot-swap decision, but harmless as a fallback |
| Measurement | I²C ADC: input voltage, output voltage, **output current** |
| Price | €25.50 ex VAT, ≈ €32 inc. Swedish VAT |

The USB-C input is an *alternative* mains source, not a requirement — and since the design has no
external ports, it would only ever be reached with the box open. That does give you in-place
charging as a backup if you're ever without the bay charger.

**Standby current: ~0.3 mA on battery**, ~1 mA running from USB-C (irrelevant here — there is no
external port). That is a datasheet figure rather than a bench measurement, so Phase 3 should still
confirm it, but it is decisive: at 0.3 mA the circuit costs about as much as the cells' own
self-discharge over the timescales this device is stored for. See "Standby" below.

### The other architecture

The Raspberry Pi dependency is real and it bit in 2026, when substrate supply constraints from the
AI hardware boom left the Zero 2 W unobtainable for months. One architecture escapes it without
giving up 4K or image quality: a **UVC camera module carrying its own tuned ISP**, which removes the
need for the host to have one — and therefore for it to be a Pi.

That path has its own document: **[UVC-BUILD.md](UVC-BUILD.md)**. It shares this build's battery,
enclosure, storage and interface decisions and differs only in the host and camera — and it offers
a materially better sensor (IMX585, **+1.6 stops**) at the cost of crop room and three unresolved
measurements.

### Path B — DS3231 + P-FET latch

**Kept as a documented alternative, not the recommendation.** The dearest path (€45 all-in, once
the external boost and fuel gauge it needs are counted) and the most work, in exchange for an
advantage that only pays off over *months* of storage: roughly 10× lower standby, because the
P-FET
disconnects the boost *entirely*, so its quiescent draw drops out of the equation instead of
becoming the dominant standby load. A handful of through-hole parts and one SOT-23 FET; there's
prior art in the `pi-wake-on-rtc` project.

#### How the latch works

```
  pack ──┬─────────────[ P-FET ]──── boost 5V ──── Pi + camera
         │                 │gate
         │              100k pull-up (off by default)
         │                 │
         │            ┌────┴────┐
         └─ DS3231 ───┤  pulls  │◄── button (RC hold)
            INT (OD)  │  gate   │◄── Pi GPIO "hold me on"
            Vbat      │   low   │
                      └─────────┘
```

1. Pi writes an alarm time to the DS3231 over I²C, then halts.
2. At alarm time `INT` goes low → P-FET conducts → Pi boots. The DS3231's alarm flag **latches
   low until cleared over I²C**, so it holds power across the whole boot with no timing circuit.
3. Booted Pi drives its hold-GPIO, then clears the alarm flag.
4. At end of shutdown `dtoverlay=gpio-poweroff` releases that GPIO → latch drops → power gone.

**Two things that bite people here:**

- **`BBSQW` must be set to 1.** By default the DS3231 disables its `INT/SQW` output when running
  on backup power — i.e. the alarm pin is dead exactly when you need it to fire. The single most
  common failure in this circuit.
- **No watchdog in the failure path.** If the Pi hangs mid-session it never releases the latch
  and the pack drains to the BMS cutoff — you lose a charge cycle, not hardware. Mitigate with
  the Pi's hardware watchdog (`dtparam=watchdog=on` + systemd `WatchdogSec`), which reboots a
  hung Pi into a state that can decide to halt properly. (Path A has the same exposure; the
  Witty Pi can be given a scheduled hard cut-off as a backstop.)

### Choosing between them

Both paths present the Pi with the same interface — an I²C clock to write an alarm to, and a
GPIO handshake at shutdown — so **the capture software is identical either way** and the choice
is genuinely deferrable. Start on path A to get a working device sooner; move to path B if the
measured boost quiescent dominates standby. Buying both costs about €49 and keeps the decision
open.

**This is now decided: path A.** It is €15 cheaper all-in, one 65×30 mm board instead of three
parts, gives voltage *and* current for free, and handles low-voltage shutdown and recovery in
firmware. Its ~0.3 mA standby costs about the same as the cells' own self-discharge over a month,
so path B's 10× advantage buys nothing at the timescale this device is stored for.

**Build path B only if the requirement changes to months of unattended standby** — for example a
box left out through a season, or solar operation where the pack must survive a long dark spell.
The circuit and its `BBSQW` trap are documented above so that remains a live option.

## Decision 3 — field configuration

Button → Pi boots (~20 s) → raises its own WiFi AP for 5 minutes → phone browser gets a full
settings page (interval, duration, start time, exposure caps, live preview frame) → confirm →
Pi writes the wake alarm and halts. Works identically on iOS and Android, which BLE-from-a-web-
page does not (**iOS has no Web Bluetooth**).

## Decision 4 — no display in the box

A display sealed inside an opaque box needs a **second window** to be useful, and every window
is another seal to fail, another surface to fog, and a hole to align a PCB behind. That's real
enclosure complexity bought for information the web page already presents better.

**Chosen instead: an illuminated waterproof pushbutton** — 16 mm vandal-resistant, IP65, LED
ring. One hole serving as both input and status indicator, which is what the target form factor
wants anyway.

| Signal | Meaning |
|---|---|
| dark | asleep, waiting for its alarm |
| solid, dim | booting |
| slow pulse | AP up, waiting for configuration |
| single flash per frame | shooting — shows both liveness and the interval |
| amber | battery low |
| red | error, card full |

Two caveats. The LED can only be driven while the Pi is awake, so "armed and sleeping" reads as
dark — correct behaviour, and better for stealth. And **mount the button on a different face
from the lens**, or the flash will bounce off the inside of the window at night.

One button is sufficient if actions are separated by press duration: short = status, long =
raise AP, very long = abort and halt. A second button is a couple of euros if an unambiguous
abort feels better in the field.

**No OLED anywhere, not even on the bench.** A display would require writing display code before
it could help you debug, which is backwards, and it shows less than a terminal does. Bench
visibility comes over the wire instead — see "Bench debugging" below.

---

## Bill of materials

| # | Part | Role | ≈ EUR |
|---|---|---|---|
| 1 | Raspberry Pi Zero 2 W | capture computer | 20 |
| 2 | Raspberry Pi Camera Module 3 (standard, 75° D) | IMX708, 11.9 MP, 4608×2592, AF | 30 |
| 3 | 22-pin → 15-pin FFC cable | Zero uses the narrow connector — easy to forget | 5 |
| 4 | 128 GB A2 microSD (Samsung Pro Plus / SanDisk Extreme) | OS + frames | 15 |
| 5 | 2 × **protected** 18650 (Samsung 35E / LG MJ1) + quality hot-swap holder | 7.0 Ah / 25.9 Wh | 22 |
| 6 | 16 mm IP65 illuminated pushbutton + driver transistor | input and status in one hole | 10 |
| 7 | IP65 box, ≈120×80×55 mm (Hammond 1554) — or 3D printed | enclosure, designed to open | 18 |
| 8 | 37 mm screw-in UV filter + O-ring + adhesive | optical window | 12 |
| 9 | PTFE vent plug (M12) + silica gel sachets | condensation control | 8 |
| 10 | 1/4"-20 threaded inserts | tripod / clamp mount | 5 |
| | | **subtotal** | **≈ 145** |

**The 3.7 V → 5 V boost is no longer a shared item.** Path A's board has one onboard; path B needs
an external one. Each path therefore carries its own power control, boost and battery measurement:

| Path | Power control + boost | Battery measurement | Path total | **Grand total** |
|---|---|---|---|---|
| **A** | **Witty Pi 4 L3V7** — RTC, power control, **onboard 5 V/3 A boost**, charger, 65×30×7 mm — €30 | **included** (I²C ADC) | €30 | **≈ €175** |
| **A′** | Witty Pi 4 Mini (€22) + Pololu U3V50F5 boost (€18) — fallback if the L3V7 is unavailable | **included** (I²C ADC) | €40 | ≈ €185 |
| **B** | DS3231 + AO3401A P-FET, passives, protoboard (€15) + Pololu U3V50F5 boost (€18) | MAX17048 breakout — €12 | €45 | **≈ €190** |

**Path A is now both the cheapest and by far the simplest** — one 65×30 mm board carrying the RTC,
the power switching, the boost, a charger and the voltage/current ADC, against three separate parts
on path B. Its one remaining unknown is standby current, which is the same measurement that already
gates this decision.

Buying path A and path B together is ~€75 and keeps the decision open. Buying A′ as well is
pointless unless the L3V7 turns out to be unobtainable.

The enclosure is priced as a commercial IP65 box to keep the build cost holistic; **a 3D printed
case is the likely route**, in which case that €18 becomes filament and the design constraints
below still apply.

### Accessories — outside the box, reusable

| Item | Role | ≈ EUR |
|---|---|---|
| 4-bay 18650 charger (Nitecore / XTAR) | charges cells at ~2 A each, ~2 h | 25 |
| Spare set of 2 protected 18650s | a second set is a second full session | 22 |
| USB power meter | **not optional** — you cannot size a battery from datasheets | 15 |
| USB-UART adapter (CP2102/FTDI), **optional** | early boot and kernel-panic visibility | 5 |

### Bench debugging — over the wire, not a screen

Through Phases 1–4 the device sits on a bench next to a laptop, so debugging goes over a wire.
No display is needed, and adding one would mean writing display code before it could help.

| Approach | Cost | Shows you |
|---|---|---|
| **SSH over WiFi** | free | everything — `journalctl -f`, a real shell |
| **USB gadget (`g_ether`)** | free, one cable | the same, with no WiFi dependency at all |
| USB-UART on GPIO 14/15 | €5 | **early boot and kernel panics**, which SSH cannot reach |

USB gadget mode is the neat one: the Zero 2 W's micro-USB OTG port supports it, so
`dtoverlay=dwc2` in `config.txt` plus `modules-load=dwc2,g_ether` in `cmdline.txt` gives a network
interface over a single cable to the laptop — nothing to buy, nothing to solder.

> **Trap worth remembering: the OTG port can back-power the Pi**, so USB debugging and power
> measurement are mutually exclusive. Any current reading taken with a laptop cable attached is
> meaningless. Use SSH-over-WiFi whenever the meter is connected, and USB gadget when it isn't.

The UART adapter is genuinely optional — a stock Raspberry Pi OS image rarely needs early-boot
visibility — but at €5 it is strictly more useful than a display would have been.

### Power in — hot-swap cells, charged externally

**There is no charger on the board, deliberately.** The box must be opened to retrieve the SD card
anyway, so cells come out and charge in an external bay charger. That deletes the on-board charging
circuit, deletes the load-sharing problem, and charges *faster* — a bay charger runs ~2 A per cell
in about 2 h, against 8–9 h for a 1 A on-board charger feeding 7 Ah. (For the record: the TP4056
that used to sit in this slot is a **1 A** part. There is no 2 A variant of that chip, only lower
settings via `RPROG`.)

The real gain is that **spare cells convert directly into runtime.** A second matched set in your
bag is a second full session with no waiting.

**No live swapping is needed.** Power down, swap, power up — the RTC keeps time and schedule on its
own backup (supercap on the Witty Pi, CR2032 on the DS3231), so removing every cell doesn't lose
the wake alarm.

Four things this makes your responsibility:

- **Protected cells are now mandatory.** Pack protection previously came from the DW01 on the
  charge module. Without it, use protected button-top cells (~69–70 mm, so size holders for the
  extra ~4 mm) or fit a small 1S BMS. Loose cells handled, pocketed and dropped in bags are exactly
  the case protection exists for.
- **Swap as a matched set, never one cell.** Cells in parallel equalise through each other, and
  inserting a full cell beside a depleted one drives a large current directly between them, limited
  only by their internal resistance. Keep sets of the same chemistry, capacity and age, label them,
  and rotate them together.
- **The holder is now reliability-critical** — it is the only path between the cells and the Pi.
  Buy a good one with proper spring contacts and retention, or design retention into the printed
  sled. Cheap holders lose contact under vibration, and a dropout ends the session.
- **Refresh the desiccant at each swap**, since every opening admits humid air.

#### How many cells?

Electrically there's no meaningful limit. Cells sit in parallel at 1S, so adding them raises
capacity and lowers internal resistance without changing voltage, and the boost's input current is
unaffected. The limits are physical and procedural. With protected cells (~80 mm holders) against a
115 × 75 × 50 mm interior:

| Cells | Holder footprint | Fits? |
|---|---|---|
| 2 | ~76 × 40 mm | comfortably — **the design point** |
| 3 in a row | ~76 × 60 mm | yes, snug |
| 4 in a row | ~76 × 80 mm | **no** — exceeds the 75 mm width |
| 4 as 2×2 | ~76 × 40 × 42 mm | footprint fits, but 42 of 50 mm height leaves nothing for the Pi |

**Three is the practical ceiling in this box**; four needs a larger or taller one — which a printed
case makes easy to arrange if you want it.

One systems interaction to remember: **more battery re-opens the storage question.** At 4 cells
(14 Ah) a 2 s interval runs 45 h and writes 178 GB at q80 — over a 128 GB card. The adaptive
quality rule degrades gracefully rather than failing mid-session, but if you commit to 3–4 cells,
revisit the card size deliberately.

### Battery measurement — and why it can't live on the Pi

**The Raspberry Pi has no ADC.** Not a limited one — none at all, on any model. There is no analog
input on the SoC, so a voltage divider cannot be read from the board. This isn't a case of the
software being messy; the hardware simply isn't there. Any battery reading needs an external chip.

And one is genuinely needed — this is not a development-only part. The web UI reports charge, and more importantly the device has to answer *"is there enough left to finish a
six-hour session?"* before you walk away from it.

**On path A it comes free.** The Witty Pi's MCU has an ADC and exposes readings over I²C at
address `0x08`:

| Register | Reading |
|---|---|
| `0x01`–`0x02` | input voltage |
| `0x03`–`0x04` | output voltage |
| `0x05`–`0x06` | **output current** |

That is strictly more than a fuel gauge gives you. Output current in particular suits this project
better than a percentage would: the real question is hours-to-completion, and
`remaining Wh ÷ measured W` answers it directly once Phase 0 has characterised the draw.

**On path B you need to add something,** because the DS3231 has no ADC either:

- **MAX17048 (~€12)** — worth its price for two specific reasons. The Li-ion discharge curve is
  flat, roughly 3.6–3.8 V across most of the usable capacity, so voltage alone is a poor charge
  estimate and the chip runs a battery model to compensate. It also stays on the pack at 3 µA and
  keeps modelling while the Pi is off, so a freshly woken box knows its state immediately instead
  of re-converging.
- **ADS1115 + resistor divider (~€4)** — raw voltage, and you write the discharge curve yourself.
  Perfectly adequate given you'll know your average draw from Phase 0.

### Camera swap options (all share the CSI connector)

| Module | Sensor | Why | Caveat |
|---|---|---|---|
| **Cam Module 3** | IMX708, 1/2.43", 11.9 MP | default; autofocus, good outdoor DR | — |
| Cam Module 3 Wide | IMX708, 120° D | vistas, big-sky sunsets | more distortion, softer corners |
| HQ Camera IMX477 + 6/16 mm CS lens | 1/2.3", 12.3 MP | best quality; fixed manual focus & aperture is an *advantage* for timelapse | ~38 mm cube + lens — breaks "pocketable" |
| Arducam Owlsight OV64A40 | 1/1.32", 64 MP | biggest sensor in a small module | **verify first** — the Zero 2 W's 512 MB RAM reportedly can't reach full resolution |

Buy the standard Module 3 first. The swap path exists; don't spend it on day one.

**Considering a bigger sensor, or a different host?** [SENSORS.md](SENSORS.md) surveys the IMX
range, explains why Sony sensors carry no ISP, and sets out what ISP **tuning** is — the real
reason this design keeps returning to the Raspberry Pi. Untuned, an ISP doesn't just produce poor
colour; the 3A loop stops working entirely, which would break exposure ramping. Raspberry Pi are
close to the only vendor shipping open, tooled, validated tuning for cheap sensors. It also makes
the case that a locked-off timelapse recovers much of a large sensor's advantage through exposure
time alone. Short version:
the IMX477 HQ Camera is the one sensible upgrade, and its value is the **C/CS lens mount** rather
than the +0.3 stops of sensor area — everything larger leaves the Raspberry Pi ecosystem and takes
the battery budget with it.

---

## Power budget

### Shooting

| | |
|---|---|
| Pi Zero 2 W idle, stock headless | ~115–144 mA @ 5 V = 0.58–0.72 W |
| Pi Zero 2 W idle, **tuned** (see checklist) | **~77 mA @ 5 V = 0.39 W** |
| Pi + Cam Module 3, capture loop, peak | ~250–300 mA @ 5 V = 1.25–1.50 W |
| **Design point (time-averaged, untuned)** | **1.1 W at the 5 V rail** |
| 12 h session | 13.2 Wh at the rail |
| ÷ 88 % boost efficiency | 15.0 Wh from the cells |
| at 3.7 V nominal | 4.05 Ah |
| +25 % derate (cold, ageing, don't run flat) | **≈ 5.4 Ah needed** |

2 × 3500 mAh gives **7.0 Ah / 25.9 Wh** → roughly **20 h at 20 °C, ~14 h at 0 °C** on the untuned
design point. Comfortable against the 12 h target, which you want because Li-ion loses real
capacity in the cold. Never charge the pack below 0 °C — if it comes home frozen, let it warm first.

**Tuned, that becomes ~27 h at 20 °C and ~19 h at 0 °C.** Since idle dominates, a 33 % cut to the
idle floor is about a 28 % cut to total draw — which buys back the entire cold-weather derate for
free. Read the other way: tuning is what would let a *smaller* pack still clear 12 h, if you later
want the box slimmer. Treat the untuned figures as the design point and the tuned figures as
headroom, until Phase 1 measures the real numbers.

### Active — where the energy goes during a session

The shooting figures above are a single time-averaged number. Decomposing one capture cycle at
interval **T** is more useful, because it shows which lever is worth pulling.

| Component | What it is | Estimate |
|---|---|---|
| `P_base` | tuned Pi idle, camera not initialised | **0.39 W** |
| `P_cam` | camera pipeline **streaming** | **~0.5 W** ← the big unknown |
| `E_readout` | sensor readout + ISP, one frame | ~0.1 J |
| `E_encode` | software JPEG at 12 MP | ~0.5 J |
| `E_write` | 4 MB to SD + fsync | ~0.05 J |

**The item that is easy to miss: a naive picamera2 loop leaves the sensor streaming the whole
time.** You `start()` once and call `capture_file()` in a loop, and between frames the camera keeps
running — roughly 0.5 W burning continuously, comparable to the entire tuned idle floor. The
session floor is therefore not `P_base` but `P_base + P_cam`, and the actual photography is a
rounding error beside it:

| At a 5 s interval, camera left streaming | Energy per frame | Share |
|---|---|---|
| Camera streaming | 2.50 J | **48 %** |
| Pi base idle | 1.95 J | 37 % |
| JPEG encode | 0.50 J | 10 % |
| Readout + SD write | 0.15 J | 3 % |

#### Stopping the camera between frames

Because exposure is locked by design (see `camera.py`), restarting costs no AE/AWB convergence —
the usual objection to `stop()`/`start()` around each capture doesn't apply here. Modelling ~1 s of
camera-on time per frame:

| Interval | Streaming | Stopped | Saving | Runtime on 25.9 Wh |
|---|---|---|---|---|
| 2 s | 1.27 W | 1.02 W | 20 % | 18 h → 22 h |
| 5 s | 1.04 W | 0.64 W | **38 %** | 22 h → **36 h** |
| 15 s | 0.94 W | 0.47 W | **50 %** | 24 h → **48 h** |
| 30 s | 0.92 W | 0.43 W | **53 %** | 25 h → **53 h** |

**This is a bigger lever than every `config.txt` change combined, and it's pure software.** The
saving scales with interval because streaming cost is proportional to `T` while capture work is
fixed — the longer the wait between frames, the more of what you're paying for is a sensor doing
nothing.

> **Every figure in this subsection is provisional.** `P_cam` is inferred from a "Pi Zero W +
> Camera Module 3 never exceeds 300 mA" measurement minus idle, not measured directly. At 0.25 W
> the savings roughly halve; at 0.7 W they grow. The whole table swings on that one number.
> Calibrate before designing around it.

#### One counterintuitive tuning note

For the encode phase specifically, use the **`performance` governor, not `powersave`.** Race-to-idle
wins on a Pi: static power is paid for the whole duration, so finishing an encode in 0.4 s at full
clock generally costs less total energy than 0.9 s at reduced clock. The governor advice that helps
during idle is backwards during a capture burst.

#### Calibration protocol — about two hours of bench work

| # | Measure | How |
|---|---|---|
| 1 | `P_base` | Tuned, headless, camera never initialised; 5 min average |
| 2 | `P_cam` | Same, with picamera2 started and streaming but *not* capturing. Subtract #1 |
| 3 | `E_capture` | 100 captures at a long interval; total Wh minus baseline, ÷ 100 |
| 4 | `t_encode` | Time `capture_file()` against `capture_array()` to separate encode from readout |
| 5 | `t_startup` | `start()` → first valid frame |
| 6 | Whole session | 1 h at the real interval, both modes, back to back |

Six numbers, and the model above becomes predictive instead of indicative.

### Standby

| | Path A (L3V7) | Path B (latch) |
|---|---|---|
| Whole board, RTC + boost + control | **~0.3 mA** (datasheet) | — |
| RTC on backup, `BBSQW` set | — | 1–3 µA |
| Boost converter | included above | 0 — fully disconnected |
| P-FET off + gate network | — | <1 µA |
| Pack protection IC | ~5 µA | ~5 µA |
| MAX17048 hibernate | — (measurement is onboard) | 3 µA |
| **total** | **≈ 0.3 mA** | **≈ 10–30 µA** |
| **7 Ah pack, in theory** | **2.7 years** | >20 years |

Theoretical life is the wrong comparison, though, because **neither is limited by the circuit —
both are limited by the cells.** Set the two against Li-ion's own ~2.5 %/month self-discharge:

| Stored for | Path A drain | Path B drain | Self-discharge | **Pack remaining, A vs B** |
|---|---|---|---|---|
| 1 week | 0.7 % | 0.07 % | 0.6 % | 98.7 % vs 99.3 % |
| **1 month** | **3.1 %** | **0.3 %** | **2.5 %** | **94 % vs 97 %** |
| 6 months | 18.5 % | 1.9 % | ~14 % | 68 % vs 84 % |

**At the "weeks of standby" the requirement asks for, path A's circuit costs about the same as the
cells leaking on their own.** Three percentage points after a month is roughly 40 minutes of
runtime — irrelevant. Path B's 10× advantage only becomes material over *months* of unattended
storage, and a pack would be topped up before a trip anyway.

That is what settles the path decision: **path A is cheaper, smaller and simpler, and its only
disadvantage doesn't bite at the timescale this device is actually used over.**

Either way, contrast both with the halted-Pi figure of **six days** — the value of switching the
rail rather than relying on `shutdown -h` is what both paths exist to provide.

### Over-discharge — three layers, and only one of them is any use

A natural assumption is that the cells' protection circuits handle running flat. They don't, or
at least not in the way that matters. Note the ordering:

| Layer | Trips at | What it actually does |
|---|---|---|
| **Firmware / software graceful shutdown** | **3.1 V** (L3V7 default, settable 3.0–4.2 V) | clean halt, filesystem intact, cycle life preserved |
| Boost converter input cutoff | ~2.9 V (U3V50F5 minimum input) | nothing useful — it simply stops |
| Cell protection PCB | ~2.5 V | prevents cell damage |

**The boost quits at 2.9 V, above the protection threshold at 2.5 V.** So in normal operation the
cell protection never activates — the boost dies first and the Pi loses power abruptly. Protection
exists for shorts and faults, not for routine over-discharge.

Graceful shutdown is therefore required regardless of path, for two reasons beyond cell chemistry:
running to the cutoff every time is an **unclean shutdown every time** (survivable thanks to atomic
writes, but that's the safety net, not the plan), and repeatedly discharging to 2.5 V instead of
stopping at ~3.1 V measurably shortens Li-ion cycle life.

**Path A gets this in firmware.** Below the low-voltage threshold it emulates a button click, the
Pi shuts down gracefully, and it then cuts power. A separate **recovery voltage threshold** stops
it restarting until the voltage comes back up.

**Path B must implement both halves in software.** The trigger is easy — the MAX17048 has an alert
output with a configurable threshold. The second half is the subtle one:

> If the Pi halts on low battery but the DS3231 alarm still stands, it wakes at the next scheduled
> time, boots onto a flat pack, discovers low battery and halts again — **repeating until the cells
> reach the protection cutoff**, burning boot energy each cycle. Path B must clear the alarm or set
> a far-future one when halting for low battery, because it has no firmware recovery threshold to
> fall back on.

Voltage sag is not a complication here: two 18650s in parallel present ~25 mΩ, so a 0.35 A draw
sags roughly 9 mV. Thresholds can be set against the resting curve without correction.

### Interval, storage, and how long the film actually is

At 4608×2592 JPEG q90 ≈ 4 MB/frame:

Only one row applies at a time — this is a menu of choices, not a total.

**Sizing principle: the card is emptied at every recharge, and the battery binds within a charge.**
So the card only ever needs to hold **one full charge's worth of frames** at the shortest interval
you'd realistically use. It is not accumulating across deployments.

Frames on one full charge, using the tuned camera-stopped model (`P = 0.39 + 1.25/T`):

| Interval | Runtime | Frames | Video @ 24 fps | at q80 (~2.2 MB) | at q90 (~4 MB) |
|---|---|---|---|---|---|
| 2 s | 22.5 h | 40,500 | 28 min | **89 GB** | 162 GB |
| 5 s | 35.6 h | 25,600 | 18 min | 56 GB | 103 GB |
| 10 s | 44.3 h | 15,950 | 11 min | 35 GB | 64 GB |
| 30 s | 52.8 h | 6,340 | 4.4 min | 14 GB | 25 GB |
| 60 s | 55.5 h | 3,330 | 2.3 min | 7.3 GB | 13 GB |

**128 GB covers every case at q80**, including the pathological one — a 22-hour continuous 2-second
timelapse. At q90 the same case needs 162 GB, and if frames run to 8 MB on a detailed daylight
cityscape it would exceed even a 256 GB card. **Hence q80 as the default and a 128 GB card**
(item 4), saving €10 and removing the failure mode rather than buying around it.

**Adaptive quality.** The device knows the interval and planned duration at arm time, so
`storage.py` should compute the budget and pick quality to fit:

```
expected_frames = duration / interval
choose highest q such that expected_frames × size(q) < free_space × 0.9
```

Short sessions get q90 and the extra margin; long ones drop to q80 and still complete. If even q80
doesn't fit, the config page should say so and propose a longer interval rather than filling the
card mid-session. Show the estimate at arm time — *"8,640 frames, ~19 GB, fits"* — so the decision
is visible before you walk away. This needs an empirical **size-versus-quality curve from Phase 0**.

On whether q80 is visible: at 24 fps each frame is on screen for 42 ms, and a 12 MP frame is being
downscaled to a 4K output, so blocking is essentially invisible in motion. **One caveat worth
knowing:** artifacts can surface *after* grading, because deflickering and exposure correction
stretch tonal values — and a smooth sunset sky gradient is the worst case for JPEG blocking. If a
session is destined for heavy grading, q90 buys margin. That is precisely what the adaptive rule
should hand you when the budget allows.

Worth internalising early: **a 12 h night at 10 s is three minutes of footage.** Most sunset
sequences want 2–5 s.

### Rejected: encoding video on-device

Tempting, because the desired output is a video and stills are 13× larger than H.264 would be. It
doesn't survive contact with the details.

**The hardware encoder can't do it.** The Zero 2 W's VideoCore IV tops out at **1080p30** H.264 —
4K would have to be encoded in software, which is exactly the CPU cost the design avoids.

| At a 5 s interval | JPEG | On-the-fly software H.264 |
|---|---|---|
| Energy per frame | 3.20 J | ~3.95 J |
| Average power | 0.64 W | ~0.79 W |
| Runtime | 36 h | **~29 h** |
| Storage per frame | 4 MB | ~0.3 MB |

So the power math roughly works — a 15–20 % runtime cost, not a catastrophe — and it would allow a
32 GB card, **saving about €17**. Encoding at the *end* of a session is strictly worse: 8,640
frames at ~1.5 fps is 1.6 h of full-CPU work costing ~3 Wh, **13 % of the pack**, plus 1.6 h of
dead time, for a job that takes five minutes on a laptop.

**The disqualifier isn't power, it's the workflow.** Inter-frame compression makes deflickering
impossible — residual flicker is baked into the pixels and motion estimation smears it between
frames — and it removes cropping, which is the stated reason for shooting 4K at all. No re-grading,
no re-timing, no dropping bad frames. A power cut can also lose the whole file rather than one
frame. €17 on a €190 build is not worth losing every downstream option on footage you can't
reshoot.

*If crop room ever stops mattering,* capturing at 3840×2160 instead of 4608×2592 is another 30 % off
both storage and encode energy — but that spends the requirement, so it's a separate decision.

A nuance on interval vs power: power-cycling per frame costs ~15–20 s of boot (~30 J) versus
~36 J to idle through a 60 s gap — break-even around a 1 minute interval. Below that, keep the
Pi awake. Above it the saving is real, but per-frame SD power cycling is a corruption risk not
worth the milliwatts. **Keep the Pi awake for the whole session; the latch's job is between
sessions.**

Note this cuts *with* the tuning work rather than against it: a tuned idle of 0.39 W makes 60 s of
idling cost ~23 J, pushing break-even out to roughly **78 s**. Cheaper idling makes per-frame power
cycling *less* attractive, so the decision to stay awake through a session gets stronger as the
stack gets leaner.

### Extending runtime, ranked by value

The design already clears the 6–12 h requirement. If you want more, these are the levers in order
of return.

**1. Multiple scheduled windows instead of one long session.** The one worth building, and nearly
free — the RTC already supports it. A sunset doesn't need twelve continuous hours; it needs ninety
minutes. Shoot 05:30–07:00 and 20:00–21:30 with a **hard power-cut between them**, and a 25.9 Wh
pack covers **about a week of dawn-and-dusk sequences** rather than one long day. For cityscape and
sunset work this multiplies useful deployment time far more than any efficiency tuning can. It
needs `scheduler.py` to hold a list of windows rather than a single start time, and the wake alarm
to be rewritten at the end of each window.

**2. Stop the camera between frames.** Covered above — 38–53 % depending on interval, pure
software, pending calibration.

**3. A third cell.** 3 × 18650 → 10.5 Ah / 38.9 Wh, +50 % runtime for about 50 g. The dullest
option and the most reliable.

**4. Solar.** A 5–6 W panel could harvest 15–25 Wh/day in Swedish summer — genuinely indefinite
operation. Two problems: a panel fights the unobtrusive-pocket-box goal, and at this latitude it's
useless from roughly November to February.

**5. Adaptive interval.** Stretch the interval when the scene isn't changing. Saves frames and
storage more than power, given the floor dominates.

---

## Enclosure

- **Optical window: a screw-in 37 mm UV filter**, not cut acrylic. Flat, coated, cleanable,
  replaceable when scratched, and already round. Bond it over the hole with an O-ring.
- Lens as close to the glass as possible with a **black felt collar** in the gap — otherwise
  internal reflections ghost across any bright sky.
- **One window only.** The illuminated button is the status indicator (Decision 4), so there's
  no second aperture to seal.
- **Silica gel inside plus a PTFE vent plug.** A sealed box that goes out warm and cools
  overnight fogs its window from the inside, and you only find out on the footage.
- 1/4"-20 insert in the base. In practice a **clamp beats a tripod** for leaving something
  somewhere — a tripod is conspicuous, blows over, and invites theft.

### Design it to be opened, not to stay shut

**No external ports at all** — no charging socket, no USB, no SD slot through the wall. One window,
one button, nothing else.

This is a positive choice rather than a compromise. Retrieving the SD card already requires opening
the box, so **opening is the normal service action, not an exceptional event.** Adding a sealed
port to avoid it would mean designing and maintaining a second sealing interface to save a step you
still have to perform. Every hole is a leak path; the cheapest hole is the one that isn't there.

Since it will be opened routinely — after every session for the card, and at every swap for the
cells — design accordingly:

- **Captive fasteners or latches**, not loose screws you'll drop in wet grass at dusk.
- **A silicone O-ring or gasket seated in a machined or printed channel**, not adhesive foam tape.
  A gasket in a groove survives hundreds of cycles; stuck-on foam degrades and shifts within a
  handful.
- **A lid that can only go on one way** — an asymmetric bolt pattern or a locating pin. Every
  reassembly happens in the field, often in poor light and a hurry.
- **Desiccant that's easy to reach and replace**, because each opening admits humid air.
- Prefer a lid that opens **away from the lens window**, so the optical surface isn't handled or
  set face-down during a swap.

A 3D printed case makes all of this easier to arrange than a commercial box — captive-nut pockets,
a proper gasket groove, a cell sled with retention, and a lens hood can all be printed in.

---

## Software outline (not yet started)

Python + picamera2 on the Pi, no firmware anywhere else.

- `camera.py` — locks everything automatic: `AeEnable=False`, `AwbEnable=False`, explicit
  `ColourGains`, fixed `LensPosition`. Autofocus hunting between frames ruins a sequence. Because
  those are locked, `stop()`/`start()` around each capture costs no reconvergence — make streaming
  vs stopped a **config flag**, so the calibration run can measure both.
- `scheduler.py` — **monotonic deadlines, not `sleep(interval)`**, or capture time accumulates
  as drift. Skip a late frame rather than catching up. Model a session as a **list of windows**,
  not a single start/stop — see "Extending runtime"; multi-window scheduling with a power-cut
  between windows is the highest-value runtime extension available.
- `ramp.py` — a sunset spans ~10 stops; naive per-frame auto-exposure strobes. Measure mean
  luma, correct by a **capped step of ≤1/6 stop per frame**. Shutter first up to a motion-blur
  cap (~1/25 s), then gain.
- `storage.py` — write `NNNNNN.jpg.tmp`, fsync, rename, fsync the directory. Power loss costs at
  most one frame. Log `ExposureTime`/`AnalogueGain`/lux per frame to `frames.csv`. Also owns the
  **storage budget**: at arm time, pick JPEG quality so the planned session fits the free space
  (see "Interval, storage…"), and surface the estimate on the config page.
- `rtc.py` — set the wake alarm and clear the flag on boot. Keep behind a small interface with
  one implementation per power-control path (`WittyPiClock` / `Ds3231Clock`), so switching
  between them is a config change rather than a rewrite.
- `status.py` — button press durations and LED blink codes.
- `web.py` — FastAPI settings page, served only while the AP is up.
- Read-only root via overlayfs, frames on a separate ext4 data partition.
- Trim boot: disable `NetworkManager-wait-online`, `ModemManager`, `avahi`, `triggerhappy`, Pi
  Bluetooth, swap. Target ~15–20 s to first frame.
- Laptop side: `ffmpeg` with `deflicker=mode=pm:size=10`, driven by `frames.csv`.

### Power-tuning checklist

Because idle is ~85 % of consumption, tuning the stack is the single highest-leverage software
work in the project. Published measurements take a headless Zero 2 W from **120–144 mA down to
74–100 mA** — one report reaching **77 mA with WiFi still enabled**. That's roughly a **third off
the idle floor** and about **28 % off total draw**.

| Change | Measured saving |
|---|---|
| Disable HDMI output | 17–30 mA |
| Remove the `vc4-kms-v3d` driver | 16–17 mA |
| Disable composite/TV out | 16–17 mA |
| Disable ACT and power LEDs | 2–5 mA |

Roughly, in `config.txt`: comment out `dtoverlay=vc4-kms-v3d`, disable TV out, `dtoverlay=disable-bt`,
`dtparam=audio=off`, `dtparam=act_led_trigger=none`, `disable_splash=1`, `boot_delay=0`. Then on the
systemd side, disable `bluetooth`, `ModemManager`, `avahi-daemon`, `triggerhappy` and
`dphys-swapfile`, mask `NetworkManager-wait-online`, set journald `Storage=volatile`, and mount
with `noatime`.

> **Verify these against the OS release you actually install.** Parameter names have shifted across
> Bullseye → Bookworm → Trixie, especially around KMS and display. Apply them **one at a time with
> the USB meter attached** and record the delta — a flag that silently does nothing is worse than
> no flag, because you'll budget for a saving you never got.

#### Disabling cores — potentially the largest lever, and the one with a real trade-off

Jeff Geerling reports **halving the Zero 2 W's idle power by disabling cores** (`maxcpus=` on the
kernel command line). If that holds, it is worth more than every `config.txt` change above
combined, because idle is ~85 % of total consumption.

**But it cuts directly against race-to-idle.** The stills JPEG encoder is multithreaded, so fewer
cores means a longer encode — more time at higher power, and a higher floor on the shortest
sustainable interval. The two effects pull in opposite directions:

| | 4 cores | 1–2 cores |
|---|---|---|
| Idle floor | baseline | **~half** |
| JPEG encode time | baseline | longer, roughly inversely with core count |
| Net effect | — | **unknown — measure it** |

Given how lopsided the idle/active split is, fewer cores may still win comfortably. But this is
exactly the kind of assumption that needs measuring both ways rather than reasoning about: run the
same session at `maxcpus=1`, `2` and `4`, and compare **Wh per frame**, not idle current alone.
Idle current alone will flatter the low-core case and hide the encode penalty.

Three more, not in the published lists:

- **`rfkill block wifi` outside the AP window.** The 77 mA figure was measured *with* the radio up.
  This device needs WiFi for five minutes at configuration time and never again during a session.
- **Stop the camera pipeline between frames.** The sensor and ISP draw current whenever streaming;
  at a 30 s interval you're powering them for 30 s to use half a second. The usual objection is
  that restarting costs AE/AWB convergence — but **exposure is locked here by design**, so that
  cost doesn't apply. Project-specific, unmeasured, and probably the most promising lever left.
- **Journald to tmpfs and `noatime`** stop background SD writes waking things up. Small, free.

**What doesn't exist:** the Pi has **no suspend-to-RAM.** There's no S3 state on BCM2710 — the only
options are idle and halted. That's why the idle floor is a floor you can lower but never sleep
through, and why cutting the rail between sessions needs the RTC hardware rather than a software
fix.

---

## Suggested order of work

**Phase 0 — bench truth, before buying anything else.** Items 1–4 plus a USB power meter. Run
off a power bank on a windowsill, shoot a real sunset-to-night with a throwaway `rpicam-still`
loop, assemble with ffmpeg. *Exit:* you like the image quality, and you have measured Wh/hour,
real file sizes at **q80 and q90 both** (the size-versus-quality curve the adaptive rule needs),
and **full-resolution JPEG encode time**. Every number above is an estimate until
this replaces it. If the IMX708 disappoints, the thing to reconsider is the camera module — not
the architecture.

Encode time matters more than it looks: picamera2 encodes stills **in software**, so at 12 MP on a
1 GHz A53 it's likely the longest single step in a capture and sets the floor on the shortest
interval the device can sustain. See [IMAGE-PIPELINE.md](IMAGE-PIPELINE.md) §3.

**Phase 1 — capture app, and power tuning.** Interval accuracy, locked exposure, atomic writes,
metadata log. Then work the power-tuning checklist with the USB meter attached, one change at a
time, recording each delta — this is worth ~28 % of total draw and is cheaper than any hardware
change available to you.

**Phase 2 — exposure ramping.** Separate because it decides whether sunsets look good.

**Phase 3 — power control.** Confirm the **L3V7's ~0.3 mA standby** on the bench, then set the
low-voltage and recovery thresholds and prove them by running a session to empty. Bring up whichever you choose (path A: vendor scripts plus a scheduled cut-off backstop;
path B: breadboard, verify `BBSQW`, then protoboard). Either way, verify the `gpio-poweroff`
handshake and finish with 50 forced power-cuts mid-capture, requiring a clean card mount every
time.

**Phase 4 — AP config page, button, and blink codes.**

**Phase 5 — enclosure and an unattended overnight run in real weather.**

---

## Verification

| What | How |
|---|---|
| Image quality | Phase 0 sunset sequence, at 100 % and as a 4K crop |
| JPEG encode time | Time 20 full-res captures; sets the minimum sustainable interval |
| Size vs quality | 20 frames each at q75/q80/q85/q90, varied scenes; feeds the storage budget |
| Storage budget | Arm a session larger than free space; must refuse, not fill the card mid-run |
| Interval accuracy | `frames.csv` timestamps — stddev of deltas under 50 ms |
| Shooting power | USB meter across a 1 h run vs the 1.1 W design point |
| Tuned idle floor | USB meter, per change, one at a time; target ≤80 mA headless |
| `P_cam`, streaming | picamera2 started but not capturing, minus base idle — the model's key input |
| Camera stop/start saving | 1 h at the real interval, streaming vs stopped, back to back |
| Core count | Same session at `maxcpus=1`/`2`/`4`; compare **Wh per frame**, not idle current |
| Multi-window scheduling | Two windows in one night with a power-cut between; both sequences complete |
| Standby power | µA meter on the pack over 24 h with power cut; confirm the ~0.3 mA datasheet figure |
| Low-voltage shutdown | Run a session to the threshold; must halt cleanly, cut power, and not re-wake flat |
| Shutdown safety | 50 forced power-cuts mid-capture; card mounts clean every time |
| Wake accuracy | Alarm 12 h out; first frame within a few seconds |
| Battery honesty | One run to empty, logging MAX17048 against actual runtime |
| Weatherproofing | Overnight outdoors in rain; inspect the window for condensation |
| Gasket durability | 20 open/close cycles, then repeat the rain test |
| Holder retention | Shake and drop-test a loaded sled; no contact dropout under vibration |
| Cell swap | Full swap with the device armed; wake alarm and schedule survive |
| Full system | Configure, leave 24 h, retrieve, assemble without a laptop in the field |

---

## Known risks

| Risk | Mitigation |
|---|---|
| IMX708 quality disappoints at dusk | Phase 0 answers this before €140 more is spent; HQ Camera is the fallback, at the cost of pocketability |
| L3V7 standby exceeds its 0.3 mA datasheet figure | Confirm on the bench in Phase 3; path B is the escape hatch if it is far off |
| Flat pack re-wakes and drains to the protection cutoff | Firmware recovery threshold on path A; on path B, clear the alarm when halting for low battery |
| Path B: `BBSQW` not set → alarm never fires | Explicit test — set an alarm, pull Vcc, confirm `INT` goes low on backup power |
| Pi hangs, power never cut, pack drains | Hardware watchdog; BMS undervoltage is the backstop — costs a charge cycle, not hardware |
| SD corruption on power loss | Atomic writes + read-only root + `gpio-poweroff` handshake; verified by the 50-cut test |
| Exposure flicker through sunset | Capped-step ramp + logged metadata + post deflicker — three independent defences |
| Window fogging | Desiccant + vent plug; caught by the overnight field test |
| Cold cuts runtime | 25 % derate already in the budget; 7.0 Ah against a 5.4 Ah requirement |
| Parallel cells mismatched on swap | Matched labelled sets, protected cells, rotate together — never top up one cell |
| Holder contact dropout ends a session | Quality holder with retention; verified by shake test |
| Gasket wear from routine opening | O-ring in a groove, not adhesive foam; re-test after 20 cycles |
| Theft | Clamp mount, unremarkable enclosure, don't leave it where you'd mind losing €190 |

---

## Sources

- [Pi Zero 2 W power deep dive](https://www.cnx-software.com/2021/12/09/raspberry-pi-zero-2-w-power-consumption/)
- [Pi Zero power consumption after shutdown](https://forums.raspberrypi.com/viewtopic.php?t=150303)
- [Camera Module 2 & 3 power draw](https://forums.raspberrypi.com/viewtopic.php?t=347469)
- [Raspberry Pi autofocus camera modules](https://www.raspberrypi.com/news/new-autofocus-camera-modules/)
- [Pololu U3V50F5](https://www.pololu.com/product/2565)
- [Witty Pi 4 L3V7](https://www.uugear.com/product/witty-pi-4-l3v7/)
- [Witty Pi 4 Mini](https://www.uugear.com/product/witty-pi-4-mini/)
- [pi-wake-on-rtc](https://github.com/bablokb/pi-wake-on-rtc)
- [Arducam Owlsight OV64A40](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/64MP-OV64A40/)
- [Tuning the Raspberry Pi Zero 2 W for minimum power consumption](https://www.lo-tech.co.uk/wiki/Tuning_the_RaspberryPi_Zero2W_for_Minimum_Power_Consumption)
- [Headless Zero 2 W, 30–40 % power reductions](https://forums.raspberrypi.com/viewtopic.php?t=392265)
- [Disabling cores to halve the Zero 2 W's power consumption — Jeff Geerling](https://www.jeffgeerling.com/blog/2021/disabling-cores-reduce-pi-zero-2-ws-power-consumption-half/)
- [Rockchip RV1106 datasheet](https://rockchip.fr/RV1106%20datasheet%20V1.9.pdf)
- [Luckfox Pico Pro / Max overview](https://www.cnx-software.com/2024/02/29/luckfox-pico-pro-pico-max-rockchip-rv1106-boards-100m-ethernet-5mp-camera/)
