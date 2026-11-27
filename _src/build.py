#!/usr/bin/env python3
"""Build ismosolutions.com: _src/ -> the repo root (served by GitHub Pages).

Standard library only. On this PC run it from WSL:  wsl -e python3 _src/build.py

  templates/   base page, header, footer
  pages/       page bodies; {{key}} placeholders are filled from strings.txt
  strings.txt  "[key]" on its own line, the value below it ("#" lines are comments)
  static/      copied as-is to the root (logo, icons, og.png, krot.svg)
  style.css    minified and inlined into every page; its sha256 goes into the meta CSP

Placeholders: {{key}} string · {{i:name}} inline icon · {{x:name}} generated block.

GitHub Pages skips folders that start with "_", so _src/ is never published. Every file the
build writes is listed in _src/built.txt; the next build deletes files from that list that it
no longer makes, and nothing else (CNAME, .git and _src/ are never touched).
"""
import base64, gzip, hashlib, html, json, os, re, sys
from datetime import date

SRC = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(SRC)
SITE = "https://ismosolutions.com"
BUDGET = 14 * 1024            # gzip bytes per HTML page (HTML + inlined CSS)
PLAY_URL = "https://play.google.com/store/apps/details?id=app.krot.vpn"
FORM_ACTION = "https://api.web3forms.com/submit"
FORM_KEY = "dfe6542c-331c-4881-89ed-593775add7d0"   # Web3Forms access key: public by design
EMAIL = "hello@ismosolutions.com"

# The Organization object. krotvpn.org carries the identical object (same @id).
ORG = {"@type": "Organization", "@id": SITE + "/#organization", "name": "Ismo Solutions",
       "url": SITE + "/", "logo": SITE + "/logo-512.png", "email": EMAIL,
       "sameAs": ["https://krotvpn.org/", SITE + "/"]}

# id, path, template, flags
PAGES = [
    dict(id="home", path="/", tpl="home", website=1),
    dict(id="about", path="/about", tpl="about"),
    dict(id="contact", path="/contact", tpl="contact"),
    dict(id="privacy", path="/privacy", tpl="privacy"),
    dict(id="thanks", path="/thanks", tpl="thanks", noindex=1),
    dict(id="404", path="/404", tpl="404", noindex=1),
]


def _p(*ds):
    return "".join('<path d="%s"/>' % d for d in ds)


ICONS = {
    "phone": '<rect x="6" y="2" width="12" height="20" rx="3"/>' + _p("M11 18h2"),
    "db": '<ellipse cx="12" cy="5" rx="8" ry="3"/>' + _p("M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"),
    "pen": _p("M12 19l7-7 3 3-7 7-3-3z", "M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z", "M2 2l7.6 7.6") + '<circle cx="11" cy="11" r="2"/>',
    "shield": _p("M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "m9 12 2 2 4-4"),
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/>' + _p("M7 11V7a5 5 0 0 1 10 0v4"),
    "focus": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>',
    "chat": _p("M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"),
    "layers": _p("m12 2 10 5-10 5L2 7z", "m2 17 10 5 10-5", "m2 12 10 5 10-5"),
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/>' + _p("m22 7-10 6L2 7"),
    "arrow": _p("M5 12h14M13 6l6 6-6 6"),
}
PLAY_GLYPH = ('<svg viewBox="0 0 24 24" aria-hidden="true">'
              '<path fill="#4285F4" d="M3.6 1.9 13.4 12 3.6 22.1C3.2 21.9 3 21.5 3 21V3c0-.5.2-.9.6-1.1z"/>'
              '<path fill="#34A853" d="M3.6 1.9c.3-.1.7-.1 1 .1l12.2 6.6-3.4 3.4z"/>'
              '<path fill="#EA4335" d="m3.6 22.1 9.8-10.1 3.4 3.4L4.6 22c-.3.2-.7.2-1 .1z"/>'
              '<path fill="#FBBC04" d="m16.8 8.6 3.6 2c1 .6 1 2.2 0 2.8l-3.6 2-3.4-3.4z"/></svg>')

warnings = []


def icon(name):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>' % ICONS[name])


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(data, bytes):
        with open(path, "wb") as f:
            f.write(data)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)


def load_strings():
    out, key, buf = {}, None, []
    for line in read(os.path.join(SRC, "strings.txt")).splitlines():
        m = re.fullmatch(r"\[([\w.-]+)\]\s*", line)
        if m:
            if key:
                out[key] = "\n".join(buf).strip()
            key, buf = m.group(1), []
        elif key and not line.startswith("#"):
            buf.append(line)
    if key:
        out[key] = "\n".join(buf).strip()
    return out


def minify_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r"\s*:\s*(?=[^{]*;|[^{]*})", ":", css)
    return css.replace(";}", "}").strip()


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


class Renderer:
    def __init__(self, strings, page):
        self.s, self.page = strings, page

    def key(self, k):
        if k.startswith("p."):
            k = self.page["id"] + "." + k[2:]
        if k not in self.s:
            raise KeyError("missing string [%s] (page %s)" % (k, self.page["id"]))
        return self.s[k]

    def fill(self, text):
        for _ in range(6):
            new = re.sub(r"\{\{([^{}]+)\}\}", self._one, text)
            if new == text:
                return new
            text = new
        return text

    def _one(self, m):
        tok = m.group(1).strip()
        kind, _, arg = tok.partition(":")
        if not arg:
            return self.key(tok)
        if kind == "i":
            return icon(arg)
        if kind == "x":
            return getattr(self, "x_" + arg.replace("-", "_"))()
        raise ValueError("unknown placeholder {{%s}}" % tok)

    def x_badge(self):
        href = PLAY_URL or "#TODO-play-url"
        extra = ' rel="noopener"' if PLAY_URL else ' data-todo="play-url"'
        return ('<a class="gp" href="%s"%s>%s<span><small>Get it on</small><b>Google Play</b></span></a>'
                % (href, extra, PLAY_GLYPH))

    def x_email(self):
        return '<a href="mailto:%s">%s</a>' % (EMAIL, EMAIL)

    def x_form(self):
        return read(os.path.join(SRC, "templates", "form.html")).replace("%%ACTION%%", FORM_ACTION) \
            .replace("%%KEY%%", FORM_KEY).replace("%%REDIRECT%%", SITE + "/thanks")

    def x_band(self):
        return ('<section class="band" aria-labelledby="band-h"><div class="c band-g"><div><h2 id="band-h">%s</h2><p>%s</p></div>'
                '<div class="ctas"><a class="btn" href="/contact">%s</a><a class="more" href="mailto:%s">%s</a></div></div></section>'
                % (self.key("band.h2"), self.key("band.p"), self.key("band.cta"), EMAIL, EMAIL))

    def x_year(self):
        return str(date.today().year)


def jsonld(page):
    graph = [ORG]
    if page.get("website"):
        graph.append({"@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/", "name": "Ismo Solutions",
                      "inLanguage": "en", "publisher": {"@id": ORG["@id"]}})
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))
    json.loads(data)
    return '<script type="application/ld+json">%s</script>' % data.replace("</", "<\\/")


def out_file(path):
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    elif not rel.endswith(".html"):
        rel += ".html"
    return rel


def main():
    S = load_strings()
    built = []

    def emit(rel, data):
        write(os.path.join(OUT, rel), data)
        built.append(rel)

    for f in sorted(os.listdir(os.path.join(SRC, "static"))):
        emit(f, open(os.path.join(SRC, "static", f), "rb").read())

    css = minify_css(read(os.path.join(SRC, "style.css")))
    style_hash = "sha256-" + base64.b64encode(hashlib.sha256(css.encode()).digest()).decode()
    # GitHub Pages can't send headers, so the policy goes in a meta tag (frame-ancestors and
    # report-uri are ignored there). No scripts run on this site; JSON-LD is data, not script.
    csp = ("default-src 'none'; img-src 'self'; style-src '%s'; manifest-src 'self'; "
           "form-action 'self' https://api.web3forms.com; base-uri 'none'" % style_hash)
    base = read(os.path.join(SRC, "templates", "base.html"))
    header = read(os.path.join(SRC, "templates", "header.html"))
    footer = read(os.path.join(SRC, "templates", "footer.html"))
    lastmod_path = os.path.join(SRC, "lastmod.json")
    lastmod = json.loads(read(lastmod_path)) if os.path.exists(lastmod_path) else {}
    today = date.today().isoformat()
    sizes, sitemap = [], []

    for page in PAGES:
        R = Renderer(S, page)
        body = read(os.path.join(SRC, "pages", page["tpl"] + ".html"))
        url = page["path"]
        title = R.fill(R.key(page["id"] + ".title"))
        desc = strip_tags(R.fill(R.key(page["id"] + ".desc")))
        if len(title) > 60:
            warnings.append("title > 60 chars (%d) on %s" % (len(title), url))
        if len(desc) > 155:
            warnings.append("description > 155 chars (%d) on %s" % (len(desc), url))
        head = ['<meta http-equiv="Content-Security-Policy" content="%s">' % csp,
                '<title>%s</title>' % html.escape(title),
                '<meta name="description" content="%s">' % html.escape(desc)]
        if page.get("noindex"):
            head.append('<meta name="robots" content="noindex">')
        else:
            head += ['<link rel="canonical" href="%s%s">' % (SITE, url),
                     '<meta property="og:type" content="website">',
                     '<meta property="og:site_name" content="Ismo Solutions">',
                     '<meta property="og:url" content="%s%s">' % (SITE, url),
                     '<meta property="og:title" content="%s">' % html.escape(title),
                     '<meta property="og:description" content="%s">' % html.escape(desc),
                     '<meta property="og:image" content="%s/og.png">' % SITE,
                     '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
                     '<meta property="og:image:alt" content="%s">' % html.escape(R.key("ui.og_alt")),
                     '<meta property="og:locale" content="en_US">',
                     '<meta name="twitter:card" content="summary_large_image">']
        head.append(jsonld(page))
        hdr = R.fill(header)
        if url != "/":
            hdr = hdr.replace('href="%s"' % url, 'href="%s" aria-current="page"' % url)
        doc = R.fill(base).replace("%%HEAD%%", "\n".join(head)).replace("%%CSS%%", css) \
            .replace("%%HEADER%%", hdr).replace("%%MAIN%%", R.fill(body)).replace("%%FOOTER%%", R.fill(footer))
        if "{{" in doc or "%%" in doc:
            sys.exit("unfilled placeholder on %s: %s" % (url, re.search(r"\{\{[^}]*\}\}|%%\w+%%", doc).group(0)))
        if len(re.findall(r"<h1[\s>]", doc)) != 1:
            sys.exit("page %s must have exactly one <h1>" % url)
        rel = out_file(url)
        emit(rel, doc)
        sizes.append((rel, len(doc.encode()), len(gzip.compress(doc.encode(), 9)), title, desc))
        if not page.get("noindex"):
            h = hashlib.sha256(doc.encode()).hexdigest()
            if lastmod.get(rel, [None])[0] != h:
                lastmod[rel] = [h, today]
            sitemap.append((url, lastmod[rel][1]))

    emit("robots.txt", "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)
    emit("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n'
         % "\n".join("<url><loc>%s%s</loc><lastmod>%s</lastmod></url>" % (SITE, u, m) for u, m in sitemap))
    emit("site.webmanifest", json.dumps({
        "name": "Ismo Solutions", "short_name": "Ismo", "start_url": "/", "display": "standalone",
        "background_color": "#F7F7F4", "theme_color": "#0E1A33",
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/logo-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/logo.svg", "sizes": "any", "type": "image/svg+xml"}]}, indent=1) + "\n")

    # Remove files an earlier build made that this build no longer makes.
    list_path = os.path.join(SRC, "built.txt")
    old = read(list_path).split() if os.path.exists(list_path) else []
    for rel in set(old) - set(built):
        p = os.path.join(OUT, rel)
        if os.path.isfile(p) and not rel.startswith(("_", ".")) and rel != "CNAME":
            os.remove(p)
            print("removed stale", rel)
    write(list_path, "\n".join(sorted(built)) + "\n")
    write(lastmod_path, json.dumps(lastmod, indent=1, sort_keys=True) + "\n")
    write(os.path.join(SRC, "pages.tsv"), "file\ttitle\tdescription\n" + "".join(
        "%s\t%s\t%s\n" % (rel, t, d) for rel, _, _, t, d in sizes))

    print("%-16s %7s %6s" % ("page", "bytes", "gzip"))
    over = 0
    for rel, raw, gz, _, _ in sizes:
        flag = "  OVER BUDGET" if gz > BUDGET else ""
        over += bool(flag)
        print("%-16s %7d %6d%s" % (rel, raw, gz, flag))
    print("budget: %d bytes gzip per page" % BUDGET)
    print("CSP style hash: %s" % style_hash)
    if not PLAY_URL:
        warnings.append("PLAY_URL not set: the Google Play badge links to #TODO-play-url")
    todos = sorted(set(re.findall(r'data-todo="([\w-]+)"', "".join(read(os.path.join(OUT, r[0])) for r in sizes))))
    if todos:
        warnings.append("visible TODO placeholders: " + ", ".join(todos))
    for w in warnings:
        print("WARNING:", w)
    if over:
        sys.exit("%d page(s) over the %d-byte gzip budget" % (over, BUDGET))


if __name__ == "__main__":
    main()
