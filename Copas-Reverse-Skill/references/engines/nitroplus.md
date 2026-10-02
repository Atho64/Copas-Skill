# Nitro+

**Evidence**: `*.npa` archives, `*.pak` variants, exe strings `Nitro`.

**Layout**: `.npa` containers (several crypto variants across titles), scenario inside as compressed script files, CP932.

**Extract**: GARbro covers several Nitro+ `.npa` variants; arc_conv/QuickBMS cover others. Identify the exact variant from the archive header before decrypting.

**Indonesian injection**: unpack → translate script files → repack with the same tool, or same-length patch. ASCII fine.

**Tools**: GARbro (NPA), arc_conv, QuickBMS.
