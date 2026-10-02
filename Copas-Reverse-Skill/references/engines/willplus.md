# WillPlus / AdvHD

**Evidence**: `arc/` folder with `.dat` archives (`PWFA`-family magic on newer AdvHD), GameExe strings `AdvHD`/`WillPlus`.

**Layout**: archives `.dat` (several generations; older WillPlus simple, AdvHD v1/v2 documented in community tools). Scenario `snp`/`.s` files: bytecode with text records; some builds carry a separate name table. Encoding CP932 (some later builds UTF-8).

**Extract**: GARbro covers several archive generations; VNTextPatch has WillPlus/AdvHD script extractors.

**Indonesian injection**: prefer VNTextPatch-style extract/inject pairs; same-length patching works on text records when lengths live outside the record. ASCII fine.

**Tools**: VNTextPatch, GARbro.
