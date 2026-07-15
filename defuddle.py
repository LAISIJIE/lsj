#!/usr/bin/env python3
"""
defuddle — Extract readable content from HTML pages.
Zero external dependencies (stdlib only).

Usage:
    cat article.html | python3 defuddle.py         # pipe
    python3 defuddle.py -f article.html            # file
    python3 defuddle.py -f article.html -m         # markdown output
"""
from __future__ import annotations

import argparse
import re
import sys

# Tags whose content is always removed
REMOVED_ELEMENTS = {
    "script", "style", "noscript", "nav", "footer", "header",
    "aside", "form", "input", "button", "select", "textarea",
    "label", "svg", "canvas", "iframe",
}

# Positive class/id signal — elements matching these are good content candidates
POSITIVE_PAT = re.compile(
    r"\b(article|content|post|entry|story|body|text|main|"
    r"articleBody|articlebody)\b", re.I,
)

# Negative class/id signal — likely boilerplate
NEGATIVE_PAT = re.compile(
    r"\b(comment|sidebar|widget|advert|sponsor|promo|related|"
    r"social|share|breadcrumb|pagination|disclaimer|cookie|"
    r"nav|footer|header|menu|breadcrumb|recommend|popular|"
    r"tags|tagged|archive|meta|byline)\b", re.I,
)

PAGE_WIDTH = 78


# ─── dom helpers (stdlib) ───────────────────────────────────────────────

def _remove_tags(html: str, *tags: str) -> str:
    """Remove entire elements (open + content + close) for *tags."""
    pattern = "|".join(tags)
    return re.sub(
        rf'<({pattern})\b[^>]*>.*?</\1\s*>',
        "",
        html,
        flags=re.DOTALL | re.I,
    )


def _strip_html(html: str) -> str:
    """Strip all tags, return text with preserved paragraph breaks."""
    # Replace block-level tags with newlines
    html = re.sub(
        r'</?(?:p|div|h[1-6]|li|blockquote|br|tr|section|article'
        r'|figure|figcaption|table|pre)\b[^>]*>',
        "\n",
        html,
        flags=re.I,
    )
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"[\xa0\u200b\u200c]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse excess blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── content extraction ─────────────────────────────────────────────────

def _find_content_area(html: str) -> str:
    """Return the HTML fragment that is most likely the main content."""
    html = _remove_tags(html, *REMOVED_ELEMENTS)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

    # Strategy 1: explicit semantic landmarks
    for tag in ("main", "article", "[role=main]", '[itemprop=articleBody]'):
        if tag.startswith("["):
            attr = tag.strip("[]")
            key, _, val = attr.partition("=")
            if val:
                pat = rf'<[a-z]+\b[^>]*{re.escape(key)}\s*=\s*["\']?{re.escape(val)}["\']?[^>]*>'
            else:
                pat = rf'<[a-z]+\b[^>]*{re.escape(key)}\s*[^>]*>'
            m = re.search(pat + r"(.*?)</[a-z]+\s*>", html, flags=re.DOTALL | re.I)
            if m:
                return m.group(1)
        else:
            m = re.search(
                rf'<{tag}\b[^>]*>(.*?)</{tag}\s*>',
                html, flags=re.DOTALL | re.I,
            )
            if m:
                return m.group(1)

    # Strategy 2: score div-like containers by paragraph + content density
    scored: list[tuple[float, str]] = []
    for m in re.finditer(
        r'<(div|section)\b([^>]*)>(.*?)</\1\s*>',
        html, flags=re.DOTALL | re.I,
    ):
        inner = m.group(3)
        p_count = len(re.findall(r'<p\b', inner, re.I))
        h_count = len(re.findall(r'<h[1-6]\b', inner, re.I))
        a_count = len(re.findall(r'<a\b', inner, re.I))
        inner_text = re.sub(r"<[^>]+>", "", inner)
        char_len = len(inner_text.strip())
        attrs = m.group(2)

        if char_len < 100:
            continue

        score = p_count * 50 + h_count * 30 + char_len * 0.5
        # Boost if positive class/id signals
        if POSITIVE_PAT.search(attrs):
            score *= 1.5
        # Penalize if negative class/id signals
        if NEGATIVE_PAT.search(attrs):
            score *= 0.3
        # Penalize link-heavy sections
        if p_count > 0:
            link_ratio = a_count / (p_count + h_count + 1)
            if link_ratio > 2:
                score *= 0.4

        scored.append((score, inner))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # Strategy 3: body fallback
    m = re.search(
        r'<body\b[^>]*>(.*?)</body\s*>',
        html, flags=re.DOTALL | re.I,
    )
    return m.group(1) if m else html


# ─── output formatting ──────────────────────────────────────────────────

def format_text(html: str, width: int = PAGE_WIDTH) -> str:
    """Extract and format article as plain text."""
    content = _find_content_area(html)
    text = _strip_html(content)
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        # Simple reflow — join short lines, break long ones
        wrapped = _reflow(para, width)
        lines.append(wrapped)
    return "\n\n".join(lines)


def format_markdown(html: str, width: int = PAGE_WIDTH) -> str:
    """Extract and format article as Markdown."""
    content = _find_content_area(html)

    # Convert headings
    content = re.sub(
        r'<h1\b[^>]*>(.*?)</h1>',
        lambda m: "# " + _strip_html(m.group(1)),
        content, flags=re.DOTALL | re.I,
    )
    content = re.sub(
        r'<h2\b[^>]*>(.*?)</h2>',
        lambda m: "## " + _strip_html(m.group(1)),
        content, flags=re.DOTALL | re.I,
    )
    content = re.sub(
        r'<h[3-6]\b[^>]*>(.*?)</h[3-6]>',
        lambda m: "### " + _strip_html(m.group(1)),
        content, flags=re.DOTALL | re.I,
    )

    # Convert links
    content = re.sub(
        r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda m: f"[{_strip_html(m.group(2))}]({m.group(1)})",
        content, flags=re.DOTALL | re.I,
    )

    # Convert images
    content = re.sub(
        r'<img\b[^>]*src\s*=\s*["\']([^"\']+)["\'][^>]*alt\s*=\s*["\']([^"\']*)["\'][^>]*>',
        lambda m: f"![{m.group(2)}]({m.group(1)})",
        content, flags=re.I,
    )
    content = re.sub(
        r'<img\b[^>]*src\s*=\s*["\']([^"\']+)["\'][^>]*>',
        lambda m: f"![]({m.group(1)})",
        content, flags=re.I,
    )

    # Convert bold/italic
    content = re.sub(
        r'<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>',
        lambda m: "**" + _strip_html(m.group(1)) + "**",
        content, flags=re.DOTALL | re.I,
    )
    content = re.sub(
        r'<(?:em|i)\b[^>]*>(.*?)</(?:em|i)>',
        lambda m: "*" + _strip_html(m.group(1)) + "*",
        content, flags=re.DOTALL | re.I,
    )

    # Convert code
    content = re.sub(
        r'<code\b[^>]*>(.*?)</code>',
        lambda m: "`" + _strip_html(m.group(1)) + "`",
        content, flags=re.DOTALL | re.I,
    )
    content = re.sub(
        r'<pre\b[^>]*>(.*?)</pre>',
        lambda m: "\n```\n" + _strip_html(m.group(1)) + "\n```\n",
        content, flags=re.DOTALL | re.I,
    )

    # Convert lists
    content = re.sub(
        r'<li\b[^>]*>(.*?)</li>',
        lambda m: "- " + _strip_html(m.group(1)),
        content, flags=re.DOTALL | re.I,
    )

    text = _strip_html(content)
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        wrapped = _reflow(para, width)
        lines.append(wrapped)
    return "\n\n".join(lines)


def _reflow(text: str, width: int) -> str:
    """Simple text reflow: join short lines and break long ones at width."""
    # Don't reflow code blocks or list items
    if text.startswith("```") or text.startswith("- ") or text.startswith("#"):
        return text
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = words[0]
    for w in words[1:]:
        if len(current) + 1 + len(w) <= width:
            current += " " + w
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return "\n".join(lines)


# ─── CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract readable content from HTML pages.",
    )
    parser.add_argument(
        "-f", "--file",
        help="Read HTML from file instead of stdin.",
    )
    parser.add_argument(
        "-m", "--markdown",
        action="store_true",
        help="Output in Markdown format.",
    )
    parser.add_argument(
        "--url",
        help="Fetch HTML from a URL.",
    )
    parser.add_argument(
        "--width",
        type=int, default=PAGE_WIDTH,
        help=f"Wrap text at this width (default {PAGE_WIDTH}, 0 = no wrap).",
    )
    args = parser.parse_args()

    width = args.width or PAGE_WIDTH

    html: str

    if args.url:
        from urllib.request import urlopen
        from urllib.error import URLError
        try:
            with urlopen(args.url, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except URLError as e:
            print(f"Error fetching URL: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.file:
        try:
            with open(args.file, encoding="utf-8") as fh:
                html = fh.read()
        except FileNotFoundError:
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
    else:
        html = sys.stdin.read()

    if not html.strip():
        print("No input.", file=sys.stderr)
        sys.exit(1)

    if args.markdown:
        result = format_markdown(html, width=width)
    else:
        result = format_text(html, width=width)

    if result:
        print(result)
    else:
        print("(no readable content found)", file=sys.stderr)


if __name__ == "__main__":
    main()
