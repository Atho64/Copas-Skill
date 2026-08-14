"""Verify .cstl translations against locked glossary."""
from __future__ import annotations

import argparse
import json
import re


def load_locked(path: str) -> dict:
    if not path:
        return {"characters": [], "terms": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_apo(s: str) -> str:
    return s.replace("\u2019", "'").replace("\u2018", "'")


def verify(cstl_path: str, locked_path: str) -> list[dict]:
    from .cstl_io import ensure_cstl, load_cstl
    data = ensure_cstl(load_cstl(cstl_path))
    locked = load_locked(locked_path)
    issues: list[dict] = []
    chars = locked.get("characters", [])
    terms = locked.get("terms", [])

    for ln in data.get("lines", []):
        msg = (ln.get("message") or "")
        tmsg = (ln.get("trans_message") or "")
        is_t = bool(ln.get("is_translated"))
        num = ln.get("line_num")
        src_norm = normalize_apo(msg)
        t_norm = normalize_apo(tmsg)

        # empty translation check
        if is_t and not tmsg.strip() and msg.strip():
            issues.append({"line_num": num, "kind": "empty_translation", "detail": "is_translated but trans_message empty"})
        # kana residue: hiragana/katakana left in translation (for Indonesian target)
        if is_t and tmsg and re.search(r"[\u3040\u30ff]", tmsg):
            issues.append({"line_num": num, "kind": "kana_residue", "detail": "kana left in translation"})

        # name_not_preserved: check characters whose render differs from source and source appears but render not in translation
        # Also term consistency
        if not is_t or not tmsg.strip():
            continue
        for ch in chars:
            src = str(ch.get("canonical") or ch.get("src") or "").strip()
            render = str(ch.get("render") or ch.get("dst") or "").strip()
            aliases = [str(a).strip() for a in (ch.get("aliases") or []) if str(a).strip()]
            candidates = [src] + aliases
            if not src:
                continue
            # If render is same as src, nothing to check
            if normalize_apo(render) == normalize_apo(src):
                continue
            # Source mentions this name but translation does not contain render
            hit = any(normalize_apo(c).lower() in src_norm.lower() for c in candidates if c)
            if hit and normalize_apo(render).lower() not in t_norm.lower():
                issues.append({"line_num": num, "kind": "name_not_preserved", "name": src, "render": render, "detail": f"source has '{src}' but translation missing '{render}'"})

        for t in terms:
            src = str(t.get("src") or "").strip()
            dst = str(t.get("dst") or "").strip()
            if not src or t.get("keep_source"):
                continue
            if not dst or normalize_apo(dst) == normalize_apo(src):
                continue
            if normalize_apo(src).lower() in src_norm.lower() and normalize_apo(dst).lower() not in t_norm.lower():
                # Only flag if dst not found and src left as-is (leakage)
                if normalize_apo(src).lower() in t_norm.lower():
                    issues.append({"line_num": num, "kind": "term_not_preserved", "src": src, "dst": dst})

    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify .cstl against locked glossary")
    ap.add_argument("cstl_path")
    ap.add_argument("locked_path", nargs="?", default="")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args(argv)
    issues = verify(a.cstl_path, a.locked_path)
    print(json.dumps(issues, ensure_ascii=False, indent=2))
    print(f"\n{len(issues)} issue(s)")
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
