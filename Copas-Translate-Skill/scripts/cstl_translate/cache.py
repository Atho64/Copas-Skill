"""Query and small deterministic operations on CopasTool project backups (.copas / .copas.zip).

  cache stats <project>
  cache show <project> --range A-B [--file F] [--status all|translated|untranslated|polished|hidden]
  cache dump <project> [--range A-B] [--file F] --out seg.json [--changed-since OLD]
  cache set-hidden <project> --range A-B [--file F] [--unhide] [--apply]
  cache fill-dupes <project> [--max-chars 60] [--apply]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re

from . import cstl_io

_WS = re.compile(r"\s+")


def parse_range(s: str | None) -> tuple[int, int] | None:
    if not s:
        return None
    a, b = s.split("-", 1)
    lo, hi = int(a), int(b)
    if lo > hi:
        raise ValueError(f"bad range {s!r}")
    return lo, hi


def changed_line_nums(data: dict, baseline_path: str) -> set[int]:
    old_data = cstl_io.ensure_cstl(cstl_io.load_cstl(baseline_path))
    old = {
        int(ln["line_num"]): (ln.get("trans_name") or "", ln.get("trans_message") or "")
        for ln in old_data.get("lines", [])
    }
    return {
        int(ln["line_num"])
        for ln in data.get("lines", [])
        if (ln.get("trans_name") or "", ln.get("trans_message") or "") != old.get(int(ln["line_num"]), ("", ""))
    }


def _select_lines(
    data: dict,
    rng: tuple[int, int] | None = None,
    files: list[str] | None = None,
    status: str = "all",
    only: set[int] | None = None,
):
    allowed = set(files) if files else None
    for ln in cstl_io.ordered_lines(data):
        num = int(ln["line_num"])
        if rng and not (rng[0] <= num <= rng[1]):
            continue
        if allowed is not None and ln.get("file", "") not in allowed:
            continue
        if only is not None and num not in only:
            continue
        hidden = bool(ln.get("_hidden"))
        is_t = bool(ln.get("is_translated"))
        is_p = bool(ln.get("_polished"))
        if status == "translated" and (hidden or not is_t):
            continue
        elif status == "untranslated" and (hidden or is_t or not (ln.get("message") or "").strip()):
            continue
        elif status == "polished" and (hidden or not is_p):
            continue
        elif status == "hidden" and not hidden:
            continue
        yield ln


def stats(data: dict) -> dict:
    summary = {
        "projectName": data.get("projectName"),
        "projectType": data.get("projectType"),
        "source_lang": data.get("source_lang"),
        "target_lang": data.get("target_lang"),
        "total": 0,
        "workable": 0,
        "translated": 0,
        "untranslated": 0,
        "polished": 0,
        "hidden": 0,
        "empty": 0,
        "per_file": [],
    }
    per: dict[str, dict] = collections.OrderedDict()
    for ln in cstl_io.ordered_lines(data):
        fname = ln.get("file", "")
        row = per.setdefault(fname, {"file": fname, "total": 0, "workable": 0, "translated": 0, "untranslated": 0, "hidden": 0})
        summary["total"] += 1
        row["total"] += 1
        if ln.get("_hidden"):
            summary["hidden"] += 1
            row["hidden"] += 1
            continue
        if not (ln.get("message") or "").strip():
            summary["empty"] += 1
            continue
        summary["workable"] += 1
        row["workable"] += 1
        if ln.get("is_translated"):
            summary["translated"] += 1
            row["translated"] += 1
            if ln.get("_polished"):
                summary["polished"] += 1
        else:
            summary["untranslated"] += 1
            row["untranslated"] += 1
    summary["per_file"] = list(per.values())
    return summary


def _norm_key(ln: dict) -> tuple[str, str]:
    name = (ln.get("name") or "").strip()
    msg = _WS.sub(" ", (ln.get("message") or "").strip())
    return name, msg


def fill_dupes(data: dict, max_chars: int = 60) -> list[dict]:
    """Find untranslated non-hidden lines matching already-translated short `(name, message)` lines."""
    donors: dict[tuple[str, str], dict] = {}
    for ln in cstl_io.ordered_lines(data):
        if ln.get("_hidden") or not ln.get("is_translated"):
            continue
        tmsg = ln.get("trans_message") or ""
        msg = ln.get("message") or ""
        if not msg.strip() or not tmsg.strip() or len(msg) > max_chars:
            continue
        k = _norm_key(ln)
        donors.setdefault(k, {
            "donor_line_num": ln["line_num"],
            "trans_name": ln.get("trans_name"),
            "trans_message": tmsg,
        })
    matches: list[dict] = []
    for ln in cstl_io.ordered_lines(data):
        if ln.get("_hidden") or ln.get("is_translated") or not (ln.get("message") or "").strip():
            continue
        hit = donors.get(_norm_key(ln))
        if hit:
            matches.append({
                "line_num": ln["line_num"],
                "donor_line_num": hit["donor_line_num"],
                "trans_name": hit["trans_name"],
                "trans_message": hit["trans_message"],
            })
    return matches


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query and small fixes on CopasTool project backups")
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("stats", help="Project and per-file translation counts")
    st.add_argument("cstl_path")
    st.add_argument("--json", action="store_true")

    sh = sub.add_parser("show", help="Print compact side-by-side lines")
    sh.add_argument("cstl_path")
    sh.add_argument("--range", metavar="A-B")
    sh.add_argument("--file", action="append", dest="files")
    sh.add_argument("--status", choices=["all", "translated", "untranslated", "polished", "hidden"], default="all")
    sh.add_argument("--width", type=int, default=120)

    du = sub.add_parser("dump", help="Export lines to JSON for external review")
    du.add_argument("cstl_path")
    du.add_argument("--range", metavar="A-B")
    du.add_argument("--file", action="append", dest="files")
    du.add_argument("--status", choices=["all", "translated", "untranslated", "polished", "hidden"], default="translated")
    du.add_argument("--changed-since", metavar="OLD_PROJECT")
    du.add_argument("--out", required=True)

    hd = sub.add_parser("set-hidden", help="Hide or unhide lines in range/files")
    hd.add_argument("cstl_path")
    hd.add_argument("--range", metavar="A-B")
    hd.add_argument("--file", action="append", dest="files")
    hd.add_argument("--unhide", action="store_true")
    hd.add_argument("--apply", action="store_true")

    fd = sub.add_parser("fill-dupes", help="Propagate translations across identical short lines")
    fd.add_argument("cstl_path")
    fd.add_argument("--max-chars", type=int, default=60)
    fd.add_argument("--apply", action="store_true")

    a = ap.parse_args(argv)
    try:
        rng = parse_range(getattr(a, "range", None))
    except ValueError as e:
        ap.error(str(e))

    if a.cmd in ("set-hidden", "fill-dupes") and a.apply:
        with cstl_io.locked(a.cstl_path):
            cstl_io.backup_cstl(a.cstl_path)
            data = cstl_io.ensure_cstl(cstl_io.load_cstl(a.cstl_path))
            if a.cmd == "set-hidden":
                if rng is None and not a.files:
                    ap.error("set-hidden requires --range and/or --file")
                n = 0
                target_hidden = not a.unhide
                for ln in _select_lines(data, rng=rng, files=a.files, status="all"):
                    if bool(ln.get("_hidden")) != target_hidden:
                        ln["_hidden"] = target_hidden
                        n += 1
                cstl_io.save_cstl(a.cstl_path, data)
                print(f"{'unhid' if a.unhide else 'hid'} {n} line(s)")
            else:
                rows = fill_dupes(data, max_chars=a.max_chars)
                by_num = {int(ln["line_num"]): ln for ln in data.get("lines", [])}
                for r in rows:
                    ln = by_num.get(int(r["line_num"]))
                    if ln is None:
                        continue
                    if (ln.get("name") or "").strip():
                        ln["trans_name"] = r["trans_name"]
                    else:
                        ln["trans_name"] = None
                    ln["trans_message"] = r["trans_message"]
                    ln["is_translated"] = True
                cstl_io.save_cstl(a.cstl_path, data)
                cstl_io.log_event(a.cstl_path, {"event": "fill-dupes", "applied": len(rows)})
                print(f"filled {len(rows)} duplicate line(s)")
        return 0

    data = cstl_io.ensure_cstl(cstl_io.load_cstl(a.cstl_path))
    if a.cmd == "stats":
        s = stats(data)
        if a.json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            print(f"{s['projectName']} [{s['source_lang']} -> {s['target_lang']}] "
                  f"workable={s['translated']}/{s['workable']} untranslated={s['untranslated']} "
                  f"polished={s['polished']} hidden={s['hidden']} total={s['total']}")
            for f in s["per_file"]:
                print(f"  {f['file']:32s} {f['translated']:4d}/{f['workable']:4d} (hidden={f['hidden']})")
    elif a.cmd == "show":
        w = a.width
        for ln in _select_lines(data, rng=rng, files=a.files, status=a.status):
            st = "H" if ln.get("_hidden") else ("P" if ln.get("_polished") else ("T" if ln.get("is_translated") else "."))
            src_name = ln.get("name")
            tr_name = ln.get("trans_name")
            spk = f"[{src_name} -> {tr_name}] " if src_name or tr_name else ""
            src = " ".join((ln.get("message") or "").split())[:w]
            dst = " ".join((ln.get("trans_message") or "").split())[:w]
            print(f"{ln['line_num']:5d} {st} {ln.get('file', '')}  {spk}{src}")
            if dst:
                print(f"        -> {dst}")
    elif a.cmd == "dump":
        only = changed_line_nums(data, a.changed_since) if a.changed_since else None
        rows = [
            {
                "line_num": ln["line_num"],
                "file": ln.get("file", ""),
                "name": ln.get("name"),
                "message": ln.get("message", ""),
                "trans_name": ln.get("trans_name"),
                "trans_message": ln.get("trans_message") or "",
                "is_translated": bool(ln.get("is_translated")),
            }
            for ln in _select_lines(data, rng=rng, files=a.files, status=a.status, only=only)
        ]
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print(f"dumped {len(rows)} line(s) -> {a.out}")
    elif a.cmd == "set-hidden":
        if rng is None and not a.files:
            ap.error("set-hidden requires --range and/or --file")
        target_hidden = not a.unhide
        n = sum(1 for ln in _select_lines(data, rng=rng, files=a.files, status="all")
                if bool(ln.get("_hidden")) != target_hidden)
        print(f"would {'unhide' if a.unhide else 'hide'} {n} line(s) (preview; add --apply)")
    elif a.cmd == "fill-dupes":
        rows = fill_dupes(data, max_chars=a.max_chars)
        for r in rows[:30]:
            print(f"{r['line_num']:5d} <- {r['donor_line_num']:5d}  {r['trans_message']}")
        print(f"{len(rows)} line(s) would be filled (preview; add --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
