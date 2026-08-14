"""Polish (AI QA) write-back — applies polished text over translated lines."""
from __future__ import annotations

import argparse
import json

from .cstl_io import backup_cstl, ensure_cstl, load_cstl, save_cstl


def apply_polish(cstl_path: str, polished: list[dict]) -> int:
    backup_cstl(cstl_path)
    data = ensure_cstl(load_cstl(cstl_path))
    by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
    applied = 0
    for it in polished:
        try:
            num = int(it["line_num"])
        except Exception:
            continue
        ln = by_num.get(num)
        if ln is None:
            continue
        pmsg = it.get("polished_text") if "polished_text" in it else it.get("trans_message") or it.get("text") or ""
        pmsg = str(pmsg).replace("\n", "\\n").replace("<br>", "\\n")
        if pmsg.strip():
            ln["trans_message"] = pmsg
        pname = it.get("polished_name") if "polished_name" in it else it.get("trans_name")
        if pname is not None and str(pname).strip():
            ln["trans_name"] = str(pname).strip()
        applied += 1
    save_cstl(cstl_path, data)
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description="Polish write-back")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("cstl_path")
    w.add_argument("polished_json_path")
    a = ap.parse_args(argv)
    if a.cmd == "write":
        with open(a.polished_json_path, encoding="utf-8") as f:
            items = json.load(f)
        if isinstance(items, dict) and "polished" in items:
            items = items["polished"]
        n = apply_polish(a.cstl_path, items)
        print(f"polished {n} line(s)")


if __name__ == "__main__":
    main()
