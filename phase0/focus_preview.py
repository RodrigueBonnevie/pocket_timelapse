#!/usr/bin/env python3
"""Live view in a browser, with a 1:1 loupe, for focusing the lens.

focus_assist.py gives a number in a terminal, which confirms a peak but cannot
tell you whether the thing that is sharp is the thing you care about. This
serves the camera's own MJPEG frames straight to a browser - the camera already
produces JPEG, so there is no encoder in the path and nothing to install - with
a magnified 1:1 crop beside them.

The loupe is the point. A 4K frame shown in a browser window is displayed at
perhaps a quarter scale, which throws away exactly the fine detail that
separates sharp from nearly sharp. The loupe samples the frame at one source
pixel per screen pixel, so the difference is visible by eye. It can be moved to
a corner to check for tilt or field curvature, which a centre-only view hides.

Exposure is left automatic on purpose. Focusing happens whenever you happen to
be standing at the camera, including at dusk.

    ./focus_preview.py               # then open http://localhost:8080
    ./focus_preview.py --port 9000

Ctrl-C to stop.
"""

import argparse
import json
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v4l2

WIDTH, HEIGHT = 1920, 1080

PAGE = b"""<!doctype html>
<meta charset="utf-8"><title>Focus</title>
<style>
  :root { --bg:#111; --fg:#eee; --dim:#888; --ok:#4ade80; --line:#4ade80; }
  * { box-sizing:border-box }
  body { margin:0; background:var(--bg); color:var(--fg); font:13px/1.4
         ui-monospace,SFMono-Regular,Menlo,monospace; }
  .wrap { display:flex; flex-direction:column; height:100vh }
  .stage { position:relative; flex:1; min-height:0 }
  .stage img { width:100%; height:100%; object-fit:contain; background:#000; display:block }
  #box { position:absolute; border:1px solid var(--line); box-shadow:0 0 0 9999px rgba(0,0,0,.35);
         pointer-events:none }
  .hud { display:flex; align-items:center; gap:16px; padding:10px 14px;
         border-top:1px solid #333; flex-wrap:wrap }
  canvas { background:#000; border:1px solid #333; image-rendering:pixelated }
  .col { display:flex; flex-direction:column; gap:6px }
  .now { font-size:34px; font-weight:700; font-variant-numeric:tabular-nums; line-height:1 }
  .best { color:var(--dim); font-variant-numeric:tabular-nums }
  .peak { color:var(--ok) }
  .bar { width:100%; height:18px; background:#222; border-radius:3px; overflow:hidden }
  .fill { height:100%; width:0; background:var(--ok); transition:width .08s linear }
  .grow { flex:1; min-width:180px }
  button { background:#2a2a2a; color:var(--fg); border:1px solid #555; border-radius:3px;
           padding:6px 10px; font:inherit; cursor:pointer }
  button:hover { background:#3a3a3a }
  button.on { background:var(--ok); color:#000; border-color:var(--ok) }
  .lbl { color:var(--dim); margin-right:2px }
</style>
<div class="wrap">
  <div class="stage"><img id="live" src="/stream"><div id="box"></div></div>
  <div class="hud">
    <canvas id="loupe" width="320" height="320"></canvas>
    <div class="col grow">
      <div><span class="now" id="now">--</span> <span class="best" id="best">best --</span></div>
      <div class="bar"><div class="fill" id="fill"></div></div>
      <div>
        <span class="lbl">where</span>
        <button data-a="c" class="on">centre</button><button data-a="tl">TL</button
        ><button data-a="tr">TR</button><button data-a="bl">BL</button
        ><button data-a="br">BR</button>
        <span class="lbl" style="margin-left:10px">zoom</span>
        <button data-z="1" class="on">1:1</button><button data-z="2">2x</button
        ><button data-z="4">4x</button>
        <button id="reset" style="margin-left:10px">reset peak</button>
      </div>
    </div>
  </div>
</div>
<script>
const img = document.getElementById('live'), cv = document.getElementById('loupe');
const ctx = cv.getContext('2d', {willReadFrequently:true});
const box = document.getElementById('box');
const C = cv.width;
let anchor = 'c', zoom = 1, best = 0, smooth = null;
ctx.imageSmoothingEnabled = false;

function sel(attr, val) {
  document.querySelectorAll('button['+attr+']').forEach(b =>
    b.classList.toggle('on', b.getAttribute(attr) === String(val)));
  if (attr === 'data-a') anchor = val; else zoom = +val;
  best = 0;                                  // a new region has its own scale
}
document.querySelectorAll('button[data-a]').forEach(b =>
  b.onclick = () => sel('data-a', b.dataset.a));
document.querySelectorAll('button[data-z]').forEach(b =>
  b.onclick = () => sel('data-z', b.dataset.z));
document.getElementById('reset').onclick = () => { best = 0; };

// Source rectangle in frame pixels for the current anchor and zoom.
function region() {
  const W = img.naturalWidth, H = img.naturalHeight;
  if (!W) return null;
  const s = Math.min(Math.round(C / zoom), W, H);       // source square
  const m = Math.round(Math.min(W, H) * 0.04);          // keep corners off the edge
  const pos = {
    c:  [(W - s) / 2, (H - s) / 2],
    tl: [m, m],            tr: [W - s - m, m],
    bl: [m, H - s - m],    br: [W - s - m, H - s - m],
  }[anchor];
  return {x: Math.round(pos[0]), y: Math.round(pos[1]), s: s, W: W, H: H};
}

// Gradient energy on the loupe pixels themselves - full resolution, not a
// downscaled copy, which is the whole reason this is more sensitive than a
// metric computed on the streamed frame.
function measure() {
  const d = ctx.getImageData(0, 0, C, C).data;
  let sum = 0, n = 0;
  const st = 2;
  for (let y = 0; y < C - st; y += st) {
    for (let x = 0; x < C - st; x += st) {
      const i = (y * C + x) * 4, j = (y * C + x + st) * 4, k = ((y + st) * C + x) * 4;
      const a = d[i] * .299 + d[i+1] * .587 + d[i+2] * .114;
      const b = d[j] * .299 + d[j+1] * .587 + d[j+2] * .114;
      const c = d[k] * .299 + d[k+1] * .587 + d[k+2] * .114;
      sum += (b - a) * (b - a) + (c - a) * (c - a); n++;
    }
  }
  return n ? Math.sqrt(sum / n) : 0;
}

// Place the region indicator over the letterboxed image, which object-fit
// centres rather than stretching.
function placeBox(r) {
  const rect = img.getBoundingClientRect(), ar = r.W / r.H;
  let w = rect.width, h = rect.width / ar;
  if (h > rect.height) { h = rect.height; w = rect.height * ar; }
  const ox = (rect.width - w) / 2, oy = (rect.height - h) / 2, k = w / r.W;
  box.style.left = (ox + r.x * k) + 'px';  box.style.top = (oy + r.y * k) + 'px';
  box.style.width = (r.s * k) + 'px';      box.style.height = (r.s * k) + 'px';
}

function tick() {
  const r = region();
  if (r) {
    ctx.drawImage(img, r.x, r.y, r.s, r.s, 0, 0, C, C);
    placeBox(r);
    const s = measure();
    smooth = smooth === null ? s : 0.7 * smooth + 0.3 * s;
    best = Math.max(best, smooth);
    now.textContent = smooth.toFixed(2);
    best_.textContent = 'best ' + best.toFixed(2);
    fill.style.width = (best ? 100 * smooth / best : 0) + '%';
    now.className = 'now' + (smooth >= best - 0.01 ? ' peak' : '');
  }
  requestAnimationFrame(tick);
}
const now = document.getElementById('now'), best_ = document.getElementById('best');
const fill = document.getElementById('fill');
requestAnimationFrame(tick);
</script>
"""


class Shared:
    """One slot the capture thread fills and the HTTP threads read."""

    def __init__(self):
        self.new = threading.Condition()
        self.frame = None
        self.seq = 0
        self.running = True

    def publish(self, frame):
        with self.new:
            self.frame = frame
            self.seq += 1
            self.new.notify_all()

    def wait_for(self, seen, timeout=5.0):
        with self.new:
            if self.seq == seen:
                self.new.wait(timeout)
            return self.frame, self.seq


def capture(dev, shared):
    """Pure relay. The sharpness metric moved into the browser, so nothing here
    decodes a frame - which is why the stream runs faster than it used to."""
    with v4l2.Device(dev) as cam:
        fcc, w, h, _ = cam.configure("MJPG", WIDTH, HEIGHT)
        cam.set(v4l2.CID_EXPOSURE_AUTO, 3)          # Aperture Priority = camera's own AE
        cam.set(v4l2.CID_AUTO_WHITE_BALANCE, 1)
        cam.start()
        print(f"streaming {fcc} {w}x{h}, exposure automatic")
        while shared.running:
            shared.publish(cam.grab())
        cam.stop()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
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
            pass


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
    threading.Thread(target=capture, args=(dev, shared), daemon=True).start()

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
