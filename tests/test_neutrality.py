"""Package neutrality: no maintainer product tree leakage."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests._helpers import PKG_ROOT

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".yaml",
    ".yml",
    ".txt",
    ".stub",
    ".json",
    ".example",
    ".sh",
}

FORBIDDEN = (
    re.compile(r"DiskHNSW"),
    re.compile(r"hnsw-predictor-ndf"),
    re.compile(r"hotspot-optimization"),
    re.compile(r"ou_[0-9a-f]{8,}"),
    re.compile(r"/home/huawei/"),
)

DEPRECATED_CONTEXT = re.compile(
    r"(deprecated|retired|migration|historical|legacy|已 deprecated|已退役|无 Commander)",
    re.IGNORECASE,
)


def _iter_text_files(root: Path) -> list[Path]:
    skip_dirs = {"__pycache__", ".git", "tests"}
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore"}:
            out.append(path)
    return out


class TestNeutrality(unittest.TestCase):
    def test_no_forbidden_maintainer_leaks(self) -> None:
        violations: list[str] = []
        for path in _iter_text_files(PKG_ROOT):
            if path.name == ".gitignore":
                continue
            rel = path.relative_to(PKG_ROOT)
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in FORBIDDEN:
                for match in pattern.finditer(text):
                    start = max(0, match.start() - 120)
                    end = min(len(text), match.end() + 120)
                    context = text[start:end]
                    if pattern.pattern == r"/home/huawei/" and path.name == ".gitignore":
                        continue
                    if DEPRECATED_CONTEXT.search(context):
                        continue
                    violations.append(f"{rel}: {match.group(0)!r} @ …{context.strip()}…")
        self.assertEqual(violations, [], "forbidden maintainer-specific strings found:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
