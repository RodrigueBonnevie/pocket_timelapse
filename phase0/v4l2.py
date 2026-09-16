"""Minimal pure-stdlib V4L2 bindings.

Written against ctypes rather than shelling out to v4l2-ctl so Phase 0 needs
nothing installed, and so the same code can run later on a minimal embedded
host where adding packages is inconvenient.

Only the subset this project needs: enumerate formats and controls, get/set
controls, and grab single frames via mmap streaming (uvcvideo does not support
read() I/O, so the buffer dance is unavoidable).
"""

import ctypes as C
import fcntl
import mmap
import os

u8, u32, i32, ul, lo = C.c_uint8, C.c_uint32, C.c_int32, C.c_ulong, C.c_long

# --- ioctl encoding ---------------------------------------------------------
_NONE, _WRITE, _READ = 0, 1, 2


def _ioc(d, nr, size):
    return (d << 30) | (size << 16) | (ord("V") << 8) | nr


def _IOR(nr, t):   return _ioc(_READ, nr, C.sizeof(t))
def _IOW(nr, t):   return _ioc(_WRITE, nr, C.sizeof(t))
def _IOWR(nr, t):  return _ioc(_READ | _WRITE, nr, C.sizeof(t))


# --- structures -------------------------------------------------------------
class Capability(C.Structure):
    _fields_ = [("driver", C.c_char * 16), ("card", C.c_char * 32),
                ("bus_info", C.c_char * 32), ("version", u32),
                ("capabilities", u32), ("device_caps", u32), ("reserved", u32 * 3)]


class FmtDesc(C.Structure):
    _fields_ = [("index", u32), ("type", u32), ("flags", u32),
                ("description", C.c_char * 32), ("pixelformat", u32),
                ("mbus_code", u32), ("reserved", u32 * 3)]


class PixFormat(C.Structure):
    _fields_ = [("width", u32), ("height", u32), ("pixelformat", u32),
                ("field", u32), ("bytesperline", u32), ("sizeimage", u32),
                ("colorspace", u32), ("priv", u32), ("flags", u32),
                ("ycbcr_enc", u32), ("quantization", u32), ("xfer_func", u32)]


class Format(C.Structure):
    _fields_ = [("type", u32), ("_pad", u32), ("pix", PixFormat),
                ("_raw", u8 * (200 - C.sizeof(PixFormat)))]


class FrmSizeDiscrete(C.Structure):
    _fields_ = [("width", u32), ("height", u32)]


class FrmSizeStepwise(C.Structure):
    _fields_ = [("min_width", u32), ("max_width", u32), ("step_width", u32),
                ("min_height", u32), ("max_height", u32), ("step_height", u32)]


class _FrmSizeUnion(C.Union):
    _fields_ = [("discrete", FrmSizeDiscrete), ("stepwise", FrmSizeStepwise)]


class FrmSizeEnum(C.Structure):
    _fields_ = [("index", u32), ("pixel_format", u32), ("type", u32),
                ("u", _FrmSizeUnion), ("reserved", u32 * 2)]


class Fract(C.Structure):
    _fields_ = [("numerator", u32), ("denominator", u32)]


class _FrmIvalUnion(C.Union):
    _fields_ = [("discrete", Fract), ("stepwise", Fract * 3)]


class FrmIvalEnum(C.Structure):
    _fields_ = [("index", u32), ("pixel_format", u32), ("width", u32),
                ("height", u32), ("type", u32), ("u", _FrmIvalUnion),
                ("reserved", u32 * 2)]


class RequestBuffers(C.Structure):
    _fields_ = [("count", u32), ("type", u32), ("memory", u32),
                ("capabilities", u32), ("flags", u8), ("reserved", u8 * 3)]


class TimeVal(C.Structure):
    _fields_ = [("tv_sec", lo), ("tv_usec", lo)]


class TimeCode(C.Structure):
    _fields_ = [("type", u32), ("flags", u32), ("frames", u8), ("seconds", u8),
                ("minutes", u8), ("hours", u8), ("userbits", u8 * 4)]


class Buffer(C.Structure):
    _fields_ = [("index", u32), ("type", u32), ("bytesused", u32), ("flags", u32),
                ("field", u32), ("timestamp", TimeVal), ("timecode", TimeCode),
                ("sequence", u32), ("memory", u32), ("m_offset", ul),
                ("length", u32), ("reserved2", u32), ("request_fd", i32)]


class Control(C.Structure):
    _fields_ = [("id", u32), ("value", i32)]


class QueryCtrl(C.Structure):
    _fields_ = [("id", u32), ("type", u32), ("name", C.c_char * 32),
                ("minimum", i32), ("maximum", i32), ("step", i32),
                ("default_value", i32), ("flags", u32), ("reserved", u32 * 2)]


class QueryMenu(C.Structure):
    _pack_ = 1                       # the kernel declares this one packed
    _fields_ = [("id", u32), ("index", u32), ("name", C.c_char * 32),
                ("reserved", u32)]


# The kernel ABI is not negotiable, so catch a bad field layout at import
# rather than as a confusing EINVAL three calls later.
assert C.sizeof(Format) == 208, C.sizeof(Format)
assert C.sizeof(Buffer) == 88, C.sizeof(Buffer)
assert C.sizeof(QueryMenu) == 44, C.sizeof(QueryMenu)

VIDIOC_QUERYCAP = _IOR(0, Capability)
VIDIOC_ENUM_FMT = _IOWR(2, FmtDesc)
VIDIOC_G_FMT = _IOWR(4, Format)
VIDIOC_S_FMT = _IOWR(5, Format)
VIDIOC_REQBUFS = _IOWR(8, RequestBuffers)
VIDIOC_QUERYBUF = _IOWR(9, Buffer)
VIDIOC_QBUF = _IOWR(15, Buffer)
VIDIOC_DQBUF = _IOWR(17, Buffer)
VIDIOC_STREAMON = _IOW(18, i32)
VIDIOC_STREAMOFF = _IOW(19, i32)
VIDIOC_G_CTRL = _IOWR(27, Control)
VIDIOC_S_CTRL = _IOWR(28, Control)
VIDIOC_QUERYCTRL = _IOWR(36, QueryCtrl)
VIDIOC_QUERYMENU = _IOWR(37, QueryMenu)
VIDIOC_ENUM_FRAMESIZES = _IOWR(74, FrmSizeEnum)
VIDIOC_ENUM_FRAMEINTERVALS = _IOWR(75, FrmIvalEnum)

BUF_TYPE_VIDEO_CAPTURE = 1
MEMORY_MMAP = 1
CTRL_FLAG_NEXT_CTRL = 0x8000_0000
CTRL_TYPE = {1: "int", 2: "bool", 3: "menu", 4: "button", 5: "int64",
             6: "ctrl-class", 7: "string", 8: "bitmask", 9: "int-menu"}

CID_BRIGHTNESS = 0x0098_0900
CID_AUTO_WHITE_BALANCE = 0x0098_090C
CID_GAIN = 0x0098_0913
CID_WHITE_BALANCE_TEMPERATURE = 0x0098_091A
CID_EXPOSURE_AUTO = 0x009A_0901
CID_EXPOSURE_ABSOLUTE = 0x009A_0902
CID_FOCUS_ABSOLUTE = 0x009A_090A
EXPOSURE_MANUAL = 1              # V4L2_EXPOSURE_MANUAL, both control namings


def fourcc(v):
    return "".join(chr((v >> s) & 0xFF) for s in (0, 8, 16, 24))


def fourcc_of(s):
    return sum(ord(c) << (8 * i) for i, c in enumerate(s))


class Device:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)
        self._bufs = []

    def close(self):
        for m in self._bufs:
            m.close()
        self._bufs.clear()
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _io(self, req, arg):
        fcntl.ioctl(self.fd, req, arg)
        return arg

    # --- introspection ------------------------------------------------------
    def capability(self):
        return self._io(VIDIOC_QUERYCAP, Capability())

    def formats(self):
        out, i = [], 0
        while True:
            f = FmtDesc(index=i, type=BUF_TYPE_VIDEO_CAPTURE)
            try:
                self._io(VIDIOC_ENUM_FMT, f)
            except OSError:
                return out
            out.append((fourcc(f.pixelformat), f.description.decode()))
            i += 1

    def frame_sizes(self, pixfmt):
        out, i = [], 0
        while True:
            f = FrmSizeEnum(index=i, pixel_format=fourcc_of(pixfmt))
            try:
                self._io(VIDIOC_ENUM_FRAMESIZES, f)
            except OSError:
                return out
            if f.type != 1:               # only discrete matters for a webcam
                return out
            out.append((f.u.discrete.width, f.u.discrete.height))
            i += 1

    def frame_intervals(self, pixfmt, w, h):
        out, i = [], 0
        while True:
            f = FrmIvalEnum(index=i, pixel_format=fourcc_of(pixfmt), width=w, height=h)
            try:
                self._io(VIDIOC_ENUM_FRAMEINTERVALS, f)
            except OSError:
                return out
            if f.type != 1:
                return out
            d = f.u.discrete
            out.append(d.denominator / d.numerator if d.numerator else 0)
            i += 1

    def controls(self):
        """Walk the driver's own list rather than probing known CIDs, so
        vendor-private controls show up too."""
        out, cid = [], 0
        while True:
            q = QueryCtrl(id=cid | CTRL_FLAG_NEXT_CTRL)
            try:
                self._io(VIDIOC_QUERYCTRL, q)
            except OSError:
                return out
            cid = q.id
            entry = {"id": q.id, "name": q.name.decode(),
                     "type": CTRL_TYPE.get(q.type, str(q.type)),
                     "min": q.minimum, "max": q.maximum, "step": q.step,
                     "default": q.default_value, "flags": q.flags}
            if q.type == 3:
                entry["menu"] = self._menu(q)
            out.append(entry)

    def _menu(self, q):
        items = {}
        for idx in range(q.minimum, q.maximum + 1):
            m = QueryMenu(id=q.id, index=idx)
            try:
                self._io(VIDIOC_QUERYMENU, m)
            except OSError:
                continue
            items[idx] = m.name.decode(errors="replace")
        return items

    def get(self, cid):
        return self._io(VIDIOC_G_CTRL, Control(id=cid)).value

    def set(self, cid, value):
        self._io(VIDIOC_S_CTRL, Control(id=cid, value=value))

    # --- capture ------------------------------------------------------------
    def configure(self, pixfmt, width, height):
        f = Format(type=BUF_TYPE_VIDEO_CAPTURE)
        f.pix.width, f.pix.height = width, height
        f.pix.pixelformat = fourcc_of(pixfmt)
        f.pix.field = 1                                     # NONE (progressive)
        self._io(VIDIOC_S_FMT, f)
        return fourcc(f.pix.pixelformat), f.pix.width, f.pix.height, f.pix.sizeimage

    def start(self, nbufs=4):
        self._io(VIDIOC_REQBUFS, RequestBuffers(count=nbufs,
                                                type=BUF_TYPE_VIDEO_CAPTURE,
                                                memory=MEMORY_MMAP))
        for i in range(nbufs):
            b = self._io(VIDIOC_QUERYBUF, Buffer(index=i, type=BUF_TYPE_VIDEO_CAPTURE,
                                                 memory=MEMORY_MMAP))
            self._bufs.append(mmap.mmap(self.fd, b.length,
                                        mmap.MAP_SHARED,
                                        mmap.PROT_READ | mmap.PROT_WRITE,
                                        offset=b.m_offset))
            self._io(VIDIOC_QBUF, Buffer(index=i, type=BUF_TYPE_VIDEO_CAPTURE,
                                         memory=MEMORY_MMAP))
        self._io(VIDIOC_STREAMON, i32(BUF_TYPE_VIDEO_CAPTURE))

    def grab(self):
        b = self._io(VIDIOC_DQBUF, Buffer(type=BUF_TYPE_VIDEO_CAPTURE,
                                          memory=MEMORY_MMAP))
        data = self._bufs[b.index][:b.bytesused]
        self._io(VIDIOC_QBUF, Buffer(index=b.index, type=BUF_TYPE_VIDEO_CAPTURE,
                                     memory=MEMORY_MMAP))
        return data

    def stop(self):
        self._io(VIDIOC_STREAMOFF, i32(BUF_TYPE_VIDEO_CAPTURE))
        for m in self._bufs:
            m.close()
        self._bufs.clear()
        self._io(VIDIOC_REQBUFS, RequestBuffers(count=0,
                                                type=BUF_TYPE_VIDEO_CAPTURE,
                                                memory=MEMORY_MMAP))
