# Sensor options — and why the small one is enough

*Companion to [HARDWARE.md](HARDWARE.md). Background reading, not decisions.*

"Just use a bigger sensor" is the obvious question to ask of any camera project, and it deserves a
real answer rather than a shrug. This document surveys what's available, explains why the market
looks the way it does, and sets out the reason a 1/2.43" sensor is an adequate choice for a
locked-off timelapse specifically — which is not the same as saying it would be adequate for
handheld photography.

---

## 1. Sony IMX sensors do not have ISPs

This surprises people, so it's worth stating plainly: **IMX477, IMX708 and IMX283 output raw Bayer
over MIPI CSI-2 and nothing else.** Sony does not integrate an image signal processor into them.

The pattern across the industry is consistent, and it runs the opposite way to intuition:

- **Small, cheap sensors sometimes integrate an ISP.** The OV5640 does, which is precisely why it
  works with a bare microcontroller — that's the Arducam Mega, and it's why that module exists at
  all.
- **Large, good sensors never do.** They're designed for systems that already have a real ISP, so
  putting one on the die would be wasted silicon.

Where you *do* find a large sensor advertised "with ISP", it is a **companion chip sharing the
board**. Arducam sells the IMX283 two ways that make this explicit: as a **USB 3.0 module with an
onboard ISP**, and as a MIPI module paired with their separate **xISP "ImageEK"** processor for
NVIDIA Jetson Orin. The ISP is a distinct product precisely because those hosts lack a suitable
one.

So the search for "an IMX sensor with a built-in ISP that an MCU could drive" has no answer. It
isn't a gap waiting to be filled; it's a consequence of where ISPs live in the stack. See
[IMAGE-PIPELINE.md](IMAGE-PIPELINE.md) for what an ISP actually does and why it can't be skipped.

---

## 2. The sensors, ranked by what matters

For a fixed field of view, low-light performance tracks **total sensor area** more than anything
else, so the useful comparison is in stops relative to the current choice.

| Sensor | Format | Resolution | Pixel | Pixel area | Sensor area | vs IMX708 | Fits this build? |
|---|---|---|---|---|---|---|---|
| IMX219 | 1/4" | 3280×2464, 8 MP | 1.12 µm | 1.25 µm² | 10 mm² | −1.2 stops | yes, but strictly worse |
| **IMX708** | 1/2.43" | 4608×2592, 11.9 MP | 1.40 µm | 1.96 µm² | 23 mm² | — | **current choice** |
| IMX519 | 1/2.53" | 4656×3496, 16 MP | 1.22 µm | 1.49 µm² | 24 mm² | +0.05 | yes; more pixels, smaller ones |
| **IMX477** | 1/2.3" | 4056×3040, 12.3 MP | **1.55 µm** | **2.40 µm²** | 30 mm² | **+0.3** | **yes — and C/CS mount** |
| OV64A40 | 1/1.32" | 9248×6944, 64 MP | 1.008 µm | 1.02 µm² | 65 mm² | +1.5 | RAM-limited on a Zero 2 W |
| IMX283 | 1" | 5472×3648, 20 MP | 2.40 µm | 5.76 µm² | 115 mm² | +2.3 | **no** — USB 3.0 or Jetson |
| M4/3 (e.g. IMX294) | 4/3" | 4144×2822, 11.7 MP | 4.63 µm | 21.4 µm² | 225 mm² | **+3.3** | **no** — different project |

Two things worth reading off that table. **Megapixels and light-gathering are unrelated** — the
64 MP OV64A40 has *half* the pixel area of the 12 MP IMX708, and gets its advantage purely from
being physically larger overall. And **IMX477's headline gain over IMX708 is small**: +0.3 stops of
area, +22 % pixel area. It is not a different class of sensor.

### The discontinuity above 1/1.3"

This is the structural fact that shapes the options:

**Below roughly 1/1.3", you get MIPI modules the Pi drives with its own ISP. Above it, you leave
the Raspberry Pi ecosystem entirely** and land in USB 3.0 or Jetson territory — where idle power
goes from 0.4 W to several watts and the battery-powered pocket-box premise collapses.

The IMX283 illustrates it well. Arducam's USB 3.0 version has an onboard ISP, but the **Pi Zero 2 W
is USB 2.0 only**, and that module outputs *uncompressed YUY2* — a 20 MP YUY2 frame is roughly
40 MB, beyond both the Zero's 512 MB of RAM and its bus bandwidth. The MIPI version targets Jetson.
Neither is a Pi Zero part.

---

## 3. Micro Four Thirds and second-hand lenses

The appeal is obvious: 3.3 stops of light-gathering, and a deep second-hand market of good glass.
Two problems.

**The lens idea only pays if the sensor has that image circle.** Adapting an M4/3 lens onto a
1/2.3" sensor uses only the centre of the projected image — an enormous crop factor, a physically
large lens, and no light-gathering benefit whatsoever. The photons that would have helped land
outside the sensor.

**A real M4/3 sensor means an astronomy camera** — ZWO ASI294, QHY and similar. Those are USB 3.0,
raw output only, no ISP, €600–1000, drawing 2–5 W before any cooling, and physically large before
you attach glass. That's not a variant of this project; it's a mains-powered or big-battery project
with a different enclosure, a different host, and a different cost bracket.

---

## 4. The counterpoint that undercuts the whole question

**In a locked-off timelapse, exposure time is nearly free.**

The case for a large sensor is strongest when you are constrained to short exposures — handheld
work, or moving subjects, where you cannot simply leave the shutter open. This project is neither.
The camera is clamped to something solid and the subject is a sunset.

At dusk you can expose for 1/4 s, 1 s, or longer between frames and collect more photons directly,
which is most of what a bigger sensor was going to buy. A 30 s interval leaves an enormous exposure
budget entirely unused.

That is not free, and the caveats are real:

- Longer exposures mean more sensor-on time, which costs power (see the active power budget in
  [HARDWARE.md](HARDWARE.md)).
- Thermal noise and hot pixels rise with exposure length, especially on a warm sensor in a sealed
  box.
- The bright end of a sunset still needs short exposures, so this only helps the dark half of the
  ramp.

But the direction is clear: **a small sensor on a tripod is a far better proposition than a small
sensor handheld**, and this rig is always on a tripod. That recovers a substantial fraction of the
2–3 stops without changing a single component.

---

## 5. Recommendation

**Stay with the IMX708 for v1.** It is 11.9 MP, autofocus, with dynamic range Raspberry Pi have
spent years tuning, and it clears the 4K-with-crop-room requirement directly. Whether its image
quality is *actually* good enough for your sunsets is a question Phase 0 answers in an evening for
the price of a camera module — and that is a far better test than any table on this page.

**If an upgrade is wanted later, it's the IMX477 HQ Camera — but be clear about why.**

The sensor gain is only +0.3 stops. **The real value is the C/CS mount.** That opens cheap CCTV
glass at €20–40, or adapted C-mount cine lenses from the second-hand market. And for timelapse
specifically, manual focus and a fixed mechanical aperture are *advantages* rather than
compromises: no focus breathing, no aperture flicker between frames — both genuine contributors to
the flicker that `ramp.py` and the post-processing deflicker exist to fight.

The costs are honest ones. About €60 for the module plus a lens, and a 38 × 38 × 18.4 mm body
before glass, which is where **"pocketable" genuinely ends**. It uses the same Pi, the same ISP and
the same libcamera stack, so it is a drop-in swap with **zero architectural change** — the
enclosure is the only thing that has to be redesigned.

---

## Sources

- [Raspberry Pi Camera Module 3 / IMX708 announcement](https://www.raspberrypi.com/news/new-autofocus-camera-modules/)
- [Arducam 64MP OwlSight OV64A40](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/64MP-OV64A40/)
- [Arducam 20MP IMX283 USB 3.0 module with onboard ISP](https://www.arducam.com/arducam-20mp-usb-3-0-camera-module-with-16mm-c-mount-lens-b0477.html)
- [Arducam xISP "Klarity" — external ISP for IMX283 on Jetson](https://www.arducam.com/arducam-xisp-klarity-pre-tuned-isp-1-20mp-high-sensitivity-mipi-camera-for-nvidia-jetson-orin-nx-orin-nano.html)
- [Arducam Mega SPI camera — integrated ISP, 5 MP ceiling](https://docs.arducam.com/Arduino-SPI-camera/MEGA-SPI/MEGA-SPI-Camera/)
