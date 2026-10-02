# Unity

**Evidence**: `<Game>_Data/` folder, `unityplayer.dll` / exe strings `UnityPlayer`, `resources.assets`, `sharedassets*.assets`, `*.unity3d` bundles.

**Layout**: dialogue lives in TextAssets or serialized MonoBehaviour fields — implementation depends on the VN framework (Naninovel, Fungus, custom). TXT/JSON TextAssets are common; Naninovel scripts are plain text inside assets.

**Extract**: browse assets with UABE/AssetStudio/UnityPatcher (GUI tools) or `AssetRipper` for a full project dump; `msg-tool` exports TextAssets. Identify the VN framework from script names, then find its script assets.

**Indonesian injection**: if text is in TextAssets: export → translate → re-import same asset (UABE) keeping byte length where the tool requires, or use AssetRipper round-trip. UTF-8 rendering is native; fonts on Steam releases almost always cover Latin. Naninovel/Fungus have official localization hooks — prefer those when present.

**Tools**: UABE, AssetStudio, AssetRipper, msg-tool, framework-native localization.
