# Language-Pair Localization Profiles

Primary focus: **Japanese → Indonesian (`ja-id`)**, with dedicated rules for **English → Indonesian (`en-id`)** and **Japanese → English (`ja-en`)**. Saved project prompts (`prompt_header`, `ai_check_prompt`) and confirmed glossaries still govern when present; these profiles fill in defaults and guide human/agent review.

---

## `#ja-id` Japanese → Indonesian (Primary)

### 1. Pronouns & Address Matrix (Speaker × Addressee)
Never impose one global `aku/kamu` or `saya/Anda` pair. Track each speaker-addressee pair in `CATATAN_CERITA.md`:
- **Zero-pronoun preference**: omit subjects/objects when Indonesian reads naturally without them (`食べる？` → `"Mau makan?"`, not `"Apakah kamu mau makan?"`).
- **Intimate / peers / family**: `aku / kamu` or `aku / kau` (or `aku / [nama]` / kinship `Kak`, `Bang`, `Dik`). Reserve `gue / lo` strictly for modern/rough characters whose setting calls for it.
- **Polite / seniors / workplace / strangers**: `saya / Anda` only for truly stiff/official distance; more often `saya / Pak|Bu|Kak|Mbak|Mas|[nama]-san` or role titles.
- **Period / fantasy / noble**: `aku / engkau`, `hamba / tuan`, or `beta / baginda` only when the worldbuilding explicitly warrants it.
- Do **not** mechanically map `私 → saya`, `僕/俺 → aku`, `お前 → lo`. Japanese pronouns signal speaker persona, while Indonesian pronouns depend on *who is speaking to whom* in that moment.

### 2. Subject, Object, Directionality & Modality
- **Omitted subjects/objects**: resolve *who acts on whom* from context (`context_before`, speaker `name`, scene flow). Never replace an intentional mystery with invented names/gender.
- **Benefactives & passives**: track `-てあげる` (giving favor), `-てもらう` (receiving favor), `-てくれる` (other acts for speaker), adversative passive `-られる` (unwanted event), and causative `-させる` (`membuat/menyuruh`).
- **Epistemic modality**: preserve certainty levels (`〜はずだ` = seharusnya/pasti, `〜わけだ` = pantas saja/artinya, `〜らしい` = katanya/kelihatannya, `〜かもしれない` = mungkin/bisa jadi, `〜つもり` = berniat).

### 3. Particles, Aizuchi & Conversational Idioms
Translate **communicative function**, not dictionary glosses:
- `なるほど`: *"Oh, begitu"*, *"Pantas saja"*, *"Masuk akal"*, *"Jadi begitu..."* — never translate every hit as `"Begitu ya"`.
- `そう / そうですね`: *"Iya"*, *"Benar juga"*, *"Kurasa begitu"*, *"Hmm..."* depending on agreement vs hesitation.
- `ね / よ / よね / な / さ / わ`: express via natural Indonesian phrasing or light spoken particles (`ya`, `kan`, `kok`, `lho`, `nih`, `sih`, `deh`) suited to the character's voice — never attach `-ya/-kan` mechanically to every sentence.
- `お邪魔します` / `いただきます` / `お疲れ様`: localize naturally by situation (*"Permisi"`, *"Selamat makan"`, *"Kerja bagus hari ini"* / *"Terima kasih kerja kerasnya"*).

### 4. Names, Honorifics & Onomatopoeia
- **Hepburn & standalone forms**: keep surname, given name, and nickname distinct in `glossary.locked.json` (`Hayakawa Mugi`, `Hayakawa`, `Mugi`, `Mucchan`). Never guess ambiguous kanji readings; flag unresolved names in `CATATAN_CERITA.md` / `needs_review`.
- **Honorifics**: follow project policy (keep `-san/-kun/-chan/-sama/-senpai/-sensei` OR localize to Indonesian kinship/titles `Kak/Pak/Bu/Guru`). Never mix both policies within the same relationship.
- **Onomatopoeia & SFX (giongo/gitaigo & vocal fillers)**: localize strictly into vivid, genuine Indonesian verbs, adverbs, or native Indonesian vocal cues matching scene emotion/context. **Never** leave raw katakana or import English comic SFX / fillers (`uh/uhh/uhhh`, `uhm`, `erm`, `hng/hngh/ngh/ungh/mmph`, `sniff/snif/sniffle`, `sob`, `sigh`, `gasp`, `gulp`, `groan`, `grunt`, `hmph`, `tch`, `tsk`, `pfft`, `cough`, `pant`, `smirk`, `sweatdrop`, `eek`, `ugh`, `ergh`):
  - **Hesitation / thinking / clearing throat (`えっと`, `うーん`, `うー`, `uhhh`, `uhm`, `erm`)**: `emm...`, `hmm...`, `anu...` (ragu/berpikir), `ehm...` (berdeham), `eh...` / `lho...` (bingung).
  - **Straining / pain / muffled effort (`ぐっ`, `くっ`, `うぅ`, `んっ`, `んっしょ`, `hng`, `hngh`, `mmph`, `groan`, `grunt`)**: `akh!`, `aduh...`, `duh...` (kesakitan/terbentur); `hup!` (angkat beban/tenaga); `mmm...` / `hmm...` (mulut terbungkam/menahan suara); `mengerang tertahan` / `menggeram` (narasi).
  - **Crying vs runny nose (`くすん`, `ぐすっ`, `ひっく`, `ずずっ`, `sniff`, `snif`, `sob`)**: `*hiks*`, `hiks...`, `huu...` / `terisak`, `sesenggukan` (menangis); `srot...`, `*menarik ingus*` (pilek/menyedot ingus); `*membuang ingus*` / `*mengelap hidung*` (meniup tisu `ちーん`).
  - **Sighing / relief / exhaustion (`ふう`, `はあ`, `sigh`)**: `hah...`, `huh...`, `menghela napas`.
  - **Startled / shocked (`あっ`, `ひっ`, `ぎくっ`, `gasp`)**: `hah?!`, `ih!`, `deg`, `tersentak`.
  - **Swallowing / nervous (`ごくり`, `gulp`)**: `glek`, `menelan ludah`.
  - **Scoffing / clicking tongue (`ふん`, `ちっ`, `hmph`, `tch`, `tsk`, `pfft`)**: `cih`, `heh`, `ck` / `decaknya`, `mendengus`.
  - **Coughing (`ごほん`, `げほっ`, `cough`)**: `uhuk`, `ehm`, `terbatuk`.
  - **Panting (`はぁはぁ`, `ぜぇぜぇ`, `pant`)**: `hah... hah...`, `hh... hh...`, `terengah-engah`.
  - **Heartbeat / silence (`ドキドキ`, `シーン`)**: `dag-dig-dug` / `deg-degan` / `berdebar kencang`; `hening...` / `sunyi seketika`; `ニヤリ` → `menyeringai`.

### 5. Natural Indonesian Syntax & Anti-Translationese
- **Spoken dialogue vs narration**: dialogue must breathe like real speech (contractions where appropriate, natural interruptions `—`, realistic hesitations); narration should flow smoothly without stiffening into bureaucratic prose.
- **Avoid mechanical calques**: do not spam `telah`, `sedang`, `adalah`, `merupakan`, `oleh karena itu`, `dengan demikian`, or triple `yang` relative chains (`yang ... yang ... yang ...`).
- **Punctuation & CP932 note**: replace `。` → `.`, `、`, → `,`, `！？` → `!?`, fullwidth spaces `\u3000` → regular spaces or clean removal. Use `"..."` quotes unless the project explicitly enables `kagikakko` (`「...」`). When targeting classic CP932/Shift-JIS game patches, avoid diacritics (`é`, `ü`).

---

## `#en-id` English → Indonesian

### 1. Tense & Aspect Restraint
- Indonesian marks tense by context and time adverbs, not verb inflection. Avoid translating every English past/progressive/future verb with `telah`, `sudah`, `sedang`, `akan`.
- Keep temporal markers only when contrast or completion matters (`already` → `sudah`, `used to` → `dulu`).

### 2. Structural Calques to Rewrite
- **Passive bloat**: `"The door was opened by him"` → `"Dia membuka pintu itu"` or `"Dibukanya pintu itu"`, not `"Pintu itu dibuka olehnya"`.
- **Abstract nominalizations**: `"the arrival of the train"` → `"kereta itu tiba"` rather than `"kedatangan kereta itu"`.
- **Existential & cleft clutter**: `"There was a cold feeling in her chest"` → `"Dada terasa dingin"` instead of `"Ada sebuah perasaan dingin..."`.
- **Excessive `yang` chains**: split or recast multi-clause English modifiers so each sentence stays crisp.

### 3. Idioms, Phrasal Verbs & Pronouns
- Translate idioms and phrasal verbs by intent (`turned on her heel` → `langsung berbalik`, `rule out` → `mengesampingkan`, `So?` → `Memangnya kenapa?`).
- Disambiguate `you`, `brother/sister`, `uncle/aunt`, `captain/doctor` using scene context and `CATATAN_CERITA.md` (`kakak/adik`, `abang/mbak`, `om/tante`, `kapten/dokter`).
- **SFX, vocal fillers & stage cues**: never leave English sounds/fillers untranslated (`uhh/uhhh`, `uhm`, `erm`, `sniff/snif`, `sob`, `sigh`, `gasp`, `gulp`, `groan`, `hmph`, `tch`, `cough`, `pant`, `smirk`). Adapt by context into Indonesian (`emm...`/`ehm...`/`hmm...`/`anu...`, `*hiks*`/`hiks...`/`terisak`/`sesenggukan`, `hah...`/`menghela napas`, `deg`/`tersentak`, `glek`, `uhuk`, `cih`/`ck`, `terengah-engah`, `menyeringai`).
- Keep proper nouns, ship/organization names, and glossary `keep_source` entries exact (`verify` & `scan` enforce Latin boundary integrity).

---

## `#ja-en` Japanese → English

### 1. Omitted Subjects & Coreference
- Restore implied subjects/objects cleanly (`I`, `you`, `he`, `she`, `it`, `we`, `they`) from scene context without repeating full names awkwardly across consecutive lines.
- Check `-てあげる/-てもらう/-てくれる` and passive/causative roles so who benefits or suffers is never reversed.

### 2. Natural Dialogue, Register & Tense
- Match Japanese speech register (`keigo`, rough `ore/temee`, timid `ano...`, refined `desu wa`) with natural English word choice, sentence rhythm, and contractions — never stiff literalisms (`"As expected of..."`, `"It cannot be helped"`, `"What do you mean by that?"` when `"Wait, what?"` or `"Just as I thought"` fits the voice).
- Keep narrative tense consistent across scenes (literary past tense is standard for VN narration unless the brief specifies present tense).

### 3. Names, Honorifics & Onomatopoeia
- Apply the project's honorific policy consistently (`-san/-kun/-chan/-sama/-senpai/-sensei` kept vs localized to `Mr./Ms./Senior/Miss`).
- Translate Japanese punctuation (`。` → `.`, `、`, → `,`, `「」` → `"..."` unless `kagikakko` requested, em-dash `—`).
- Render Japanese onomatopoeia via natural English verbs, adverbs, or established English sound effects (`ドキドキ` → `pounding` / `*thump-thump*`, `ざわざわ` → `murmuring`).
