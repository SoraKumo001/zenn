"""Validate Zenn html-embed code blocks in a Markdown file."""

import re
import sys
from pathlib import Path

MAX_BYTES = 50 * 1024
FORBIDDEN_PATTERN = re.compile(
    r"<(?:html|head|body|script|form|button|textarea|select|iframe|link)\b|<a\s|@import|\bon[a-z]+\s*=",
    re.IGNORECASE,
)


def validate_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    embeds = re.findall(r"```html-embed\r?\n(.*?)\r?\n```", text, re.DOTALL)
    if not embeds:
        print(f"No html-embed blocks found in {path}")
        return 0

    has_error = False
    for idx, block in enumerate(embeds, 1):
        size_bytes = len(block.encode("utf-8"))
        forbidden = FORBIDDEN_PATTERN.findall(block)
        font_sizes = [int(px) for px in re.findall(r"font-size:\s*(\d+)px", block)]
        small_fonts = [px for px in font_sizes if px < 12]
        has_dark = '[data-theme="dark"]' in block
        has_mobile = "@media" in block and "640px" in block

        issues = []
        if size_bytes > MAX_BYTES:
            issues.append(f"size {size_bytes}B exceeds 50KB")
        if forbidden:
            issues.append(f"forbidden tokens: {sorted(set(forbidden))}")
        if small_fonts:
            issues.append(f"font-size < 12px: {small_fonts}")
        if not has_dark:
            issues.append('missing [data-theme="dark"] selector')
        if not has_mobile:
            issues.append("missing @media (max-width: 640px) responsive rule")

        status = "OK" if not issues else "FAIL"
        print(f"[{status}] Block #{idx}: {size_bytes} bytes")
        for issue in issues:
            print(f"  - {issue}")
            has_error = True

    return 1 if has_error else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_html_embed.py <markdown-file>")
        sys.exit(2)
    sys.exit(validate_file(Path(sys.argv[1])))
