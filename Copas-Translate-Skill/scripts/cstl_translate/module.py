"""Module management for cstl-translate — reusable per-book settings packs."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

MODULES_ROOT = Path.home() / ".cstl-translate" / "modules"


def _module_dir(name: str) -> Path:
    p = MODULES_ROOT / name
    return p


def create_module(name: str, source_lang: str = "Japanese", target_lang: str = "Indonesian") -> Path:
    d = _module_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "glossary.locked.json").write_text(json.dumps({"characters": [], "terms": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "translate_prompt.md").write_text(f"Translate {source_lang} -> {target_lang} faithfully. Keep honorifics. Use glossary.\n", encoding="utf-8")
    (d / "polish_prompt.md").write_text("", encoding="utf-8")
    meta = {"name": name, "source_lang": source_lang, "target_lang": target_lang}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def list_modules():
    if not MODULES_ROOT.exists():
        return []
    return sorted([p.name for p in MODULES_ROOT.iterdir() if p.is_dir()])


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL modules")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cr = sub.add_parser("create")
    cr.add_argument("name")
    cr.add_argument("--source-lang", default="Japanese")
    cr.add_argument("--target-lang", default="Indonesian")
    ls = sub.add_parser("list")
    sh = sub.add_parser("show")
    sh.add_argument("name")
    ld = sub.add_parser("load")
    ld.add_argument("name")
    ld.add_argument("--work", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "create":
        d = create_module(a.name, a.source_lang, a.target_lang)
        print(f"module {a.name} -> {d}")
    elif a.cmd == "list":
        for n in list_modules():
            print(n)
        if not list_modules():
            print("(no modules)")
    elif a.cmd == "show":
        d = _module_dir(a.name)
        if not d.exists():
            raise SystemExit(f"module not found: {a.name}")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        for fn in ("glossary.locked.json", "translate_prompt.md", "polish_prompt.md"):
            p = d / fn
            print(f"\n--- {fn} {'(exists)' if p.exists() else '(missing)'} ---")
            if p.exists():
                print(p.read_text(encoding="utf-8")[:2000])
    elif a.cmd == "load":
        d = _module_dir(a.name)
        if not d.exists():
            raise SystemExit(f"module not found: {a.name}")
        work = Path(a.work)
        work.mkdir(parents=True, exist_ok=True)
        for fn in ("glossary.locked.json", "translate_prompt.md", "polish_prompt.md"):
            src = d / fn
            if src.exists():
                dst = work / ("glossary.locked.json" if fn == "glossary.locked.json" else ("user_prompt.md" if fn == "translate_prompt.md" else "polish_prompt.md"))
                shutil.copy2(src, dst)
                print(f"{fn} -> {dst}")


if __name__ == "__main__":
    main()
