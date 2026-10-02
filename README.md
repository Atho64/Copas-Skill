# Copas-Skill

Agent skills for translating visual novels into Indonesian, built around [CopasTool](https://atho64.github.io/cstl).

| Skill | Purpose |
|---|---|
| [`Copas-Translate-Skill/`](Copas-Translate-Skill/) | Translate VNs via CopasTool backups (`.copas`/`.copas.zip`/legacy `.cstl`) or JSON/EPUB/Luca inputs: glossary, aligned agent translation, export, QA. |
| [`Copas-Reverse-Skill/`](Copas-Reverse-Skill/) | Reverse engineer galgame folders: identify the engine, extract scenario text, translate to Indonesian, inject back into the game, verify. |

Each folder is a self-contained skill with its own `SKILL.md`. To install, copy (or symlink) a skill folder into your agent's skills directory, e.g. `~/.claude/skills/Copas-Translate-Skill/`.

The two skills are designed to chain: **Copas-Reverse-Skill** extracts game text into VNTP JSON (`id_input/`) and injects the translated JSON (`id_output/`) back; **Copas-Translate-Skill** owns glossary, translation rules, and batch QA in between.

Development checks: `python -B -m unittest discover -s tests -v` (run inside a skill folder that has `tests/`).
