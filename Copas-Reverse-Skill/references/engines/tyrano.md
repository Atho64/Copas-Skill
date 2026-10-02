# TyranoBuilder / TyranoScript

**Evidence**: `tyrano/` engine folder, `index.html`, scenario in `data/scenario/*.ks`-like `.ks`/`.tjs` files, config JSONs.

**Layout**: browser-tech engine; scenario files are plain text (TyranoScript tags `[text]`, `[cm]`, `[p]`, `[name]`...). Assets in `data/`. No encryption normally.

**Extract**: read scenario files as UTF-8 text; dialogue is lines between Tyrano tags; speaker via `[name param="..."]` or character definitions in config.

**Indonesian injection**: edit the scenario text directly (UTF-8, no length limits); keep tags verbatim. Browser rendering handles Latin text natively.

**Tools**: none needed beyond a text editor — this is a plain-text engine.
