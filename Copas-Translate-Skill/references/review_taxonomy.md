# Defect Taxonomy (A–E) & Translationese Checklist

Standard reference for **Blind Reader**, **Reviewer**, **Challenger**, and **Consistency Auditor**. Every finding belongs to **A, B, C, or D**. **E (Redline)** is a forbidden zone: any edit touching an E-redline without a valid waiver is rejected.

---

## Class A — Mistranslation / Factual Error (Severity 3, occasionally 2)

Source meaning is wrong, inverted, or omitted. **Must cite `source_evidence`**. Common causes:

| Cause | Pair | Bad → Good Example |
|---|---|---|
| Omitted subject / reversed agent (`誰が誰に`) | `ja-id` | `助けてもらった` → *"Aku menolongnya"* → *"Dia menolongku"* |
| Negation / rhetorical question flipped | `ja-id` / `en-id` | `知らん顔するな` → *"Jangan pura-pura tidak tahu"* (not *"Dia tidak tahu"*); `So?` → *"Ya?"* → *"Memangnya kenapa?"* |
| Epistemic modality error | `ja-id` / `ja-en` | `来るはずだ` → *"Dia pasti sudah datang"* → *"Seharusnya dia datang"* |
| `-てあげる/-てもらう/-てくれる` mix-up | `ja-id` / `ja-en` | `買ってあげた` → *"Aku dibelikan"* → *"Aku membelikannya"* |
| Idiom / phrasal verb literalized | `en-id` | `turned on her heel` → *"berbalik di tumitnya"* → *"langsung berbalik pergi"* |
| Pronoun antecedent mismatch | `en-id` / `ja-id` | `I've got her` (referring to a ship) → *"Aku menangkapnya (perempuan)"* → *"Kapalnya sudah kudapat"* |
| Dropped modifier / clause / quantifier | all | `one of the old classrooms` → *"ruang kelas tua"* (missing *"salah satu"*) |
| Knowledge boundary leak | all | Making a speaker refer to a secret only revealed in `context_after` |

---

## Class B — Target-Language Defect (Severity 3 or 2)

Broken, ungrammatical, or non-idiomatic target text even without looking at the source:

| Defect | Pair | Bad → Good |
|---|---|---|
| Non-word / malformed affixation | `ja-id` / `en-id` | `mengambilkan` vs `mengambil`; `ketidakpercayaan yang nyata` → `sulit dipercaya`; typo / broken morphology |
| Wrong lexical collocation | `ja-id` / `en-id` | `membuka saluran komunikasi menuju markas` → `hubungi markas`; `mengambil keputusan sekejap` → `langsung memutuskan` |
| Unnatural register clash in same utterance | `ja-id` / `en-id` | Mixing `saya` + `lo` in one normal line without ironic intent |
| Broken English grammar / tense flip | `ja-en` | Mid-narration jump from past to present without scene shift |
| Missing syntactic argument | all | Incomplete clause (`Dia berlari ke lantai bawah sistem...` missing verb/preposition) |
| Leaked kana/kanji or JP punctuation | `ja-id` / `ja-en` | `。`, `、`, `！`, stray `っ`, `ー`, or untranslated kanji in Latin output |
| English comic/vocal SFX residue | `ja-id` / `en-id` | `Uhhh...`, `Hngh!`/`Hng...`, `*snif*`/`*sniff*`, `*sigh*`, `*gasp*`, `hmph`, `tch` → `Emm...`/`Hmm...`, `Akh!`/`Aduh...`/`Hup!`/`Mmm...`, `*hiks*`/`srot...`, `hah...`, `deg`, `cih`/`ck` |

---

## Class C — Translationese / AI Slop (Severity 2 or 1; Reviewer reports Sev ≥ 2)

Target text is grammatically valid, but reads stiffly like translated source syntax. Check all 14 symptoms:

| # | Symptom | Example (`ja-id` / `en-id` / `ja-en`) → Fix |
|---|---|---|
| 1 | **Source word-order calque** | `为了.../Untuk melakukan X, dia pun...` when natural ID says `Dia ... demi ...` |
| 2 | **Tense-marker spam (`telah/sedang/akan`)** | `Dia telah berjalan menuju pintu dan telah membukanya` → `Dia berjalan ke pintu dan membukanya` |
| 3 | **`adalah / merupakan` copula bloat** | `Itu adalah hal yang merupakan kesalahan` → `Itu kesalahan besar` |
| 4 | **`yang` chain stacking (≥3 levels)** | `Pria yang berdiri di dekat pintu yang menuju ke ruangan yang gelap itu` → `Pria yang berdiri di dekat pintu ruang gelap itu` |
| 5 | **Unnatural passive `di-... oleh`** | `Pesan itu dibaca olehnya dengan cepat` → `Dia membaca pesan itu cepat-cepat` |
| 6 | **Abstract nominalization** | `Melakukan pengamatan terhadap pergerakan musuh` → `Mengamati gerak-gerik musuh` |
| 7 | **Existential `Ada sebuah...` / `Terdapat...`** | `Ada sebuah senyum tipis di wajahnya` → `Senyum tipis tersungging di bibirnya` |
| 8 | **Mechanical particle / aizuchi mapping** | Every `なるほど` → `Begitu ya`, every `ね` → `, ya`, every `そう` → `Begitu` |
| 9 | **Pronoun overuse (`aku/kamu/saya/Anda/dia`)** | Repeating `aku`/`kamu` in every short reply where Indonesian omits pronouns naturally |
| 10 | **Connector bloat (`oleh karena itu / dengan demikian`)** | Casual VN monologue using `Oleh karena itu, aku memutuskan...` → `Jadi aku memutuskan...` |
| 11 | **Register / scene mismatch** | Stiff formal Indonesian in a panicked shout or casual banter (`Mohon Anda berhenti!` → `Berhenti!`) |
| 12 | **Stiff JP→EN calques** | `"As expected of Senpai!"`, `"It can't be helped"`, `"What do you mean by that?"` → natural English phrasing |
| 13 | **Wordy battle / UI / command lines** | `"Open a communication channel to headquarters!"` → `"Patch me through to HQ!"` / `"Hubungi markas!"` |
| 14 | **Sentence-level surgery needed** | When multiple calques tangle in one sentence, rewrite the whole sentence (`offending` = full sentence) rather than patching one word |

**Do NOT report as Class C**: pure synonym preference (`berkata`/`ujar`), deliberately terse/stuttered dialogue matching the source rhythm, or rules locked in `POLISH_REDLINES.md` / `decisions.json`.

---

## Class D — Cross-Line Inconsistency (Severity 2)

Handled primarily by the **Consistency Auditor** from `inventory.json`:
- Same term translated multiple ways (`旧校舎` → `gedung lama` / `bangunan tua`).
- Same character `name` mapped to different `trans_name` variants (`speaker_drift`).
- Repeated verbatim catchphrases or system lines (`callbacks`) translated inconsistently.
- **Legitimate variation (do NOT report)**: context-dependent shifts recorded in `CATATAN_CERITA.md` / `redline` (e.g., Mugi speaking differently to a teacher vs his childhood friend).

---

## Class E — Redlines (Forbidden Zone)

Any rendering locked in `POLISH_REDLINES.md`, `review/config.json`, or `decisions.json` (`settled`, `errata`). Touching an E-redline without a valid `waivable` flag and `"redline_waiver"` automatically invalidates the finding.
