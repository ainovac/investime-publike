# Investime Publike

Innovation4Albania (I4A) pilot for a public-investment dashboard that links data across four systems:

- **AFMIS** — budget planning
- **APP/SPE** — e-procurement (real data from [app.gov.al](https://www.app.gov.al))
- **KPP** — procurement complaints (real data from the KPP appeals register)
- **SIFQ** — Treasury commitments, invoices, and payments

APP and KPP are scraped from public registers. AFMIS and SIFQ are not publicly accessible, so this repo documents their logical structure from official sources and generates synthetic AFMIS/SIFQ data that joins to the real APP/KPP backbone.

## Setup

```bash
pip install -r requirements.txt
```

Regenerate synthetic AFMIS/SIFQ tables (fixed seed, overwrites `output/` only):

```bash
python src/generate_afmis_sifq.py
```

Run checks:

```bash
pytest tests/ -v
```

## Layout

```
data/app/          real APP scrapes (notices, documents, realizations)
data/kpp/          real KPP appeals
docs/              source documents and per-system structure notes
schema/            field inventories for AFMIS and SIFQ
src/               scrapers and the synthetic generator
output/            generated AFMIS and SIFQ CSVs
tests/             schema, join, and date-order checks
```

AFMIS and SIFQ stay separate everywhere: different docs, schemas, generator tables, and `output/` folders. There is no confirmed technical primary key between them; the join is modeled as a composite business key (`viti_fiskal + kodi_institucioni + kodi_programi + kodi_projekti + kodi_llogarie_ekonomike`).

See `CLAUDE.md` for field-citation rules, join caveats, and current dataset status.
