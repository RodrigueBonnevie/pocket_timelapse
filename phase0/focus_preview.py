#!/usr/bin/env python3
"""Live view in a browser, with a sharpness readout, for focusing the lens.

focus_assist.py gives you a number in a terminal, which is fine for confirming
a peak but useless for the part that actually matters: seeing whether the thing
you care about is the thing that is sharp. This serves the camera's own MJPEG
frames straight to a browser - the camera already produces JPEG, so there is no
encoder in the path and nothing to install - with the sharpness metric beside
them.

Exposure is left automatic on purpose. Focusing happens whenever you happen to
be standing at the camera, including at dusk, and a locked exposure just makes
the picture too dark to judge.

    ./focus_preview.py               # then open http://localhost:8080
    ./focus_preview.py --port 9000

Ctrl-C to stop.
"""

import argparse
import io
import json
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2
from PIL import Image, ImageFilter, ImageStat

WIDTH, HEIGHT = 1920, 1080     # enough detail to judge focus, fast enough to feel live
SHARPNESS_EVERY = 3            # frames; the edge filter is the expensive part

PAGE = b"""<!doctype html>
<meta charset="utf-8"><title>Focus</title>
<style>
  :root { --bg:#111; --fg:#eee; --dim:#888; --ok:#4ade80; }
  * { box-sizing:border-box }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.4
         ui-monospace,SFMono-Regular,Menlo,monospace; }
  .wrap { display:flex; flex-direction:column; height:100vh }
  img { flex:1; min-height:0; width:100%; object-fit:contain; background:#000 }
  .hud { display:flex; align-items:center; gap:24px; padding:12px 16px;
         border-top:1px solid #333; flex-wrap:wrap }
  .now { font-size:40px; font-weight:700; font-variant-numeric:tabular-nums }
  .best { color:var(--dim); font-variant-numeric:tabular-nums }
  .peak { color:var(--ok) }
  .bar { flex:1; min-width:200px; height:22px; background:#222; border-radius:3px;
         overflow:hidden }
  .fill { height:100%; width:0; background:var(--ok); transition:width .08s linear }
  button { background:#333; color:var(--fg); border:1px solid #555; border-radius:3px;
           padding:8px 14px; font:inherit; cursor:pointer }
  button:hover { background:#444 }
</style>
<div class="wrap">
  <img src="/stream">
  <div class="hud">
    <div class="now" id="now">--</div>
    <div class="bar"><div class="fill" id="fill"></div></div>
    <div class="best" id="best">best --</div>
    <button onclick="fetch('/reset')">reset peak</button>
  </div>
</div>
<script>
setInterval(async () => {
  const r = await fetch('/stat'); const d = await r.json();
  now.textContent = d.sharp.toFixed(2);
  best.textContent = 'best ' + d.best.toFixed(2);
  fill.style.width = (d.best ? 100 * d.sharp / d.best : 0) + '%';
  now.className = 'now' + (d.sharp >= d.best - 0.01 ? ' peak' : '');
}, 100);
</script>
"""


class Shared:
    """One slot the capture thread fills and the HTTP threads read."""

    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.seq = 0
        self.new = threading.Condition(self.lock)
        self.sharp = 0.0
        self.best = 0.0
        self.running = True

    def publish(self, frame, sharp):
        with self.new:
            self.frame = frame
            self.seq += 1
            if sharp is not None:
                self.sharp = sharp
                self.best = max(self.best, sharp)
            self.new.notify_all()

    def wait_for(self, seen, timeout=5.0):
        with self.new:
            if self.seq == seen:
                self.new.wait(timeout)
            return self.frame, self.seq


def sharpness(jpeg):
    """Edge energy on a centre crop. Absolute value is meaningless; only the
    peak as you turn the barrel matters, which is what the bar shows."""
    im = Image.open(io.BytesIO(jpeg))
    im.draft("L", (960, 540))
    im = im.convert("L")
    w, h = im.size
    centre = im.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
    return ImageStat.Stat(centre.filter(ImageFilter.FIND_EDGES)).stddev[0]


def capture(dev, shared):
    with v4l2.Device(dev) as cam:
        fcc, w, h, _ = cam.configure("MJPG", WIDTH, HEIGHT)
        # Everything automatic: this is for focusing, not for measuring.
        cam.set(v4l2.CID_EXPOSURE_AUTO, 3)          # Aperture Priority = camera's own AE
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 1)
        cam.start()
        print(f"streaming {fcc} {w}x{h}, exposure automatic")
        n = 0
        smooth = None
        while shared.running:
            frame = cam.grab()
            s = None
            if n % SHARPNESS_EVERY == 0:
                raw = sharpness(frame)
                smooth = raw if smooth is None else 0.7 * smooth + 0.3 * raw
                s = smooth
            shared.publish(frame, s)
            n += 1
        cam.stop()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass                                        # the bar is the output, not a log

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
        elif self.path == "/stat":
            with self.server.shared.lock:
                body = json.dumps({"sharp": self.server.shared.sharp,
                                   "best": self.server.shared.best}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/reset":
            with self.server.shared.lock:
                self.server.shared.best = 0.0
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/stream":
            self.stream()
        else:
            self.send_error(404)

    def stream(self):
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=FRAME")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        seen = 0
        try:
            while self.server.shared.running:
                frame, seen = self.server.shared.wait_for(seen)
                if frame is None:
                    continue
                self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\n"
                                 b"Content-Length: " + str(len(frame)).encode() +
                                 b"\r\n\r\n" + frame + b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass                                    # browser closed the tab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--device")
    args = ap.parse_args()

    try:
        dev = args.device or str(next(Path("/dev/v4l/by-id").glob("*Arducam*index0")))
    except StopIteration:
        sys.exit("No Arducam found under /dev/v4l/by-id.")

    shared = Shared()
    try:
        worker = threading.Thread(target=capture, args=(dev, shared), daemon=True)
        worker.start()
    except OSError as e:
        sys.exit(f"Could not open {dev}: {e}")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.shared = shared
    server.daemon_threads = True

    def bye(*_):
        shared.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)

    print(f"\n  open  http://localhost:{args.port}\n\n  Ctrl-C to stop.\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
