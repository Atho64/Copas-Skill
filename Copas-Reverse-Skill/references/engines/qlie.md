# QLIE (Key-like, "Qlie")

**Evidence**: `Game.exe` + `Data/` folder with `*.b` archives (commonly starting with a `pack`-style header), `patch/` folders, `save/`.

**Layout**: `Data/*.b` archives hold scenario (`.ks`-like QLIE script), images, sounds. Most builds unencrypted or weakly obfuscated; some commercial builds encrypt.

**Extract**: GARbro supports common QLIE archive variants; QuickBMS scripts exist. Scenario files are text-ish once unpacked; parse tags/records per build.

**Indonesian injection**: repack with the unpacking tool or same-length patch of unpacked scenario files. Keep tag structure intact. UTF-8 in many builds — check before assuming CP932.

**Tools**: GARbro (QLIE), QuickBMS.
