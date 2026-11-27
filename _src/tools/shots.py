#!/usr/bin/env python3
"""Full-page preview screenshots of the built site (light and dark) with headless Chrome.
Run from WSL after build.py:  python3 _src/tools/shots.py [page ...]
Serves the site on localhost:8766 and writes C:\\dev\\IsmoSolutions\\preview\\<page>-<width>-<scheme>.png"""
import base64, functools, http.server, os, re, sys, threading
sys.path.insert(0, os.path.dirname(__file__))
from common import PREVIEW, SITE, WORK, chrome, file_url, win
from serve import Handler

PAGES = {"home": "/", "about": "/about", "contact": "/contact", "privacy": "/privacy", "404": "/nope"}
DEFAULT = ["home", "about"]
WIDTHS = [1920, 1366, 390]
SCHEMES = {"light": 1, "dark": 0}   # Blink preferredColorScheme: 0 = dark, 1 = light
PORT = 8766
MIN_WINDOW = 500                    # Chrome won't make a window narrower than this


def wrapper(name, body):
    """Helper pages are served from the work folder via /__w/<name> (same origin, never in the repo)."""
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, name), "w", encoding="utf-8") as f:
        f.write(body)
    return "http://localhost:%d/__w/%s" % (PORT, name)


class ShotHandler(Handler):
    def send_head(self):
        if self.path.startswith("/__w/"):
            data = open(os.path.join(WORK, self.path[5:].split("?")[0]), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        return super().send_head()


def height(path, w, scheme):
    url = wrapper("measure.html", '<!doctype html><body style="margin:0"><iframe id=f src="%s" style="border:0;width:%dpx;height:900px"></iframe>'
                  '<script>f.onload=()=>{setTimeout(()=>{document.title="H="+f.contentDocument.documentElement.scrollHeight},300)}</script>'
                  % (path, w))
    dom = chrome("--virtual-time-budget=8000", "--blink-settings=preferredColorScheme=%d" % scheme,
                 "--window-size=%d,900" % max(w, MIN_WINDOW + 40), "--dump-dom", url)
    m = re.search(r"<title>H=(\d+)</title>", dom)
    return int(m.group(1)) if m else 4000


def narrow(path, w, h, scheme, out):
    """Phone widths: show the page in a w-wide iframe in a wider window, then crop with a canvas."""
    url = wrapper("shot.html", '<!doctype html><body style="margin:0"><iframe src="%s" style="display:block;border:0;width:%dpx;height:%dpx"></iframe>'
                  % (path, w, h))
    full = os.path.join(WORK, "shot-full.png")
    chrome("--window-size=%d,%d" % (MIN_WINDOW + 40, h), "--blink-settings=preferredColorScheme=%d" % scheme,
           "--virtual-time-budget=3000", "--screenshot=" + win(full), url)
    crop = os.path.join(WORK, "crop.html")
    with open(crop, "w") as f:
        f.write('<!doctype html><img id=i src="%s"><pre id=o></pre><script>i.onload=()=>{const c=document.createElement("canvas");'
                'c.width=%d;c.height=i.naturalHeight;c.getContext("2d").drawImage(i,0,0);o.textContent=c.toDataURL("image/png")}</script>'
                % (file_url(full), w))
    dom = chrome("--virtual-time-budget=8000", "--dump-dom", file_url(crop))
    m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", dom)
    if m:
        with open(out, "wb") as f:
            f.write(base64.b64decode(m.group(1)))
    os.remove(full); os.remove(crop)


def main():
    os.makedirs(PREVIEW, exist_ok=True)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), functools.partial(ShotHandler, directory=SITE))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for name in sys.argv[1:] or DEFAULT:
        path = PAGES[name]
        for w in WIDTHS:
            for sname, s in SCHEMES.items():
                h = height(path, w, s)
                out = os.path.join(PREVIEW, "%s-%d-%s.png" % (name, w, sname))
                if os.path.exists(out):
                    os.remove(out)
                if w >= MIN_WINDOW:
                    chrome("--window-size=%d,%d" % (w, h), "--blink-settings=preferredColorScheme=%d" % s,
                           "--virtual-time-budget=3000", "--screenshot=" + win(out), "http://localhost:%d%s" % (PORT, path))
                else:
                    narrow(path, w, h, s, out)
                print("%-26s %dx%d %s" % (os.path.basename(out), w, h, "ok" if os.path.exists(out) else "FAILED"), flush=True)
    srv.shutdown()


if __name__ == "__main__":
    main()
