"""Fetch VN metadata and character glossaries from the VNDB Kana API v2."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Callable

from . import glossary as glossary_mod, langpair
from .cstl_io import ensure_cstl, load_cstl
from .helpers import backup_file, has_cjk, latin_boundary_search, normalize_apostrophes

VNDB_API_URL = "https://api.vndb.org/kana"
USER_AGENT = "Copas-Translate-Skill/1.0"
VN_FIELDS = "id,title,alttitle,titles{lang,title,latin,official,main},aliases,description"
CHAR_FIELDS = "id,name,original,aliases,sex,description,vns{id,role,spoiler}"

ROLE_PRIORITY = {"main": 0, "primary": 1, "side": 2, "appears": 3}
SEX_LABELS = {"m": "male", "f": "female", "b": "both", "n": "sexless"}

_VN_ID_RE = re.compile(r"(?:vndb\.org/)?(v\d+)\b|^(\d+)$", re.I)
_SPOILER_BLOCK_RE = re.compile(r"\[spoiler\](?:(?!\[/?spoiler\]).)*?\[/spoiler\]", re.I | re.S)
_URL_TAG_RE = re.compile(r"\[url=[^\]]*\](.*?)\[/url\]", re.I | re.S)
_BBCODE_TAG_RE = re.compile(r"\[/?(?:b|i|u|s|code|raw|quote|spoiler)(?:=[^\]]*)?\]", re.I)
_HONORIFIC_TAIL_RE = re.compile(
    r"(?:[-‐‑–—]?(?:san|kun|chan|sama|sensei|senpai|dono)|さん|くん|ちゃん|様|先生|先輩|殿)$",
    re.I,
)


def normalize_vn_id(value: str | None) -> str | None:
    """Parse a VNDB VN id ('v17', '17', or 'https://vndb.org/v17') -> 'v17'."""
    s = str(value or "").strip()
    if not s:
        return None
    m = _VN_ID_RE.search(s)
    if not m:
        return None
    if m.group(1):
        return m.group(1).lower()
    if m.group(2) and s.isdigit():
        return f"v{m.group(2)}"
    return None


def vndb_post(endpoint: str, payload: dict, timeout: float = 15.0) -> dict:
    """Execute a JSON POST against the VNDB Kana API v2."""
    url = f"{VNDB_API_URL}/{endpoint.lstrip('/')}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            pass
        if exc.code == 429:
            raise RuntimeError("VNDB API rate limit (429): wait briefly and retry.") from exc
        raise RuntimeError(f"VNDB API HTTP {exc.code} on {endpoint}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"VNDB API connection failed on {endpoint}: {exc.reason}") from exc


def search_vns(
    query: str,
    limit: int = 10,
    post_fn: Callable[[str, dict], dict] | None = None,
) -> list[dict]:
    """Search visual novels on VNDB by title/alias."""
    post = post_fn or vndb_post
    resp = post("vn", {
        "filters": ["search", "=", query],
        "fields": VN_FIELDS,
        "sort": "searchrank",
        "results": max(1, min(100, int(limit))),
    })
    return list(resp.get("results") or [])


def fetch_vn(
    vn_id: str,
    post_fn: Callable[[str, dict], dict] | None = None,
) -> dict | None:
    """Fetch metadata for one VNDB visual novel ID."""
    post = post_fn or vndb_post
    vid = normalize_vn_id(vn_id) or vn_id
    resp = post("vn", {
        "filters": ["id", "=", vid],
        "fields": VN_FIELDS,
        "results": 1,
    })
    rows = resp.get("results") or []
    return rows[0] if rows else None


def fetch_vn_characters(
    vn_id: str,
    page_size: int = 100,
    max_pages: int = 50,
    post_fn: Callable[[str, dict], dict] | None = None,
) -> list[dict]:
    """Fetch all characters linked to `vn_id` across paginated VNDB results."""
    post = post_fn or vndb_post
    vid = normalize_vn_id(vn_id) or vn_id
    out: list[dict] = []
    size = max(1, min(100, int(page_size)))
    for page in range(1, max_pages + 1):
        resp = post("character", {
            "filters": ["vn", "=", ["id", "=", vid]],
            "fields": CHAR_FIELDS,
            "sort": "id",
            "results": size,
            "page": page,
        })
        out.extend(resp.get("results") or [])
        if not resp.get("more"):
            break
    return out


def pick_vn_candidate(vns: list[dict], query: str) -> dict | None:
    """Pick the strongest matching VN record from search results."""
    if not vns:
        return None
    q = normalize_apostrophes(query or "").strip().casefold()
    for vn in vns:
        names = [vn.get("title"), vn.get("alttitle")] + list(vn.get("aliases") or [])
        names += [t.get("title") for t in (vn.get("titles") or []) if isinstance(t, dict)]
        if any(normalize_apostrophes(str(n or "")).strip().casefold() == q for n in names if n):
            return vn
    return vns[0]


def clean_vndb_text(text: str | None, include_spoilers: bool = False) -> str:
    """Strip VNDB BBCode markup and optionally remove `[spoiler]` sections."""
    s = str(text or "")
    if not s:
        return ""
    if not include_spoilers:
        while _SPOILER_BLOCK_RE.search(s):
            s = _SPOILER_BLOCK_RE.sub("", s)
    s = _URL_TAG_RE.sub(r"\1", s)
    s = _BBCODE_TAG_RE.sub("", s)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _compact_space(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", text or "").strip()


def _has_japanese_kanji(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


_HONORIFIC_PAIRS = (
    ("さん", "-san"),
    ("くん", "-kun"),
    ("ちゃん", "-chan"),
    ("様", "-sama"),
    ("先生", "-sensei"),
    ("先輩", "-senpai"),
    ("殿", "-dono"),
)


def _is_honorific_or_titled(alias: str) -> bool:
    toks = normalize_apostrophes(alias or "").strip().split()
    if toks and toks[0].lower().rstrip(".") in glossary_mod._TITLES:
        return True
    return bool(_HONORIFIC_TAIL_RE.search(alias or ""))


def _strip_matched_honorific(jp: str, lat: str) -> tuple[str, str] | None:
    """If `jp` and `lat` share the same trailing honorific, return stripped `(jp_base, lat_base)`."""
    low = lat.lower()
    for jp_suf, lat_suf in _HONORIFIC_PAIRS:
        if jp.endswith(jp_suf) and low.endswith(lat_suf):
            jb = jp[: -len(jp_suf)].strip()
            lb = lat[: -len(lat_suf)].strip()
            if jb and lb:
                return jb, lb
    return None


def _extract_alias_pairs(
    raw_aliases: list[str],
    source_code: str,
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """Parse VNDB `aliases` into `(nickname_pairs, unpaired_script_aliases, note_aliases)`."""
    nicks: list[tuple[str, str]] = []
    unpaired: list[str] = []
    notes: list[str] = []
    i = 0
    while i < len(raw_aliases):
        cur = raw_aliases[i]
        nxt = raw_aliases[i + 1] if i + 1 < len(raw_aliases) else ""
        is_bilingual_pair = (
            source_code != "en"
            and nxt
            and has_cjk(cur)
            and not has_cjk(nxt)
            and bool(re.search(r"[A-Za-z]", nxt))
            and not (_is_honorific_or_titled(nxt) and not _is_honorific_or_titled(cur))
        )
        if is_bilingual_pair:
            has_space = bool(re.search(r"[\s\u3000]", cur) or re.search(r"\s", nxt))
            if has_space:
                # Multi-word alternate name (e.g. married/spoiler name) -> keep as reference note only
                notes.append(f"{cur} ({nxt})")
            else:
                stripped = _strip_matched_honorific(cur, nxt)
                if stripped and len(stripped[0]) >= 2 and not _is_honorific_or_titled(stripped[1]):
                    nicks.append(stripped)
                    notes.append(nxt)
                elif not _is_honorific_or_titled(cur) and not _is_honorific_or_titled(nxt) and len(cur) >= 2:
                    nicks.append((cur, nxt))
                else:
                    notes.append(f"{cur} ({nxt})")
            i += 2
            continue

        if _is_honorific_or_titled(cur):
            notes.append(cur)
        elif source_code == "en":
            (unpaired if not has_cjk(cur) else notes).append(cur)
        elif has_cjk(cur):
            unpaired.append(cur)
            compact = _compact_space(cur)
            if compact != cur:
                unpaired.append(compact)
        else:
            notes.append(cur)
        i += 1
    return nicks, unpaired, notes


def _char_vn_relation(char: dict, vn_id: str) -> tuple[str, int]:
    """Return `(role, spoiler)` of a character inside `vn_id`."""
    best_role = "side"
    best_prio = 99
    best_spoiler = 0
    for link in char.get("vns") or []:
        if not isinstance(link, dict) or str(link.get("id") or "").lower() != vn_id.lower():
            continue
        role = str(link.get("role") or "side").lower()
        prio = ROLE_PRIORITY.get(role, 99)
        sp = int(link.get("spoiler") or 0)
        if prio < best_prio or (prio == best_prio and sp < best_spoiler):
            best_role, best_prio, best_spoiler = role, prio, sp
    return best_role, best_spoiler


def _format_sex(sex_val) -> str:
    if isinstance(sex_val, (list, tuple)) and sex_val:
        code = str(sex_val[0] or "").lower()
    elif isinstance(sex_val, str):
        code = sex_val.lower()
    else:
        code = ""
    return SEX_LABELS.get(code, "")


def _split_cjk_latin_pair(original: str, romaji: str) -> tuple[list[tuple[str, str]], bool] | None:
    """Split bilingual two-part personal names into `[(src_part, lat_part), ...], is_japanese_order`."""
    orig = (original or "").strip()
    lat = " ".join((romaji or "").strip().split())
    if not orig or not lat:
        return None
    lat_parts = lat.split(" ")
    if len(lat_parts) != 2 or any(has_cjk(p) for p in lat_parts):
        return None
    ws_parts = [p for p in re.split(r"[\s\u3000]+", orig) if p]
    if len(ws_parts) == 2 and has_cjk(orig):
        jp_order = _has_japanese_kanji(ws_parts[0]) or not _is_pure_katakana(ws_parts[0])
        return [(ws_parts[0], lat_parts[0]), (ws_parts[1], lat_parts[1])], jp_order
    if "・" in orig and not re.search(r"[\s\u3000]", orig):
        dot_parts = [p for p in orig.split("・") if p]
        if len(dot_parts) == 2:
            return [(dot_parts[0], lat_parts[0]), (dot_parts[1], lat_parts[1])], False
    return None


def _is_pure_katakana(text: str) -> bool:
    return bool(text) and bool(re.fullmatch(r"[\u30a0-\u30ffー・]+", text))


def _format_render_name(original: str, romaji: str, name_order: str) -> str:
    lat = " ".join((romaji or "").strip().split())
    if name_order != "given-family" or not original or not lat:
        return lat
    split = _split_cjk_latin_pair(original, lat)
    if split and split[1]:
        pairs = split[0]
        return f"{pairs[1][1]} {pairs[0][1]}"
    return lat


def _load_project_corpus(cstl_path: str | None) -> tuple[str, set[str], str, list[str]]:
    """Return `(source_lang_code, speaker_set, combined_corpus, ordered_texts)`."""
    if not cstl_path:
        return "ja", set(), "", []
    data = ensure_cstl(load_cstl(cstl_path))
    sc = langpair.lang_code(data.get("source_lang") or "Japanese")
    speakers: set[str] = set()
    texts: list[str] = []
    for ln in data.get("lines", []):
        if ln.get("_hidden"):
            continue
        name = str(ln.get("name") or "").strip()
        msg = str(ln.get("message") or "")
        if name:
            speakers.add(name)
        if msg:
            texts.append(msg)
    corpus = normalize_apostrophes("\n".join(texts + sorted(speakers)))
    return sc, speakers, corpus, texts


def _count_hits(tokens: list[str], speakers: set[str], texts: list[str]) -> int:
    if not tokens:
        return 0
    hits = 0
    for sp in speakers:
        if any(_match_name(tok, sp) for tok in tokens):
            hits += 3
    for msg in texts:
        if any(_match_name(tok, msg) for tok in tokens):
            hits += 1
    return hits


def _match_name(token: str, text: str) -> bool:
    t = normalize_apostrophes(token or "").strip()
    if not t or not text:
        return False
    if has_cjk(t):
        return t in text
    return latin_boundary_search(t, text, ignore_case=True) is not None


def _choose_canonical(
    original: str,
    romaji: str,
    source_code: str,
    speakers: set[str],
    corpus: str,
) -> tuple[str, list[str], bool]:
    """Choose canonical source string, spacing variants, and `keep_source`."""
    orig = (original or "").strip()
    lat = " ".join((romaji or "").strip().split())
    if source_code == "en" or not orig:
        canon = lat or orig
        return canon, [], bool(canon and normalize_apostrophes(canon) == normalize_apostrophes(lat))
    compact = _compact_space(orig)
    if compact and compact != orig:
        if orig in speakers or (orig in corpus and compact not in speakers and compact not in corpus):
            return orig, [compact], False
        return compact, [orig], False
    return compact or orig, [], False


def _short_summary(text: str, max_chars: int = 180) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 3].rstrip() + "..."


def build_glossary_from_vndb(
    vn_id: str,
    characters_raw: list[dict],
    vn_meta: dict | None = None,
    cstl_path: str | None = None,
    source_lang: str | None = None,
    name_order: str = "family-given",
    split_names: str = "auto",
    roles: set[str] | None = None,
    max_spoiler: int = 2,
    include_spoilers: bool = False,
    matched_only: bool = False,
    existing_locked: dict | None = None,
) -> tuple[dict, list[dict]]:
    """Build a clean, lint-safe `locked` glossary dict and detailed cast metadata."""
    sc, speakers, corpus, texts = _load_project_corpus(cstl_path)
    if source_lang:
        sc = langpair.lang_code(source_lang)

    # First pass: determine eligible characters and count raw alias/name occurrences to prevent collisions
    records: list[dict] = []
    alias_freq: dict[str, int] = {}
    split_map: dict[str, set[str]] = {}

    for ch in characters_raw:
        role, spoiler = _char_vn_relation(ch, vn_id)
        if roles and role not in roles:
            continue
        if spoiler > max_spoiler:
            continue
        romaji = " ".join(str(ch.get("name") or "").strip().split())
        orig = str(ch.get("original") or "").strip()
        if not romaji and not orig:
            continue
        canon, spacing_vars, keep_source = _choose_canonical(orig, romaji, sc, speakers, corpus)
        render = canon if keep_source else _format_render_name(orig, romaji, name_order)
        if not render:
            render = canon

        raw_aliases = [str(a).strip() for a in (ch.get("aliases") or []) if str(a).strip()]
        nick_pairs, unpaired_script, note_aliases = _extract_alias_pairs(raw_aliases, sc)
        # Keep paired nicknames as standalone glossary entries rather than full-name aliases
        nick_srcs = {normalize_apostrophes(jp).lower() for jp, _ in nick_pairs}
        script_aliases = [a for a in spacing_vars + unpaired_script
                          if a != canon and a != render and normalize_apostrophes(a).lower() not in nick_srcs]

        dedup_script: list[str] = []
        seen_a: set[str] = {normalize_apostrophes(canon).lower(), normalize_apostrophes(render).lower()}
        for a in script_aliases:
            k = normalize_apostrophes(a).lower()
            if k not in seen_a:
                seen_a.add(k)
                dedup_script.append(a)
                alias_freq[k] = alias_freq.get(k, 0) + 1
        alias_freq[normalize_apostrophes(canon).lower()] = alias_freq.get(normalize_apostrophes(canon).lower(), 0) + 1

        split_parts: list[tuple[str, str, str]] = []
        family_part: tuple[str, str] | None = None
        given_part: tuple[str, str] | None = None
        if sc != "en" and orig and romaji:
            sp = _split_cjk_latin_pair(orig, romaji)
            if sp:
                (p0, l0), (p1, l1) = sp[0][0], sp[0][1]
                # Western middle-dot (`メアリ・スミス`) is [given, family]; CJK space without trailing pure-katakana is [family, given]
                ws_split = not ("・" in orig and not re.search(r"[\s\u3000]", orig))
                if not ws_split:
                    given_part, family_part = (p0, l0), (p1, l1)
                    roles_p = ("given", "family")
                elif _is_pure_katakana(p1) and not _is_pure_katakana(p0):
                    # Could be Western surname (`紬 ヴェンダース`) or Japanese katakana given (`八神 ココ`)
                    roles_p = ("part", "part")
                else:
                    family_part, given_part = (p0, l0), (p1, l1)
                    roles_p = ("family", "given")
                for (src_p, lat_p), kind_p in zip(sp[0], roles_p):
                    if src_p and lat_p:
                        split_parts.append((src_p, lat_p, kind_p))
                        split_map.setdefault(normalize_apostrophes(src_p).lower(), set()).add(lat_p)

        for n_src, n_lat in nick_pairs:
            split_map.setdefault(normalize_apostrophes(n_src).lower(), set()).add(n_lat)

        search_tokens = [canon] + dedup_script + [p[0] for p in split_parts] + [jp for jp, _ in nick_pairs]
        hits = _count_hits(search_tokens, speakers, texts) if cstl_path else 0
        if matched_only and cstl_path and hits == 0:
            continue

        sex_lbl = _format_sex(ch.get("sex"))
        desc_text = clean_vndb_text(ch.get("description"), include_spoilers=include_spoilers)
        meta_bits = [bit for bit in (role, sex_lbl) if bit]
        header = ", ".join(meta_bits)
        breakdown_bits: list[str] = []
        if family_part:
            breakdown_bits.append(f"family={family_part[0]}:{family_part[1]}")
        if given_part:
            breakdown_bits.append(f"given={given_part[0]}:{given_part[1]}")
        if not family_part and not given_part and len(split_parts) == 2:
            breakdown_bits.append(f"parts={split_parts[0][0]}:{split_parts[0][1]}/{split_parts[1][0]}:{split_parts[1][1]}")
        if nick_pairs:
            breakdown_bits.append("nick=" + ", ".join(f"{jp}:{lt}" for jp, lt in nick_pairs))
        summary = _short_summary(desc_text)
        desc_pieces = ["; ".join(breakdown_bits)] if breakdown_bits else []
        if summary:
            desc_pieces.append(summary)
        if note_aliases:
            uniq_notes = list(dict.fromkeys(note_aliases))[:5]
            desc_pieces.append(f"(aliases: {', '.join(uniq_notes)})")
        body = " | ".join(desc_pieces)
        full_desc = f"[{header}] {body}".strip() if header and body else (header or body or "character name")

        records.append({
            "vndb_id": ch.get("id") or "",
            "canonical": canon,
            "render": render,
            "raw_original": orig,
            "raw_name": romaji,
            "family_part": family_part,
            "given_part": given_part,
            "nickname_pairs": nick_pairs,
            "script_aliases": dedup_script,
            "note_aliases": list(dict.fromkeys(note_aliases)),
            "split_parts": split_parts,
            "role": role,
            "spoiler": spoiler,
            "sex": sex_lbl,
            "description": desc_text,
            "desc": full_desc,
            "keep_source": keep_source,
            "hits": hits,
        })

    records.sort(key=lambda r: (-r["hits"], ROLE_PRIORITY.get(r["role"], 99), r["canonical"]))

    locked = _initialize_locked(existing_locked)
    owned = _existing_owner_set(locked)
    kept_records: list[dict] = []

    # Pass 1: register primary character entries before splits so splits never shadow another character
    for rec in records:
        canon_k = normalize_apostrophes(rec["canonical"]).lower()
        render_k = normalize_apostrophes(rec["render"]).lower()
        if canon_k in owned or render_k in owned:
            continue
        safe_aliases = []
        for a in rec["script_aliases"]:
            ak = normalize_apostrophes(a).lower()
            # Drop aliases shared by multiple characters so `glossary lint` never raises alias_collides
            if alias_freq.get(ak, 0) > 1 or ak in owned:
                continue
            safe_aliases.append(a)
            owned.add(ak)
        owned.add(canon_k)
        owned.add(render_k)

        locked["characters"].append({
            "canonical": rec["canonical"],
            "render": rec["render"],
            "aliases": safe_aliases,
            "type": "character",
            "desc": rec["desc"],
            "keep_source": rec["keep_source"],
        })
        kept_records.append(rec)

    # Pass 2: emit standalone family names, given names, and paired nicknames
    if split_names != "none":
        for rec in kept_records:
            extra_items = list(rec["split_parts"]) + [(jp, lt, "nickname") for jp, lt in rec["nickname_pairs"]]
            for src_p, lat_p, kind_p in extra_items:
                pk = normalize_apostrophes(src_p).lower()
                lk = normalize_apostrophes(lat_p).lower()
                if len(split_map.get(pk, set())) > 1 or pk in owned or lk in owned:
                    continue
                appear_standalone = (
                    src_p in speakers
                    or (corpus and re.search(rf"(?<![\u4e00-\u9fff]){re.escape(src_p)}(?![\u4e00-\u9fff])", corpus))
                )
                if split_names == "all" or (split_names == "auto" and cstl_path and appear_standalone):
                    owned.add(pk)
                    owned.add(lk)
                    label = {"family": "family name", "given": "given name", "nickname": "nickname"}.get(kind_p, "name part")
                    role_hdr = f"{rec['role']}{', ' + rec['sex'] if rec['sex'] else ''}"
                    locked["characters"].append({
                        "canonical": src_p,
                        "render": lat_p,
                        "aliases": [],
                        "type": "character",
                        "desc": f"[{role_hdr}] {label} of {rec['render']}",
                        "keep_source": False,
                    })

    return locked, records


def _initialize_locked(existing_locked: dict | None) -> dict:
    if not existing_locked:
        return {"characters": [], "terms": [], "non_translate": []}
    return {
        "characters": [dict(c) for c in existing_locked.get("characters", [])],
        "terms": [dict(t) for t in existing_locked.get("terms", [])],
        "non_translate": list(existing_locked.get("non_translate", [])),
    }


def _existing_owner_set(locked: dict) -> set[str]:
    owned: set[str] = set()
    for c in locked.get("characters", []):
        for val in [c.get("canonical"), c.get("render")] + list(c.get("aliases") or []):
            if val:
                owned.add(normalize_apostrophes(str(val)).lower())
    return owned


def format_cast_markdown(vn_meta: dict | None, records: list[dict], include_spoilers: bool = False) -> str:
    """Render a clean Markdown character & VN reference sheet for `BOOK_BIBLE.md`."""
    lines: list[str] = []
    if vn_meta:
        vid = vn_meta.get("id") or ""
        title = vn_meta.get("title") or vid or "VNDB Visual Novel"
        alt = vn_meta.get("alttitle") or ""
        lines.append(f"# VNDB Cast Reference: {title}" + (f" ({vid})" if vid else ""))
        lines.append("")
        if alt:
            lines.append(f"- **Original title**: {alt}")
        official = [
            f"{t.get('lang')}: {t.get('title')}"
            for t in (vn_meta.get("titles") or [])
            if isinstance(t, dict) and t.get("official") and t.get("title")
        ]
        if official:
            lines.append(f"- **Official titles**: {' | '.join(dict.fromkeys(official))}")
        vn_desc = clean_vndb_text(vn_meta.get("description"), include_spoilers=include_spoilers)
        if vn_desc:
            lines.append("")
            lines.append("## Synopsis")
            lines.append(vn_desc)
    else:
        lines.append("# VNDB Cast Reference")
    lines.append("")
    lines.append(f"## Characters ({len(records)})")
    lines.append("")
    lines.append("| Original | Render | Family | Given | Nicknames | Role | Sex | Aliases / Notes |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in records:
        orig = (r.get("raw_original") or r.get("canonical") or "").replace("|", "\\|")
        rend = (r.get("render") or "").replace("|", "\\|")
        fam = f"{r['family_part'][0]} ({r['family_part'][1]})" if r.get("family_part") else "-"
        giv = f"{r['given_part'][0]} ({r['given_part'][1]})" if r.get("given_part") else "-"
        if not r.get("family_part") and not r.get("given_part") and len(r.get("split_parts") or []) == 2:
            sp = r["split_parts"]
            fam = f"{sp[0][0]}:{sp[0][1]} / {sp[1][0]}:{sp[1][1]}"
            giv = "(mixed order)"
        nicks = ", ".join(f"{jp} = {lt}" for jp, lt in (r.get("nickname_pairs") or [])) or "-"
        role = (r.get("role") or "-").replace("|", "\\|")
        sex = (r.get("sex") or "-").replace("|", "\\|")
        other_aliases = list(r.get("script_aliases") or []) + list(r.get("note_aliases") or [])
        alias_str = ", ".join(other_aliases).replace("|", "\\|")
        note_str = _short_summary(r.get("description") or "", 110).replace("|", "\\|")
        notes = f"[{alias_str}] {note_str}".strip() if alias_str and note_str else (alias_str or note_str or "-")
        lines.append(
            f"| {orig} | {rend} | {fam.replace('|', '\\|')} | {giv.replace('|', '\\|')} "
            f"| {nicks.replace('|', '\\|')} | {role} | {sex} | {notes} |"
        )
    return "\n".join(lines) + "\n"


def add_vndb_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Register VNDB CLI arguments on a subparser or standalone parser."""
    parser.add_argument("cstl_path", nargs="?", help="Optional CopasTool project (.copas / .copas.zip) for matching & inject")
    parser.add_argument("--project", dest="project_opt", help="CopasTool project path (alternative to positional)")
    parser.add_argument("--vn", help="VNDB VN ID or URL (e.g. v17, 17, https://vndb.org/v17)")
    parser.add_argument("--query", help="Search VNDB by title (defaults to projectName if project given)")
    parser.add_argument("--search", action="store_true", help="Only search and list matching VNDB entries")
    parser.add_argument("--out", help="Output path for locked glossary JSON")
    parser.add_argument("--cast-out", help="Optional Markdown cast reference sheet path")
    parser.add_argument("--merge", action="store_true", help="Merge into existing --out glossary without overwriting existing entries")
    parser.add_argument("--inject", action="store_true", help="Also inject updated glossary_text into the project backup")
    parser.add_argument("--matched-only", action="store_true", help="Keep only characters appearing in the project")
    parser.add_argument("--source-lang", help="Override source language (e.g. Japanese, English)")
    parser.add_argument("--name-order", choices=["family-given", "given-family"], default="family-given")
    parser.add_argument("--split-names", choices=["auto", "all", "none"], default="auto")
    parser.add_argument("--roles", nargs="*", help="Filter VNDB roles (main primary side appears)")
    parser.add_argument("--max-spoiler", type=int, default=2, choices=[0, 1, 2])
    parser.add_argument("--include-spoilers", action="store_true", help="Keep [spoiler] text in descriptions")
    parser.add_argument("--limit", type=int, default=10, help="Max search results for --search")
    return parser


def run_cli_args(args: argparse.Namespace, post_fn: Callable[[str, dict], dict] | None = None) -> int:
    """Execute parsed VNDB glossary CLI arguments."""
    project = args.project_opt or args.cstl_path
    query = args.query
    if not query and not args.vn and project:
        pdata = ensure_cstl(load_cstl(project))
        pname = str(pdata.get("projectName") or "").strip()
        if pname and pname.lower() != "untitled":
            query = pname

    if args.search:
        if not query and args.vn:
            vid = normalize_vn_id(args.vn)
            vn = fetch_vn(vid, post_fn=post_fn) if vid else None
            results = [vn] if vn else []
        elif query:
            results = search_vns(query, limit=args.limit, post_fn=post_fn)
        else:
            raise SystemExit("VNDB search requires --query or --vn.")
        for vn in results:
            altt = f" / {vn['alttitle']}" if vn.get("alttitle") else ""
            print(f"{vn.get('id')}\t{vn.get('title')}{altt}")
        if not results:
            print("No VNDB matches found.")
        return 0

    vn_meta: dict | None = None
    vid = normalize_vn_id(args.vn) if args.vn else None
    if vid:
        vn_meta = fetch_vn(vid, post_fn=post_fn)
    elif query or args.vn:
        q = query or args.vn or ""
        matches = search_vns(q, limit=max(5, args.limit), post_fn=post_fn)
        vn_meta = pick_vn_candidate(matches, q)
        if not vn_meta:
            raise SystemExit(f"No VNDB VN match found for {q!r}")
        vid = vn_meta["id"]
        print(f"selected VNDB {vid}: {vn_meta.get('title')}")
        if len(matches) > 1:
            alts = ", ".join(f"{m['id']} ({m.get('title')})" for m in matches[1:4])
            print(f"other matches: {alts}")
    else:
        raise SystemExit("Specify --vn <vID>, --query <title>, or a project with projectName.")

    chars_raw = fetch_vn_characters(vid, post_fn=post_fn)
    existing = None
    if args.merge and args.out and os.path.exists(args.out):
        with open(args.out, "r", encoding="utf-8-sig") as f:
            existing = json.load(f)

    roles_set = {r.lower() for r in args.roles} if args.roles else None
    locked_data, records = build_glossary_from_vndb(
        vid,
        chars_raw,
        vn_meta=vn_meta,
        cstl_path=project,
        source_lang=args.source_lang,
        name_order=args.name_order,
        split_names=args.split_names,
        roles=roles_set,
        max_spoiler=args.max_spoiler,
        include_spoilers=args.include_spoilers,
        matched_only=args.matched_only,
        existing_locked=existing,
    )

    out_path = args.out
    if not out_path:
        base_dir = os.path.dirname(os.path.abspath(project)) if project else "."
        out_path = os.path.join(base_dir, "glossary.locked.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    if os.path.exists(out_path):
        backup_file(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(locked_data, f, ensure_ascii=False, indent=2)

    issues = glossary_mod.lint_locked(locked_data)
    matched_n = sum(1 for r in records if r["hits"] > 0)
    print(
        f"vndb glossary ({vid}) -> {out_path}  "
        f"(fetched={len(chars_raw)} kept={len(records)} matched_in_project={matched_n} "
        f"total_characters={len(locked_data['characters'])} lint_issues={len(issues)})"
    )
    if args.cast_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.cast_out)) or ".", exist_ok=True)
        md = format_cast_markdown(vn_meta, records, include_spoilers=args.include_spoilers)
        with open(args.cast_out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"cast sheet -> {args.cast_out}")
    if args.inject:
        if not project:
            raise SystemExit("--inject requires a CopasTool project path.")
        glossary_mod.inject_into_cstl(project, out_path)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch character glossary from VNDB Kana API v2")
    add_vndb_arguments(ap)
    return run_cli_args(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
