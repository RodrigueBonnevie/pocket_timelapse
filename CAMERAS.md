# Camera options — the full survey

Every camera seriously considered for this project, in one table rather than scattered across three
architecture documents. Compiled 2026-09-21, after Phase 0 measured the chosen camera and found it
unfit.

Depth of analysis lives elsewhere: [UVC-BUILD.md](UVC-BUILD.md) for the UVC architecture and the
measurements, [ASTRO-BUILD.md](ASTRO-BUILD.md) for the give-up-the-ISP path, [PI-BUILD.md](PI-BUILD.md)
for CSI, [SENSORS.md](SENSORS.md) for what an ISP and its tuning actually are.

---

## How to read this

The axes, in the order they decide things:

1. **Exposure range.** A sunset spans ~10 stops. The camera already owned manages **4.91**, measured.
   This is the specification that matters and **almost nobody publishes it**.
2. **Does it keep the MCU host?** Requires UVC, MJPEG output, an onboard ISP and USB 2.0. Anything
   else forces a Linux host, ~2 W of idle floor, and six cells instead of two.
3. **Resolution ≥ 3840×2160.** Hard requirement. Above it is welcome — crop room for recomposing.
4. **Light gathering.** Matters far less than range: **+7 stops of shutter beats −1 stop of sensor**
   for a tripod-mounted timelapse. It is a tiebreaker, not a filter.
5. **Lens format.** A large sensor needs large glass, and that cost is unavoidable physics.

### The specification nobody publishes

Across roughly thirty modules, ten sensors and a dozen vendors, **two manufacturers state an
exposure range**, and both sell into microscopy. Not Arducam, not e-con, not Basler, not IDS — whose
full technical manual does not contain the word *exposure* at all.

**This is why the B0587 got past selection.** It advertises `exposure_time_absolute` 1–5000
(0.1–500 ms) and reports every value back verbatim; only 0.1–14.4 ms does anything.

Three heuristics have survived contact:

- **Absence of the claim is evidence of absence.** Vendors advertise long exposure loudly when they
  have it — Arducam's own B0588 page states 12,935,800 µs.
- **The cap tracks the target market, not the sensor or the interface.** Same silicon families,
  ranges differing by three orders of magnitude, sorted entirely by what the camera is sold for.
- **Above 4K cannot be a video part.** No video standard consumes 12 or 20 MP, so the firmware has
  nowhere to hide. Necessary, not sufficient — a bandwidth-limited high-MP camera can still cap.

---

## Tier C — keeps the MCU host

UVC · MJPEG · onboard ISP · USB 2.0. The only group that preserves the ~30 µA idle floor, two cells
instead of six, and `v4l2.py` working unchanged.

| Camera | Sensor | Format, pixel | Resolution | Exposure range | Notes |
|---|---|---|---|---|---|
| **Arducam B0587** *(owned)* | IMX678 | 1/1.8″, 2.0 µm | 3840×2160 @25 | **4.91 stops, MEASURED** | **Fails.** ~Skr 1,000 |
| **ToupTek C2CMOS12000KPA** | IMX577 | 1/2.3″, 1.55 µm | **3840×3040** @15 | **14.3 st, published** | 4:3 → 4K crop **+880 px headroom**. C-mount. Not distributed in EU |
| ToupTek C2CMOS08300KPA | IMX274 | 1/2.5″, 1.62 µm | 3840×2160 @30 | **14.3 st, published** | C-mount. Not distributed in EU |
| **e-con e-CAM82_USB** | IMX415 | 1/2.8″, 1.45 µm | 3840×2160 @30 | unpublished | **0.73–1.07 W** — lowest here. M12, 30×30×25 mm |
| e-con See3CAM_CU81 | AR0821 | 1/1.7″, **2.1 µm** | 4K, **HDR** | unpublished | USB 3.1 "backward compatible with USB 2.0" — *unverified* |
| Goobuy UCM-678-8mp-2 | IMX678 | 1/1.8″, 2.0 µm | 3840×2160 @30 | unpublished | 950 mW. Page lists *auto* exposure only — treat as a B0587 repeat |
| Camemake CM-USB2-02 | OS08A10 | 1/1.8″, 2.0 µm | 4K | unpublished | Staggered HDR mode in the sensor |

**Best candidate: C2CMOS12000KPA.** Only group member with a published range *and* crop headroom.
Costs 0.06 stops of pixel area against its 8.3 MP sibling — nothing — and needs a direct enquiry
because nimax (astroshop / optics-pro / micro-pro) does not carry the line.

---

## Tier B — UVC, but Linux-bound

USB 3.0, or no MJPEG, or both. The camera still does the ISP work; the host still has to stay awake.

| Camera | Sensor | Format, pixel | Resolution | Output | Notes |
|---|---|---|---|---|---|
| Arducam B0497 | IMX678 | 1/1.8″, 2.0 µm | 4K @15 | **YUY2 only** | Same sensor *and lens* as the B0587 |
| Arducam B0498 | IMX585 | 1/1.2″, **2.9 µm** | 4K @15 | **YUY2 only** | C-mount, **F1.4–F16 manual iris** |
| Arducam B0477 | IMX283 | **1″**, 2.4 µm | **5472×3648** @9 | **YUY2 only** | 9 fps at full res — bandwidth-limited |
| e-con See3CAM_CU200 | AR2020 | 1/1.8″, 1.4 µm | **5120×3840** @8 | **UYVY only** | TintE ISP, M12, 1.72 W, 28 g |
| IDS uEye XC `UV-36L0XC` | AR1335 | 1/3.2″, 1.1 µm | **4200×3120** | **MJPEG** | USB 3.0, **integrated lens — no mount**. "Exposure" absent from the manual |
| Arducam IMX586 / OV64A40 | — | 0.8 µm / 1/1.32″ | 48 / 64 MP | MJPEG | Webcam-derived, tiny pixels |
| ELP, SincereFirst, HBVCAM, DFRobot | IMX678 | 1/1.8″, 2.0 µm | 4K @30–60 | MJPEG | USB 3.0 rebadges, all unpublished |
| Innomaker, Vadzo, VXB | IMX415 | 1/2.8″, 1.45 µm | 4K @30 | MJPEG | USB 3.0 |

**Note the Arducam pattern:** their whole C-mount USB 3.0 line — B0497, B0498, B0477 — is **YUY2
only** by their own datasheets. Whatever the sensor, those hand the compression back to the host.

---

## Tier B — machine vision

Open or vendor protocols, raw output, no consumer ISP. Deterministic control is the product.

| Camera | Sensor | Format, pixel | Protocol | Exposure range | Price |
|---|---|---|---|---|---|
| **Basler dart daA3840-45uc** | IMX334 | 1/1.8″, 2.0 µm | **USB3 Vision — open standard** | unpublished, but **readable off the camera** via GenICam | ~€185 |
| Basler ace 2 | Pregius / STARVIS | various | USB3 Vision | **up to 10,000,000 µs, published** | Skr 5–10k |
| Allied Vision Alvium 1800 U | IMX183/226/548 | various | USB3 Vision | unpublished | — |

**GenICam cameras self-describe**: every feature's min, max and increment arrives in an XML the
camera serves, and `arv-tool-0.8 features` prints it. Discoverable in one command — but only with the
camera in hand, and *not* proof of honesty; the B0587 self-reported a range it did not honour.

The dart is 28.3 × 27 mm and under 5 g with an **S-mount thread that is M12**, so it keeps the lens
ecosystem. See [ASTRO-BUILD.md](ASTRO-BUILD.md) Variant B.

---

## Tier B — astronomy and microscopy

Built for stills under manual control. No ISP at all in the astro bodies; a hardware ISP in the
microscopy ones. All need a Linux host.

| Camera | Sensor | Format, pixel | Resolution | Exposure range | ISP | Price |
|---|---|---|---|---|---|---|
| **ZWO ASI294MC** | **IMX294** | **4/3″, 4.63 µm** | 4144×2822 | **32 µs – 30 min** | none | **Skr 10,800** |
| **ZWO ASI585MC** | IMX585 | 1/1.2″, 2.9 µm | 3840×2160 | **32 µs – 2000 s** | none | **Skr 6,350** |
| Player One Uranus-C | IMX585 | 1/1.2″, 2.9 µm | 3856×2180 | comparable | none | comparable |
| Player One Artemis-C Pro | IMX294 | 4/3″, 4.63 µm | 4144×2822 | comparable | none | ~€895 cooled |
| ToupTek E10ISPM08300KPA | IMX585 | 1/1.2″, 2.9 µm | 3840×2160 | **0.1 ms – 15 s** | **yes, 12-bit** | Skr 11,300 |
| ToupTek E3ISPM 25000A | — | — | 25 MP | 0.1 ms – 15 s (series) | yes | **Skr 6,000** |
| ToupTek E3ISPM 12000B | — | — | 12 MP | series | yes | Skr 7,300 |
| BestScope BUC5F-830DC | IMX585 | 1/1.2″, 2.9 µm | 8.3 MP | — | yes | ~$280 |

**Microscopy housings cost roughly double astronomy housings for the same silicon** — the E10ISPM and
the ASI585MC carry the same IMX585 and differ by Skr 5,000. And the microscopy ISP does not buy back
the MCU, because USB 3.2 plus a vendor SDK means Linux either way. It buys convenience, not
architecture.

---

## Outside the box

| Option | Sensor | Exposure range | Why it is here | Price |
|---|---|---|---|---|
| **Used mirrorless + `gphoto2`** | APS-C, **~3.9 µm** | **30 s – 1/4000 ≈ 17 stops** | +1.9 stops per pixel over the IMX678, a real lens mount, mature open control | **~Skr 2,500 used** |

Bulk, a few watts, a mechanical shutter to avoid — and not a module. But with size no longer a
requirement and Linux needed anyway, it is what a photographer would actually reach for, and it
costs less than the ZWO.

---

## Blocked: CSI

| Camera | Sensor | Why blocked |
|---|---|---|
| Pi Camera Module 3 | IMX708, 1/2.43″, 1.4 µm | Needs a Pi Zero 2 W — **sold out across European retailers, re-checked 2026-09-19** |
| Pi HQ Camera | IMX477, 1/2.3″, 1.55 µm | Same, plus bulk |

The best architecture of the three. libcamera hands over the sensor's exposure register *and*
Raspberry Pi ship tuned ISP data — the only vendor doing both. Unobtainable.

---

## Sensors ranked by light per pixel

Relative to the IMX678 already owned (2.0 µm, 4.00 µm²).

| Sensor | Pixel | Area | vs IMX678 |
|---|---|---|---|
| **IMX294** | 4.63 µm | 21.4 µm² | **+2.42 st** |
| APS-C, 24 MP | ~3.9 µm | 15.2 | +1.93 |
| **IMX585 / IMX485** | 2.9 µm | 8.41 | **+1.07** |
| IMX283 / IMX183 | 2.4 µm | 5.76 | +0.53 |
| AR0821 | 2.1 µm | 4.41 | +0.14 |
| **IMX678 / IMX334 / OS08A10** | 2.0 µm | 4.00 | — |
| IMX274 | 1.62 µm | 2.62 | −0.61 |
| IMX577 | 1.55 µm | 2.40 | −0.74 |
| IMX415 / IMX715 | 1.45 µm | 2.10 | −0.93 |
| AR2020 | 1.4 µm | 1.96 | −1.03 |
| AR1335 | 1.1 µm | 1.21 | −1.73 |
| IMX586 | 0.8 µm | 0.64 | −2.64 |

**Pixel size runs almost exactly opposite to resolution.** The 20 and 48 MP parts have the smallest
pixels here. Resolution and light-gathering compete for the same silicon unless sensor area is also
bought — and sensor area is paid for in glass.

**Keep the ranking in proportion.** The whole column spans about 5 stops; the exposure-range column
spans 21. Range dominates.

---

## The question to ask any vendor

> At 4K, what minimum and maximum `exposure_time_absolute` **actually change the image** — not the
> range the UVC control advertises? On the Arducam B0587 the control accepts 1–5000 (0.1–500 ms) and
> reports values back verbatim, but only about 1–144 has any effect.

---

## Status of every claim here

| Claim | Basis |
|---|---|
| B0587 exposure range 4.91 stops | **Measured**, `phase0/exposure_sweep.py` and a mode sweep |
| B0587 floor 2.3 stops too bright in daylight | **Measured** |
| Published exposure ranges — ToupTek, ZWO, Basler ace 2, See3CAM_10CUG | **Vendor-stated**, unverified |
| All other exposure ranges | **Unknown** |
| Pixel sizes, formats, resolutions | Vendor datasheets |
| Prices in SEK | astroshop.eu / micro-pro.com, landed, 2026-09-21 |
| Prices in EUR/USD | Distributor listings, not landed |
| Power figures | Vendor typical or maximum — **none measured** |
| Tier C compatibility of See3CAM_CU81 | **Assumed from "USB 2.0 backward compatible" — unverified** |
| IMX294 HDR mode reachable via SDK | **Assumed unavailable — unverified** |

Nothing in the two "published" rows should be believed without measurement. **The B0587 published a
range it did not honour, and that is the entire reason this document exists.**
