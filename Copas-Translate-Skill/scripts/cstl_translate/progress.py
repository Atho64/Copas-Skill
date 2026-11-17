"""Live translation/polish progress monitor over CopasTool project work directories."""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time

from . import batch, cstl_io

STALL_SEC = 180
_ICON = {"running": "▶", "stalled": "⏸", "ready": "✓", "needs_fix": "✗", "pending": "·", "written": "■"}


def _home_dir() -> str:
    return os.path.expanduser(os.environ.get("CSTL_TRANSLATE_HOME", "~/.cstl-translate"))


def _read_rows_tolerant(path: str) -> tuple[list[dict], int]:
    rows, bad = [], 0
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if path.lower().endswith(".jsonl"):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    else:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                rows = data.get("translations") or data.get("items") or data.get("polished") or []
            else:
                rows = data
        except json.JSONDecodeError:
            bad = 1
    return [r for r in rows if isinstance(r, dict) and any(k in r for k in ("line_num", "text_index", "i"))], bad


def _group_id(path: str) -> str:
    m = re.search(r"grp_([A-Za-z0-9]+)_src\.json$", os.path.basename(path))
    return m.group(1) if m else "0"


def _sort_key(path: str):
    gid = _group_id(path)
    m = re.match(r"^([A-Za-z]*)(\d+)$", gid)
    return (m.group(1), int(m.group(2))) if m else (gid, 0)


def snapshot(cstl_path: str, par_dir: str | None = None, stall_sec: int = STALL_SEC) -> dict:
    now = time.time()
    work = os.path.dirname(os.path.abspath(cstl_path))
    par_dir = par_dir or os.path.join(work, "par")
    data = cstl_io.ensure_cstl(cstl_io.load_cstl(cstl_path))
    lines = data.get("lines", [])
    by_num = {int(ln["line_num"]): ln for ln in lines}

    stage = "translate"
    try:
        with open(os.path.join(par_dir, "_stage.json"), encoding="utf-8-sig") as f:
            stage = json.load(f).get("stage", "translate")
    except (OSError, json.JSONDecodeError):
        pass

    counts = {"total": len(lines), "hidden": 0, "workable": 0, "untranslated": 0, "done": 0, "polished": 0}
    for ln in lines:
        if ln.get("_hidden"):
            counts["hidden"] += 1
            continue
        if not (ln.get("message") or "").strip():
            continue
        counts["workable"] += 1
        if ln.get("is_translated"):
            counts["done"] += 1
            if ln.get("_polished"):
                counts["polished"] += 1
        else:
            counts["untranslated"] += 1
    w = counts["workable"]
    counts["done_pct"] = round(100.0 * counts["done"] / w, 1) if w else 100.0
    counts["polished_pct"] = round(100.0 * counts["polished"] / w, 1) if w else 100.0

    groups = []
    for src_path in sorted(glob.glob(os.path.join(glob.escape(par_dir), "grp_*_src.json")), key=_sort_key):
        gid = _group_id(src_path)
        try:
            with open(src_path, encoding="utf-8-sig") as f:
                src_rows = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        src_nums = [int(r["line_num"]) for r in src_rows]
        files = []
        for r in src_rows:
            fn = r.get("file") or ""
            if fn and (not files or files[-1] != fn):
                files.append(fn)
        names = (f"polished_{gid}.jsonl", f"polished_{gid}.json", f"trans_{gid}.jsonl", f"trans_{gid}.json")
        if stage != "polish":
            names = names[2:] + names[:2]
        trans_path = next((p for p in (os.path.join(par_dir, nm) for nm in names) if os.path.exists(p)), None)
        g = {
            "group": gid,
            "src": len(src_nums),
            "first_line": src_nums[0] if src_nums else None,
            "last_line": src_nums[-1] if src_nums else None,
            "files": files,
            "lines": 0,
            "bad_lines": 0,
            "age_sec": None,
            "seg_hard": 0,
            "dups": 0,
            "extra": 0,
            "missing": 0,
            "warnings": {},
            "newterms": 0,
            "trans_file": trans_path,
        }
        nt = os.path.join(par_dir, f"newterms_{gid}.txt")
        if os.path.exists(nt):
            with open(nt, encoding="utf-8-sig") as f:
                g["newterms"] = sum(1 for l in f if l.strip() and not l.strip().startswith("#"))

        def _is_written(ln: dict) -> bool:
            return bool(ln.get("_polished")) if stage == "polish" else bool(ln.get("is_translated"))

        written = bool(src_nums) and all(i in by_num and _is_written(by_num[i]) for i in src_nums)
        if written:
            g["state"] = "written"
            g["lines"] = len(src_nums)
        elif trans_path is None:
            g["state"] = "pending"
        else:
            rows, bad = _read_rows_tolerant(trans_path)
            g["lines"], g["bad_lines"] = len(rows), bad
            g["age_sec"] = int(max(0, now - os.path.getmtime(trans_path)))
            rep = batch.validate(src_rows, rows, cstl_path=cstl_path)
            for h in rep["hard"]:
                if h["kind"] == "segment":
                    g["seg_hard"] = h["count"]
                elif h["kind"] == "duplicate_index":
                    g["dups"] = h["count"]
                elif h["kind"] == "extra_index":
                    g["extra"] = h["count"]
                elif h["kind"] == "missing_index":
                    g["missing"] = h["count"]
            g["warnings"] = {k: v["count"] for k, v in rep["warnings"].items()}
            seen_nums = {batch._row_line_num(r) for r in rows}
            complete = len(seen_nums & set(src_nums)) >= len(src_nums)
            if complete:
                g["state"] = "needs_fix" if (g["seg_hard"] or g["dups"] or g["extra"] or g["missing"]) else "ready"
            else:
                g["state"] = "stalled" if g["age_sec"] > stall_sec else "running"
        g["pct"] = round(100.0 * min(g["lines"], g["src"]) / g["src"], 1) if g["src"] else 100.0
        groups.append(g)

    events = []
    ev_path = os.path.join(work, "progress.jsonl")
    if os.path.exists(ev_path):
        with open(ev_path, encoding="utf-8") as f:
            tail = f.read().splitlines()[-8:]
        for line in tail:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {
        "ts": now,
        "project": data.get("projectName") or os.path.basename(cstl_path),
        "source_lang": data.get("source_lang", "Japanese"),
        "target_lang": data.get("target_lang", "Indonesian"),
        "work": work,
        "stage": stage,
        "stall_sec": stall_sec,
        "total": counts,
        "groups": groups,
        "events": events,
    }


def _in_flight_lines(snap: dict) -> int:
    return sum(min(g["lines"], g["src"]) for g in snap["groups"] if g["state"] in ("running", "stalled", "ready", "needs_fix"))


def _remaining_lines(snap: dict) -> int:
    return sum(g["src"] - min(g["lines"], g["src"]) for g in snap["groups"] if g["state"] != "written")


def rate_per_min(prev: dict | None, snap: dict) -> float | None:
    if not prev or snap["ts"] <= prev["ts"]:
        return None
    dl = _in_flight_lines(snap) - prev.get("lines", 0)
    dt = (snap["ts"] - prev["ts"]) / 60.0
    return max(0.0, dl / dt) if dt > 0 else None


def one_line(snap: dict, rate: float | None = None) -> str:
    t = snap["total"]
    parts = [f"{snap['project']} {t['done']}/{t['workable']} ({t['done_pct']:.0f}%)"]
    if snap.get("stage") == "polish" or t.get("polished"):
        parts.append(f"polish {t['polished']}/{t['workable']} ({t['polished_pct']:.0f}%)")
    live = [g for g in snap["groups"] if g["state"] in ("running", "stalled")]
    other: dict[str, list[str]] = {}
    for g in snap["groups"]:
        if g["state"] in ("ready", "needs_fix", "pending"):
            other.setdefault(g["state"], []).append(str(g["group"]))
    if live:
        parts.append(" ".join(f"{_ICON[g['state']]}{g['group']} {g['lines']}/{g['src']}" for g in live[:6]))
    for st in ("ready", "needs_fix", "pending"):
        if st in other:
            parts.append(f"{_ICON[st]}{','.join(other[st])}")
    if rate:
        parts.append(f"{rate:.1f}/min")
    return " · ".join(parts)


def write_line_file(text: str) -> None:
    line_file = os.path.join(_home_dir(), "progress.line")
    try:
        os.makedirs(os.path.dirname(line_file), exist_ok=True)
        with open(line_file, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def render_plain(snap: dict, rate: float | None = None) -> str:
    t = snap["total"]
    lines = [
        f"{snap['project']} [{snap['source_lang']} -> {snap['target_lang']}]  "
        f"({time.strftime('%H:%M:%S', time.localtime(snap['ts']))})",
        f"Translate: {t['done']}/{t['workable']} ({t['done_pct']}%) | Pending: {t['untranslated']} | Hidden: {t['hidden']}",
    ]
    if snap.get("stage") == "polish" or t.get("polished"):
        lines.append(f"Polish:    {t['polished']}/{t['workable']} ({t['polished_pct']}%)")
    lines.append("")
    if snap["groups"]:
        lines.append(f"{'Grp':<6} {'Files':<28} {'Lines':>9} {'State':<12} {'Age':>5} {'Hard':>5} {'Warn':>5} {'Terms':>5}")
        lines.append("-" * 82)
        for g in snap["groups"]:
            files_lbl = (", ".join(g["files"]) or f"{g['first_line']}-{g['last_line']}")[:28]
            age = "—" if g["age_sec"] is None else (f"{g['age_sec']}s" if g["age_sec"] < 90 else f"{g['age_sec'] // 60}m")
            hard = g["seg_hard"] + g["dups"] + g["extra"] + g["missing"]
            warn = sum(g["warnings"].values())
            lines.append(
                f"{str(g['group']):<6} {files_lbl:<28} {min(g['lines'], g['src']):>4}/{g['src']:<4} "
                f"{_ICON.get(g['state'], '') + ' ' + g['state']:<12} {age:>5} {hard:>5} {warn:>5} {g['newterms']:>5}"
            )
    else:
        lines.append("(no parallel groups — serial mode)")
    rem = _remaining_lines(snap)
    if rate:
        lines.append(f"\nRate: {rate:.1f} lines/min" + (f" | ETA ~{int(rem / rate)}m ({rem} left)" if rem else ""))
    return "\n".join(lines)


def serve(cstl_path: str, par_dir: str | None, stall_sec: int, port: int, open_browser: bool = False):
    import http.server
    import webbrowser
    page = os.path.join(os.path.dirname(__file__), "progress_page.html")
    with open(page, encoding="utf-8") as f:
        html = f.read().encode("utf-8")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/snapshot.json"):
                try:
                    snap = snapshot(cstl_path, par_dir, stall_sec)
                    write_line_file(one_line(snap))
                    body = json.dumps(snap, ensure_ascii=False).encode("utf-8")
                except Exception as e:
                    body = json.dumps({"error": str(e)}).encode("utf-8")
                ctype = "application/json; charset=utf-8"
            else:
                body, ctype = html, "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"progress dashboard: {url}  (Ctrl-C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Live multi-agent translation progress")
    ap.add_argument("cstl_path")
    ap.add_argument("--par", help="Parallel groups directory (default <work>/par)")
    ap.add_argument("--stall", type=int, default=STALL_SEC)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true")
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--line", action="store_true")
    mode.add_argument("--json", action="store_true")
    mode.add_argument("--serve", type=int, nargs="?", const=8765, metavar="PORT")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--interval", type=float, default=2.0)
    a = ap.parse_args(argv)

    if a.serve is not None:
        serve(a.cstl_path, a.par, a.stall, a.serve, a.open)
        return 0
    if a.watch:
        prev = None
        try:
            while True:
                snap = snapshot(a.cstl_path, a.par, a.stall)
                rate = rate_per_min(prev, snap) if prev else None
                txt = render_plain(snap, rate)
                os.system("cls" if os.name == "nt" else "clear")
                print(txt, flush=True)
                write_line_file(one_line(snap, rate))
                prev = {"ts": snap["ts"], "lines": _in_flight_lines(snap)}
                time.sleep(a.interval)
        except KeyboardInterrupt:
            return 0

    snap = snapshot(a.cstl_path, a.par, a.stall)
    if a.json:
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=1)
            print(f"snapshot -> {a.out}")
        else:
            print(json.dumps(snap, ensure_ascii=False, indent=1))
    elif a.line:
        line = one_line(snap)
        write_line_file(line)
        print(line)
    else:
        print(render_plain(snap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
