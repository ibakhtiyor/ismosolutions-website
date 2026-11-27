#!/usr/bin/env python3
"""Local preview of the built site that behaves like GitHub Pages: /page -> page.html,
missing -> 404.html (with status 404); _src/ and dot-folders are hidden.
Run from WSL:  python3 _src/tools/serve.py [port]   (default 8124)"""
import functools, http.server, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import SITE


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        url = self.path.split("?")[0].split("#")[0]
        path = self.translate_path(url)
        hidden = any(part.startswith(("_", ".")) for part in url.split("/") if part)
        if not hidden and os.path.isdir(path) and os.path.isfile(os.path.join(path, "index.html")):
            return super().send_head()
        if not hidden and not os.path.isfile(path) and os.path.isfile(path + ".html"):
            self.path = url + ".html"
            return super().send_head()
        if hidden or not os.path.isfile(path):
            body = open(os.path.join(SITE, "404.html"), "rb").read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return super().send_head()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
    print("Serving %s on http://localhost:%d" % (SITE, port), flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", port), functools.partial(Handler, directory=SITE)).serve_forever()
