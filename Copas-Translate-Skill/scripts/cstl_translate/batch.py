"""Batch read/write CopasTool project lines — the agent is the translation engine."""
from __future__ import annotations

import argparse
import json
import os

from .cstl_io import backup_cstl, ensure_cstl, load_cstl, save_cstl


def read_batch(cstl_path: str, size: int = 100) -> list[dict]:
    data = ensure_cstl(load_cstl(cstl_path))
    out: list[dict] = []
    for ln in data.get("lines", []):
        if not ln.get("is_translated") and (ln.get("message") or "").strip():
            out.append({
                "line_num": ln["line_num"],
                "file": ln.get("file", ""),
                "name": ln.get("name"),
                "message": ln.get("message", ""),
                "trans_message": ln.get("trans_message"),
            })
            if len(out) >= size:
                break
    return out


def read_translated_batch(cstl_path: str, size: int = 100) -> list[dict]:
    data = ensure_cstl(load_cstl(cstl_path))
    out: list[dict] = []
    for ln in data.get("lines", []):
        if ln.get("is_translated"):
            out.append({
                "line_num": ln["line_num"],
                "file": ln.get("file", ""),
                "name": ln.get("name"),
                "message": ln.get("message", ""),
                "trans_message": ln.get("trans_message") or "",
                "trans_name": ln.get("trans_name"),
            })
            if len(out) >= size:
                break
    return out


def write_back(cstl_path: str, translations: list[dict]) -> int:
    backup_cstl(cstl_path)
    data = ensure_cstl(load_cstl(cstl_path))
    by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
    applied = 0
    for it in translations:
        try:
            num = int(it["line_num"])
        except Exception:
            continue
        ln = by_num.get(num)
        if ln is None:
            continue
        tmsg = it.get("trans_message")
        if tmsg is None:
            # Support alternative key
            tmsg = it.get("translated_text") or it.get("text") or ""
        tmsg = str(tmsg)
        # Normalize: CSTL stores \n as \\n literal
        tmsg = tmsg.replace("\n", "\\n").replace("<br>", "\\n")
        tname = it.get("trans_name")
        if tname is None:
            tname = it.get("translated_name") or it.get("name")
        if tname is not None:
            tname = str(tname).strip() or None
            if tname is not None:
                ln["trans_name"] = tname
        ln["trans_message"] = tmsg
        # Mark translated if we have content or validation allows empty
        ln["is_translated"] = bool(tmsg.strip()) or bool(data.get("disable_empty_line_validation"))
        if not ln["is_translated"] and tmsg.strip():
            ln["is_translated"] = True
        if tmsg.strip():
            ln["is_translated"] = True
        applied += 1
    save_cstl(cstl_path, data)
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description="Batch read/write for CopasTool project backups")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("read", help="Print next untranslated batch as JSON")
    r.add_argument("cstl_path")
    r.add_argument("--size", type=int, default=100)

    rt = sub.add_parser("read-translated", help="Print next translated batch (for polish)")
    rt.add_argument("cstl_path")
    rt.add_argument("--size", type=int, default=100)

    w = sub.add_parser("write", help="Write translations back from a JSON file")
    w.add_argument("cstl_path")
    w.add_argument("translations_json_path")

    a = ap.parse_args(argv)
    if a.cmd == "read":
        batch = read_batch(a.cstl_path, size=a.size)
        print(json.dumps(batch, ensure_ascii=False))
    elif a.cmd == "read-translated":
        batch = read_translated_batch(a.cstl_path, size=a.size)
        print(json.dumps(batch, ensure_ascii=False))
    elif a.cmd == "write":
        try:
            with open(a.translations_json_path, encoding="utf-8") as f:
                translations = json.load(f)
        except Exception as e:
            ap.error(f"cannot read translations file: {e}")
        if isinstance(translations, dict) and "translations" in translations:
            translations = translations["translations"]
        total = len(translations)
        applied = write_back(a.cstl_path, translations)
        if applied < total:
            print(f"applied {applied} of {total} translation(s) ({total - applied} unmatched line_num)")
        else:
            print(f"applied {applied} translation(s)")


if __name__ == "__main__":
    main()
