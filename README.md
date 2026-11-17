# Copas-Skill

Agent skills for translating visual novels and books around [CopasTool](https://github.com/atho64/copastool). Primary target: **Japanese → Indonesian (`ja-id`)**, with dedicated support for **English → Indonesian (`en-id`)** and **Japanese → English (`ja-en`)**.

| Skill | Purpose |
|---|---|
| [`Copas-Translate-Skill/`](Copas-Translate-Skill/) | End-to-end translation & review pipeline for `.copas`/`.copas.zip`, VNTP JSON, EPUB, and Luca inputs: saved prompts, VNDB glossary fetching (`glossary vndb`), `state` decisions & provenance, filtered parallel `bundle` dispatch, live `progress` monitor, `verify` / `scan` / `audit` QA loop, slim adversarial / dual-model `review`, and `.copas`-only ZIP delivery (`export --format copas-zip`). Pure Python stdlib (`>= 3.10`, BS4/lxml optional for raw EPUB). |
| [`Copas-Reverse-Skill/`](Copas-Reverse-Skill/) | Extract and verify game patches through engine-specific tools or CopasTool's native Artemis PFS/AST and Kirikiri XP3/PSB route. |

Each folder is a self-contained skill with its own `SKILL.md`. To install, copy (or symlink) a skill folder into your agent's skills directory, e.g. `~/.claude/skills/Copas-Translate-Skill/`.

The two skills chain seamlessly: **Copas-Reverse-Skill** extracts game text into VNTP JSON (`id_input/`) and injects the translated JSON (`id_output/`) back; **Copas-Translate-Skill** handles glossary locking, `CATATAN_CERITA`/`STYLE_GUIDE` consistency, parallel bundle execution, mechanical linting, adversarial review, and export in between.

For existing `.copas`/`.copas.zip` projects, translation, glossary, review, and agent task packets use their matching saved prompts by default (`prompt_header`, `glossary_prompt`, `ai_check_prompt`, `agent_prompt`), resolving `{{sourceLang}}`, `{{targetLang}}`, and `{{lineCount}}` automatically. See [Copas-Translate-Skill](Copas-Translate-Skill/SKILL.md) and [CopasTool workflows](Copas-Translate-Skill/references/copastool_workflows.md).

## Quick-Start Prompt (`.copas` / `.copas.zip`)

Localization rules (pronoun/register matrix, native Indonesian SFX/onomatopoeia, anti-translationese, and QA gates) are already built into the skill, so a short starter prompt is enough:

```text
Pakai skill Copas-Translate-Skill untuk menerjemahkan "[path/ke/project.copas]" dari awal sampai selesai ([Jepang -> Indonesia], VNDB: "[vXXXX atau judul VN]").
Ambil cast dari VNDB (`glossary vndb`), siapkan `glossary.locked.json` + `CATATAN_CERITA.md` + `STYLE_GUIDE.md`, kerjakan 1000 baris awal dulu dan tampilkan ringkasan gaya/sapaan + contoh dialognya untuk ACC (Mode A), lalu setelah di-ACC selesaikan sisanya sampai lolos QA (`verify`, `scan`, `audit`), jalankan `polish` (`--stage polish`) dulu lalu Adversarial Review (`review --mode slim`), tampilkan `review_ALL.md` untuk saya `pick` dulu sebelum diekspor ke `.zip` berisi `.copas` saja (`export --format copas-zip`).
```

Development checks (run inside a skill folder that has `tests/`):
```bash
python -B -m unittest discover -s tests -v
```

Aligned with CopasTool `0.1.14-beta.4`, localization prompt updates (`e15c8d0`), optional dialogue-tag/group-speaker contracts, and an end-to-end QA/adversarial review pipeline tailored for `ja-id`, `en-id`, and `ja-en`.
