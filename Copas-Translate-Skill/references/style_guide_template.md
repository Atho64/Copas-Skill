# STYLE_GUIDE Template for Copas-Translate-Skill

Copy this to `<WORK>/STYLE_GUIDE.md` and lock in project specifics (derived from the user-approved sample batch + saved project prompt). All workers in parallel mode and all review agents read this file.

---

# Style Guide — {{projectName}} ({{sourceLang}} -> {{targetLang}})

## 1. Target Language, Voice & Pronoun Matrix
- **Pair profile**: `references/language_pairs.md#{{pairKey}}` (primary default `ja-id`; also `en-id`, `ja-en`).
- **Narration**: smooth, natural literary prose; avoid translationese (`telah`, `adalah`, passive `di-... oleh`, excessive `yang` chains for Indonesian; stiff calques / tense flips for English).
- **Dialogue**: natural spoken rhythm matching each character's personality, age, and social distance.
- **Pronoun policy**: follow the pairwise matrix in `BOOK_BIBLE.md` §2 (never collapse all speakers into one `aku/kamu` or `saya/Anda`; omit pronouns when Indonesian reads naturally without them).

## 2. Quotation, Punctuation & Typography
- **Dialogue quotes**: choose ONE and keep across all files — standard `"..."` (nested `'...'`) **OR** Japanese `「...」` (`『...』`) if `kagikakko` is enabled. Never double-wrap dialogue that already has a speaker tag.
- **Narration**: no outer quotes.
- **Japanese punctuation normalization** (`ja-id` / `ja-en`): `。` → `.`, `、`, → `,`, `！？` → `!?`, fullwidth `\u3000` removed/normalized, `──` / `―` → `—` or `--` consistently, ellipsis `...` or `…` consistently.
- **SFX, onomatopoeia & vocal fillers** (`ja-id` / `en-id`): always use native Indonesian sounds matching context (`emm...`/`ehm...`/`hmm...`/`anu...`, `*hiks*`/`hiks...`/`terisak`/`sesenggukan`, `hah...`, `deg`/`tersentak`, `glek`, `uhuk`, `cih`/`ck`), never English comic SFX (`uhhh`, `snif/sniff`, `sigh`, `gasp`, `hmph`, `tch`).
- **CP932 / Shift-JIS patch safety** (when exporting to classic JP engines): stick to ASCII `A–Z a–z 0–9` and avoid accented characters (`é`, `è`, `ü`).

## 3. Character Names, Speakers & Honorifics
- `glossary.locked.json` (`characters[].render`) is the sole authority.
- Keep standalone surname, given name, and nickname entries distinct (do not expand a short form like `Mugi` into `Hayakawa Mugi` when the source uses the given name alone).
- Supply `trans_name` for every line with non-empty source `name`; leave `trans_name: null` for narration. Preserve grouped names (`Nino & Menoa`, `??? & ???`) as one speaker field.
- **Honorific policy**: state clearly whether `-san/-kun/-chan/-sama/-senpai/-sensei` are kept verbatim or localized (`Kak/Mas/Mbak/Pak/Bu/Guru`).

## 4. Terms & Out-of-Glossary Proper Nouns
- `glossary.locked.json` (`terms[].dst`) is authoritative; `keep_source: true` stays verbatim.
- Unknown new proper nouns encountered mid-run: follow project policy (keep Hepburn/source by default) and record in `newterms_<N>.txt` / `needs_review`.

## 5. Tags, Placeholders & Line Discipline
- Preserve verbatim: `<i>`, `<b>`, `{0}`, `%s`, `\n`, `<br>`, `[ruby]`, and meaningful trailing spaces.
- **1 line in -> 1 line out**: `line_num`, count, and order never change. Never merge, split, or drop lines.

## 6. Scene / File Tone Notes (Optional)
- `scene01.json`: ...
- `scene02.json`: ...
