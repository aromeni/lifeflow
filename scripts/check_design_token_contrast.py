#!/usr/bin/env python3
"""Verify WCAG 2.2 contrast ratios for the Stage 10 design-token palette
(apps/web/src/app/globals.css).

Not wired into a build step — token colours are edited by hand far more
often than they're audited, so this is a manual/on-demand check, run and
its output recorded whenever a token colour changes (see
docs/product/design-system.md). The palette below must be kept in sync
with globals.css; it is duplicated rather than parsed from the CSS file
because the CSS carries both a light and a dark `:root` block plus a
`@theme inline` re-export layer, and a real parser would be more machinery
than a handful of colour pairs justifies at this repository's scale.

Thresholds (WCAG 2.2):
  - 4.5:1 for normal text (§1.4.3)
  - 3:1 for large text and non-text UI component boundaries (§1.4.11)
"""

from __future__ import annotations

import sys


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _channel(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1, l2 = relative_luminance(hex_to_rgb(hex1)), relative_luminance(hex_to_rgb(hex2))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# (label, foreground, background, minimum ratio required)
LIGHT_PAIRS = [
    ("text-primary on bg", "#14181f", "#f7f8fa", 4.5),
    ("text-primary on surface", "#14181f", "#ffffff", 4.5),
    ("text-secondary on bg", "#4c5563", "#f7f8fa", 4.5),
    ("text-secondary on surface", "#4c5563", "#ffffff", 4.5),
    ("text-tertiary on bg", "#646c7b", "#f7f8fa", 4.5),
    ("text-tertiary on surface", "#646c7b", "#ffffff", 4.5),
    ("accent-subtle-text on accent-subtle", "#372da3", "#eeecfd", 4.5),
    ("white on accent", "#ffffff", "#4338ca", 4.5),
    ("white on accent-hover", "#ffffff", "#372da3", 4.5),
    ("success-text on success-bg", "#1e6b37", "#eaf7ee", 4.5),
    ("warning-text on warning-bg", "#7a4e05", "#fdf3e2", 4.5),
    ("danger-text on danger-bg", "#9c2626", "#fdecec", 4.5),
    ("info-text on info-bg", "#1d4e8f", "#eaf1fd", 4.5),
    ("white on danger-solid", "#ffffff", "#b42323", 4.5),
    ("white on danger-solid-hover", "#ffffff", "#991e1e", 4.5),
    ("border-strong on surface (UI boundary)", "#838d9c", "#ffffff", 3.0),
    ("border-strong on bg (UI boundary)", "#838d9c", "#f7f8fa", 3.0),
    ("focus ring on surface (UI boundary)", "#4338ca", "#ffffff", 3.0),
]

DARK_PAIRS = [
    ("text-primary on bg (dark)", "#edf0f5", "#10131a", 4.5),
    ("text-secondary on surface (dark)", "#b6bccc", "#171b24", 4.5),
    ("text-tertiary on surface (dark)", "#838ba0", "#171b24", 4.5),
    ("text-tertiary on bg (dark)", "#838ba0", "#10131a", 4.5),
    ("accent-subtle-text on accent-subtle (dark)", "#c3bbfa", "#262247", 4.5),
    ("success-text on success-bg (dark)", "#7fd89b", "#12281c", 4.5),
    ("warning-text on warning-bg (dark)", "#f0c674", "#2c2311", 4.5),
    ("danger-text on danger-bg (dark)", "#f4a6a6", "#2c1616", 4.5),
    ("info-text on info-bg (dark)", "#9dc2f2", "#131f2e", 4.5),
    ("border-strong on surface (dark, UI boundary)", "#606b80", "#171b24", 3.0),
]


def main() -> int:
    failures: list[str] = []
    for label, fg, bg, minimum in (*LIGHT_PAIRS, *DARK_PAIRS):
        ratio = contrast_ratio(fg, bg)
        status = "PASS" if ratio >= minimum else "FAIL"
        print(f"{status}  {ratio:5.2f}:1  (>= {minimum})  {label}")
        if ratio < minimum:
            failures.append(label)

    if failures:
        print("\nContrast failures:")
        for label in failures:
            print(" -", label)
        return 1
    print(f"\nAll {len(LIGHT_PAIRS) + len(DARK_PAIRS)} token pairs meet their WCAG threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
