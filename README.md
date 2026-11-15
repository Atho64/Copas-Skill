# Copas-Skill

Agent skills for translating visual novels into Indonesian, built around [CopasTool](https://atho64.github.io/cstl).

| Skill | Purpose |
|---|---|
| [`Copas-Translate-Skill/`](Copas-Translate-Skill/) | Translate backups or JSON/EPUB/Luca inputs with a locked glossary, preceding/following context, checked batch alignment, export, and QA. Includes guidance for app spreadsheet, Auto Copas, and AI Check workflows. |
| [`Copas-Reverse-Skill/`](Copas-Reverse-Skill/) | Extract and verify Indonesian game patches through engine-specific tools or CopasTool's native Artemis PFS/AST and Kirikiri XP3/PSB route. |

Each folder is a self-contained skill with its own `SKILL.md`. To install, copy (or symlink) a skill folder into your agent's skills directory, e.g. `~/.claude/skills/Copas-Translate-Skill/`.

The two skills are designed to chain: **Copas-Reverse-Skill** extracts game text into VNTP JSON (`id_input/`) and injects the translated JSON (`id_output/`) back; **Copas-Translate-Skill** owns glossary, translation rules, and batch QA in between.

Development checks: `python -B -m unittest discover -s tests -v` (run inside a skill folder that has `tests/`).

Aligned with CopasTool `0.1.14-beta.4`, localization prompt changes in `e15c8d0` (2026-11-11), and local optional dialogue-tag/group-speaker changes reviewed on 2026-11-15. App feature details are in [CopasTool workflows](Copas-Translate-Skill/references/copastool_workflows.md); cache-backed patch building is in [Game Engine workflow](Copas-Reverse-Skill/references/guides/copastool_game_engine.md). The Python helpers do not run the app's browser automation, AI Agent, spreadsheet importer, or native engine backend.
