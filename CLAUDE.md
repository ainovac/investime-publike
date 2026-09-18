# Menaxhimi i Investimeve Publike — AFMIS/SIFQ synthetic data pilot

Innovation4Albania (I4A) pilot dashboard linking public-investment data across four
systems: **AFMIS** (budget planning), **APP/SPE** (e-procurement), **KPP** (procurement
complaints), **SIFQ** (Treasury: commitments/invoices/payments).

APP and KPP are scraped from real public registers. AFMIS and SIFQ are not accessible, so
this project documents their *logical* structure from official sources and generates
synthetic data for them that joins correctly to the real APP/KPP data.

## Hard rules (do not relax these without the user's explicit say-so)

1. **No hallucinated fields.** Every AFMIS/SIFQ field must trace to one of the three
   source docs in `docs/` — PDF section, XLSX sheet+row, or the KPI docx table — with the
   exact wording quoted. See `schema/afmis/afmis_schema.yaml` and `schema/sifq/sifq_schema.yaml`
   for the citation format.
2. If a KPI needs a field with no source, it goes in the structure doc's **Gaps** section,
   never silently added.
3. Physical table/column names, types, code formats, API endpoints are **NOT confirmed**
   (both PDF §1 and XLSX sheet `01_Permbledhje` say so explicitly). Every field is tagged
   `CONFIRMED_LOGICAL` (named in a source) or `ASSUMED` (structural necessity we added —
   surrogate keys, FKs, obviously-required value/date columns). Never present an ASSUMED
   field as if it were document-confirmed.
4. **AFMIS and SIFQ are never merged** — separate structure docs, separate schema YAMLs,
   separate tables in the generator and in `output/`.
5. There is **no confirmed technical primary key between AFMIS and SIFQ** (PDF §3.9). The
   link is modeled as a composite business key: `viti_fiskal + kodi_institucioni +
   kodi_programi + kodi_projekti + kodi_llogarie_ekonomike (230/231)`. AFMIS is at
   budget-line grain (project × year); SIFQ is at transaction grain (one row per
   commitment/invoice/payment) — joining requires aggregating SIFQ up to AFMIS's grain
   first, never a naive 1:1 join.
6. If a source is ambiguous or contradictory, **stop and ask the user** — don't pick
   silently. (Two examples already hit and resolved this session: whether Realizimeve
   register data should be force-joined to existing ref_no-identified notices — answer:
   no, kept as an independent real dataset; how to handle missing award data initially —
   answer: went and scraped it rather than synthesizing it.)

## Folder layout

AFMIS and SIFQ are kept in **separate subfolders everywhere** (rule 4 — never merged),
mirrored consistently across docs/, schema/ and output/:

```
investime-publike/
├── CLAUDE.md                    this file
│
├── data/                        REAL scraped data — never modified by the generator
│   ├── app/                     from app.gov.al (three distinct registers, see below)
│   │   ├── app_notices.csv          published tender notices, PARTIAL: 6,500/~12,510 rows
│   │   ├── app_documents.csv        one row per document attached to a notice
│   │   └── app_realizations.csv     Regjistri i Realizimeve — winner/value/award date,
│   │                                 PARTIAL: 8,000/~10,000 rows, NO ref_no (see Key findings)
│   └── kpp/
│       └── kpp_appeal.csv           KPP appeals register, COMPLETE: 5,847 rows
│
├── docs/                         source documents (shared, not AFMIS/SIFQ-specific) +
│   │                              one structure doc per system in its own subfolder
│   ├── Struktura_te_Dhenave_AFMIS_SIFQ.pdf              (source, both systems)
│   ├── Investime_Publike_Specifikim_te_dhenash...xlsx   (source, both systems)
│   ├── KPI (komente)- Menaxhimi i investimeve publike (1).docx  (source, both systems)
│   ├── afmis/
│   │   └── struktura_afmis.md   entities/grain/keys/gaps/open-questions, AFMIS only
│   └── sifq/
│       └── struktura_sifq.md    same, SIFQ only
│
├── schema/                       machine-readable field inventories, one per system
│   ├── afmis/
│   │   └── afmis_schema.yaml    11 entities, 46 fields, full source citation per field
│   └── sifq/
│       └── sifq_schema.yaml     5 entities, 40 fields, full source citation per field
│
├── src/                          scripts (scrapers done; generator pending approval)
│   ├── scrape_app_realizations.py   done — produced data/app/app_realizations.csv
│   ├── scrape_app_parashikime.py    WORKS for page 1 only — see Key findings, pagination
│   │                                  on this register needs an AJAX call we haven't solved
│   └── generate_afmis_sifq.py       NOT YET WRITTEN — Step 3, needs your approval first
│
└── output/                       generator output, once Step 3 is approved and run
    ├── afmis/                    synthetic AFMIS tables (one CSV per entity)
    └── sifq/                     synthetic SIFQ tables (one CSV per entity)
```

Why `data/` is split by *source system* (app/, kpp/) while `docs/`, `schema/`, `output/`
are split by *target system* (afmis/, sifq/): `data/` holds what we scraped, named after
where it came from; the other three hold what we're building, named after what it's for.

## Key findings from this session (don't re-derive these — verified, not assumed)

- **APP and KPP share `ref_no` (`REF-xxxxx-MM-DD-YYYY`) and `notification_no`
  (`CN/xxxxx/MMDDYYYY`)** — verified with 698 exact `ref_no` matches between our partial
  APP set and the full KPP set. This is a solid, ready-to-use join key.
- **APP's tender-notice pages never expose the contracting authority's NIPT** — only the
  name. KPP is the only real source we have for authority NIPT (`ak_nipt`/`ak_name`), and
  only for authorities that have had at least one appeal.
- **Winner NIPT / contract value / signing date live on a *different* APP register**:
  `Regjistri i Realizimeve` (`/regjistri-i-realizimeve/`), not the tender-notice pages we
  originally scraped. This register has **no `ref_no`/`notification_no` field at all** —
  it cannot be cleanly joined back to a specific already-scraped tender notice. Per the
  user's explicit decision, it's kept as its own independent real dataset
  (`data/app/app_realizations.csv`), not force-matched.
- Both `app_notices` and `app_realizations` scrapes are **partial** because the
  Claude Code session's background-task memory-pressure reaper killed the full runs twice
  each (unrelated to script bugs — see the checkpointing logic in both scraper scripts,
  which exists specifically because of this). User decided to proceed with partial data
  rather than block on completing them.
- Both APP registers (notices, realizations) are server-rendered ASP.NET/Umbraco with **no
  JSON API** — pagination is a session-cookie + CSRF-token (`__RequestVerificationToken`) +
  Umbraco route-token (`ufprt`) walk, sequential only, no `page=N` shortcut. See
  `src/scrape_app_realizations.py` docstring and the sibling `app-extract` project for the
  original tender-notice scraper.
- **A third APP register, `Regjistri i Parashikimeve`** (`/regjistri-i-parashikimeve/`, the
  annual procurement *plan*, pre-tender) was checked and has the same fields as Realizimeve
  minus the award-only ones (no new schema fields, so not currently required) — but its
  pagination does **not** follow the same form-POST pattern: page 2+ returns a loading
  spinner placeholder (`id="latest-documents"`) instead of rendered rows, meaning results
  past page 1 are populated by a client-side AJAX call we haven't reverse-engineered yet
  (`GetData/GetLastRegisters` is the likely endpoint, unconfirmed). `src/scrape_app_parashikime.py`
  exists and correctly parses page 1 (10 sample rows, not saved to `data/`) but cannot walk
  further yet. Deprioritized since it wouldn't add real value beyond what Realizimeve/notices
  already give us for the current schema — revisit only if a KPI specifically needs "planned
  but not yet published" investment data (this maps to KPI F5.2/F5.3's denominator).

## Status — all 4 steps done

- **Step 3** (`src/generate_afmis_sifq.py`): generates AFMIS + SIFQ synthetic data on top
  of the real APP/KPP backbone. Row counts (seed=42): 1,035 institutions, 10,833 AFMIS
  projects (6,500 real-backed + 4,333 synthetic "never procured", 40.0% rate), 4,490
  purchase requests (real procedures ≥ 1,000,000 ALL), 2,922 SIFQ commitments, 4,906
  invoices, 4,499 payments.
  - Project↔contract pairing is a **chronologically- and financially-constrained greedy
    match** (`match_projects_to_realizations`), not a real join (none exists - see Key
    Findings). It requires the sampled contract's award date to be ≥14 days after the
    project's real publication date, AND its real contract value to fit under a
    worst-case reading of that project's own AFMIS budget ceiling. Both constraints were
    added after the first test run caught violations of exactly these properties -  see
    git-free history in this file: don't loosen them without re-running `tests/`.
  - `output/_truth_links.csv` marks every row `contract_link_is_real_match=False` for
    this reason — never treat it as ground truth about which contract belongs to which
    procedure, only as a plausible, internally-consistent test fixture.
  - `output/afmis/_institucion_nipt_mapping.csv` is a support artifact (not an approved
    schema entity) — resolves the tension between "institucioni has no `nipt` field in
    the approved schema" (true - PDF/XLSX never named one) and "keep the real NIPT,
    document the mapping in a reference table" (the user's Step 3 instruction).
  - Entities NOT generated (see the script's module docstring for the full reasoning):
    `programi_buxhetor`, `tavan_buxhetor`, `deklarata_politikes_programit`,
    `tregues_performance`, `emp_anetar`, `roli_perdoruesi`, `zeri_ekonomik_230_231`
    (AFMIS). `kodi_programi` is left null everywhere it's a foreign key.

- **Step 4** (`tests/test_generated_data.py`): 31 pytest checks, all passing. Covers
  schema-column exactness, PK uniqueness, real-NIPT traceability (contract numbers are
  explicitly EXCLUDED from that check and instead asserted to be synthetic-by-design —
  no real contract number exists anywhere in our data, confirmed during Step 1/2), the
  AFMIS↔SIFQ composite-key join (no orphans), full date-ordering (approval < publication
  < signing-month < invoice < registration < status-change < payment-order < execution,
  nothing after 2026-09-18), and aggregated-payments-never-exceed-approved-budget. Run
  with `pytest tests/ -v` from the project root.

Re-running `python src/generate_afmis_sifq.py` is idempotent (fixed seed=42) and safe -
it only reads `data/`, never writes to it, and overwrites `output/` in place.
