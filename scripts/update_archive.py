#!/usr/bin/env python3
"""Rebuild the post lists on theloadout.fyi from Substack's public archive.

Fetches every public post from theloadoutai.substack.com and rewrites only the
HTML between the AUTO marker comments in:
  index.html           <!-- AUTO:latest-feature:start --> ... :end -->
  features/index.html  <!-- AUTO:features-list:start --> ... :end -->
  archive/index.html   <!-- AUTO:archive-list:start --> ... :end -->

Nothing else in those files is touched. If the fetch fails, returns zero posts,
or a marker is missing, the script exits without writing anything.
Stdlib only. Run from anywhere: python3 scripts/update_archive.py
"""
import html, json, os, re, sys, time, urllib.request
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


def row(p, notes=None, link_text="Read it on Substack", ind="  "):
    out = ['%s<article class="row fi" data-type="%s">' % (ind, p["kind"]),
           "%s %s" % (ind, meta(p)),
           "%s <div>" % ind,
           '%s  <h3><a href="%s" rel="noopener">%s</a></h3>' % (ind, e(p["url"]), t(p["title"]))]
    if p["summary"]:
        out.append('%s  <p class="dek">%s</p>' % (ind, t(p["summary"])))
    if notes and notes.get(p["slug"]):
        out.append('%s  <p class="inside">%s</p>' % (ind, t(notes[p["slug"]])))
    out += ['%s  <p class="go"><a href="%s" rel="noopener">%s</a></p>' % (ind, e(p["url"]), t(link_text)),
            "%s </div>" % ind, "%s</article>" % ind]
    return "\n".join(out)


def splice(text, name, body):
    pat = re.compile(r"(<!-- AUTO:%s:start[^>]*-->\n)(.*?)(\n?[ \t]*<!-- AUTO:%s:end -->)" % (name, name), re.S)
    if len(pat.findall(text)) != 1:
        raise RuntimeError("marker AUTO:%s missing or duplicated" % name)
    return pat.sub(lambda m: m.group(1) + body + "\n" + m.group(3).lstrip("\n"), text)


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

    longs = [p for p in posts if p["kind"] in ("feature", "breaking")]
    features = [p for p in posts if p["kind"] == "feature"]
    if features:
        latest = row(features[0], link_text="Read the feature")
    else:
        latest = '  <p class="empty">The first feature is on its way.</p>'
    blocks = {
        "index.html": {"latest-feature": latest},
        "features/index.html": {"features-list": "\n".join(row(p, notes) for p in longs)},
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
    except Exception as ex:
        warn("not updating: %s" % ex)
        return 1
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
