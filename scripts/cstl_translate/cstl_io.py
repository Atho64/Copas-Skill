"""CSTL .cstl bundle I/O — the single-file project format CSTL uses for Backup/Restore.

A .cstl file is a JSON dump of the in-memory CSTL project state (see cstl-main/src/project.ts
buildProjectPersistenceData / onRestoreProject). Key fields:

  projectName, projectType (json|epub|luca), source_lang, target_lang,
  translationMode, imported_files, file_order, lines: Line[],
  glossary_text, epubSourceId / epub_source (EPUB bytes), lucaRawFiles/Buffers, ...

Lines schema (see types.ts `Line`):
  line_num, file, name, message, trans_name, trans_message, is_translated,
  plus optional luca_*/epub_*/ref_lang_* fields.

This module handles read/write + backup + status for .cstl files used by cstl-translate.
It preserves unknown fields (forward-compat with CSTL version bumps).
"""
from __future__ import annotations

import base64
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path


def load_cstl(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cstl(path: str, data: dict) -> None:
    data["updatedAt"] = int(datetime.now().timestamp() * 1000)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def backup_cstl(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak.{ts}"
    try:
        with open(path, "rb") as r, open(bak, "wb") as w:
            w.write(r.read())
        return bak
    except OSError:
        return None


def ensure_cstl(data: dict) -> dict:
    """Normalize a loaded .cstl dict so pipeline code can rely on defaults."""
    data.setdefault("projectName", "Untitled")
    data.setdefault("projectType", "json")
    data.setdefault("source_lang", "Japanese")
    data.setdefault("target_lang", "Indonesian")
    data.setdefault("lines", [])
    data.setdefault("imported_files", [])
    data.setdefault("file_order", [])
    data.setdefault("glossary_text", "")
    data.setdefault("version", "vM15")
    # Normalize lines
    for ln in data.get("lines", []):
        if "line_num" not in ln:
            ln["line_num"] = 0
        ln.setdefault("file", "")
        ln.setdefault("name", None)
        ln.setdefault("message", "")
        ln.setdefault("trans_name", None)
        ln.setdefault("trans_message", None)
        ln.setdefault("is_translated", False)
    return data


def cstl_status(path: str) -> dict:
    d = ensure_cstl(load_cstl(path))
    lines = d.get("lines", [])
    total = len(lines)
    translated = sum(1 for l in lines if l.get("is_translated"))
    untranslated = total - translated
    files = sorted({l.get("file", "") for l in lines}) if lines else []
    return {
        "projectName": d.get("projectName"),
        "projectType": d.get("projectType"),
        "source_lang": d.get("source_lang"),
        "target_lang": d.get("target_lang"),
        "total": total,
        "translated": translated,
        "untranslated": untranslated,
        "files": files,
        "imported_files": d.get("imported_files", []),
    }


def build_minimal_cstl(
    name: str,
    project_type: str = "json",
    source_lang: str = "Japanese",
    target_lang: str = "Indonesian",
) -> dict:
    return ensure_cstl({
        "version": "vM15",
        "projectName": name,
        "projectType": project_type,
        "translationMode": "ai",
        "source_lang": source_lang,
        "target_lang": target_lang,
        "jsonRefLang": "",
        "epubTags": "p",
        "epubSourceId": None,
        "lucaExportLang": "en",
        "luca_profile": "default",
        "luca_mc_display_name": "Tomoya",
        "lucaRawFiles": {},
        "lucaRawBuffers": {},
        "updatedAt": int(datetime.now().timestamp() * 1000),
        "regex_filter": "",
        "pre_replace_rules": "",
        "post_replace_rules": "",
        "disable_empty_line_validation": False,
        "check_kana_residue": False,
        "check_similarity": False,
        "similarity_threshold": 0.7,
        "imported_files": [],
        "file_order": [],
        "lines": [],
        "prompt_header": "Translate to {{targetLang}}, accurate and natural. Keep line numbers unchanged. Never merge or drop lines.",
        "ai_translation_format": "numbered",
        "glossary_prompt": "",
        "ai_check_prompt": "",
        "agent_prompt": "",
        "glossary_text": "",
        "context_lines": 10,
        "context_type": "raw",
        "selection_batch_size": 100,
        "glossary_batch_size": 500,
        "ai_check_batch_size": 250,
        "selection_batch_prev_shortcut": "Alt+ArrowUp",
        "selection_batch_next_shortcut": "Alt+ArrowDown",
        "enableBackgroundChaining": False,
        "currentBackground": "",
        "dict_history": [],
    })


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="CSTL .cstl helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="Print project status")
    st.add_argument("cstl_path")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        s = cstl_status(a.cstl_path)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        print(f"\n{s['translated']}/{s['total']} translated  ({s['untranslated']} remaining)  [{s['projectType']}]")


if __name__ == "__main__":
    main()
