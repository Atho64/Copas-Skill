"""Two-tier mechanical lint for CopasTool project lines — no model, no glossary.

Tiers (shared by `batch validate`, `batch write`, `review`, and `audit`):
- hard: empty, speaker_missing, speaker_invented, structural_tokens, markup_order, trailing_space
- soft: language-pair checks from `langpair.soft_checks` + speaker_residue + markup_leak + `decisions` lint rules
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from . import cstl_io, integrity, langpair, state

HARD_KINDS = (
    "empty",
    "speaker_missing",
    "speaker_invented",
    "structural_tokens",
    "markup_order",
    "trailing_space",
)
_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|apos|nbsp);")


def lint_line(
    line: dict,
    source_lang: str = "Japanese",
    target_lang: str = "Indonesian",
    allow_tag_mismatch: bool = False,
    token_exceptions: set[int] | frozenset[int] = frozenset(),
    rules=(),
    disable_empty: bool = False,
) -> tuple[list[str], list[str]]:
    num = line.get("line_num")
    src = line.get("message") or ""
    tgt = line.get("trans_message")
    tgt_str = "" if tgt is None else str(tgt)
    sname = (line.get("name") or "").strip()
    tname = (line.get("trans_name") or "").strip()

    hard: list[str] = []
    if src.strip() and not tgt_str.strip() and not disable_empty:
        return ["empty"], []
    if sname and not tname:
        hard.append("speaker_missing")
    elif not sname and tname:
        hard.append("speaker_invented")

    exc = allow_tag_mismatch or (num is not None and int(num) in token_exceptions)
    for issue in integrity.message_issues(src, tgt_str, allow_tag_mismatch=exc):
        kind = issue["kind"]
        if kind not in hard:
            hard.append(kind)

    soft = langpair.soft_checks(src, tgt_str, source_lang, target_lang)
    if tname and langpair.name_residue(tname, source_lang, target_lang):
        soft.append("speaker_residue")
    if _ENTITY.search(tgt_str) and not _ENTITY.search(src):
        soft.append("markup_leak")
    for name, rx, _ in rules:
        if rx.search(tgt_str):
            soft.append(f"rule:{name}")
    return hard, soft


def lint_pair(
    src: str,
    tgt: str,
    allow_tag_mismatch: bool = False,
    rules=(),
    source_lang: str = "Japanese",
    target_lang: str = "Indonesian",
    src_name: str | None = None,
    tgt_name: str | None = None,
    disable_empty: bool = False,
) -> tuple[list[str], list[str]]:
    row = {
        "message": src,
        "trans_message": tgt,
        "name": src_name,
        "trans_name": tgt_name,
    }
    return lint_line(
        row,
        source_lang=source_lang,
        target_lang=target_lang,
        allow_tag_mismatch=allow_tag_mismatch,
        rules=rules,
        disable_empty=disable_empty,
    )


def audit_project(cstl_path: str, allow_tag_mismatch: bool = False, sample: int = 5) -> dict:
    data = cstl_io.ensure_cstl(cstl_io.load_cstl(cstl_path))
    d = state.load(cstl_path)
    exc = state.token_exceptions(d)
    rules = state.lint_rules(d)
    sl = data.get("source_lang", "Japanese")
    tl = data.get("target_lang", "Indonesian")
    disable_empty = bool(data.get("disable_empty_line_validation"))

    out: dict[str, dict] = {}
    for ln in cstl_io.ordered_lines(data):
        if ln.get("_hidden") or not ln.get("is_translated"):
            continue
        hard, soft = lint_line(
            ln,
            source_lang=sl,
            target_lang=tl,
            allow_tag_mismatch=allow_tag_mismatch,
            token_exceptions=exc,
            rules=rules,
            disable_empty=disable_empty,
        )
        for c in hard + soft:
            row = out.setdefault(c, {"count": 0, "lines": [], "samples": []})
            row["count"] += 1
            row["lines"].append(ln.get("line_num"))
            if len(row["samples"]) < sample:
                row["samples"].append({
                    "line_num": ln.get("line_num"),
                    "file": ln.get("file", ""),
                    "name": ln.get("name"),
                    "trans_name": ln.get("trans_name"),
                    "source": (ln.get("message") or "")[:120],
                    "target": (ln.get("trans_message") or "")[:120],
                })
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["count"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mechanical lint of translated CopasTool project lines")
    ap.add_argument("cstl_path")
    ap.add_argument("--out", help="Write full audit JSON report here")
    ap.add_argument("--json", action="store_true", help="Print full JSON report to stdout")
    ap.add_argument("--allow-tag-mismatch", action="store_true")
    ap.add_argument("--samples", type=int, default=5)
    a = ap.parse_args(argv)

    rep = audit_project(a.cstl_path, allow_tag_mismatch=a.allow_tag_mismatch, sample=a.samples)
    hard = sum(v["count"] for k, v in rep.items() if k in HARD_KINDS)
    warn = sum(v["count"] for v in rep.values()) - hard
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        for k, v in rep.items():
            nums = v["lines"]
            print(f"{k:24s} {v['count']:5d}  {nums[:12]}{' ...' if len(nums) > 12 else ''}")
        if a.out:
            print(f"report -> {a.out}")
    sys.stderr.write(f"{hard} hard issue(s), {warn} warning(s)\n")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
