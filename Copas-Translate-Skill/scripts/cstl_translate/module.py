"""Module management for cstl-translate — reusable per-book settings packs."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from . import helpers

MODULES_ROOT = Path.home() / ".cstl-translate" / "modules"


def _home_dir() -> Path:
    env = os.environ.get("CSTL_TRANSLATE_HOME")
    return Path(os.path.expanduser(env)) if env else Path.home() / ".cstl-translate"


def _modules_root() -> Path:
    if os.environ.get("CSTL_TRANSLATE_HOME"):
        return _home_dir() / "modules"
    return MODULES_ROOT


def _module_dir(name: str) -> Path:
    return _modules_root() / name


def create_module(name: str, source_lang: str = "Japanese", target_lang: str = "Indonesian") -> Path:
    d = _module_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    gl = d / "glossary.locked.json"
    if not gl.exists():
        gl.write_text(json.dumps({"characters": [], "terms": [], "non_translate": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    tp = d / "translate_prompt.md"
    if not tp.exists():
        tp.write_text(f"Translate {source_lang} -> {target_lang} faithfully. Keep honorifics and character voice. Use glossary.\n", encoding="utf-8")
    pp = d / "polish_prompt.md"
    if not pp.exists():
        pp.write_text("", encoding="utf-8")
    st = d / "style.md"
    if not st.exists():
        st.write_text("", encoding="utf-8")
    meta = {"name": name, "source_lang": source_lang, "target_lang": target_lang}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def list_modules():
    root = _modules_root()
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def load_module(name: str, work: str) -> dict:
    d = _module_dir(name)
    if not d.exists():
        raise FileNotFoundError(f"module not found: {name}")
    work_dir = Path(work)
    work_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "glossary.locked.json": "glossary.locked.json",
        "translate_prompt.md": "user_prompt.md",
        "polish_prompt.md": "polish_prompt.md",
        "style.md": "STYLE_GUIDE.md",
        "catatan_cerita.md": "CATATAN_CERITA.md",
    }
    copied = []
    for src_fn, dst_fn in mapping.items():
        src = d / src_fn
        if src.exists() and src.read_text(encoding="utf-8").strip():
            dst = work_dir / dst_fn
            if dst.exists():
                helpers.backup_file(str(dst))
            shutil.copy2(src, dst)
            copied.append(dst_fn)
    meta_file = work_dir / "active_module.json"
    meta_file.write_text(
        json.dumps({"module": name, "module_dir": str(d), "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"module": name, "module_dir": str(d), "work": str(work_dir), "copied": copied}


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL modules")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cr = sub.add_parser("create")
    cr.add_argument("name")
    cr.add_argument("--source-lang", "--source-language", dest="source_lang", default="Japanese")
    cr.add_argument("--target-lang", "--target-language", dest="target_lang", default="Indonesian")
    sub.add_parser("list")
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
        mods = list_modules()
        for n in mods:
            print(n)
        if not mods:
            print("(no modules)")
    elif a.cmd == "show":
        d = _module_dir(a.name)
        if not d.exists():
            raise SystemExit(f"module not found: {a.name}")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        for fn in ("glossary.locked.json", "translate_prompt.md", "polish_prompt.md", "style.md", "catatan_cerita.md"):
            p = d / fn
            print(f"\n--- {fn} {'(exists)' if p.exists() else '(missing)'} ---")
            if p.exists():
                print(p.read_text(encoding="utf-8")[:2000])
    elif a.cmd == "load":
        try:
            r = load_module(a.name, a.work)
        except FileNotFoundError as e:
            raise SystemExit(str(e))
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
