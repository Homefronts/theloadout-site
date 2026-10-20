# Feature summary page template

Each feature on Substack can get a short page here at `theloadout.fyi/features/<slug>/`.
It's a plain-words summary written fresh for the site, plus a big link to the full read.
That gives search engines original text on our own domain to rank, without copying the post.

This folder starts with `_`, so GitHub Pages (Jekyll) never publishes it, the sync script
skips it, and it's left out of `sitemap.xml`. The `noindex` tag is a second safety net.

## Making a new one

1. Copy this folder to `features/<slug>/`. Make the slug the plain search phrase, lowercase
   with dashes, e.g. `features/claude-code-software-we-didnt-write/`. Don't start it with `_`.
2. In the copy's `index.html`, **delete the `<meta name="robots" content="noindex">` line**
   and the comment block at the top.
3. Replace every `{{TOKEN}}`:
   - `{{TITLE}}`: the search-friendly title, `<Plain search phrase>: <hook>`. The template
     adds ` | The Loadout AI`. Aim for about 60 to 70 characters before that.
   - `{{H1}}`: the on-page headline. Usually the same as the title.
   - `{{DESCRIPTION}}`: one or two plain sentences, about 140 to 160 characters.
   - `{{SLUG}}`: the folder name.
   - `{{SUBSTACK_URL}}`: the full post URL, e.g. `https://theloadoutai.substack.com/p/...`.
     The sync script uses it to add a "Quick summary" link next to that post in the lists.
   - `{{PUBLISHED_ISO}}` / `{{MODIFIED_ISO}}`: e.g. `2026-10-20T08:38:04-04:00`.
     `{{PUBLISHED_DATE}}`: `2026-10-20`. `{{PUBLISHED_HUMAN}}`: `Oct 20, 2026`.
   - `{{READ_MINS}}`: the Substack read time in minutes, e.g. `8`.
   - `{{DEK}}`: the Substack subtitle, or a one-line version of it.
   - `{{SUMMARY_PARAGRAPHS}}`: 150 to 250 words in `<p>...</p>` paragraphs. Write it fresh.
     Keep the facts identical to the post, and keep the cautions in.
   - `{{TAKEAWAY_ITEMS}}`: 4 to 6 `<li>...</li>` lines.
4. Check nothing's left: `rg '\{\{' features/<slug>/` should print nothing.
5. Commit. The next sync run adds the page to `sitemap.xml` and links it from the Features
   list (or run `python3 scripts/update_archive.py` yourself).

Same rules as the rest of the site: no analytics, trackers, embeds or third-party anything.
The JSON-LD block is static text that browsers ignore and search engines read. It loads nothing.
