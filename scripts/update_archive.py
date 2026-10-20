#!/usr/bin/env python3
"""Rebuild the post lists on theloadout.fyi from Substack's public archive.

Fetches every public post from theloadoutai.substack.com and rewrites only the
HTML between the AUTO marker comments in:
  index.html           <!-- AUTO:latest-feature:start --> ... :end -->
  features/index.html  <!-- AUTO:features-list:start --> ... :end -->
  archive/index.html   <!-- AUTO:archive-list:start --> ... :end -->

It also rewrites sitemap.xml: the fixed pages plus every features/<slug>/index.html
it finds (folders starting with "_", like _template, and pages marked noindex are
skipped). lastmod is the newer of the page's last human commit (bot commits are
ignored, so the bot's own commits don't bump dates) and the newest post that page
lists. Feature pages that name a Substack post in
<meta name="loadout:substack-url" content="..."> get an extra "Quick summary" link
in the post lists.

Nothing else in those files is touched. If the fetch fails, returns zero posts,
or a marker is missing, the script exits without writing anything.
Stdlib only. Run from anywhere: python3 scripts/update_archive.py
Add --dry-run to see what would change (with a diff) without writing anything.
"""
import html, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PUB = "https://theloadoutai.substack.com"
API = PUB + "/api/v1/archive?sort=new&limit={limit}&offset={offset}"
PAGE = 50
MAX_PAGES = 60  # 3,000 posts; a safety stop, not a real limit
TZ = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES = os.path.join(ROOT, "data", "feature-notes.json")
WPM = 230
SITE = "https://theloadout.fyi"
SITEMAP = os.path.join(ROOT, "sitemap.xml")
# Fixed pages for the sitemap: (path on the site, file in the repo).
STATIC_PAGES = [("/", "index.html"), ("/features/", "features/index.html"),
                ("/archive/", "archive/index.html"), ("/privacy/", "privacy/index.html")]

# Section/tag slugs that map to each label. Add a "breaking" section or tag on
# Substack and posts in it show up as Breaking automatically.
FEATURE_KEYS = {"features", "feature"}
BREAKING_KEYS = {"breaking", "breaking-news", "special-edition"}
LABELS = {"issue": "Issue", "feature": "Feature", "breaking": "Breaking"}


def warn(msg):
    # Shows as a yellow annotation in GitHub Actions, plain text locally.
    print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "warning: ") + msg)


def fetch_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "theloadout.fyi archive updater (+https://theloadout.fyi)",
                "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status != 200:
                    raise RuntimeError("HTTP %s" % r.status)
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network, HTTP, JSON
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError("fetch failed for %s: %s" % (url, last))


def fetch_posts():
    posts, seen = [], set()
    for n in range(MAX_PAGES):
        batch = fetch_json(API.format(limit=PAGE, offset=n * PAGE))
        if not isinstance(batch, list):
            raise RuntimeError("unexpected API response (not a list)")
        for p in batch:
            if isinstance(p, dict) and p.get("id") not in seen:
                seen.add(p.get("id"))
                posts.append(p)
        if len(batch) < PAGE:
            break
    return posts


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def kind_of(p):
    keys = {slugify(p.get("section_slug")), slugify(p.get("section_name"))}
    for t in p.get("postTags") or []:
        if isinstance(t, dict):
            keys |= {slugify(t.get("slug")), slugify(t.get("name"))}
    if keys & BREAKING_KEYS or re.match(r"\s*breaking\b", p.get("title") or "", re.I):
        return "breaking"
    if keys & FEATURE_KEYS:
        return "feature"
    return "issue"


def short(text, limit=170):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.-–— ")
    return cut + "…"


def clean(p):
    """Return a normalized post dict, or None if it shouldn't be listed."""
    if p.get("type") not in ("newsletter", "podcast"):
        return None  # skip threads, notes-style posts, etc.
    title, slug, date = p.get("title"), p.get("slug"), p.get("post_date")
    if not (title and slug and date):
        return None
    url = p.get("canonical_url") or ""
    if not url.startswith("https://"):
        url = "%s/p/%s" % (PUB, slug)
    try:
        dt = datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return None
    kind = kind_of(p)
    words = p.get("wordcount") or 0
    return {
        "kind": kind, "title": title.strip(), "slug": slug, "url": url, "dt": dt,
        "summary": short(p.get("subtitle") or p.get("description")
                         or p.get("search_engine_description") or p.get("truncated_body_text")),
        # Read time only for long reads; daily issues are "about 3 minutes" by design and
        # Substack's wordcount includes link lists, which would overstate them.
        "mins": max(1, round(words / WPM)) if kind != "issue" and words else None,
    }


e = lambda s: html.escape(s or "", quote=True)      # attributes
t = lambda s: html.escape(s or "", quote=False)     # text


def meta(p):
    parts = ['<span class="type%s">%s</span>' % (" breaking" if p["kind"] == "breaking" else "", LABELS[p["kind"]]),
             "<span>%s</span>" % p["dt"].strftime("%b %-d, %Y")]
    if p["mins"]:
        parts.append("<span>%d min read</span>" % p["mins"])
    return '<div class="sec">%s</div>' % "".join(parts)


def row(p, notes=None, link_text="Read it on Substack", ind="  ", local=None):
    out = ['%s<article class="row fi" data-type="%s">' % (ind, p["kind"]),
           "%s %s" % (ind, meta(p)),
           "%s <div>" % ind,
           '%s  <h3><a href="%s" rel="noopener">%s</a></h3>' % (ind, e(p["url"]), t(p["title"]))]
    if p["summary"]:
        out.append('%s  <p class="dek">%s</p>' % (ind, t(p["summary"])))
    if notes and notes.get(p["slug"]):
        out.append('%s  <p class="inside">%s</p>' % (ind, t(notes[p["slug"]])))
    links = '<a href="%s" rel="noopener">%s</a>' % (e(p["url"]), t(link_text))
    if local and local.get(p["url"]):
        links += '<a href="%s">Quick summary</a>' % e(local[p["url"]])
    out += ['%s  <p class="go">%s</p>' % (ind, links),
            "%s </div>" % ind, "%s</article>" % ind]
    return "\n".join(out)


def splice(text, name, body):
    pat = re.compile(r"(<!-- AUTO:%s:start[^>]*-->\n)(.*?)(\n?[ \t]*<!-- AUTO:%s:end -->)" % (name, name), re.S)
    if len(pat.findall(text)) != 1:
        raise RuntimeError("marker AUTO:%s missing or duplicated" % name)
    return pat.sub(lambda m: m.group(1) + body + "\n" + m.group(3).lstrip("\n"), text)


def git_date(rel):
    """Date of the last non-bot commit touching rel, or None (no git, uncommitted file)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--invert-grep", "--grep=[bot]",
                              "--fixed-strings", "--", rel], cwd=ROOT, capture_output=True,
                             text=True, timeout=20).stdout.strip()
        return datetime.fromisoformat(out).astimezone(TZ).date() if out else None
    except Exception:
        return None


def feature_pages():
    """Local feature pages: [(site path, repo file, substack url or None)], sorted by slug."""
    found, base = [], os.path.join(ROOT, "features")
    for slug in sorted(os.listdir(base)):
        rel = "features/%s/index.html" % slug
        path = os.path.join(ROOT, rel)
        if slug.startswith(("_", ".")) or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            head = f.read().split("</head>", 1)[0]
        if re.search(r'<meta\s+name="robots"\s+content="[^"]*noindex', head, re.I):
            continue
        m = re.search(r'<meta\s+name="loadout:substack-url"\s+content="([^"]+)"', head)
        found.append(("/features/%s/" % slug, rel, html.unescape(m.group(1)) if m else None))
    return found


def sitemap(posts, longs, features, pages):
    newest = lambda ps: ps[0]["dt"].date() if ps else None
    content = {"/": newest(features), "/features/": newest(longs), "/archive/": newest(posts)}
    old = {}
    try:  # fallback when git can't date a file: keep what the sitemap already says
        with open(SITEMAP, encoding="utf-8") as f:
            old = dict(re.findall(r"<loc>%s([^<]*)</loc>\s*<lastmod>([^<]+)</lastmod>" % re.escape(SITE), f.read()))
    except OSError:
        pass
    urls = []
    for loc, rel in STATIC_PAGES + [(loc, rel) for loc, rel, _ in pages]:
        dates = [d for d in (git_date(rel), content.get(loc)) if d]
        day = max(dates).isoformat() if dates else old.get(loc) or datetime.now(TZ).date().isoformat()
        urls.append("  <url>\n    <loc>%s%s</loc>\n    <lastmod>%s</lastmod>\n  </url>" % (SITE, e(loc), day))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            "<!-- Generated by scripts/update_archive.py; edits here get overwritten. -->\n"
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % "\n".join(urls))


def main():
    try:
        raw = fetch_posts()
    except Exception as ex:
        warn("Substack fetch failed, leaving the site as is (%s)" % ex)
        return 0
    posts = sorted(filter(None, map(clean, raw)), key=lambda p: p["dt"], reverse=True)
    if not posts:
        warn("Substack returned zero posts, leaving the site as is")
        return 0
    try:
        with open(NOTES, encoding="utf-8") as f:
            notes = json.load(f)
    except (OSError, ValueError):
        notes = {}

    try:
        pages = feature_pages()
    except Exception as ex:
        warn("not updating: can't read feature pages (%s)" % ex)
        return 1
    local = {url: loc for loc, _, url in pages if url}

    longs = [p for p in posts if p["kind"] in ("feature", "breaking")]
    features = [p for p in posts if p["kind"] == "feature"]
    if features:
        latest = row(features[0], link_text="Read the feature", local=local)
    else:
        latest = '  <p class="empty">The first feature is on its way.</p>'
    blocks = {
        "index.html": {"latest-feature": latest},
        "features/index.html": {"features-list": "\n".join(row(p, notes, local=local) for p in longs)},
        "archive/index.html": {"archive-list": "\n".join(row(p) for p in posts)},
    }

    new = {}
    try:
        for rel, parts in blocks.items():
            path = os.path.join(ROOT, rel)
            with open(path, encoding="utf-8") as f:
                old = f.read()
            text = old
            for name, body in parts.items():
                text = splice(text, name, body)
            if text != old:
                new[path] = text
        text = sitemap(posts, longs, features, pages)
        try:
            with open(SITEMAP, encoding="utf-8") as f:
                old = f.read()
        except OSError:
            old = None
        if text != old:
            new[SITEMAP] = text
    except Exception as ex:
        warn("not updating: %s" % ex)
        return 1
    if "--dry-run" in sys.argv[1:]:
        import difflib
        for path, text in new.items():
            rel = os.path.relpath(path, ROOT)
            try:
                with open(path, encoding="utf-8") as f:
                    before = f.read().splitlines(True)
            except OSError:
                before = []
            sys.stdout.writelines(difflib.unified_diff(before, text.splitlines(True), "a/" + rel, "b/" + rel))
        print("dry run: %d posts (%d features); would update %s" % (
            len(posts), len(features), ", ".join(os.path.relpath(p, ROOT) for p in new) or "nothing"))
        return 0
    for path, text in new.items():  # write only after every file rendered cleanly
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    print("%d posts (%d features, %d breaking); %s" % (
        len(posts), len(features), len(longs) - len(features),
        ("updated " + ", ".join(os.path.relpath(p, ROOT) for p in new)) if new else "no changes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
