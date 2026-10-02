# SiglusEngine

**Evidence**: `SiglusEngine.exe`, `scene/` folder with `*.ss` packed scenario.

**Layout**: scenario `*.ss` (encrypted/compressed blocks; partially documented), string/module tables with game-specific keys.

**Extract**: community Siglus toolchains and VNTextPatch-family extractors cover several builds; many commercial builds need per-game keys. If the specific build is unsupported — stop and report.

**Indonesian injection**: structure-aware rebuild via the same toolchain that extracted; lengths are table-driven, so same-length patching is only a fallback. ASCII fine.

**Tools**: Siglus community toolchains, VNTextPatch-family (check support per build).
