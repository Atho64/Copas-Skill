"""Shared string, boundary, and backup helpers."""
from __future__ import annotations

import glob
import os
import re
import shutil
from datetime import datetime

_APOS = {"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\uff07": "'"}
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def backup_file(path: str, keep: int | None = None) -> str | None:
    """Create a timestamped backup alongside `path` and prune oldest `.bak.*` copies."""
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    bak = f"{path}.bak.{ts}"
    n = 0
    while os.path.exists(bak if n == 0 else f"{bak}_{n}"):
        n += 1
    if n:
        bak = f"{bak}_{n}"
    try:
        shutil.copy2(path, bak)
    except OSError:
        return None
    if keep is None:
        raw = os.environ.get("CSTL_BACKUP_KEEP", "10")
        try:
            keep = int(raw)
        except ValueError:
            keep = 10
    if keep > 0:
        baks = sorted(glob.glob(glob.escape(path) + ".bak.*"))
        for old in baks[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass
    return bak


def normalize_apostrophes(s: str) -> str:
    for src, dst in _APOS.items():
        s = s.replace(src, dst)
    return s


def latin_boundary_search(term: str, text: str, ignore_case: bool = False):
    """Find `term` not flanked by ASCII Latin letters."""
    t = normalize_apostrophes(term)
    h = normalize_apostrophes(text)
    if not t:
        return None
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", h, flags)


def has_kana(text: str) -> bool:
    return bool(_KANA_RE.search(text or ""))


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def iter_lines_by_file(cstl_data: dict):
    by_file: dict[str, list[dict]] = {}
    for ln in cstl_data.get("lines", []):
        by_file.setdefault(ln.get("file", ""), []).append(ln)
    return by_file
