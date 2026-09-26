"""CopasTool project backup I/O (.copas, .copas.zip, and legacy .cstl).

A .copas/.cstl file is JSON project data. Large backups use a ZIP with
project.json and custom_sources/ (see CopasTool src/project.ts). Key fields:

  projectName, projectType (json|epub|luca), source_lang, target_lang,
  translationMode, imported_files, file_order, lines: Line[],
  glossary_text, epubSourceId / epub_source (EPUB bytes), lucaRawFiles/Buffers, ...

Lines schema (see types.ts `Line`):
  line_num, file, name, message, trans_name, trans_message, is_translated,
  plus optional luca_*/epub_*/ref_lang_* fields.

This module handles the JSON project payload used by current CopasTool Backup/Restore.
Large custom-parser backups are ZIP containers with project.json and custom_sources/.
Unknown project and line fields are preserved for forward compatibility.
"""
from __future__ import annotations

import base64
import json
import os
import posixpath
import zipfile
from datetime import datetime
from pathlib import Path


def is_project_backup_path(path: str) -> bool:
    lower = str(path).lower()
    return lower.endswith((".copas", ".copas.zip", ".cstl", ".cstl.zip"))


def load_cstl(path: str) -> dict:
    """Load a JSON backup or CopasTool's project.json ZIP backup."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as zf:
            try:
                data = json.loads(zf.read("project.json").decode("utf-8-sig"))
            except KeyError as exc:
                raise ValueError("ZIP project backup has no project.json") from exc
            buffers = dict(data.get("customRawBuffers") or {})
            for name in zf.namelist():
                normalized = name.replace("\\", "/")
                prefix = "custom_sources/"
                if normalized.startswith(prefix) and not normalized.endswith("/"):
                    rel = normalized[len(prefix):]
                    if rel and not rel.startswith("/") and ".." not in rel.split("/"):
                        buffers.setdefault(rel, base64.b64encode(zf.read(name)).decode("ascii"))
            if buffers:
                data["customRawBuffers"] = buffers
            return data
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_cstl(path: str, data: dict) -> None:
    data["updatedAt"] = int(datetime.now().timestamp() * 1000)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if str(path).lower().endswith((".copas.zip", ".cstl.zip")):
        payload = dict(data)
        raw_files = payload.pop("customRawFiles", {}) or {}
        raw_buffers = payload.pop("customRawBuffers", {}) or {}
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", json.dumps(payload, ensure_ascii=False))
            written = set()
            for name, content in raw_files.items():
                rel = str(name).replace("\\", "/")
                if not rel or rel.startswith("/") or ".." in rel.split("/"):
                    continue
                zf.writestr(posixpath.join("custom_sources", rel), str(content).encode("utf-8"))
                written.add(rel)
            for name, encoded in raw_buffers.items():
                rel = str(name).replace("\\", "/")
                if rel in written or not rel or rel.startswith("/") or ".." in rel.split("/"):
                    continue
                try:
                    raw = base64.b64decode(str(encoded), validate=True)
                except Exception:
                    continue
                zf.writestr(posixpath.join("custom_sources", rel), raw)
        return
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
    """Normalize a CopasTool project payload without dropping newer fields."""
    data.setdefault("projectName", "Untitled")
    data.setdefault("projectType", "json")
    data.setdefault("source_lang", "Japanese")
    data.setdefault("target_lang", "Indonesian")
    data.setdefault("lines", [])
    data.setdefault("imported_files", [])
    data.setdefault("file_order", [])
    data.setdefault("glossary_text", "")
    data.setdefault("epub_images", [])
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
        "projectName": name,
        "projectType": project_type,
        "translationMode": "ai",
        "source_lang": source_lang,
        "target_lang": target_lang,
        "jsonRefLang": "",
        "epubTags": "p",
        "epubSourceId": None,
        "lucaExportLang": "en",
        "luca_profile": "summer-pockets-steam",
        "luca_mc_display_name": "Tomoya",
        "lucaRawFiles": {},
        "lucaRawBuffers": {},
        "updatedAt": int(datetime.now().timestamp() * 1000),
        "regex_filter": "",
        "pre_replace_rules": "",
        "post_replace_rules": "",
        "disable_empty_line_validation": False,
        "check_linebreak": False,
        "check_length_ratio": False,
        "length_ratio_threshold": 2.5,
        "check_language": False,
        "check_punctuation": False,
        "check_untrans_name": False,
        "check_kana_residue": False,
        "check_similarity": False,
        "similarity_threshold": 0.7,
        "ignore_paste_names": False,
        "enable_uncertain_marking": False,
        "safe_tags_for_chatgpt": False,
        "agent_max_turns": 10,
        "show_furigana": False,
        "furigana_type": "hiragana",
        "font_size": 14,
        "enable_dictionary": False,
        "dictionary_engine": "llm",
        "show_epub_images": True,
        "epub_images": [],
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
        "parallel_batch_size": 1,
        "subagent_workers": 3,
        "enableBackgroundChaining": False,
        "currentBackground": "",
        "enable_ai_check_chaining": True,
        "enable_ai_check_story_context": True,
        "enable_ai_check_agent_memory": True,
        "increment_enabled": False,
        "enable_logging": False,
        "proofread_settings": {},
        "dict_history": [],
    })


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="CopasTool project backup helpers")
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
