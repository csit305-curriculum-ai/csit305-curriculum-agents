# Corpus sources

Accessed 2 Nov 2026 (UTC+4) by Sanjay Patanannadan. Raw files are **not committed**, because no redistribution licence is stated for any of them. Run `scripts/fetch_corpus.sh` to download them into `corpus/raw/`, then compare the hashes below. A hash mismatch means the source has changed: stop and log it (Doc 3 edge case "changed source-file hash").

| File | Title / publisher | Edition | Source URL (as fetched) | Pages | Language | Grades used | SHA-256 | Licence | Indexed? |
|---|---|---|---|---|---|---|---|---|---|
| moe_math_scope_sequence_g1-12.pdf | Scope and Sequence: Math G1-12 (Work in Progress), UAE Ministry of Education | PDF created 27 Feb 2019 (internal title "ALL IN ONE - EDITED 12-9") | https://web.archive.org/web/2022id_/https://www.moe.gov.ae/Ar/ImportantLinks/Assessment/Documents/Curriculum-docs/Scope%20and%20Sequence%20_%20Math%20G1-12%20_%20Work_in_Progress.pdf | 144 | English + Arabic | 1–4 parsed; 3–4 used by tasks | e878c0c39a2f58aef36d8ff423472302f5ac268ab2bdb56be2c396fddb8234cf | No licence stated (© MoE). Public download; redistribution unclear | Yes: 408 outcome rows, Grades 1–4 |
| moe_science_framework_2019-20.pdf | MOE Science Framework 2019-20, UAE Ministry of Education | PDF created 24 Feb 2019 | https://web.archive.org/web/2022id_/https://www.moe.gov.ae/Ar/ImportantLinks/Assessment/Documents/Curriculum-docs/MOE%20Science%20Framework%202019-20.pdf | 86 | KG mapping in English; **Grade 1–12 outcomes in Arabic only** | none | 483a7be74c4f240d99aea23bb5168fd3845bceb976541b1d3ff6357afe8fe43e | No licence stated (© MoE) | **No** (Arabic-only G1–4; DEC 007) |
| timss2023_uae_encyclopedia.pdf | TIMSS 2023 Encyclopedia: United Arab Emirates (IEA / TIMSS & PIRLS International Study Center, Boston College) | 2024 | https://timss2023.org/wp-content/uploads/2024/10/United-Arab-Emirates.pdf | 13 | English | Grade 4 maths topics; Cycle 1 (G1–4) science content | 5cddac03fe5b114960a5bfcea696cda3a90f991bcbe88991571a291274d6af59 | © IEA. Public; redistribution unclear | Yes: 2 records (maths Exhibit 1, science Exhibit 3) |

Discovery: the MoE URLs were listed on Dubai Modern Education School's "MOE Standards" page (https://dmes.ae/en/moe-curriculum/moe-standards/). The original moe.gov.ae links returned **HTTP 404** on 2 Nov 2026, so the Internet Archive copies were used.

## Missing (needed before the main experiment)
- **Grade 3–4 Science outcomes in English with outcome IDs.** None found. The MoE framework has G3/G4 codes (e.g. `1.1.1.4.G3`) but only in Arabic. Science retrieval currently depends on one ~600-token TIMSS summary of Cycle 1. This is too thin to test grade-specific grounding, and it blocks Doc 3 TEST 001 (remove one Grade 4 Science outcome).
  Options for the group:
  (a) find the English MoE science standards or the Inspire Science G3/G4 scope and sequence;
  (b) have a bilingual member translate the G3/G4 outcomes, recorded as a derived source;
  (c) run TEST 001 on Grade 4 Maths instead and record the change as a DEC.
- The **2019 Mathematics/Science standards** PDFs linked on the DMES page (the "Download" buttons) could not be resolved to a URL.
- The **Grade 1–2 science** gap is the same as Grades 3–4, but it is out of scope (Doc 3 T3 uses Grades 3–4).
