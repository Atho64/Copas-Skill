# Extended engine/format catalog

Identification clues for families without a dedicated page. Like the GalTransl catalog this is modeled on: **these are clues, not support claims.** Confirm with two independent signals before acting (see `engine_identification.md`), and prefer the tool sweep — most of these are already implemented in GARbro, msg-tool, arc_conv, crage, or QuickBMS scripts.

Legend: **Encoding** = typical script text encoding. "exe strings" = run `copas_reverse.detect`, which scans executables for engine names.

## Mid-tier Japanese VN engines (A–Z)

| Family | Tell-tale evidence | Encoding | Tools to try |
|---|---|---|---|
| Aoi | exe strings `Aoi` | cp932 | GARbro, arc_conv |
| Appare! | exe strings `Appare` | cp932 | arc_conv |
| Ares | exe strings `Ares` | cp932 | GARbro |
| Blink | exe strings `Blink` | cp932 | arc_conv |
| Bug System | exe strings `Bug System` | cp932 | GARbro |
| Caramel Box | exe strings `Caramel Box` | cp932 | arc_conv |
| Chimera | exe strings `Chimera` | cp932 | GARbro |
| Circus | exe strings `CIRCUS`, `.cps` images | cp932 | arc_conv, GARbro |
| ClockUp | exe strings `ClockUp` | cp932 | GARbro |
| D.O. | exe strings `D.O.` | cp932 | QuickBMS |
| Debonosu | exe strings `Debonosu` | cp932 | GARbro |
| Frontwing | exe strings `Frontwing` | cp932 | GARbro |
| Giga | `.gpk`/`.gpd`-family archives | cp932 | GARbro, QuickBMS |
| Hulotte | exe strings `Hulotte` | cp932 | GARbro |
| HuneX | exe strings `HuneX` | cp932 | GARbro |
| Ice | exe strings `Ice` | cp932 | arc_conv |
| Image | exe strings `IMAGE` | cp932 | QuickBMS |
| Innocent Grey | exe strings `Innocent Grey`, `.imi` images | cp932 | GARbro |
| JAST | exe strings `JAST` | cp932/Shift-JIS variants | QuickBMS |
| KID | exe strings `KID` | cp932 | QuickBMS |
| Liar-soft | exe strings `Liar`, `.lpk`-family archives | cp932 | GARbro, arc_conv |
| Littlewitch | exe strings `Littlewitch` | cp932 | GARbro |
| Lupinus | exe strings `Lupinus` | cp932 | GARbro |
| Marmalade | exe strings `Marmalade` | cp932 | arc_conv |
| Mink | exe strings `MINK` | cp932 | arc_conv |
| Navel | exe strings `Navel` | cp932 | GARbro |
| NEXTON / Tactics | exe strings `Nexton`/`Tactics`, `.pak` archives | cp932 | GARbro, arc_conv |
| Orchis | exe strings `Orchis` | cp932 | GARbro |
| Pajamas | exe strings `Pajamas`, `.pja`-family | cp932 | GARbro |
| Purple software | exe strings `Purple` | cp932 | GARbro |
| Ransel | archives named `.rar` (not RAR format) | cp932 | QuickBMS |
| Ruf / Dyna | exe strings `Ruf` | cp932 | QuickBMS |
| SAGA Planets | exe strings `SAGA` | cp932 | GARbro |
| Silk | exe strings `Silk` | cp932 | arc_conv |
| Silky's | exe strings `Silky's` | cp932 | arc_conv, GARbro |
| SoftPal | exe strings `SoftPal`, `.pac` archives | cp932 | GARbro |
| Studio e.go! | exe strings `Studio e.go`, `MEG`-family archives | cp932 | GARbro |
| Sugar Pot | exe strings `Sugar Pot` | cp932 | GARbro |
| Symphony | exe strings `Symphony` | cp932 | GARbro |
| Taskforce | exe strings `Taskforce` | cp932 | QuickBMS |
| Trial | exe strings `Trial` | cp932 | GARbro |
| Unison Shift | exe strings `Unison` | cp932 | GARbro |
| Xuse | exe strings `Xuse` | cp932 | GARbro |
| Yamato | exe strings `Yamato` | cp932 | QuickBMS |
| Zyx | exe strings `Zyx` | cp932 | QuickBMS |

## Engine variants (use the parent page)

| Variant | Parent page |
|---|---|
| Kirikiri ZX / KAG XP / self-boot XP3 exes | `kirikiri.md` |
| ONScripter / ONScripter-EN / Ponscripter | `nscripter.md` |
| RPG Maker XP / VX / VX Ace / MV / MZ | `rpgmaker.md` |
| Wolf RPG Editor v1 / v2 / newer | `wolf.md` |
| AdvHD v1 / v2, old WillPlus | `willplus.md` |
| YU-RIS crypto generations | `yuris.md` |
| Artemis builds (plain/encrypted `.pfs`) | `artemis.md` |
| MAGES builds (CP932 vs UTF-8) | `mages.md` |

## Other regions & Western engines

| Family | Tell-tale evidence | Encoding | Tools to try |
|---|---|---|---|
| BKEngine (CN) | `.bkarc`-family, exe strings `BKEngine` | utf-8 | community BKE tools |
| Chinese localization of a JP engine | usually the original engine's files with UTF-8 text | utf-8 | identify the base engine first |
| Construct 2/3 | `data.js`, `c2runtime.js`, `data.c3` | utf-8 | text in JS/JSON directly |
| GameMaker | `data.win` (`FORM` magic) | utf-8 | UndertaleModTool — see `gamemaker.md` |
| Godot | `*.pck` (`GDPC` magic) | utf-8 | gdsdecomp — see `godot.md` |
| Ren'Py | `*.rpa` (`RPA-3.0 `) | utf-8 | see `renpy.md` |
| RPG Maker MV/MZ | `data/Map*.json` | utf-8 | see `rpgmaker.md` |
| TyranoBuilder | `tyrano/` folder | utf-8 | see `tyrano.md` |
| Unity | `*_Data/` | utf-8 | see `unity.md` |

## Generic containers & fallbacks

| Situation | Approach |
|---|---|
| Unknown `.pak` / `.arc` / `.dat` / `.bin` / `.pak`-like archive | Extension means nothing alone — hexdump the header, then sweep tools on a copy: GARbro → msg-tool → arc_conv → crage → QuickBMS script search |
| QuickBMS | Huge community script archive; search for the game/engine name, run on copies only |
| arc_conv / crage | Cover dozens of legacy Japanese archive formats; run with the game folder on a copy |
| msg-tool | Wide archive/toolkit coverage, command-line friendly |
| Text inside images (CGs, logos, UI) | Out of scope for script patching — needs redraw work; list as "not handled" in the delivery report |
| Console / handheld ports | Different toolchains entirely; out of scope unless the user asks explicitly |

## How to add a family to this catalog

When you identify a new family during a project: add a row here (evidence you actually observed, not folklore), add detection rules to `scripts/copas_reverse/detect.py` if the evidence is machine-checkable, and promote it to its own page once you have a verified extraction/injection path for it.
