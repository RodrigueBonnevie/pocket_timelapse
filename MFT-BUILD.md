# Pocket Timelapse Camera — the Micro Four Thirds build

**The decided path.** A used Panasonic body runs its own exposure and writes to its own card; an MCU
switches power on a schedule and presses the shutter. Everything this project spent a month fighting
— exposure range, bit depth, ISP tuning, demosaic, colour — is already solved inside a camera that
costs €150 second-hand.

[CAMERA-BUILD.md](CAMERA-BUILD.md) is the survey that led here. This is the machine.

---

## Why, in three measured numbers

| | Arducam B0587 (measured) | MFT body |
|---|---|---|
| Usable exposure range | **8.27 stops** against a sunset's 13.01 | **~17 stops** |
| Delivered dynamic range | **8.9 stops**, 31 % of a frame in 4 code values | **12-bit raw** |
| Sensor area | 33.6 mm² | **224.9 mm² — +2.74 stops** |

The first two are why the UVC path closed — see the verdict in [UVC-BUILD.md](UVC-BUILD.md). The
third is a bonus.

---

## Phase 0 — and the first half needs no electronics at all

**The pivot rests on one hypothesis: that 12- or 14-bit raw from a large sensor actually fixes the
sunset.** Test that before building anything, using the Canon EOS 450D already owned.

### 0a — does raw actually solve it? (no hardware, this week)

The 450D is a 2008 APS-C DSLR: 12.2 MP, 1/4000–30 s, raw, LP-E5 battery, **E3 2.5 mm remote
terminal**. No Magic Lantern (DIGIC III, not on the supported list — verify rather than assume), no
built-in intervalometer.

1. Shoot a full sunset on it: **raw, aperture priority, Auto ISO, manual focus at infinity**, 2 s
   interval, driven by a €15 intervalometer or `gphoto2` from a laptop.
2. Grade and assemble the same way the Arducam sequence was.
3. **Compare directly against the 3073-frame Arducam sunset.** Specifically: are the shadows still
   piled into a handful of levels? Does the highlight detail in the clouds survive?

**This is the only experiment that can invalidate the whole pivot**, and it costs nothing but an
evening. If raw does not visibly fix what the 8-bit JPEG broke, stop and reconsider before buying a
body.

The 450D is a fair proxy: **5.2 µm pixels on 328 mm²**, so slightly *more* light per pixel than the
GX7's 3.75 µm. Older silicon with worse QE and read noise offsets that, so call it a wash — which
means a good result on the 450D will not flatter the eventual camera.

### 0b — does a camera behave like an appliance? (~€25)

Three questions, in order. Any "no" changes the design.

1. **Free, tonight — done 2026-09-21: the 450D passes.** Switched on, battery pulled, battery
   reinserted, and it **comes back on without touching the switch**. That is the behaviour the whole
   architecture needs, confirmed on real hardware rather than assumed.

   **What it does not prove.** Nothing about Panasonic — different firmware, different vendor, and
   this has to be re-run on the GX7 before committing. Nothing about whether it comes back *ready to
   shoot* as opposed to merely powered. And nothing about the coupler path specifically, though the
   coupler should behave *better*: an original identifies itself as a coupler rather than
   impersonating a battery, which is why cameras power-cycle cleanly on them.

   **Three follow-ups, still free:**
   - Pull, reinsert, and immediately press the shutter. **How long until it actually fires?**
   - Does it keep its settings — mode, ISO, drive, focus — across the power loss?
   - Pull the battery **during a write to the card**, then check the card mounts clean. This is the
     50-power-cuts test from [PI-BUILD.md](PI-BUILD.md), and it decides the shutdown rule below.
2. **With a DR-E5 / ACK-E5 coupler (~€20):** cut and restore the rail with the switch left on.
   **Does it boot ready to shoot?** This is the highest-risk unknown in the architecture.
3. **With an optocoupler on the 2.5 mm jack (~€5):** does a GPIO pulse fire the shutter reliably,
   100 times in a row, with no dropped frames?

**What transfers to the Panasonic:** all of it except the on-camera scripting. The 2.5 mm remote jack
is the *same connector* on both. The power architecture, the RTC, the scheduling and the enclosure
method are identical.

**What does not:** shutter wear (the 450D is mechanical, ~100 k rated, so **do not run production
sessions on it** — 8,640 actuations is a session), power figures, and physical size.

> **The 450D is arguably the better prototype**, because it has no intervalometer and forces the
> external trigger to be built — and the Panasonic's built-in intervalometer very likely cannot be
> restarted after a power cycle, so that trigger is needed there too.

---

## The body

| Body | Sensor | E-shutter | Intervalometer | Coupler | Used |
|---|---|---|---|---|---|
| **Panasonic GX7** | MFT, 16 MP | **yes** | yes | DMW-DCC11 | **~€150** |
| Panasonic G7 | MFT, 16 MP | yes | yes | DMW-DCC8 | ~€180 |
| Panasonic GX85 | MFT, 16 MP | yes | yes | DMW-DCC11 | ~€250 |

**GX7 is the value pick.** The electronic shutter is the decisive feature: 8,640 actuations a session
against a 100,000 rating makes a mechanical shutter a consumable, and an electronic one makes the
number meaningless. 16 MP at 4592×3448 crops to 4592×2583 — above 4K with room to recompose.

---

## The lens

**One modern manual wide**, and vintage glass for longer views.

A lens with a real aperture ring **cannot flicker**. An electronic lens re-actuates its diaphragm
every frame and does not land in the same place twice, which is visible brightness stepping through
the sequence — the standard workarounds exist precisely because of this. Manual glass removes the
failure mode rather than mitigating it, and removes a motor that could drift on power-up.

| Lens | Why | ≈ |
|---|---|---|
| **7artisans / Meike 12 mm f/2.8, native MFT** | ~84° diagonal, manual aperture, 46 mm filter thread | €150 |
| M42 / MD / FD vintage + adapter | longer views, €20–60 a lens, adapts on MFT's 19.25 mm flange | €10–25 adapter |

The 46 mm filter thread matters: **a 52 mm filter serves as the enclosure window**, so the original
37–52 mm window plan survives rather than needing the 77 mm plate an APS-C body with a fast zoom
would demand.

---

## Power and trigger

### The rail

The MCU switches the pack **once at the start of a session and once at the end** — never between
frames. At 2–10 s intervals per-frame cycling is impossible or pointless; see
[CAMERA-BUILD.md](CAMERA-BUILD.md).

```
  18650 pack (3.7 V) ──[ P-FET ]── boost to 7.4 V ── DC coupler ── camera
                          │gate
                       DS3231 INT (alarm, open-drain, latches low)
                          │
                       MCU hold-GPIO  ── releases at end of session
```

Switching **before** the boost is deliberate: the converter's quiescent draw leaves the standby
budget entirely, exactly as in [PI-BUILD.md](PI-BUILD.md) path B. Standby is then cells'
self-discharge, not circuitry.

**Set `BBSQW = 1` on the DS3231.** By default it disables `INT/SQW` on backup power — the alarm pin
is dead precisely when it must fire. This is the single most common failure in this circuit.

### The shutter

The 2.5 mm TRS remote jack, on both Canon E3 and Panasonic:

| Contact | Function |
|---|---|
| Sleeve | ground |
| Ring | **S1 — half press**: wake, meter, autofocus |
| Tip | **S2 — full press**: shutter |

Two optocouplers, one per contact, driven from MCU GPIOs. Sequence per frame:

```
  assert S1        -> wake and meter
  wait ~150 ms
  assert S2        -> shutter
  hold ~100 ms
  release S2, S1
```

Wire **both** even with manual focus and manual exposure: the half-press is what wakes a dozing
meter, and it costs one optocoupler. Optical isolation matters here — the camera's trigger contacts
should share no ground path with the pack.

### Never cut the rail during a write

The MCU cuts power at the end of a session, and a raw file is still being written for seconds after
the shutter closes — roughly 15 MB on the 450D, 20 MB on the GX7, onto a card that may manage only
5–10 MB/s.

**Rule: stop triggering, wait, then open the latch.** Five seconds is a cheap margin against a
corrupted card and a lost session, and the cost is five seconds of idle at the very end of a run.
Confirm the actual write time per body rather than trusting the estimate — and test surviving a cut
mid-write anyway, because eventually one will happen.

### Budget

At ~1.6 W with the camera awake for the whole session (see the sizing in
[CAMERA-BUILD.md](CAMERA-BUILD.md)):

| Session | Cells |
|---|---|
| 6 h | 2 |
| 8 h | 2 |
| 12 h | 3 |

The MCU adds ~0.15 W while running and microamps between sessions — negligible either way.

---

## Bill of materials

| # | Part | Role | ≈ EUR |
|---|---|---|---|
| 1 | Panasonic GX7, used | body | 150 |
| 2 | 7artisans / Meike 12 mm f/2.8 MFT | manual aperture, cannot flicker | 150 |
| 3 | DMW-DCC11 DC coupler | external power | 20 |
| 4 | Adjustable boost to 7.4 V | from the pack | 15 |
| 5 | 2 × 18650 + sled | ~25 Wh | 20 |
| 6 | DS3231 + AO3401A P-FET + passives | scheduled wake, switched rail | 12 |
| 7 | ESP32-C3 | interval timing, trigger, config AP | 8 |
| 8 | 2 × optocoupler + 2.5 mm lead | shutter and half-press | 6 |
| 9 | Bay charger | charge outside the box | 25 |
| 10 | 52 mm filter as the window | optical window | 20 |
| 11 | IP65 case ≈ 180 × 130 × 110 mm | enclosure | 25 |
| 12 | Vent plug, desiccant, O-rings, 1/4″ inserts | sealing and mount | 25 |
| | | **total** | **≈ 476** |
| | | *excluding body and lens* | **≈ 176** |

Storage is the camera's own SD card. No microSD on the host, no fuel gauge, no storage code.

---

## Software — what little there is

Running on the ESP32-C3, and that is the whole of it:

- **`schedule`** — read the session plan, set the DS3231 alarm, release the latch when done.
- **`interval`** — monotonic deadlines, not `sleep(interval)`, or capture time accumulates as drift.
  Skip a late frame rather than catching up.
- **`trigger`** — the S1/S2 sequence above.
- **`config`** — button raises a WiFi AP for five minutes; a phone browser sets interval, duration
  and start time. Same approach as [PI-BUILD.md](PI-BUILD.md) Decision 3.

**Gone entirely:** `camera.py`, `ramp.py`, `storage.py`, the V4L2 bindings, the exposure ladder, the
white-balance workaround, the demosaic that the astro path would have needed. The camera does all of
it, and does it better.

**Laptop side, unchanged:** `ffmpeg` with `deflicker`, and raw development with a single grade
applied across the sequence.

---

## Known risks

| Risk | Mitigation |
|---|---|
| **Camera does not boot on rail-up** | Phase 0b question 2. **The 450D passes the battery-pull version of this test.** Re-run on the GX7 before committing — Panasonic firmware is a different question. Use a **genuine** coupler |
| Rail cut mid-write corrupts the card | Stop triggering, wait ~5 s, then open the latch. Verify the write time per body |
| **Raw does not visibly fix the sunset** | Phase 0a, before any spending. This invalidates the pivot, not the parts |
| Auto ISO ramp flickers frame to frame | Manual aperture removes the aperture component; `deflicker` and a single graded curve handle the rest |
| Heat in a sealed box | Far less than a mirrorless shooting video, but still untested. Shade, light-coloured case, avoid midday |
| Condensation on a large air volume | Desiccant plus a PTFE vent plug, as in the other builds |
| Theft — the box now contains a camera | A €150 body is the point. Do not put anything you would miss in it |
| Panasonic intervalometer will not resume after a power cycle | Assumed true; the external trigger exists for this reason |
| DS3231 `BBSQW` unset, alarm never fires | Explicit test: set an alarm, pull Vcc, confirm `INT` goes low on backup |

---

## Order of work

1. **0a — the sunset on the 450D.** Raw, Av, Auto ISO. Grade it. Compare against the Arducam
   session. *This gates everything.*
2. **0b — the appliance tests.** Battery yank, then coupler, then optocoupler.
3. Buy the GX7 and the 12 mm. Repeat 0b on it, and confirm the electronic shutter and the
   intervalometer behaviour after a power cycle.
4. Breadboard the DS3231 latch. Verify `BBSQW` and a scheduled wake.
5. ESP32 firmware: schedule, interval, trigger.
6. Enclosure, window, an unattended overnight run in real weather.
