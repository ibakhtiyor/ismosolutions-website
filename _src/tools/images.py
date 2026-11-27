#!/usr/bin/env python3
"""Make the PNG icons and the OG image from static/logo.svg, using headless Chrome.

Run from WSL:  python3 _src/tools/images.py
Writes into _src/static/: favicon-32.png, apple-touch-icon.png, icon-192.png, logo-512.png, og.png.
Only needed when the logo or the OG design changes; the outputs are kept in the repo.
"""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from common import SRC, WORK, chrome, file_url, win

STATIC = os.path.join(SRC, "static")
FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif"


def shot(work, name, w, h, body):
    page = os.path.join(work, name + ".html")
    with open(page, "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;width:%dpx;height:%dpx;overflow:hidden}</style>%s'
                % (w, h, body))
    out = os.path.join(STATIC, name)
    chrome("--window-size=%d,%d" % (w, h), "--default-background-color=00000000", "--screenshot=" + win(out), file_url(page))
    print("%-22s %dx%d %7d bytes" % (name, w, h, os.path.getsize(out)))


def main():
    os.makedirs(WORK, exist_ok=True)
    work = tempfile.mkdtemp(prefix="img-", dir=WORK)
    logo = open(os.path.join(STATIC, "logo.svg"), encoding="utf-8").read().strip()
    full = logo.replace("<svg ", '<svg width="100%" height="100%" ', 1)
    for name, size in (("favicon-32.png", 32), ("icon-192.png", 192), ("logo-512.png", 512)):
        shot(work, name, size, size, '<div style="width:%dpx;height:%dpx">%s</div>' % (size, size, full))
    # Apple touch icon: iOS adds its own rounded corners, so fill the square with the gradient.
    shot(work, "apple-touch-icon.png", 180, 180,
         '<div style="width:180px;height:180px;background:linear-gradient(135deg,#6366f1,#22d3ee)">%s</div>'
         % full.replace('rx="15"', 'rx="0"'))
    # OG image: calm card in the site's light palette.
    shot(work, "og.png", 1200, 630, """
<div style="width:1200px;height:630px;box-sizing:border-box;padding:88px 96px;background:#F7F7F4;color:#0E1A33;
font-family:%s;display:flex;flex-direction:column;justify-content:space-between;position:relative">
 <div style="display:flex;align-items:center;gap:22px;font-size:40px;font-weight:700;letter-spacing:-.02em">
  <div style="width:84px;height:84px">%s</div>Ismo Solutions</div>
 <div style="font-size:92px;font-weight:700;letter-spacing:-.045em;line-height:1;max-width:980px">We build software people trust.</div>
 <div style="display:flex;justify-content:space-between;align-items:center;font-size:28px;color:#4D5A72">
  <span>ismosolutions.com</span><span>Makers of Krot VPN</span></div>
 <div style="position:absolute;left:0;right:0;bottom:0;height:12px;background:linear-gradient(120deg,#6366f1,#22d3ee)"></div>
</div>""" % (FONT, full))
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
