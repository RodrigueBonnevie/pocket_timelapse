# From Photons to JPEG — why the camera dictates the board

*Companion to [PI-BUILD.md](PI-BUILD.md). Background reading, not decisions.*

Decision 1 in the hardware document rules out a microcontroller and picks a Linux board. That
looks like a statement about processing power, and it isn't. This document explains what
actually happens between the sensor and the SD card, where each part of it runs, and why the
real constraint is memory and dedicated silicon rather than clock speed.

---

## 1. A sensor doesn't output an image

The IMX708 outputs a **raw Bayer mosaic** — not a picture. Every photosite sits under a single
colour filter in a repeating 2×2 pattern, so each pixel records one of red, green or blue and is
missing the other two.

| | |
|---|---|
| Photosites | 4,608 × 2,592 = **11,943,936** |
| Bit depth | 10 bits |
| **Raw frame** | **≈ 14.9 MB** |
| Demosaiced RGB, 8-bit | ≈ 35.8 MB |

That ~15 MB is data, not an image. Something has to reconstruct the two missing channels at every
one of those twelve million pixels before anything can display or compress it.

## 2. The pipeline

```
black level  →  lens shading  →  bad pixel  →  DEMOSAIC  →  white balance
     →  colour correction matrix  →  gamma / tone curve  →  DENOISE
     →  sharpen  →  YCbCr  →  JPEG ENCODE
```

Most of these stages are cheap — a multiply and an add per pixel, or a lookup. Three are not:

- **Demosaic** reconstructs the missing colour channels using edge-directed interpolation over a
  neighbourhood. Naive interpolation produces zippering and false colour along edges, so any
  decent implementation is looking at a 5×5 window and making decisions. Tens of operations per
  pixel.
- **Denoise** is typically multi-scale, running the same analysis at several resolutions and
  recombining. Comparable cost or worse.
- **JPEG encode** — DCT, quantisation, entropy coding over every 8×8 block.

Across the whole chain, budget **100–200 arithmetic operations per output pixel**. At twelve
million pixels that's **on the order of 1.2–2.4 billion operations per frame.**

## 3. Where each stage runs

This is the part worth internalising: on a Raspberry Pi, **almost none of it runs on the ARM
cores.**

| Stage | Runs on |
|---|---|
| Demosaic, shading, bad pixel, WB, CCM, gamma, denoise, sharpen | **Hardware ISP block** in the VideoCore silicon |
| Statistics for metering | Same ISP, emitted as a side channel |
| 3A — auto-exposure, auto-white-balance, autofocus | ARM CPU, operating on downscaled stats |
| JPEG encode (stills) | **ARM CPU, in software** |
| Buffer plumbing, filesystem, OS | ARM CPU |

The Raspberry Pi camera team draw the line explicitly: the ISP only processes pixels and never
runs control algorithms, and the number-crunching inside the control algorithms is *tiny*
compared to producing the pixels. So the 3A loop — the part that feels like "the clever bit" — is
nearly free. The expensive part is fixed-function hardware.

**One thing worth flagging:** picamera2 encodes still JPEGs **in software**, through a
multithreaded encoder. The hardware MJPEG/H.264 block that exists on Pi 4 and earlier isn't used
for the stills path. At 12 MP on a 1 GHz Cortex-A53 this is likely a few hundred milliseconds and
is probably the single longest step in a capture.

> **Measure this in Phase 0.** If a full-resolution JPEG encode takes closer to a second than to
> 200 ms, it sets a floor on how short an interval the device can actually sustain, and it's the
> first thing to optimise (encoder choice, quality setting, or dropping to a hardware-friendly
> path).

## 4. What the load actually is

The ISP handles 4608×2592 at about 14 fps — roughly **167 Mpixel/s**. A timelapse at a 5 s
interval needs 12 Mpixel every 5 s, or **2.4 Mpixel/s.**

**You are using about 1.4% of the pipeline's capacity.** The Pi is wildly over-provisioned for
the rate you need. You can't buy a smaller thing that has an ISP at all — that's the whole
problem.

Which inverts the energy story from what you'd expect:

| At a 5 s interval | Energy per cycle |
|---|---|
| Keeping Linux idle for 5 s @ 0.58 W | 2.9 J |
| The capture itself (~0.5 s of extra draw — *estimated, measure it*) | ~0.5 J |
| **Capture's share of the total** | **≈ 14 %** |

| At a 30 s interval | Energy per cycle |
|---|---|
| Idle for 30 s | 17.4 J |
| The capture | ~0.5 J |
| **Capture's share** | **≈ 3 %** |

**Roughly 85–97% of the battery goes to keeping Linux alive between frames, not to photography.**
This single fact drives several decisions in the hardware document: why the idle floor is the
number that matters, why the power-cycling break-even lands around a one-minute interval, and why
cutting the rail entirely between *sessions* is worth building hardware for.

## 5. Why a microcontroller can't do this

Two walls. The first is absolute.

**The frame doesn't fit.** An ESP32-S3 has 512 KB of internal SRAM and commonly 2–8 MB of PSRAM.
A single raw frame is **15 MB**; the demosaiced RGB intermediate is ~36 MB. One frame exceeds the
entire usable address space. No amount of streaming cleverness fixes a demosaic, which needs a
neighbourhood around every pixel.

**There's no ISP.** Running that billion-operation pipeline in software on a 240 MHz dual-core
with no relevant SIMD means seconds to tens of seconds per frame — and the output would still
look worse than dedicated silicon, because good demosaic and denoise are genuinely hard problems
that vendors have spent years tuning.

Note that neither wall is "the MCU is too slow." A hypothetical MCU with 32 MB of RAM and an ISP
block would be perfect. That part exists — it's what a Rockchip RV1106 is — which is why the
Luckfox option appeared in the original comparison and was rejected on toolchain grounds, not
architecture.

## 6. So how do ESP32 cameras work at all?

They sidestep the problem, and it's a legitimate trick.

Modules like the OV5640 and the Arducam Mega have **the ISP and a JPEG encoder built into the
camera module itself.** The sensor package hands the MCU finished JPEG bytes over SPI or DCMI.
The MCU never sees raw, never demosaics, never allocates a frame buffer — it just spools
compressed bytes to an SD card. That's why an ESP32-CAM works.

What that costs:

- You inherit the module vendor's **fixed ISP tuning** — cost-optimised silicon aimed at
  doorbells and video calls, and not adjustable.
- Resolution is capped at what those integrated ISPs support, hence the ~5 MP ceiling.
- No raw output, and **coarse, limited exposure control.**

That last point matters more here than the resolution does. A sunset spans about ten stops, and
smooth ramping needs fine per-frame control over shutter and gain (see `ramp.py` in the hardware
document). An integrated ISP that decides its own exposure and won't let you set it in small
steps makes the one thing this device exists to do impossible.

## 7. What you're actually buying

**Not CPU. An ISP block, and enough RAM to hold a frame.**

The quad-core Cortex-A53 in the Pi Zero 2 W is almost incidental to the imaging — it runs the 3A
loop, the software JPEG encode, and the filesystem. The reason a "beefier board" is required is
that a hardware ISP and ~50 MB of addressable working memory only come packaged inside things
that also happen to run Linux.

## 8. Where this shows up elsewhere in the design

- **The Arducam Owlsight 64 MP caveat** is the same constraint from the other side. A 64 MP raw
  frame is ~80 MB and the RGB intermediate is far larger; the Zero 2 W's 512 MB — minus the
  contiguous CMA region the ISP requires — can't hold it. The sensor is fine; the board isn't.
- **The interval-versus-power break-even** falls out of §4: because the idle floor dominates,
  longer intervals don't save proportionally, and the saving from power-cycling per frame only
  overtakes boot cost around a minute.
- **Keeping the Pi awake through a session** is cheap relative to the alternative precisely
  because the capture bursts are a small fraction of the energy.
- **Phase 0's power measurement** is really a measurement of the idle floor plus the JPEG encode
  time. Those two numbers determine everything downstream.
- **The power-tuning checklist** exists because of §4. If captures were the dominant cost there
  would be little to tune — you'd be paying for photography and that's that. Because the idle floor
  dominates instead, stripping the display stack, radios and background services off a headless Pi
  is worth about 28 % of total draw, which is more than any board swap available at this
  resolution could deliver.
- **Nothing smaller helps**, and §5 is why: the small low-power Linux SoCs (RV1106, SG200x) carry
  ISPs capped at 5 MP. They sit *between* the ESP32 and the Pi, and they land on the wrong side of
  the same wall. See the board comparison in the hardware document.

---

## Sources

- [An open source camera stack for Raspberry Pi using libcamera](https://www.raspberrypi.com/news/an-open-source-camera-stack-for-raspberry-pi-using-libcamera/)
- [ISP versus control algorithms — Raspberry Pi forums](https://forums.raspberrypi.com/viewtopic.php?t=299743)
- [picamera2 JPEG encoder source](https://github.com/raspberrypi/picamera2/blob/main/picamera2/encoders/jpeg_encoder.py)
- [Using the hardware JPEG encoder — picamera2 issue #752](https://github.com/raspberrypi/picamera2/issues/752)
- [Camera Module 3 / IMX708 announcement](https://www.raspberrypi.com/news/new-autofocus-camera-modules/)
