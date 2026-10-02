"""Scan CopasTool project lines for glossary gaps and artefacts (supplements verify)."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter


def normalize_apo(s: str) -> str:
    return s.replace("\u2019", "'").replace("\u2018", "'")


def _load_locked(path: str) -> dict:
    if not path:
        return {"characters": [], "terms": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def scan(cstl_path: str, locked_path: str, mode: str = "all") -> dict:
    from .cstl_io import ensure_cstl, load_cstl
    data = ensure_cstl(load_cstl(cstl_path))
    locked = _load_locked(locked_path)
    known_srcs = {normalize_apo(str(t.get("src") or t.get("canonical") or "")).lower() for t in locked.get("terms", []) + locked.get("characters", []) if str(t.get("src") or t.get("canonical") or "").strip()}
    known_srcs |= {normalize_apo(str(ch.get("render") or "")).lower() for ch in locked.get("characters", []) if ch.get("render")}

    result: dict = {"discover": [], "terms": [], "strays": [], "merges": []}

    # discover: CJK tokens appearing >=2 that are not in locked
    counter: Counter[str] = Counter()
    lines = data.get("lines", [])
    for ln in lines:
        msg = ln.get("message") or ""
        for m in re.findall(r"[\u3400-\u9fff]{2,}", msg):
            if 2 <= len(m) <= 8:
                counter[m] += 1
        for m in re.findall(r"[\u30a0-\u30ff]{2,}", msg):
            if 2 <= len(m) <= 10:
                counter[m] += 1
        name = (ln.get("name") or "").strip()
        if name and re.search(r"[\u3400-\u9fff\u30a0-\u30ff]", name):
            counter[name] += 5

    for tok, c in counter.items():
        if c < 2:
            continue
        if normalize_apo(tok).lower() in known_srcs:
            continue
        # Check if tok appears in source but render missing regime
        bins = {"tok": tok, "count": c, "examples": []}
        for ln in lines:
            if tok in (ln.get("message") or ""):
                bins["examples"].append({"line_num": ln.get("line_num"), "message": ln.get("message")[:80]})
                if len(bins["examples"]) >= 3:
                    break
        result["discover"].append(bins)

    # terms: glossary term dst missing -> src leaked
    for t in locked.get("terms", []):
        src = str(t.get("src") or "").strip()
        dst = str(t.get("dst") or "").strip()
        if not src or t.get("keep_source") or not dst or dst.lower() == src.lower():
            continue
        hits = []
        for ln in lines:
            if not ln.get("is_translated"):
                continue
            msg = normalize_apo(ln.get("message") or "").lower()
            tmsg = normalize_apo(ln.get("trans_message") or "").lower()
            if src.lower() in msg and dst.lower() not in tmsg and src.lower() in tmsg:
                hits.append({"line_num": ln.get("line_num"), "message": ln.get("message")[:60], "trans_message": (ln.get("trans_message") or "")[:60]})
        if hits:
            result["terms"].append({"src": src, "dst": dst, "hits": hits[:5]})

    # strays: latin tokens in translation not in source (hallucination signal)
    for ln in lines:
        if not ln.get("is_translated"):
            continue
        src = normalize_apo(ln.get("message") or "")
        tmsg = normalize_apo(ln.get("trans_message") or "")
        src_tokens = set(re.findall(r"[A-Za-z]{2,}", src))
        stray_tokens = [tok for tok in re.findall(r"[A-Za-z]{2,}", tmsg) if tok not in src_tokens and len(tok) >= 3]
        # Filter common Indonesian/English stop-ish
        common = {"the", "and", "for", "yang", "dan", "ini", "itu", "dengan", "untuk", "dari", "akan", "adalah", "tidak", "saya", "kamu"}
        stray_tokens = [t for t in stray_tokens if t.lower() not in common]
        if stray_tokens:
            # Only flag short suspicious names
            suspects = [t for t in stray_tokens if 2 <= len(t) <= 12 and t.istitle()]
            if suspects:
                result["strays"].append({"line_num": ln.get("line_num"), "strays": suspects[:5], "trans_message": tmsg[:80]})

    # merges: suspicious merged tokens (long camelCase / latin without spaces)
    for ln in lines:
        msg = ln.get("message") or ""
        tmsg = ln.get("trans_message") or ""
        for txt, kind in [(msg, "source"), (tmsg, "trans")]:
            for m in re.finditer(r"[A-Za-z]{10,}", txt):
                tok = m.group(0)
                # Long lower without spaces or camelCase jump
                if re.search(r"[a-z]{8,}[A-Z]", tok) or (len(tok) >= 15 and tok.islower()):
                    result["merges"].append({"line_num": ln.get("line_num"), "kind": kind, "token": tok})

    # Filter by mode
    if mode != "all":
        result = {k: v for k, v in result.items() if k == mode}
    # Trim discover to top
    if "discover" in result:
        result["discover"].sort(key=lambda x: -x["count"])
        result["discover"] = result["discover"][:50]
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan CopasTool project for glossary gaps / artefacts")
    ap.add_argument("cstl_path")
    ap.add_argument("--locked", default="")
    ap.add_argument("--mode", choices=["all", "discover", "terms", "strays", "merges"], default="all")
    a = ap.parse_args(argv)
    res = scan(a.cstl_path, a.locked, mode=a.mode)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    total = sum(len(v) for v in res.values())
    print(f"\n{total} finding(s) across {list(res.keys())}")


if __name__ == "__main__":
    main()
