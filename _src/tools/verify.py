#!/usr/bin/env python3
"""Check the built site (the repo root) after build.py. Exit 1 on any problem.
Run from WSL:  python3 _src/tools/verify.py

Checks: HTML nesting, duplicate ids, inline styles, <img> width/height/alt, JSON-LD and the
Organization object, internal links and fragments, banned words, outside resources (only the
Web3Forms POST target is allowed), meta CSP matching the inlined CSS, unique titles and
descriptions, canonical + Open Graph on indexable pages, sitemap URLs, gzip size budget."""
import base64, gzip, hashlib, json, os, re, sys
from html.parser import HTMLParser
sys.path.insert(0, os.path.dirname(__file__))
from common import SITE as OUT

BUDGET = 14 * 1024
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
OPTIONAL = {"p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "option"}
BANNED = (r"russia|росси|bypass|обход|censor|unblock|blocking|firewall|amnezia|wireguard|openvpn|ipsec|"
          r"shadowsocks|vless|vmess|\breality\b|xray|v2ray|trojan|nordvpn|expressvpn|surfshark|proton")
FORM_ACTION = "https://api.web3forms.com/submit"
# Outside links people may click (not resources the page loads).
OK_EXTERNAL = ("https://krotvpn.org/", "https://play.google.com/store/apps/details?id=app.krot.vpn")
ORG = {"@type": "Organization", "@id": "https://ismosolutions.com/#organization", "name": "Ismo Solutions",
       "url": "https://ismosolutions.com/", "logo": "https://ismosolutions.com/logo-512.png",
       "email": "hello@ismosolutions.com", "sameAs": ["https://krotvpn.org/", "https://ismosolutions.com/"]}
problems = []


class P(HTMLParser):
    def __init__(self, name):
        super().__init__(convert_charrefs=True)
        self.name, self.stack, self.ids, self.refs, self.res, self.ld, self._ld = name, [], set(), [], [], [], None
        self.meta, self.links, self.forms, self.styles, self._st = {}, {}, [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "style" in a:
            problems.append("%s: inline style on <%s>" % (self.name, tag))
        if a.get("id"):
            if a["id"] in self.ids:
                problems.append("%s: duplicate id %s" % (self.name, a["id"]))
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.refs.append(a["href"])
        elif tag == "link" and a.get("href"):
            (self.links.setdefault(a.get("rel"), []).append(a["href"]))
            if a.get("rel") != "canonical":
                self.res.append(a["href"])
        for k in ("src", "srcset", "poster", "data"):
            if a.get(k):
                self.res.append(a[k])
        if tag == "img":
            if not ({"width", "height", "alt"} <= set(a)):
                problems.append("%s: <img> without width/height/alt" % self.name)
            if a.get("src", "").endswith((".png", ".jpg", ".jpeg")):
                problems.append("%s: raster image %s should be WebP" % (self.name, a["src"]))
        if tag == "meta":
            k = a.get("name") or a.get("property") or a.get("http-equiv")
            if k:
                self.meta[k] = a.get("content", "")
        if tag == "form":
            self.forms.append(a)
        if tag == "script":
            if a.get("type") == "application/ld+json":
                self._ld = ""
            else:
                problems.append("%s: <script> found (the site runs no JS)" % self.name)
        if tag == "style":
            self._st = ""
        if tag not in VOID:
            self.stack.append(tag)

    def handle_data(self, d):
        if self._ld is not None:
            self._ld += d
        if self._st is not None:
            self._st += d

    def handle_endtag(self, tag):
        if tag == "script" and self._ld is not None:
            self.ld.append(self._ld); self._ld = None
        if tag == "style" and self._st is not None:
            self.styles.append(self._st); self._st = None
        if tag in VOID:
            return
        while self.stack and self.stack[-1] != tag and self.stack[-1] in OPTIONAL:
            self.stack.pop()
        if not self.stack or self.stack[-1] != tag:
            problems.append("%s: unexpected </%s> (open: %s)" % (self.name, tag, "/".join(self.stack[-4:])))
            return
        self.stack.pop()


def resolve(path):
    path = path.split("#")[0].split("?")[0]
    if path == "":
        return True
    f = os.path.join(OUT, path.lstrip("/"))
    if path.endswith("/"):
        return os.path.isfile(os.path.join(f, "index.html"))
    return os.path.isfile(f) or os.path.isfile(f + ".html")


pages = sorted(f for f in os.listdir(OUT) if f.endswith(".html"))
titles, descs, sizes = {}, {}, []
for name in pages:
    doc = open(os.path.join(OUT, name), encoding="utf-8").read()
    p = P(name); p.feed(doc); p.close()
    rest = [t for t in p.stack if t not in OPTIONAL]
    if rest:
        problems.append("%s: unclosed %s" % (name, rest))
    if not doc.startswith("<!doctype html>"):
        problems.append(name + ": no doctype")
    noindex = "noindex" in p.meta.get("robots", "")
    # Title / description
    t = re.search(r"<title>(.*?)</title>", doc)
    t = t.group(1) if t else ""
    d = p.meta.get("description", "")
    if not t or not d:
        problems.append(name + ": missing title or description")
    if t in titles:
        problems.append("%s: title same as %s" % (name, titles[t]))
    if d in descs:
        problems.append("%s: description same as %s" % (name, descs[d]))
    titles[t], descs[d] = name, name
    if not noindex:
        canon = p.links.get("canonical", [""])[0]
        want = "https://ismosolutions.com/" + ("" if name == "index.html" else name[:-5])
        if canon != want:
            problems.append("%s: canonical %r, expected %r" % (name, canon, want))
        for k in ("og:title", "og:description", "og:url", "og:image", "og:type", "twitter:card"):
            if not p.meta.get(k):
                problems.append("%s: missing %s" % (name, k))
    # CSP
    csp = p.meta.get("Content-Security-Policy", "")
    if not csp:
        problems.append(name + ": no meta CSP")
    else:
        if "form-action 'self' https://api.web3forms.com" not in csp:
            problems.append(name + ": CSP form-action does not allow Web3Forms")
        for st in p.styles:
            h = "sha256-" + base64.b64encode(hashlib.sha256(st.encode()).digest()).decode()
            if "'%s'" % h not in csp:
                problems.append(name + ": inline <style> hash not in CSP")
    # JSON-LD
    if not p.ld:
        problems.append(name + ": no JSON-LD")
    for raw in p.ld:
        try:
            g = json.loads(raw)["@graph"]
            assert all("@type" in n for n in g)
            org = [n for n in g if n["@type"] == "Organization"]
            assert org and org[0] == ORG, "Organization object differs from the agreed one"
        except Exception as e:
            problems.append("%s: bad JSON-LD (%s)" % (name, e))
    # Forms
    for f in p.forms:
        if f.get("action") != FORM_ACTION or f.get("method", "").lower() != "post":
            problems.append("%s: form must POST to %s" % (name, FORM_ACTION))
    # Links and resources
    for r in p.refs:
        if r.startswith("#"):
            if r != "#TODO-play-url" and r[1:] not in p.ids:
                problems.append("%s: broken fragment %s" % (name, r))
        elif r.startswith("/#"):
            target = open(os.path.join(OUT, "index.html"), encoding="utf-8").read()
            if 'id="%s"' % r[2:] not in target:
                problems.append("%s: broken link %s" % (name, r))
        elif r.startswith("/") and not r.startswith("//"):
            if not resolve(r):
                problems.append("%s: broken link %s" % (name, r))
        elif r.startswith("mailto:"):
            if "hello@ismosolutions.com" not in r:
                problems.append("%s: unexpected mailto %s" % (name, r))
        elif not r.startswith(OK_EXTERNAL):
            problems.append("%s: outside link not on the allow list: %s" % (name, r))
    for r in p.res:
        if not r.startswith("/") or r.startswith("//"):
            problems.append("%s: outside resource %s" % (name, r))
        elif not resolve(r):
            problems.append("%s: missing resource %s" % (name, r))
    # Words
    text = re.sub(r"<[^>]+>", " ", doc)
    for m in re.finditer(BANNED, text, re.I):
        problems.append("%s: banned word '%s'" % (name, m.group(0)))
    # Size
    gz = len(gzip.compress(doc.encode(), 9))
    sizes.append((name, len(doc.encode()), gz))
    if gz > BUDGET:
        problems.append("%s: %d bytes gzip, over the %d budget" % (name, gz, BUDGET))

# Sitemap: every URL resolves, every indexable page listed.
sm = open(os.path.join(OUT, "sitemap.xml"), encoding="utf-8").read()
locs = re.findall(r"<loc>https://ismosolutions\.com(/[^<]*)</loc>", sm)
for u in locs:
    if not resolve(u):
        problems.append("sitemap: %s does not resolve" % u)
for f in ("CNAME", "robots.txt", "site.webmanifest", "favicon.svg", "favicon-32.png", "apple-touch-icon.png",
          "icon-192.png", "logo-512.png", "og.png", "404.html"):
    if not os.path.isfile(os.path.join(OUT, f)):
        problems.append("missing file " + f)
if open(os.path.join(OUT, "CNAME")).read().strip() != "ismosolutions.com":
    problems.append("CNAME changed")

print("%-16s %7s %6s" % ("page", "bytes", "gzip"))
for n, raw, gz in sizes:
    print("%-16s %7d %6d" % (n, raw, gz))
print("%d pages checked, %d sitemap URLs" % (len(pages), len(locs)))
for x in problems:
    print("PROBLEM:", x)
sys.exit(1 if problems else 0)
