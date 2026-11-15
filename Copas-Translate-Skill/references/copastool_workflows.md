# CopasTool workflows

Use this reference when working through the app, copied AI output, or a spreadsheet. Verified against CopasTool `0.1.14-beta.4`, commit `e15c8d0` (2026-11-11), and the local tag-toggle/ampersand-name changes reviewed on 2026-11-15. Source files below are relative to the CopasTool checkout; use them to recheck behavior when the app changes.

## Copied AI formats and localization prompts

The app supports five output formats. Its JSON array format means one array per line, rather than a single enclosing array. The Python helper's `batch` format is a separate array of objects.

| App format | Output shape |
|---|---|
| Numbered, tags on (default) | `12. [D] Spica: "Aku duluan ya."` or `13. [N] Suara terdengar.` |
| Numbered, tags off | `12. Spica: "Aku duluan ya."` or `13. Suara terdengar.` |
| Block | `[line 12]` followed by optional `type: choice`, optional `speaker: Spica`, and `text: ...` |
| XML | `<lines><line num="12" speaker="Spica"><text>...</text></line></lines>` |
| JSONL | `{"num":12,"speaker":"Spica","text":"..."}` per line |
| JSON array | `[12,"Spica","..."]` for dialogue, `[13,"..."]` for narration, per line |

In numbered input, `[File: script-name]` appears at the beginning and when the file changes. It identifies the current script and is not an output line. With dialogue tags enabled, repeat the exact `[D]`/`[N]` tag; apply rejects a returned tag that changes the source type. Untagged legacy replies remain accepted. A narration line stays narration even when its text contains a colon. Commas, ampersands (`&`/`＆`), and apostrophes inside a speaker name belong to the name. Keep `Nino & Menoa`, `Nino, Menoa & Ichito`, and anonymous groups such as `??? & ???` as a single speaker field.

The **Use [D]/[N] tags in numbered format** checkbox is available in dashboard and project settings. Its backup field is `use_dialogue_tags` (default true when missing); the app state/Agent setting is `useDialogueTags`. With it disabled, use `N. Name: dialogue` or `N. narration`. The app adapts outgoing numbered headers/examples and paste placeholders while retaining the saved custom prompt. This applies to manual copy, Auto Translate/Copas, delegated translate prompts, and live Copas TL. Other copied formats are unaffected.

When tags are disabled, any returned tags are stripped and their type check is skipped; speaker, count, duplicate-ID, and unknown-ID validation still applies. Do not turn off tags or enable Ignore Paste Names solely to bypass a rejected batch. For helper-generated prompts, `--no-dialogue-tags` selects the untagged numbered contract without altering the helper's batch JSON.

Use the format selected in the app and preserve IDs and line count. Preserve choice fields, engine variables, markup, `<br>` markers, and intentional spacing. XML needs escaped text; JSON strings need escaped quotes and backslashes. Japanese quotation-mark variants are available. Respect the project's chosen quotation style rather than double-wrapping dialogue.

Current localization defaults use context to resolve omitted subjects and pronouns, distinguish spoken dialogue from literary narration, follow character register and relationships, and keep names consistent with the glossary. They use Hepburn for Japanese names unless an established Western spelling applies, include separately used given/family names, and localize onomatopoeia. Avoid inventing gender or relationships when the source is ambiguous. Existing custom project prompts still determine style.

App prompt variables: `{{sourceLang}}`, `{{targetLang}}`, `{{lineCount}}`. `context_lines` supplies preceding context; `context_lines_after` supplies following context (default 0, app range 0 to 50). `context_type` chooses raw, translated, or both. `<Context>` and `<Context_After>` are reference-only sections. They must not add translated rows. Following context happens later in the story.

With `safe_tags_for_chatgpt`, the app can replace section tags with `=== LABEL ===` markers. Keep the same distinction between context, glossary, summary, and the lines to translate. Do not copy these section labels into dialogue.

Sources: `src/constants.ts`, `src/ai-format.ts`, `src/speaker-name.ts`, `src/translate.ts`, `src/project.ts`.

## Inline glossary and rolling story context

With `glossary_in_loop`, one translation reply also extracts new glossary entries. This works through Auto Translate, manual copy/paste, and Auto Copas. The standalone glossary prompt forbids script translation, so do not append it unchanged to a translation request.

The combined reply contains the translation first, then an optional `<summary>`, then:

```text
<new_terms>
[character] 麦 = Mugi {male given name}
[item] 炬燵 = kotatsu {household item}
</new_terms>
```

Use an empty `<new_terms></new_terms>` when there are no new terms. Do not number the block or count its entries as translated lines. Supported types are character, place, organization, item, ability, title, concept, and term. Skip terms already in the glossary and use the same target spelling as the translation. Include standalone names used to address a character.

The app separates these sections before parsing translations, merges terms into `glossary_text`, and marks applied rows `_glossary_extracted`. Rolling story context uses `enableBackgroundChaining` and `currentBackground`. These flags are app state, not a substitute for the helper's locked glossary.

For helper work, save only the typed entries when converting them with `glossary from-text`. Review and merge them into the locked glossary without overwriting confirmed renderings, then inject it. Do not pass an entire AI response containing translations into the glossary converter, or a `<new_terms>` block into `batch write`.

Sources: `src/constants.ts` (`INLINE_GLOSSARY_INSTRUCTION`), `src/glossary.ts`, `src/translate.ts`, `src/auto-translate.ts`.

## Spreadsheet round trip

Export from **Tools -> Export to Spreadsheet** or the dashboard project card's **Sheet** button. The `.xlsx` workbook has:

| Tab | Contents |
|---|---|
| `Lines` | `line_num`, `file`, `name`, `message`, `trans_name`, `trans_message`, `is_translated`, `bookmarked`, `status`, and `extra` JSON |
| `Glossary` | `source`, `target`, `type`, `description` |
| `Info` | Allowlisted project settings as key/value rows, plus a format marker |

Preserve line IDs, filenames, and source text while editing translation columns. `extra` carries structural fields such as `custom_index`, `custom_raw`, Luca/EPUB fields, language references, and review flags. Keep it intact. The `Info` allowlist includes `use_dialogue_tags`, so a new project restored from the sheet retains this preference. Merge into an existing project only updates translation-side fields/flags and the glossary; it does not change that project's settings. Headers determine columns; their order may change. A renamed Lines tab is found by its `message` column. Keep Glossary and Info recognizable by name.

Import with **Tools -> Import Spreadsheet into This Project** while the original project is open, then choose **Merge into This Project**. Matching rows require both `line_num` and `file`. For matching rows, only translations and selected flags are updated; the source message and existing structural metadata stay intact. Unmatched rows are appended, so an accidental changed filename/ID can introduce duplicate or misaligned rows. Verify matched/added counts. Glossary entries merge by source term, and incoming entries can replace existing targets; review that change against the locked glossary.

Dashboard **Restore from Spreadsheet (.xlsx)** creates a new project. Creating a project from a sheet imports its source text, metadata, and allowlisted Info settings. It does not preserve the original EPUB, EPUB images, raw Luca/custom-parser sources, or external engine cache. Game engine paths and `glossary_in_loop` are also outside the current Info allowlist. Use `.copas` backups plus the engine cache for a complete game workflow, and merge sheet edits into that project instead of treating the workbook as a complete backup.

Google Sheets is a file editor in this route: upload `.xlsx`, edit, download Microsoft Excel `.xlsx`, then import manually. There is no live Google account sync and no automatic merge on project open. The Python translation CLI does not parse `.xlsx`.

Source: `src/spreadsheet.ts` (`STRUCT_KEYS`, `INFO_KEYS`, `mergeSpreadsheetIntoCurrentProject`), `src/xlsx.ts`.

## AI Check and Deep Check

Use AI Check to correct real errors with minimal edits. The app's automatic check can apply high-confidence objective fixes; medium/low-confidence changes enter its review queue. `ai_check_auto_apply_high` disables automatic high-confidence apply when false; `ai_check_review_mode` requests review. A local sanity gate drops unchanged corrections and queues rewrites changing more than 60% of tokens.

The local linter can fix leftover Japanese punctuation and double spaces and supply glossary/CJK hints to the AI. Rejected suggestions are recorded as rejection memory. `ai_check_deep_mode` runs two passes: meaning accuracy, then naturalness. API checks use structured JSON with repair; copied/Copas checks can use plaintext. Correction reasons should use the target language.

Preserve `ai_check_*` settings and `_ai_checked`/`_ai_confirmed` row flags in backup round trips. The helper's `verify` and `scan` produce heuristic reports; `polish write` applies agent-provided edits. None of them runs the app's linter, confidence scoring, queue, Deep Check, or rejection memory. Do not claim an app review flag proves the source/translation is accurate.

Sources: `src/ai-check.ts`, `src/ai-check-linter.ts`, `src/auto-translate.ts`, `src/project.ts`.

## API, Auto Copas, and the app's AI Agent

The app supports OpenAI-compatible, Gemini, and Anthropic APIs. Auto Copas instead drives Gemini, ChatGPT, DeepSeek, or Arena through the clipboard in a native app: Camoufox on Windows and an in-app WebView on Android. It is unavailable in the PWA. Initial Windows browser setup can download a large runtime; user login and model selection happen in that browser.

Choose the route already authorized by the user. Preserve their API settings and credentials; do not copy them into prompts, glossaries, skills, or deliverables. Auto Copas can start a new chat every configured number of batches. Its retries and thinking controls are app features; do not keep manually retrying a stalled browser workflow indefinitely.

The in-app AI Agent offers project read/search tools, translation/edit tools, prompt/glossary/settings edits, memory, plans, and delegation. These belong to the app's chat runtime, not to this skill's shell or the coding agent's tool inventory. The separate automatic Agent translation loop uses `read_lines`, `search_text`, `get_context`, and `get_glossary`; it commits translation JSON with optional glossary suggestions, rolling context, and file notes. Do not mix those schemas with helper `batch write` JSON.

The app chat shows a mutation preview for changes to more than 10 lines. Keep that confirmation step when operating through the app. It is not a new approval requirement for helper writes the user has already requested. Follow the available app/browser automation tools for actual interaction, and leave login to the user when needed.

Sources: `src/agent-tools-schema.ts`, `src/agent-review.ts`, `src/agent-translate.ts`, `src/auto-copas/`, `README.en.md`.

## Luna Hooker and VN Overlay

LunaTranslator's Network Services uses port `2333`. CopasTool matches hooked game dialogue to project lines. Check mode displays matches; TL mode translates missing lines and saves them into the project using API or Copas. Windows has a floating overlay with click-through and fullscreen diagnostics.

`liveBatchSize` lets Copas TL mode translate the hooked line plus the next untranslated lines. Those additional lines are translated and saved; this differs from reference-only `context_lines_after`. Auto Copas has one active conversation, so live Copas TL stops while an Auto Translate/Extract/Check loop is using it. Do not run both consumers concurrently.

Gameplay/hooking is a runtime workflow that needs a game the user is running. It does not extract a rebuildable script/archive, create a game patch, or replace round-trip verification. When chaining the reverse skill, follow its game-copy and runtime authorization boundaries.

Sources: `src/live-translator.ts`, `src/luna-hooker.ts`, `src/overlay-controller.ts`, `src/types.ts`.

## UI language and saving

Dashboard settings can choose English or Indonesian UI. UI language is separate from source/target translation languages. Follow the visible labels when controlling the app; do not change the translation target because the interface language changes.

Native Backup, Backup All, Export, and glossary export use the remembered save folder, or a per-save dialog when **Always ask where to save** is enabled. Verify the actual resulting path. A cancelled Save As dialog cancels the save; Android's cancelled initial folder picker can fall back to Download. Browser folder backups can need renewed permission after restart.

Sources: `src/i18n/`, `src/native-save-folder.ts`, `src/folder-backup.ts`, `src/download-helper.ts`.
