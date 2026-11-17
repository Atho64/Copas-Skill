# CATATAN_CERITA Template (Pre-Translation / Pre-Review Fact Sheet)

Before launching parallel batches (or full adversarial review), have 1–2 fast agents scan representative files (or run `precedents` if part of the project is already translated) to lock down **facts** in `<WORK>/CATATAN_CERITA.md`. Wrong facts cause systematic cross-file mistranslations (wrong gender, wrong kinship term, shifting rank/honorifics, wrong pronoun register).

Only record facts directly supported by source evidence (with `file` + `line_num`). Put guesses under **Needs Confirmation**.

---

# Catatan Cerita — {{projectName}} ({{source_lang}} -> {{target_lang}})

## 1. Characters
| Source Name | Reading / Render | Gender | Role / Rank | Speech Quirks | Evidence (file #line_num) |
|---|---|---|---|---|---|
| 速川麦 | Hayakawa Mugi | M | Student, protagonist's friend | Casual, blunt | `scene01.json #12` |
| スピカ | Spica | F | Transfer student | Polite, slightly formal | `scene01.json #45` |

## 2. Pairwise Pronoun & Address Matrix (Essential for `ja-id` / `en-id`)
| Speaker | Addressee | JP Source Form | Target Pronoun Pair | Honorific / Kinship | Notes / Scene Shifts |
|---|---|---|---|---|---|
| Mugi | Protagonist | `お前` / `呼び捨て` | `aku / kamu` (or `lo/gue`) | bare name | Childhood friends |
| Spica | Teacher | `私` / `〜先生` | `saya / Pak` (or `Bu`) | `Pak /Sensei` | Formal classroom |
| Spica | Mugi | `私` / `〜くん` | `aku / kamu` | `Mugi-kun` (or `Mugi`) | Warm, slightly polite |

## 3. Places, Organizations, Items & Terms (Out-of-Glossary Discoveries)
| Source | Category | Proposed Render / Keep Source | Context / Evidence |
|---|---|---|---|
| `旧校舎` | place | `gedung sekolah lama` | `scene02.json #104` |

## 4. Scene / Route Overview
| File | Line Range | POV / Protagonist | One-line Summary |
|---|---|---|---|
| `scene01.json` | 1–240 | Protagonist | Opening morning walk and transfer intro |

## 5. Project-Wide Policy Decisions (Settle Before Parallel Translation or Review)
Settle these once with the user and record confirmed choices in `state settle` / `STYLE_GUIDE.md` / `review/config.json`:

| Policy | Options | Decided | Evidence / Date |
|---|---|---|---|
| Honorifics (`-san/-kun/-chan/-sama/-senpai/-sensei`) | Keep verbatim / Localize (`Kak/Pak/Bu`) / Mixed | | |
| Dialogue quotation style | Standard `"..."` / Japanese `「...」` (`kagikakko`) | | |
| Unknown proper nouns / Western names | Keep Hepburn/source / Transliterate | | |
| Narrative tense (`ja-en`) | Past / Present | | |
| Pronoun default for neutral peers (`ja-id` / `en-id`) | `aku/kamu` / `aku/kau` / drop when natural | | |
| Collective / non-human pronouns | `mereka` / `ia` / `itu` | | |
| Onomatopoeia / SFX style | Natural prose verb / Italicized SFX / Both | | |

## 6. Ambiguities Requiring User / Coordinator Ruling
- `<Example: Character X gender/relationship unstated in scene01; see #88>`
- `<Example: Kanji name reading unconfirmed (神楽坂); see #15>`
