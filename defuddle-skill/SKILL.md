---
name: defuddle
description: >
  Extract readable content from HTML pages, stripping navigation, sidebars,
  ads, and other clutter. Produces clean plaintext or Markdown output.
  Use when Codex needs to extract the main article text from an HTML file
  or URL, convert web content to Markdown, or clean up messy HTML for
  further processing.
---

# Defuddle

Read HTML from a file (or stdin) and output the main article content as clean
text or Markdown.

## Usage

```python
from scripts import defuddle

raw_html = open("article.html").read()       # or fetch from URL
text = defuddle.format_text(raw_html)        # plain text
md   = defuddle.format_markdown(raw_html)    # Markdown
```

The entry point module lives at `scripts/defuddle.py` and provides two
functions:

- **`format_text(html, width=78)`** — plain text, auto-wrapped
- **`format_markdown(html, width=78)`** — Markdown output (headings,
  bold, italic, links, images, code blocks, lists)

Both accept optional `width` (0 = no wrapping).

## CLI usage from the user's terminal

```bash
python3 scripts/defuddle.py -f article.html       # plain text
python3 scripts/defuddle.py -f article.html -m     # Markdown
python3 scripts/defuddle.py --url https://...      # fetch URL
cat article.html | python3 scripts/defuddle.py     # pipe
```

The tool is bundled for reliability — no pip install needed.
It uses only Python 3.10+ stdlib (`re`, `html.parser`, `argparse`, `sys`).

## When to use

- The user provides an HTML file and asks to extract the readable content
- HTML needs cleaning into plain text for LLM context, summarisation, etc.
- Converting a web page to Markdown format
- Stripping boilerplate (nav, ads, sidebars, footers) from HTML
- Working with fetched web page snapshots
