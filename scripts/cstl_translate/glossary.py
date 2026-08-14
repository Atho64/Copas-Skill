"""Glossary extract / inject for CSTL .cstl. Also handles glossary.locked.json build."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter

from .cstl_io import ensure_cstl, load_cstl, save_cstl
from .helpers import backup_file


def _kanji(s: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", s or ""))


def extract_candidates(cstl_path: str, top_k: int = 200) -> dict:
    """Heuristic extraction from source messages — frequency of CJK tokens + katakana."""
    data = ensure_cstl(load_cstl(cstl_path))
    counter: Counter[str] = Counter()
    for ln in data.get("lines", []):
        msg = ln.get("message") or ""
        # Extract: kanji sequences, katakana sequences, and bracket names
        for m in re.findall(r"[\u3400-\u9fff]{2,}", msg):
            if 2 <= len(m) <= 8:
                counter[m] += 1
        for m in re.findall(r"[\u30a0-\u30ff]{2,}", msg):
            if 2 <= len(m) <= 10:
                counter[m] += 1
        name = (ln.get("name") or "").strip()
        if name:
            counter[name] += 3  # speaker names are strong signals
    # Keep those appearing >=2 times, or speaker names
    cands = [(tok, c) for tok, c in counter.items() if c >= 2]
    cands.sort(key=lambda x: (-x[1], x[0]))
    characters: list[dict] = []
    terms: list[dict] = []
    for tok, c in cands[:top_k]:
        # Heuristic type: treat repeated speaker names / person-like kanji as character
        if _kanji(tok) and len(tok) <= 5 and c >= 3:
            characters.append({"canonical": tok, "render": tok, "aliases": [], "type": "character", "desc": "character name", "keep_source": False, "count": c})
        else:
            terms.append({"src": tok, "dst": tok, "category": "term", "count": c})
    return {"characters": characters, "terms": terms, "non_translate": []}


def parse_glossary_text(text: str) -> dict:
    """Parse CSTL glossary_text format: [type] source = target {desc} per line."""
    chars: list[dict] = []
    terms: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\s*\[([a-z ]+)\]\s*(.*)$", line, re.I)
        gtype = "term"
        body = line
        if m:
            gtype = re.sub(r"\s+", "-", m.group(1).strip().lower())
            body = m.group(2).strip()
        # Normalize type aliases
        aliases = {"char": "character", "chars": "character", "name": "character", "names": "character",
                    "place": "place", "location": "place"}
        gtype = aliases.get(gtype, gtype)
        # Split on = or :
        sep = body.find("=")
        if sep == -1:
            sep = body.find(":")
        if sep == -1:
            continue
        src = body[:sep].strip()
        rest = body[sep + 1:].strip()
        # Optional trailing {desc}
        desc = ""
        dm = re.search(r"\{([^{}]+)\}\s*$", rest)
        if dm:
            desc = dm.group(1).strip()
            rest = rest[:dm.start()].strip()
        dst = rest
        if not src or not dst:
            continue
        if gtype == "character":
            chars.append({"canonical": src, "render": dst, "aliases": [], "type": "character", "desc": desc or "character name"})
        else:
            terms.append({"src": src, "dst": dst, "category": gtype, "desc": desc})
    return {"characters": chars, "terms": terms}


def serialize_glossary_text(locked: dict) -> str:
    lines: list[str] = []
    for ch in locked.get("characters", []):
        src = ch.get("canonical") or ch.get("src") or ""
        dst = ch.get("render") or ch.get("dst") or ""
        desc = (ch.get("desc") or "character name").strip()
        if src and dst:
            lines.append(f"[character] {src} = {dst} {{{desc}}}")
    for t in locked.get("terms", []):
        src = t.get("src") or ""
        dst = t.get("dst") or ""
        cat = (t.get("category") or t.get("type") or "term").strip().lower()
        desc = (t.get("desc") or "").strip()
        if src and dst:
            suffix = f" {{{desc}}}" if desc else ""
            lines.append(f"[{cat}] {src} = {dst}{suffix}")
    return "\n".join(lines)


def inject_into_cstl(cstl_path: str, locked_path: str) -> None:
    with open(locked_path, "r", encoding="utf-8") as f:
        locked = json.load(f)
    data = ensure_cstl(load_cstl(cstl_path))
    backup_file(cstl_path)
    data["glossary_text"] = serialize_glossary_text(locked)
    # Also persist locked file path hint for verify/scan convenience
    save_cstl(cstl_path, data)
    print(f"injected glossary_text ({len(data['glossary_text'].splitlines())} entries) -> {cstl_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL glossary helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="Extract candidate glossary from .cstl source lines")
    ex.add_argument("cstl_path")
    ex.add_argument("--out", required=True)
    ex.add_argument("--top-k", type=int, default=200)

    ft = sub.add_parser("from-text", help="Convert CSTL glossary_text file to locked JSON")
    ft.add_argument("--text", required=True)
    ft.add_argument("--out", required=True)

    inj = sub.add_parser("inject", help="Inject locked glossary into .cstl glossary_text")
    inj.add_argument("cstl_path")
    inj.add_argument("locked_path")

    a = ap.parse_args(argv)
    if a.cmd == "extract":
        locked = extract_candidates(a.cstl_path, top_k=a.top_k)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(locked, f, ensure_ascii=False, indent=2)
        print(f"locked glossary -> {a.out}  (characters={len(locked['characters'])} terms={len(locked['terms'])})")
    elif a.cmd == "from-text":
        with open(a.text, "r", encoding="utf-8") as f:
            txt = f.read()
        locked = parse_glossary_text(txt)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(locked, f, ensure_ascii=False, indent=2)
        print(f"locked glossary -> {a.out}")
    elif a.cmd == "inject":
        inject_into_cstl(a.cstl_path, a.locked_path)


if __name__ == "__main__":
    main()
