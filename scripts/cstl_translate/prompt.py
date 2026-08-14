"""Manage per-project user prompts (user_prompt.md / polish_prompt.md)."""
from __future__ import annotations

import argparse
import os

PROMPT_HEADERS = {
    "numbered": 'You are a visual novel translator. Translate to Native {{targetLang}}, accurate and natural.\n- Keep line numbers unchanged. Never merge or drop lines.\n- Translate or romanize all character names.\n- Keep Japanese honorifics (-san, -kun, -chan, etc.).\n- Convert onomatopoeia to natural {{targetLang}}. Do not leave Japanese particles (っ, ッ).\n- No euphemisms. No informal/slang pronouns (lo, lu, gue, gua, etc.).\nOutput in ```plaintext block.\n\nExample:\n12. Spica: "Aku duluan ya."',
    "block": 'You are a visual novel translator. Translate to Native {{targetLang}}, accurate and natural.\n- Keep [line N] and type field unchanged. Never add, remove, or renumber blocks.\n- Translate or romanize all speaker names.\n- Keep Japanese honorifics (-san, -kun, -chan, etc.).\nOutput in ```plaintext block using the same [line N] / speaker / text format.',
    "xml": 'You are a professional VN translator translating {{sourceLang}} -> {{targetLang}}. Keep all XML tags and structure. Translate speaker and <text> only.',
    "jsonl": 'You are a visual novel translator. Translate speaker and text values only. Keep num and all other fields unchanged.',
    "jsonarray": 'You are a visual novel translator. Output JSON array per line [id,"name","text"] or [id,"text"]. Keep ids unchanged.',
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL prompt helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ini = sub.add_parser("init", help="Create a starter user_prompt.md")
    ini.add_argument("--format", choices=["numbered", "block", "xml", "jsonl", "jsonarray"], default="numbered")
    ini.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "init":
        hdr = PROMPT_HEADERS[a.format]
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(hdr + "\n")
        print(f"user_prompt -> {a.out} [format={a.format}]")


if __name__ == "__main__":
    main()
