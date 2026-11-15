"""Manage per-project user prompts (user_prompt.md / polish_prompt.md)."""
from __future__ import annotations

import argparse
import os

LOCALIZATION_RULES = """Translate visual novel text from {{sourceLang}} to {{targetLang}}.
- Preserve meaning, emotional intensity, viewpoint, and each speaker's register. Make dialogue sound spoken and narration read naturally.
- Resolve omitted subjects and pronouns from surrounding context. Do not invent a speaker, relationship, or plot detail when the evidence is unclear.
- Follow the locked glossary for names and terms, including standalone family/given names and nicknames. Use Hepburn for Japanese names unless an established spelling applies.
- Follow project instructions for honorifics, pronouns, and quotation style. Localize onomatopoeia naturally; preserve intentional stutters and expressive sounds.
- Preserve engine variables, placeholders, markup, inline <br>, stored \\n markers, and meaningful trailing spaces.
- Keep every input line number, its order, and its dialogue/narration identity. Never merge, split, add, or drop lines.
- Use preceding/following context, reference-language text, and story summaries only as evidence. Translate only the requested lines.
"""

FORMAT_RULES = {
    "batch": """Return a JSON array of objects with line_num, trans_message, and trans_name.
For every non-empty source name, supply trans_name using the glossary. For narration, omit trans_name or set it to null. Names may contain commas, ampersands (& or ＆), or apostrophes; use the name field, not punctuation, to identify a speaker.
If the input is a context envelope, translate only its lines array. Do not return context_before/context_after, metadata, or glossary entries as translations.
Example schema: [{"line_num":12,"trans_name":"Spica","trans_message":"[translated dialogue]"},{"line_num":13,"trans_name":null,"trans_message":"[translated narration]"}]
""",
    "numbered": """Return exactly {{lineCount}} numbered lines inside one ```plaintext block.
Dialogue: 12. [D] Spica: "[translated dialogue]"
Narration: 13. [N] [translated narration]
Echo the exact [D]/[N] tag from the input. Never add a speaker to [N]. [File: ...] labels identify the script file; do not output them.
""",
    "block": """Return exactly {{lineCount}} [line N] blocks inside one ```plaintext block.
Preserve line headers, field order, and type: choice when present. Translate speaker and text only; never add a speaker to narration.
Example schema:
[line 12]
speaker: Spica
text: "[translated dialogue]"

[line 13]
text: [translated narration]
""",
    "xml": """Return exactly {{lineCount}} <line> elements in a <lines> root inside one ```xml block.
Preserve elements, num/type attributes, and structure. Translate speaker attributes and <text> content only. Escape XML special characters, including <br> as &lt;br&gt; in text.
Example schema: <lines><line num="12" speaker="Spica"><text>"[translated dialogue]"</text></line><line num="13"><text>[translated narration]</text></line></lines>
""",
    "jsonl": """Return exactly {{lineCount}} valid JSON objects, one per input line, inside one ```jsonl block.
Keep num and all metadata fields unchanged; translate speaker and text values only. Escape inner quotes and backslashes as JSON requires.
Example schema:
{"num":12,"speaker":"Spica","text":"[translated dialogue]"}
{"num":13,"text":"[translated narration]"}
""",
    "jsonarray": """Return exactly {{lineCount}} valid JSON arrays, one per input line, inside one ```jsonl block.
Use [number,"speaker","text"] for dialogue and [number,"text"] for narration, without spaces after commas. Do not wrap the rows in another array. Keep numbers unchanged and escape JSON strings correctly.
Example schema:
[12,"Spica","[translated dialogue]"]
[13,"[translated narration]"]
""",
}

PROMPT_HEADERS = {fmt: LOCALIZATION_RULES + "\n" + rules for fmt, rules in FORMAT_RULES.items()}

NUMBERED_UNTAGGED_RULES = """Return exactly {{lineCount}} numbered lines inside one ```plaintext block.
Dialogue: 12. Spica: "[translated dialogue]"
Narration: 13. [translated narration]
Use Name: dialogue only for lines with a speaker. Keep narration without a speaker prefix, even when its text contains a colon. Preserve group speaker names containing commas or ampersands as one name.
Do not add dialogue/narration type tags. [File: ...] labels identify the script file; do not output them.
"""


def build_prompt(fmt: str, source_lang=None, target_lang=None, line_count=None, kagikakko=False, dialogue_tags=True) -> str:
    prompt = PROMPT_HEADERS[fmt]
    if fmt == "numbered" and not dialogue_tags:
        prompt = LOCALIZATION_RULES + "\n" + NUMBERED_UNTAGGED_RULES
    for key, value in (("sourceLang", source_lang), ("targetLang", target_lang), ("lineCount", line_count)):
        if value is not None:
            prompt = prompt.replace("{{" + key + "}}", str(value))
    if kagikakko:
        if fmt in ("numbered", "block", "xml"):
            prompt = prompt.replace('"[translated dialogue]"', '「[translated dialogue]」')
        prompt += '\nEnclose spoken dialogue in Japanese quotation marks 「」, without double-wrapping existing quotes. Keep narration unquoted.\n'
    return prompt


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL prompt helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ini = sub.add_parser("init", help="Create a starter user_prompt.md")
    ini.add_argument("--format", choices=list(PROMPT_HEADERS), default="numbered")
    ini.add_argument("--out", required=True)
    ini.add_argument("--source-lang")
    ini.add_argument("--target-lang")
    ini.add_argument("--line-count", type=int)
    ini.add_argument("--kagikakko", action="store_true")
    ini.add_argument("--no-dialogue-tags", action="store_true", help="Generate numbered output without [D]/[N]; other formats are unchanged")
    a = ap.parse_args(argv)
    if a.cmd == "init":
        if a.line_count is not None and a.line_count < 1:
            ap.error("--line-count must be positive")
        hdr = build_prompt(a.format, a.source_lang, a.target_lang, a.line_count, a.kagikakko, not a.no_dialogue_tags)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(hdr + "\n")
        print(f"user_prompt -> {a.out} [format={a.format}]")


if __name__ == "__main__":
    main()
