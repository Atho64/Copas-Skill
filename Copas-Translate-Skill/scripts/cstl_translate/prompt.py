"""Manage per-project user prompts (user_prompt.md / polish_prompt.md) and language-pair profiles."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import langpair
from .cstl_io import ensure_cstl, load_cstl

LOCALIZATION_RULES = """Translate visual novel text from {{sourceLang}} to {{targetLang}}.
- Preserve meaning, emotional intensity, viewpoint, and each speaker's register. Make dialogue sound spoken and narration read naturally.
- Resolve omitted subjects and pronouns from surrounding context. Do not invent a speaker, relationship, or plot detail when the evidence is unclear.
- Follow the locked glossary for names and terms, including standalone family/given names and nicknames. Use Hepburn for Japanese names unless an established spelling applies.
- Follow project instructions for honorifics, pronouns, and quotation style. Localize onomatopoeia naturally; preserve intentional stutters and expressive sounds.
- Preserve engine variables, placeholders, markup, inline <br>, stored \\n markers, and meaningful trailing spaces.
- Keep every input line number, its order, and its dialogue/narration identity. Never merge, split, add, or drop lines.
- Use preceding/following context, reference-language text, and story summaries only as evidence. Translate only the requested lines.
"""

JP_ID_RULES = """Japanese to Indonesian localization:
- Choose pronouns and forms of address per speaker, addressee, relationship, and scene. Do not impose one global aku/kamu or saya/Anda pair. Omit a pronoun when Indonesian reads naturally without one; Japanese 私/僕/俺 alone does not settle the Indonesian register.
- Track who acts on whom, omitted subjects, negation, conditions, uncertainty, and viewpoint. Preserve what the speaker knows at that point; do not resolve an intentional ambiguity with invented facts.
- Distinguish spoken politeness from intimacy, sarcasm, or social distance. Use consistent character voice while allowing evidence-based changes between addressees or scenes.
- Render idioms, sentence particles, aizuchi, and context-sensitive greetings by their function. Do not mechanically map every そう/なるほど to one phrase or every ね/よ to one particle.
- Strictly localize all SFX, vocal fillers, sighs, sobs, and onomatopoeia into genuine Indonesian matching context — NEVER output English comic SFX or fillers (never use uh/uhhh, uhm, erm, hng/hngh/ngh/ungh/mmph, sniff/snif, sob, sigh, gasp, gulp, groan, hmph, tch, pfft, cough, pant, smirk). Examples by context: hesitation/thinking/clearing throat -> emm..., hmm..., anu..., ehm...; muffled/straining/pain (ぐっ/くっ/んっ/hngh) -> akh!, aduh..., duh..., hup!, mmm..., mengerang tertahan; crying/sobbing -> *hiks*, hiks..., terisak, sesenggukan; runny nose/sniffing (ずずっ) -> srot..., *menarik ingus*; sigh -> hah..., menghela napas; gasp -> hah?!, deg, tersentak; gulp -> glek; scoff/click tongue -> cih, heh, ck; cough -> uhuk, terbatuk; panting -> hah... hah..., terengah-engah; heartbeat -> deg-degan, dag-dig-dug.
- Keep established name readings and standalone surnames/given names/nicknames distinct. Do not guess a kanji name reading. Honorifics and kinship address follow the project policy and actual relationship.
- Write natural Indonesian syntax, without adding saya/Anda, telah, adalah, oleh karena itu, or modern slang to every line. Preserve deliberate repetition, hesitation, roughness, and narrative voice.
- Translate everyday words normally; record unresolved proper nouns or genuinely ambiguous meanings separately with line IDs and evidence, never inside the game dialogue.
"""

JP_ID_REVIEW_RULES = """Japanese to Indonesian review:
- Check meaning first: subject/object, negation, modality, missing clauses, relationships, perspective, and knowledge at this point in the scene.
- Then read the Indonesian for idiom, collocation, pronoun/register drift, character voice, and unlocalized English SFX/fillers (replace uh/uhhh, snif/sniff, sob, sigh, gasp, gulp, hmph, tch, etc. with natural Indonesian like emm/ehm/hmm, hiks/sesenggukan, hah, glek, cih/ck according to context). Recheck each rewrite against Japanese; a wording preference alone is not an error.
- Preserve confirmed decisions and accepted semantic fixes. Give each correction a short reason citing source text or line IDs; do not silently resolve an uncertainty or rewrite sound dialogue.
"""

EN_ID_RULES = """English to Indonesian localization:
- Choose pronouns, kinship terms (kakak/adik/abang/mbak/pak/bu), and register per speaker-addressee relationship; never default everything to saya/Anda or aku/kamu.
- Avoid English structural calques: do not spam tense auxiliaries (telah/sudah/sedang/akan), passive di-... oleh when active or bare-verb Indonesian flows better, nominalization chains, or excessive "yang" clauses.
- Translate idioms, phrasal verbs, tag questions, and sarcasm by communicative intent rather than word-for-word glosses.
- Strictly localize all English SFX, vocal fillers, and stage/sound cues into natural Indonesian matching context — NEVER keep uh/uhhh, uhm, erm, sniff/snif, sob, sigh, gasp, gulp, groan, hmph, tch, cough, pant, smirk (use emm/ehm/hmm/anu, *hiks*/terisak/sesenggukan, hah.../menghela napas, deg/tersentak, glek, uhuk, cih/ck, terengah-engah instead).
- Keep glossary names/terms exact, preserve capitalization-based proper nouns per policy, and check gender/number/addressee from scene context.
- Keep spoken VN dialogue natural and concise; distinguish internal monologue from narration.
"""

EN_ID_REVIEW_RULES = """English to Indonesian review:
- Check meaning accuracy first: idioms/phrasal verbs, negation/rhetorical reversals, comparatives, pronoun/antecedent reference, dropped modifiers or clauses.
- Then check natural Indonesian phrasing: remove translationese (passive/nominalization/telah-adalah bloat, unnatural yang-stacking, stiff spoken dialogue) and replace any leftover English SFX/vocal fillers (uh/uhhh, snif/sniff, sigh, gasp, gulp, hmph, tch, etc.) with natural Indonesian (emm/ehm/hmm, hiks/sesenggukan, hah, glek, cih/ck) without altering facts or character voice.
- Preserve confirmed glossary terms, redlines, and accepted fixes. Cite English source evidence when reporting A/C issues.
"""

JP_EN_RULES = """Japanese to English localization:
- Restore omitted Japanese subjects, objects, and implied referents cleanly from context without awkwardly repeating character names in adjacent clauses.
- Match each character's voice and social register (casual, polite keigo, rough ore/washi, refined ojousama) using natural English diction and contractions rather than robotic literalism.
- Follow the project policy for honorifics (-san/-kun/-chan/-sama/-senpai/-sensei) and Hepburn readings; keep standalone given/family names and nicknames distinct.
- Maintain consistent narrative tense (typically past tense for VN narration unless the project brief specifies present).
- Render aizuchi, sentence-final particles, idioms, and onomatopoeia naturally in English; avoid stiff calques ("As expected of...", "It can't be helped") when idiomatic English fits better.
"""

JP_EN_REVIEW_RULES = """Japanese to English review:
- Check meaning first: omitted subjects/objects, te-ageru/morau/kureru directionality, passive/causative roles, negation, epistemic modality, and scene knowledge boundaries.
- Then check English fluency and voice: remove stiff Japanese syntax calques, unnatural repetitions, tense slips, and mechanical particle/aizuchi translations.
- Preserve locked glossary spellings, honorific policy, and confirmed fixes; cite Japanese source evidence for meaning/translationese issues.
"""


def is_jp_id(source_lang, target_lang) -> bool:
    return langpair.pair_code(source_lang, target_lang) == ("ja", "id")


def is_en_id(source_lang, target_lang) -> bool:
    return langpair.pair_code(source_lang, target_lang) == ("en", "id")


def is_jp_en(source_lang, target_lang) -> bool:
    return langpair.pair_code(source_lang, target_lang) == ("ja", "en")


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


def _pair_rules(source_lang, target_lang, task: str = "translate") -> str:
    if task == "ai-check":
        if is_jp_id(source_lang, target_lang):
            return JP_ID_REVIEW_RULES
        if is_en_id(source_lang, target_lang):
            return EN_ID_REVIEW_RULES
        if is_jp_en(source_lang, target_lang):
            return JP_EN_REVIEW_RULES
        return ""
    if task in ("translate", "agent"):
        if is_jp_id(source_lang, target_lang):
            return JP_ID_RULES
        if is_en_id(source_lang, target_lang):
            return EN_ID_RULES
        if is_jp_en(source_lang, target_lang):
            return JP_EN_RULES
    return ""


def build_prompt(fmt: str, source_lang=None, target_lang=None, line_count=None, kagikakko=False, dialogue_tags=True) -> str:
    prompt = PROMPT_HEADERS[fmt]
    if fmt == "numbered" and not dialogue_tags:
        prompt = LOCALIZATION_RULES + "\n" + NUMBERED_UNTAGGED_RULES
    extra = _pair_rules(source_lang, target_lang, "translate")
    if extra:
        prompt += "\n" + extra
    for key, value in (("sourceLang", source_lang), ("targetLang", target_lang), ("lineCount", line_count)):
        if value is not None:
            prompt = prompt.replace("{{" + key + "}}", str(value))
    if kagikakko:
        if fmt in ("numbered", "block", "xml"):
            prompt = prompt.replace('"[translated dialogue]"', '「[translated dialogue]」')
        prompt += '\nEnclose spoken dialogue in Japanese quotation marks 「」, without double-wrapping existing quotes. Keep narration unquoted.\n'
    return prompt


TASK_FIELDS = {
    "translate": "prompt_header",
    "glossary": "glossary_prompt",
    "ai-check": "ai_check_prompt",
    "agent": "agent_prompt",
    "summary": "summary_prompt",
    "ai-check-summary": "ai_check_summary_prompt",
    "dictionary": "dictionary_prompt",
}

FALLBACK_PROMPTS = {
    "translate": LOCALIZATION_RULES,
    "glossary": "Extract recurring proper nouns, character names, and story-specific terminology from {{sourceLang}} into {{targetLang}}. Follow existing glossary spellings. Include independently used names; exclude common everyday vocabulary. Do not translate the script lines.",
    "ai-check": "Review the existing {{targetLang}} translation against {{sourceLang}}. Correct real errors with minimal edits, preserving valid wording, character voice, and quotation style. Return only lines requiring a correction.",
    "agent": LOCALIZATION_RULES,
    "summary": "Summarize the supplied story context and lines briefly, preserving established events, characters, and relationships.",
    "ai-check-summary": "Summarize confirmed localization decisions and accepted corrections for consistency in subsequent review batches.",
    "dictionary": "Explain the supplied {{sourceLang}} word or expression in {{targetLang}} using its context.",
}

OUTPUT_CONTRACTS = {
    "translate": FORMAT_RULES["batch"],
    "glossary": "Return only typed glossary entries, one per line: [type] source = target {description}. Supported types: character, place, organization, item, ability, title, concept, term. Omit terms already in glossary_text. Return empty text if there are no new entries.",
    "ai-check": "Return a JSON array containing only corrections: {line_num, polished_text, polished_name?, reason?, confidence?}. Use the original line IDs. polished_text is the complete corrected message without a speaker prefix; polished_name is the corrected speaker when needed. Return [] if no correction is required.",
    "agent": FORMAT_RULES["batch"] + "\nThe app's internal action/commit/tool protocol is not used by this helper. Use only tools available in your current environment, and return the translation array for serial write-back.",
}


def saved_prompts(data: dict) -> dict[str, str]:
    prompts = {field: str(data.get(field) or "") for field in TASK_FIELDS.values()}
    if not prompts["summary_prompt"]:
        prompts["summary_prompt"] = str(data.get("summaryPrompt") or "")
    return prompts


def render_variables(text: str, data: dict, line_count=None) -> str:
    values = {"sourceLang": data.get("source_lang") or "Japanese",
              "targetLang": data.get("target_lang") or "Indonesian"}
    if line_count is not None:
        values["lineCount"] = line_count
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def project_prompt_info(data: dict, task: str = "translate", line_count=None) -> dict:
    field = TASK_FIELDS[task]
    prompts = saved_prompts(data)
    saved = prompts[field]
    selected = saved if saved.strip() else FALLBACK_PROMPTS[task]
    sl = data.get("source_lang")
    tl = data.get("target_lang")
    if not saved.strip():
        extra = _pair_rules(sl, tl, task)
        if extra:
            selected += "\n" + extra
    instruction = render_variables(selected, data, line_count)
    if task in OUTPUT_CONTRACTS:
        instruction += "\n\nHelper input/output contract:\n" + OUTPUT_CONTRACTS[task]
        instruction += "\nIn the supplied packet, lines.message is the original text, lines.trans_message is the existing translation, and name/trans_name are separate speaker fields. Apply the saved prompt's task and style rules using this helper contract for input fields and output serialization. Context and other saved prompts do not add output rows."
        instruction += "\nWhen present, project_brief supplements the saved task prompt with project facts, character/addressee voice, and confirmed decisions. Explicit user directions take priority; otherwise retain the saved prompt and glossary when a supplement conflicts. Use cited file/line/route scopes and keep uncertainties unresolved."
        if task in ("translate", "agent", "ai-check") and langpair.lang_code(tl or "Indonesian") == "id":
            instruction += "\nLocalize all SFX, vocal fillers, sighs, and sobs into natural Indonesian matching context (e.g. emm/ehm/hmm/anu, akh/aduh/hup/mmm, *hiks*/sesenggukan, srot..., hah..., deg/tersentak, glek, uhuk, cih/ck); never leave English comic SFX/fillers (uh/uhhh, uhm, erm, hng/hngh/mmph, snif/sniff, sob, sigh, gasp, gulp, groan, hmph, tch, cough, pant, smirk) in Indonesian text."
    return {
        "task": task,
        "prompt_field": field,
        "prompt_source": "project" if saved.strip() else "fallback",
        "language_pair": langpair.pair_key(sl or "Japanese", tl or "Indonesian"),
        "language_guide": langpair.guide_ref(sl or "Japanese", tl or "Indonesian"),
        "prompts": prompts,
        "instruction": instruction,
    }


def extract_project_prompts(project_path: str, out_dir: str, overwrite: bool = False) -> list[str]:
    data = ensure_cstl(load_cstl(project_path))
    root = Path(out_dir)
    snapshots = {root / (field + ".md"): text for field, text in saved_prompts(data).items()}
    snapshots[root / "glossary_text.txt"] = str(data.get("glossary_text") or "")
    conflicts = [path for path, text in snapshots.items()
                 if path.exists() and path.read_bytes().decode("utf-8-sig") != text]
    if conflicts and not overwrite:
        raise FileExistsError("prompt snapshots already contain different text; use a new directory or --overwrite: " + ", ".join(map(str, conflicts)))
    root.mkdir(parents=True, exist_ok=True)
    for path, text in snapshots.items():
        if not path.exists() or path in conflicts:
            with path.open("w", encoding="utf-8", newline="") as output:
                output.write(text)
    return [str(path) for path in snapshots]


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL prompt helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ini = sub.add_parser("init", help="Create a starter user_prompt.md")
    ini.add_argument("--format", choices=list(PROMPT_HEADERS))
    ini.add_argument("--out", required=True)
    ini.add_argument("--project", help="Use the saved task prompt from a .copas/.copas.zip backup")
    ini.add_argument("--task", choices=list(TASK_FIELDS), default="translate")
    ini.add_argument("--source-lang")
    ini.add_argument("--target-lang")
    ini.add_argument("--line-count", type=int)
    ini.add_argument("--kagikakko", action="store_true")
    ini.add_argument("--no-dialogue-tags", action="store_true", help="Generate numbered output without [D]/[N]; other formats are unchanged")
    extract = sub.add_parser("extract", help="Save the project's prompts and glossary verbatim for inspection")
    extract.add_argument("project")
    extract.add_argument("--out-dir", required=True)
    extract.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "extract":
        try:
            paths = extract_project_prompts(a.project, a.out_dir, a.overwrite)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        print(f"extracted {len(paths)} prompt/glossary snapshots -> {a.out_dir}")
        return
    if a.cmd == "init":
        if a.line_count is not None and a.line_count < 1:
            ap.error("--line-count must be positive")
        if a.project:
            if a.format is not None or a.kagikakko or a.no_dialogue_tags:
                ap.error("--project uses saved style and the task's helper output contract; template format/quote/tag options apply only without --project")
            data = ensure_cstl(load_cstl(a.project))
            if a.source_lang is not None:
                data["source_lang"] = a.source_lang
            if a.target_lang is not None:
                data["target_lang"] = a.target_lang
            info = project_prompt_info(data, a.task, a.line_count)
            hdr = info["instruction"]
            source = f"{info['prompt_source']}:{info['prompt_field']}"
        else:
            if a.task != "translate":
                ap.error("--task requires --project")
            fmt = a.format or "numbered"
            hdr = build_prompt(fmt, a.source_lang, a.target_lang, a.line_count, a.kagikakko, not a.no_dialogue_tags)
            source = f"template:{fmt}"
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            f.write(hdr + "\n")
        print(f"user_prompt -> {a.out} [{source}]")


if __name__ == "__main__":
    main()
