"""Polish (AI QA) write-back — applies polished text over translated lines."""
from __future__ import annotations

import argparse
import json

from . import audit, batch, state
from .cstl_io import backup_cstl, ensure_cstl, load_cstl, locked, log_event, save_cstl
from .integrity import check_message, check_snapshot, expected_lines, normalize_message


def apply_polish(
    cstl_path: str,
    polished: list[dict],
    expected_batch=None,
    *,
    allow_tag_mismatch: bool = False,
    force: bool = False,
) -> int:
    data = ensure_cstl(load_cstl(cstl_path))
    by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
    dec = state.load(cstl_path)
    exc = state.token_exceptions(dec)
    if expected_batch is not None:
        expected = {line["line_num"]: line for line in expected_lines(expected_batch)}
        if not isinstance(polished, list) or any(not isinstance(item, dict) for item in polished):
            raise ValueError("polished corrections must be an array of objects")
        nums = [item.get("line_num") for item in polished]
        if any(type(num) is not int for num in nums) or len(set(nums)) != len(nums):
            raise ValueError("corrections must have unique integer line numbers")
        for item in polished:
            num = item["line_num"]
            source = expected.get(num)
            if source is None or "trans_message" not in source:
                raise ValueError(f"line {num} is not in the expected translated batch")
            current = by_num.get(num)
            check_snapshot(current, source, translation=True)
            if not current.get("is_translated"):
                raise ValueError(f"line {num} is not translated")
            pmsg = item.get("polished_text") if "polished_text" in item else item.get("trans_message") if "trans_message" in item else item.get("text")
            check_message(
                source.get("message") or "",
                pmsg,
                num,
                allow_tag_mismatch=(allow_tag_mismatch or num in exc),
            )
            pname = item.get("polished_name") if "polished_name" in item else item.get("trans_name", current.get("trans_name"))
            if not (source.get("name") or "").strip() and "polished_name" not in item and "trans_name" not in item:
                pname = None
            if pname is not None and not isinstance(pname, str):
                raise ValueError(f"speaker on line {num} must be a string or null")
            if bool((source.get("name") or "").strip()) != bool(pname and pname.strip()):
                raise ValueError(f"speaker presence changed on line {num}")
        if not polished:
            return 0

    with locked(cstl_path):
        backup_cstl(cstl_path)
        if expected_batch is None:
            data = ensure_cstl(load_cstl(cstl_path))
            by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
        sl, tl = data.get("source_lang", "Japanese"), data.get("target_lang", "Indonesian")
        applied = 0
        for it in polished:
            try:
                num = int(it["line_num"]) if "line_num" in it else int(it["text_index"])
            except Exception:
                continue
            ln = by_num.get(num)
            if ln is None:
                continue
            pmsg = it.get("polished_text") if "polished_text" in it else it.get("trans_message") or it.get("text") or ""
            pmsg = normalize_message(str(pmsg))
            pname = it.get("polished_name") if "polished_name" in it else it.get("trans_name")
            if expected_batch is None and not force:
                cand_name = (str(pname).strip() or None) if pname is not None else ln.get("trans_name")
                if not (ln.get("name") or "").strip():
                    cand_name = None
                hard, _ = audit.lint_line(
                    {
                        "line_num": num,
                        "name": ln.get("name"),
                        "message": ln.get("message") or "",
                        "trans_name": cand_name,
                        "trans_message": pmsg,
                    },
                    source_lang=sl,
                    target_lang=tl,
                    allow_tag_mismatch=allow_tag_mismatch,
                    token_exceptions=exc,
                )
                if hard:
                    continue
            if pmsg.strip():
                ln["trans_message"] = pmsg
            if pname is not None and str(pname).strip():
                ln["trans_name"] = str(pname).strip()
            if expected_batch is not None and not (ln.get("name") or "").strip():
                ln["trans_name"] = None
            ln["_polished"] = True
            applied += 1
        save_cstl(cstl_path, data)
    log_event(cstl_path, {"event": "polish", "applied": applied, "total": len(polished)})
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description="Polish write-back")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("cstl_path")
    w.add_argument("polished", nargs="+", metavar="POLISHED_JSON")
    w.add_argument("--expect-batch", help="Validate correction IDs, current source/translation, speakers, and message integrity before writing")
    w.add_argument("--force", action="store_true")
    w.add_argument("--allow-tag-mismatch", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "write":
        try:
            items = batch.load_many(a.polished)
            expected = None
            if a.expect_batch:
                with open(a.expect_batch, encoding="utf-8-sig") as f:
                    expected = json.load(f)
            else:
                dups = batch.duplicates(items)
                if dups and not a.force:
                    ap.error(f"duplicate line_num across inputs: {dups[:20]} (use --force)")
            n = apply_polish(
                a.cstl_path,
                items,
                expected_batch=expected,
                allow_tag_mismatch=a.allow_tag_mismatch,
                force=a.force,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            ap.error(str(exc))
        print(f"polished {n} line(s)")


if __name__ == "__main__":
    main()
