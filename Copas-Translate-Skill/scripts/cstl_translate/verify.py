"""Verify CopasTool project translations against structural tokens and the locked glossary."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import langpair, state
from .cstl_io import ensure_cstl, load_cstl
from .helpers import has_cjk, latin_boundary_search, normalize_apostrophes
from .integrity import message_issues

TITLES = {
    "lieutenant", "lt", "commander", "cmdr", "captain", "capt", "ensign", "doctor", "dr", "mr", "mrs", "ms",
    "miss", "admiral", "counselor", "counsellor", "chief", "elder", "hunter", "sir", "lady", "lord",
    "professor", "prof", "sergeant", "major", "colonel", "general", "cadet", "nurse", "ambassador",
    "president", "senator", "father", "mother", "brother", "sister", "master", "mistress", "minister",
    "chancellor", "governor", "director", "agent", "specialist",
}
_TAGS = re.compile(r"</?[ib]>")
_AUX_NEXT = re.compile(
    r"\s+(?:you|we|i|they|he|she|it|your|our|this|that|there|the|a|an|not|anyone|someone|everyone)\b",
    re.I,
)


def load_locked(path: str) -> dict:
    if not path:
        return {"characters": [], "terms": []}
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def normalize_apo(s: str) -> str:
    return normalize_apostrophes(s)


def _title_words(locked: dict) -> set[str]:
    extra = {
        normalize_apostrophes(str(t.get("src") or "")).lower().rstrip(".")
        for t in locked.get("terms", [])
        if t.get("src") and str(t.get("category", "")).lower() in ("rank", "title", "role")
    }
    return TITLES | {w for w in extra if " " not in w}


def _core_name(name: str, titles: set[str]) -> str:
    toks = name.split()
    while len(toks) > 1 and toks[0].lower().rstrip(".") in titles:
        toks = toks[1:]
    core = " ".join(toks)
    if " of " in core:
        core = core.split(" of ", 1)[0]
    return core


def _name_in_source(name: str, src: str) -> bool:
    if has_cjk(name):
        return name in src
    h = normalize_apostrophes(src)
    t = normalize_apostrophes(name)
    for m in re.finditer(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", h):
        if " " not in t and _AUX_NEXT.match(h, m.end()) and (m.start() == 0 or h[:m.start()].rstrip()[-1:] in ".!?\"“‘—("):
            continue
        return True
    return False


def _match_token(token: str, text: str) -> bool:
    if not token or not text:
        return False
    if has_cjk(token):
        return token in text
    return latin_boundary_search(token, text, ignore_case=True) is not None


def verify(cstl_path: str, locked_path: str = "") -> list[dict]:
    data = ensure_cstl(load_cstl(cstl_path))
    locked = load_locked(locked_path)
    dec = state.load(cstl_path)
    exc = state.token_exceptions(dec)
    tc = langpair.lang_code(data.get("target_lang") or "Indonesian")
    latin_target = tc in langpair.LATIN_TARGETS
    titles = _title_words(locked)

    issues: list[dict] = []
    chars = locked.get("characters", [])
    terms = locked.get("terms", [])

    for ln in data.get("lines", []):
        if ln.get("_hidden"):
            continue
        msg = ln.get("message") or ""
        tmsg = ln.get("trans_message") or ""
        sname = (ln.get("name") or "").strip()
        tname = (ln.get("trans_name") or "").strip()
        is_t = bool(ln.get("is_translated"))
        num = ln.get("line_num")

        if is_t and not tmsg.strip() and msg.strip():
            issues.append({"line_num": num, "kind": "empty_translation", "detail": "is_translated but trans_message empty"})
        if is_t and latin_target and tmsg and langpair.KANA.search(tmsg):
            issues.append({"line_num": num, "kind": "kana_residue", "detail": "kana left in translation"})
        if not is_t or not tmsg.strip():
            continue

        allow_exc = num is not None and int(num) in exc
        for issue in message_issues(msg, tmsg, allow_tag_mismatch=allow_exc):
            issues.append({"line_num": num, **issue})

        msg_plain = _TAGS.sub("", msg)
        tmsg_plain = _TAGS.sub("", tmsg)

        for ch in chars:
            src = str(ch.get("canonical") or ch.get("src") or "").strip()
            render = src if ch.get("keep_source") else str(ch.get("render") or ch.get("dst") or "").strip()
            aliases = [str(a).strip() for a in (ch.get("aliases") or []) if str(a).strip()]
            candidates = [c for c in [src] + aliases if c]
            if not src or not render:
                continue
            # Check speaker name alignment when speaker matches this character
            if sname and any(normalize_apo(c).lower() == normalize_apo(sname).lower() for c in candidates):
                if tname and not _match_token(render, tname):
                    issues.append({
                        "line_num": num,
                        "kind": "speaker_not_preserved",
                        "name": sname,
                        "render": render,
                        "detail": f"speaker '{sname}' translated as '{tname}', expected '{render}'",
                    })
            if normalize_apo(render) == normalize_apo(src) and has_cjk(src):
                continue
            hit = any(_match_token(c, msg_plain) and _name_in_source(c, msg_plain) for c in candidates)
            if hit:
                core = _core_name(render, titles)
                if not _match_token(render, tmsg_plain) and (core == render or not _match_token(core, tmsg_plain)):
                    issues.append({
                        "line_num": num,
                        "kind": "name_not_preserved",
                        "name": src,
                        "render": render,
                        "detail": f"source has '{src}' but translation missing '{render}'",
                    })

        for t in terms:
            src = str(t.get("src") or "").strip()
            dst = str(t.get("dst") or "").strip()
            if not src or t.get("keep_source") or not dst or normalize_apo(dst) == normalize_apo(src):
                continue
            if _match_token(src, msg_plain) and not _match_token(dst, tmsg_plain) and _match_token(src, tmsg_plain):
                issues.append({"line_num": num, "kind": "term_not_preserved", "src": src, "dst": dst})

    return issues


def _key(issue: dict) -> tuple:
    return (issue.get("kind"), int(issue.get("line_num") or 0), issue.get("detail") or issue.get("name") or issue.get("src") or "")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify CopasTool project against the locked glossary")
    ap.add_argument("cstl_path")
    ap.add_argument("locked_path", nargs="?", default="")
    ap.add_argument("--json", action="store_true", help="Print pure JSON to stdout")
    ap.add_argument("--json-out", "--out", dest="out", default=None, help="Write issues JSON to file")
    ap.add_argument("--baseline", help="Hide reviewed false positives saved in this JSON file")
    ap.add_argument("--write-baseline", metavar="FILE", help="Save current issues as baseline JSON")
    a = ap.parse_args(argv)

    issues = verify(a.cstl_path, a.locked_path)
    if a.write_baseline:
        with open(a.write_baseline, "w", encoding="utf-8") as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)
    hidden = 0
    if a.baseline and os.path.exists(a.baseline):
        with open(a.baseline, "r", encoding="utf-8-sig") as f:
            known = {_key(i) for i in json.load(f)}
        shown = [i for i in issues if _key(i) not in known]
        hidden = len(issues) - len(shown)
        issues = shown
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)
    print(json.dumps(issues, ensure_ascii=False, indent=2))
    if not a.json:
        print(f"\n{len(issues)} issue(s)" + (f" ({hidden} known in baseline hidden)" if hidden else ""))
    sys.stderr.write(f"{len(issues)} issue(s)\n")


if __name__ == "__main__":
    main()
