"""Precedent sheet (BOOK_BIBLE.md) extracted from already-translated lines.

For every speaker name, character, and recurring JP/EN term occurring in the
pending groups' source lines, report how already-translated lines rendered it.
"""
from __future__ import annotations

import argparse
import collections
import json
import re

from .cstl_io import ensure_cstl, load_cstl
from .helpers import has_cjk, latin_boundary_search, normalize_apostrophes as N
from .scan import _COMMON_WORDS, _proper_noun_vocab

_LATIN_WORD = re.compile(r"[A-Z][A-Za-z'’\-]{2,}")
_JP_TOK = re.compile(r"[\u3400-\u9fff]{2,8}|[\u30a0-\u30ff]{2,10}")


def _glossary_index(locked: dict | None) -> dict[str, tuple[str, str, str]]:
    gl: dict[str, tuple[str, str, str]] = {}
    for c in (locked or {}).get("characters", []):
        render = str(c.get("canonical") if c.get("keep_source") else (c.get("render") or c.get("canonical") or ""))
        note = str(c.get("desc") or c.get("note") or "")
        for n in [c.get("canonical"), c.get("render")] + list(c.get("aliases") or []):
            if n:
                gl[N(str(n)).lower()] = ("character", render, note)
    for t in (locked or {}).get("terms", []):
        src = str(t.get("src") or "")
        if src:
            dst = f"{src} (keep source)" if t.get("keep_source") else str(t.get("dst") or "")
            gl[N(src).lower()] = (str(t.get("category") or "term"), dst, str(t.get("desc") or t.get("note") or ""))
    return gl


def build(lines: list[dict], pending_rows: list[dict], locked: dict | None = None, title: str = "BOOK_BIBLE") -> str:
    done = [ln for ln in lines if not ln.get("_hidden") and ln.get("is_translated") and (ln.get("trans_message") or "").strip()]
    gl = _glossary_index(locked)
    vocab = _proper_noun_vocab(lines)

    # 1. Speaker precedents
    pend_speakers = collections.Counter(str(r.get("name") or "").strip() for r in pending_rows if (r.get("name") or "").strip())
    spk_rows = []
    for spk, cnt in pend_speakers.most_common():
        glo = gl.get(N(spk).lower())
        seen_tr = collections.Counter()
        for ln in done:
            if (ln.get("name") or "").strip() == spk and (ln.get("trans_name") or "").strip():
                seen_tr[(ln.get("trans_name") or "").strip()] += 1
        if glo:
            prec = f"glossary ({glo[0]}): **{glo[1]}**" + (f" ({glo[2]})" if glo[2] else "")
        elif seen_tr:
            top = ", ".join(f"**{k}** x{v}" for k, v in seen_tr.most_common(3))
            prec = f"prior speaker rendering: {top}"
        else:
            prec = "**NEW speaker**: settle before mass translation"
        spk_rows.append(f"| {spk} ({cnt}) | {prec} |")

    # 2. Proper noun / recurring JP term precedents
    terms_cnt: collections.Counter[str] = collections.Counter()
    for r in pending_rows:
        msg = str(r.get("message") or r.get("source_text") or "")
        for m in _LATIN_WORD.finditer(N(msg)):
            w = m.group()[:-2] if m.group().endswith("'s") else m.group()
            if w in vocab and w.lower() not in _COMMON_WORDS and not w.isupper():
                terms_cnt[w] += 1
        for m in _JP_TOK.finditer(msg):
            tok = m.group()
            if tok not in pend_speakers:
                terms_cnt[tok] += 1

    term_rows = []
    for w, cnt in terms_cnt.most_common(60):
        glo = gl.get(N(w).lower())
        if not glo and cnt < 2:
            continue
        seen = kept = 0
        for ln in done:
            src_txt = ln.get("message") or ""
            hit = (w in src_txt) if has_cjk(w) else (latin_boundary_search(w, src_txt, ignore_case=True) is not None)
            if not hit:
                continue
            seen += 1
            tr_txt = ln.get("trans_message") or ""
            if (w in tr_txt) if has_cjk(w) else (latin_boundary_search(w, tr_txt, ignore_case=True) is not None):
                kept += 1
        if glo:
            prec = f"glossary {glo[0]}: **{glo[1]}**" + (f" ({glo[2]})" if glo[2] else "")
        elif seen == 0:
            prec = "**new term**: not in translated lines yet"
        elif kept == seen:
            prec = f"kept verbatim in {seen}/{seen} lines"
        elif kept == 0:
            prec = f"localized in all {seen} translated lines (check context for exact rendering)"
        else:
            prec = f"mixed: kept {kept}/{seen} lines (unify via glossary)"
        term_rows.append(f"| {w} ({cnt}) | {prec} |")

    out = [
        f"# {title} (extracted from {len(done)} translated line(s))",
        "",
        "Confirmed translations and locked glossary entries govern all parallel batches.",
        "",
    ]
    if spk_rows:
        out += ["## Speakers in pending groups", "", "| Speaker (pending hits) | Precedent / Glossary |", "|---|---|", *spk_rows, ""]
    out += ["## Terms & proper nouns in pending groups", "", "| Term (pending hits) | Precedent / Glossary |", "|---|---|", *(term_rows or ["| (none) | — |"]), ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build BOOK_BIBLE precedent sheet from translated lines")
    ap.add_argument("cstl_path")
    ap.add_argument("--for", dest="sources", nargs="+", required=True, metavar="SRC_JSON")
    ap.add_argument("--locked", help="Locked glossary JSON")
    ap.add_argument("--out", help="Write Markdown here (default stdout)")
    ap.add_argument("--title", default="BOOK_BIBLE")
    a = ap.parse_args(argv)

    data = ensure_cstl(load_cstl(a.cstl_path))
    pending_rows: list[dict] = []
    for p in a.sources:
        with open(p, encoding="utf-8-sig") as f:
            payload = json.load(f)
        rows = payload.get("lines") if isinstance(payload, dict) else payload
        pending_rows.extend(r for r in (rows or ()) if isinstance(r, dict))
    locked_data = None
    if a.locked:
        with open(a.locked, encoding="utf-8-sig") as f:
            locked_data = json.load(f)
    md = build(data.get("lines", []), pending_rows, locked_data, a.title)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"precedents -> {a.out} ({md.count(chr(10))} lines)")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
