import os
import re
from datetime import datetime


def backup_file(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak.{ts}"
    try:
        with open(path, "rb") as r, open(bak, "wb") as w:
            w.write(r.read())
        return bak
    except OSError:
        return None


def normalize_apostrophes(s: str) -> str:
    return s.replace("\u2019", "'").replace("\u2018", "'").replace("\u02BC", "'")


_KANA_RE = re.compile(r"[\u3040\u30ff]")


def has_kana(text: str) -> bool:
    return bool(_KANA_RE.search(text or ""))


def iter_lines_by_file(cstl_data: dict):
    by_file: dict[str, list[dict]] = {}
    for ln in cstl_data.get("lines", []):
        by_file.setdefault(ln.get("file", ""), []).append(ln)
    return by_file
