"""Language-pair profiles. Primary: Japanese -> Indonesian; also English -> Indonesian
and Japanese -> English. Profiles drive mechanical checks (audit, review gate) and
which pair-specific rules a task packet points to."""
from __future__ import annotations

import re

ALIASES = {
    "ja": {"japanese", "jepang", "bahasa jepang", "日本語", "ja", "jp", "jpn", "ja-jp"},
    "id": {"indonesian", "indonesia", "bahasa indonesia", "id", "ind", "id-id", "in"},
    "en": {"english", "inggris", "bahasa inggris", "en", "eng", "en-us", "en-gb"},
    "zh": {"chinese", "中文", "简体中文", "繁體中文", "zh", "zh-cn", "zh-tw", "zho"},
    "ko": {"korean", "한국어", "ko", "kor"},
}

SUPPORTED = {
    "ja-id": "Japanese -> Indonesian (primary)",
    "en-id": "English -> Indonesian",
    "ja-en": "Japanese -> English",
}

KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\uff66-\uff9f]")
KANJI = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
JP_PUNCT = re.compile(r"[。、「」『』【】〈〉《》！？～〜・（）：；―]")
LATIN_TARGETS = {"id", "en"}

# (minimum visible source chars, lowest ratio, highest ratio) of target/source visible length
LENGTH_RATIO = {
    "ja-id": (8, 0.9, 7.0),
    "ja-en": (8, 0.9, 7.0),
    "en-id": (40, 0.6, 2.0),
}

ENGLISH_FUNCTION = {"the", "and", "of", "you", "is", "are", "was", "were", "with", "that", "this",
                    "have", "what", "your", "for", "not", "but", "they", "there", "would"}
ID_FORMAL = {"anda", "saya"}
ID_SLANG = {"gue", "gua", "gw", "lo", "lu", "elo", "elu"}
# English comic/VN SFX and vocal fillers that should be localized to Indonesian (never block tags via _TOKEN stripping)
ID_ENGLISH_SFX = re.compile(
    r"\b(?:"
    r"uh+|uhm+|umm+|erm+|ugh+|ergh+|urgh+|a+rgh+|agh+|ack+|u+ngh+|h+n+g+h*|n+g+h+|m+p+h+|"
    r"ouch+|oomph+|ow{2,}|eww+|yikes+|whoa+|woah+|sheesh+|j+eez+|g+eez+|"
    r"snif+|sniffl(?:e|es|ed|ing)|snorts?|"
    r"sigh(?:s|ed|ing)?|gasps?|groans?|grunts?|gulps?|sobs?|sobbed|sobbing|pants?|"
    r"smirks?|snickers?|chuckles?|giggles?|whimpers?|shrieks?|squeaks?|yelps?|yawns?|coughs?|sneezes?|hiccups?|"
    r"mumbles?|murmurs?|mutters?|whines?|growls?|huffs?|wheezes?|thumps?|throbs?|ba-?dumps?|"
    r"blush(?:es|ed|ing)?|pouts?|frowns?|scowls?|glares?|stares?|winces?|flinches?|shudders?|shivers?|shrugs?|nods?|"
    r"thuds?|thwacks?|smacks?|whacks?|slams?|crashes?|splashes?|swoosh(?:es)?|whoosh(?:es)?|"
    r"clatters?|rattles?|creaks?|rustles?|clanks?|clinks?|screech(?:es)?|splats?|clicks?|"
    r"pff+t*|humph+|hmph+|tch+|tsk+|phew+|whew+|eek+|eep+|bleh+|shh+|shush+|sweatdrops?"
    r")\b",
    re.I,
)

_TOKEN = re.compile(r"<[^<>\r\n]*>|\{[^{}\r\n]+\}|%[-+#0-9.]*[A-Za-z%]|\\[A-Za-z]+(?:\[[^\]\r\n]*\])?|\\.")


def lang_code(name) -> str:
    s = str(name or "").strip().casefold()
    for code, names in ALIASES.items():
        if s in names:
            return code
    return s or "unknown"


def pair_code(source_lang, target_lang) -> tuple[str, str]:
    return lang_code(source_lang), lang_code(target_lang)


def pair_key(source_lang, target_lang) -> str:
    return "-".join(pair_code(source_lang, target_lang))


def guide_ref(source_lang, target_lang) -> str | None:
    key = pair_key(source_lang, target_lang)
    return f"references/language_pairs.md#{key}" if key in SUPPORTED else None


def visible(text: str) -> str:
    """Text without markup/placeholders/escapes/whitespace: what length ratios compare."""
    return re.sub(r"\s+", "", _TOKEN.sub("", text or ""))


def soft_checks(src: str, tgt: str, source_lang, target_lang) -> list[str]:
    """Style/residue warnings for one translated line. Never blocking."""
    s, t = src or "", tgt or ""
    if not t.strip():
        return []
    sc, tc = pair_code(source_lang, target_lang)
    key = f"{sc}-{tc}"
    out: list[str] = []
    vs, vt = visible(s), visible(t)
    if sc != tc and len(vs) >= 6 and vs == vt and re.search(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff]", vs):
        out.append("identical_untranslated")
    if tc in LATIN_TARGETS:
        if sc == "ja" and KANA.search(t):
            out.append("kana_residue")
        if sc in ("ja", "zh") and KANJI.search(t):
            out.append("kanji_residue")
        if JP_PUNCT.search(t):
            out.append("jp_punct")
        if re.search(r"\s+[,!?;:](?!\d)|\s+\.(?!\.)", t):
            out.append("space_before_punct")
        if re.search(r"\S {2,}\S", t) and not re.search(r"\S {2,}\S", s):
            out.append("double_space")
        if t.count('"') % 2 or t.count("“") != t.count("”"):
            out.append("odd_quotes")
    if tc == "id":
        words = set(re.findall(r"[a-z]+", t.casefold()))
        if words & ID_FORMAL and words & ID_SLANG:
            out.append("register_mix")
        if sc == "en" and len(words & ENGLISH_FUNCTION) >= 3:
            out.append("english_residue")
        if ID_ENGLISH_SFX.search(_TOKEN.sub(" ", t)):
            out.append("english_sfx_residue")
    ratio = LENGTH_RATIO.get(key)
    if ratio and len(vs) >= ratio[0] and vt:
        r = len(vt) / max(1, len(vs))
        if r < ratio[1]:
            out.append("too_short")
        elif r > ratio[2]:
            out.append("too_long")
    return out


def name_residue(name: str | None, source_lang, target_lang) -> bool:
    sc, tc = pair_code(source_lang, target_lang)
    return bool(name) and tc in LATIN_TARGETS and sc in ("ja", "zh") and bool(CJK.search(name))
