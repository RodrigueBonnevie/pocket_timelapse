"""UVC Extension Unit access, pure stdlib.

The standard V4L2 controls only reach what the UVC spec defines. Vendor
silicon hides the rest behind an extension unit, which the kernel exposes
raw via UVCIOC_CTRL_QUERY -- no mapping, no v4l2-ctl, no libuvc.
"""

import ctypes as C
import fcntl

SET_CUR, GET_CUR, GET_MIN, GET_MAX = 0x01, 0x81, 0x82, 0x83
GET_RES, GET_LEN, GET_INFO, GET_DEF = 0x84, 0x85, 0x86, 0x87

QUERY_NAME = {SET_CUR: "SET_CUR", GET_CUR: "GET_CUR", GET_MIN: "GET_MIN",
              GET_MAX: "GET_MAX", GET_RES: "GET_RES", GET_LEN: "GET_LEN",
              GET_INFO: "GET_INFO", GET_DEF: "GET_DEF"}


class XuQuery(C.Structure):
    _fields_ = [("unit", C.c_uint8), ("selector", C.c_uint8),
                ("query", C.c_uint8), ("size", C.c_uint16),
                ("data", C.POINTER(C.c_uint8))]


assert C.sizeof(XuQuery) == 16

UVCIOC_CTRL_QUERY = (3 << 30) | (C.sizeof(XuQuery) << 16) | (ord("u") << 8) | 0x21


def query(fd, unit, selector, code, size, payload=None):
    buf = (C.c_uint8 * size)(*(payload or b"\0" * size))
    q = XuQuery(unit=unit, selector=selector, query=code, size=size,
                data=C.cast(buf, C.POINTER(C.c_uint8)))
    fcntl.ioctl(fd, UVCIOC_CTRL_QUERY, q)
    return bytes(buf)


def length(fd, unit, selector):
    """GET_LEN answers in 2 bytes and is the only way to size the rest."""
    return int.from_bytes(query(fd, unit, selector, GET_LEN, 2), "little")


def info(fd, unit, selector):
    return query(fd, unit, selector, GET_INFO, 1)[0]


def describe_info(bits):
    names = [(0x01, "get"), (0x02, "set"), (0x04, "disabled"),
             (0x08, "autoupdate"), (0x10, "async")]
    return ",".join(n for b, n in names if bits & b) or "none"


# --- Sonix ASIC register window (extension unit 3, selector 1) -------------
# Protocol per Kurokesu's SONiX_UVC_TestAP: a read is a dummy SET_CUR of the
# address with cmd 0xFF, then a GET_CUR that returns the byte in slot 2.

SONIX_UNIT = 3
SONIX_ASIC_RW = 1


def asic_read(fd, addr):
    pkt = bytes((addr & 0xFF, (addr >> 8) & 0xFF, 0x00, 0xFF))
    query(fd, SONIX_UNIT, SONIX_ASIC_RW, SET_CUR, 4, pkt)
    return query(fd, SONIX_UNIT, SONIX_ASIC_RW, GET_CUR, 4)[2]


def asic_write(fd, addr, val):
    pkt = bytes((addr & 0xFF, (addr >> 8) & 0xFF, val & 0xFF, 0x00))
    query(fd, SONIX_UNIT, SONIX_ASIC_RW, SET_CUR, 4, pkt)
