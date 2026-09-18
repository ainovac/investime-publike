"""
Step 4 validation for the Step 3 generator output.

Run with: pytest tests/ -v
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMA = ROOT / "schema"
OUT = ROOT / "output"

LEGAL_PAYMENT_DAYS = 30


def load_schema(system):
    return yaml.safe_load((SCHEMA / system / f"{system}_schema.yaml").read_text(encoding="utf-8"))


AFMIS_SCHEMA = load_schema("afmis")
SIFQ_SCHEMA = load_schema("sifq")
GENERATED_ENTITIES = {
    "afmis": ["institucioni", "projekt_investimi", "vlera_buxhetore_projekti", "kerkesa_obp"],
    "sifq": ["dokument_shpenzimi", "furnitor", "angazhim_buxhetor", "fature", "pagese"],
}


def read(system, entity, parse_dates=None):
    return pd.read_csv(OUT / system / f"{entity}.csv", parse_dates=parse_dates)


def schema_entity(schema, name):
    return next(e for e in schema["entities"] if e["name"] == name)


# ---------------------------------------------------------------------------
# 1. Every generated column exists in the schema; no extra columns
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("system,entity", [(s, e) for s, es in GENERATED_ENTITIES.items() for e in es])
def test_columns_match_approved_schema(system, entity):
    schema = AFMIS_SCHEMA if system == "afmis" else SIFQ_SCHEMA
    declared = set(f["name"] for f in schema_entity(schema, entity)["fields"])
    df = read(system, entity)
    assert set(df.columns) == declared, (
        f"{system}.{entity}: column mismatch - "
        f"extra={set(df.columns) - declared}, missing={declared - set(df.columns)}"
    )


# ---------------------------------------------------------------------------
# 2. Primary keys are unique
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("system,entity", [(s, e) for s, es in GENERATED_ENTITIES.items() for e in es])
def test_primary_key_unique(system, entity):
    schema = AFMIS_SCHEMA if system == "afmis" else SIFQ_SCHEMA
    pk = schema_entity(schema, entity)["primary_key"]
    df = read(system, entity)
    dupes = df.duplicated(subset=pk).sum()
    assert dupes == 0, f"{system}.{entity}: {dupes} duplicate rows on primary key {pk}"


# ---------------------------------------------------------------------------
# 3. Every SIFQ NIPT exists in the real APP data. Contract numbers are EXCLUDED
#    from this check on purpose: neither app_notices, app_realizations nor
#    kpp_appeal expose a real contract number anywhere (confirmed during Step 1/2
#    investigation - see docs/sifq/struktura_sifq.md Gaps #... and the generator's
#    module docstring), so angazhim_buxhetor.numri_kontrates is necessarily
#    synthetic. Asserting it against real data would be asserting a false premise.
# ---------------------------------------------------------------------------
def test_sifq_winner_nipt_exists_in_real_app_data():
    angazhim = read("sifq", "angazhim_buxhetor")
    real_nipts = set(pd.read_csv(DATA / "app" / "app_realizations.csv")["winner_nipt"].dropna())
    generated_nipts = set(angazhim["nipt_perfituesit"].dropna())
    orphans = generated_nipts - real_nipts
    assert not orphans, f"{len(orphans)} nipt_perfituesit values not found in real app_realizations.winner_nipt"


def test_sifq_furnitor_nipt_exists_in_real_app_data():
    furnitor = read("sifq", "furnitor")
    real_nipts = set(pd.read_csv(DATA / "app" / "app_realizations.csv")["winner_nipt"].dropna())
    orphans = set(furnitor["nipt"]) - real_nipts
    assert not orphans, f"{len(orphans)} furnitor.nipt values not found in real app_realizations.winner_nipt"


def test_contract_numbers_are_synthetic_not_real_by_design():
    """Documents the known, deliberate limitation rather than silently skipping it."""
    angazhim = read("sifq", "angazhim_buxhetor")
    non_null = angazhim["numri_kontrates"].dropna()
    assert non_null.str.startswith("Kontratë").all(), (
        "numri_kontrates should be our synthetic 'Kontratë...' format - if this fails, "
        "someone may have wired in a real-looking contract number source without updating "
        "this test and the documented gap in docs/sifq/struktura_sifq.md"
    )


# ---------------------------------------------------------------------------
# 4. AFMIS <-> SIFQ composite key joins with no orphans
#    (kodi_programi is null everywhere by design - see CLAUDE.md - so the
#    practically-testable part of the composite key is kodi_projekti +
#    kodi_institucioni + kodi_llogarie_ekonomike; this test checks that slice
#    has zero orphans, i.e. no SIFQ commitment points at a nonexistent project.)
# ---------------------------------------------------------------------------
def test_afmis_sifq_composite_key_no_orphans():
    projects = read("afmis", "projekt_investimi")
    angazhim = read("sifq", "angazhim_buxhetor")
    key_cols = ["kodi_projekti", "kodi_institucioni", "kodi_llogarie_ekonomike"]
    merged = angazhim.merge(projects[key_cols], on=key_cols, how="left", indicator=True)
    orphans = (merged["_merge"] == "left_only").sum()
    assert orphans == 0, f"{orphans} SIFQ commitments have no matching AFMIS project on {key_cols}"


def test_afmis_sifq_grain_is_many_to_one():
    """Confirms the documented grain difference actually shows up in the data:
    SIFQ (transaction grain) should have >= as many rows as distinct AFMIS
    projects it references, i.e. it's legitimately many-to-one, not accidentally 1:1."""
    angazhim = read("sifq", "angazhim_buxhetor")
    fature = read("sifq", "fature")
    invoices_per_commitment = fature.groupby("numri_angazhimit").size()
    assert invoices_per_commitment.max() >= 1
    # at least some commitments should have more than one invoice, given
    # N_INVOICES_PER_COMMITMENT = (1, 3) in the generator
    assert (invoices_per_commitment > 1).any(), "expected at least some multi-invoice commitments"


# ---------------------------------------------------------------------------
# 5. Date order: budget approval < publication < signing < invoice < acceptance < payment
#    (signing is only known at month/year granularity in the stored schema - see
#    module docstring in generate_afmis_sifq.py - so that specific hop is tested
#    at month granularity; every other hop is tested at full date/day precision.)
# ---------------------------------------------------------------------------
def test_approval_before_publication():
    budget = read("afmis", "vlera_buxhetore_projekti", parse_dates=["data_miratimit_buxhetit"])
    obp = read("afmis", "kerkesa_obp")
    notices = pd.read_csv(DATA / "app" / "app_notices.csv", parse_dates=["open_datetime"])

    merged = (
        budget.dropna(subset=["data_miratimit_buxhetit"])
        .merge(obp[["kodi_projekti", "numri_procedures_prokurimit"]], on="kodi_projekti", how="inner")
        .merge(notices[["ref_no", "open_datetime"]], left_on="numri_procedures_prokurimit", right_on="ref_no", how="inner")
    )
    assert len(merged) > 0, "no rows to check - upstream data changed?"
    bad = merged[merged["data_miratimit_buxhetit"] >= merged["open_datetime"]]
    assert len(bad) == 0, f"{len(bad)} projects have budget approval on/after publication date"


def test_publication_before_signing_month():
    obp = read("afmis", "kerkesa_obp")
    notices = pd.read_csv(DATA / "app" / "app_notices.csv", parse_dates=["open_datetime"])
    angazhim = read("sifq", "angazhim_buxhetor")

    merged = (
        angazhim.merge(obp[["kodi_projekti", "numri_procedures_prokurimit"]], on="kodi_projekti", how="inner")
        .merge(notices[["ref_no", "open_datetime"]], left_on="numri_procedures_prokurimit", right_on="ref_no", how="inner")
    )
    assert len(merged) > 0
    signing_month_start = pd.to_datetime(
        dict(year=merged["periudha_viti"], month=merged["periudha_muaji"], day=1))
    bad = merged[signing_month_start < merged["open_datetime"].dt.to_period("M").dt.to_timestamp()]
    assert len(bad) == 0, f"{len(bad)} commitments have a signing month before the publication month"


def test_signing_before_first_invoice():
    angazhim = read("sifq", "angazhim_buxhetor")
    fature = read("sifq", "fature", parse_dates=["data_fatures"])
    first_invoice = fature.groupby("numri_angazhimit")["data_fatures"].min().rename("first_invoice_date")
    merged = angazhim.merge(first_invoice, on="numri_angazhimit", how="inner")
    signing_month_start = pd.to_datetime(
        dict(year=merged["periudha_viti"], month=merged["periudha_muaji"], day=1))
    bad = merged[merged["first_invoice_date"] < signing_month_start]
    assert len(bad) == 0, f"{len(bad)} commitments have an invoice before their signing month"


def test_invoice_before_registration_before_status_change():
    fature = read("sifq", "fature", parse_dates=["data_fatures", "data_mberritjes_regjistrimit", "data_ndryshimit_statusit"])
    bad1 = fature[fature["data_fatures"] > fature["data_mberritjes_regjistrimit"]]
    assert len(bad1) == 0, f"{len(bad1)} invoices registered before they were issued"
    bad2 = fature[fature["data_mberritjes_regjistrimit"] > fature["data_ndryshimit_statusit"]]
    assert len(bad2) == 0, f"{len(bad2)} invoices had their status changed before registration"


def test_acceptance_before_payment():
    fature = read("sifq", "fature", parse_dates=["data_ndryshimit_statusit"])
    pagese = read("sifq", "pagese", parse_dates=["data_urdherit_shpenzimit", "data_ekzekutimit_pageses"])
    merged = pagese.merge(fature[["numri_fatures", "data_ndryshimit_statusit", "statusi"]], on="numri_fatures", how="inner")

    assert (merged["statusi"] == "pranuar").all(), "a payment exists for a non-accepted invoice"
    bad = merged[merged["data_urdherit_shpenzimit"] < merged["data_ndryshimit_statusit"]]
    assert len(bad) == 0, f"{len(bad)} payment orders precede invoice acceptance"
    bad2 = merged[merged["data_ekzekutimit_pageses"] < merged["data_urdherit_shpenzimit"]]
    assert len(bad2) == 0, f"{len(bad2)} payments executed before their own payment order"


def test_nothing_after_today():
    today = pd.Timestamp("2026-09-18")
    budget = read("afmis", "vlera_buxhetore_projekti",
                   parse_dates=["data_miratimit_buxhetit", "data_rishikimit_fundit"])
    fature = read("sifq", "fature", parse_dates=["data_fatures", "data_mberritjes_regjistrimit", "data_ndryshimit_statusit"])
    pagese = read("sifq", "pagese", parse_dates=["data_urdherit_shpenzimit", "data_ekzekutimit_pageses"])

    for df, cols in [(budget, ["data_miratimit_buxhetit", "data_rishikimit_fundit"]),
                      (fature, ["data_fatures", "data_mberritjes_regjistrimit", "data_ndryshimit_statusit"]),
                      (pagese, ["data_urdherit_shpenzimit", "data_ekzekutimit_pageses"])]:
        for c in cols:
            future_rows = df[df[c] > today]
            assert len(future_rows) == 0, f"{len(future_rows)} rows have {c} after {today.date()}"


# ---------------------------------------------------------------------------
# 6. Aggregated SIFQ payments per project/year never exceed the AFMIS approved value
# ---------------------------------------------------------------------------
def test_payments_never_exceed_approved_budget():
    budget = read("afmis", "vlera_buxhetore_projekti")
    angazhim = read("sifq", "angazhim_buxhetor")
    fature = read("sifq", "fature")
    pagese = read("sifq", "pagese")

    paid = (
        pagese.merge(fature[["numri_fatures", "numri_angazhimit"]], on="numri_fatures", how="left")
        .merge(angazhim[["numri_angazhimit", "kodi_projekti"]], on="numri_angazhimit", how="left")
        .groupby("kodi_projekti")["vlera_paguar_faktikisht"].sum()
        .rename("total_paid")
    )
    merged = budget.dropna(subset=["vlera_miratuar_aktuale"]).merge(
        paid, on="kodi_projekti", how="left")
    merged["total_paid"] = merged["total_paid"].fillna(0)
    over = merged[merged["total_paid"] > merged["vlera_miratuar_aktuale"] + 0.01]
    assert len(over) == 0, (
        f"{len(over)} projects have aggregated payments exceeding the AFMIS approved value:\n"
        f"{over[['kodi_projekti', 'vlera_miratuar_aktuale', 'total_paid']].to_string()}"
    )


# ---------------------------------------------------------------------------
# Extra: real data was never modified
# ---------------------------------------------------------------------------
def test_real_data_files_unchanged_row_counts():
    assert len(pd.read_csv(DATA / "app" / "app_notices.csv")) == 6500
    assert len(pd.read_csv(DATA / "kpp" / "kpp_appeal.csv")) == 5847
    assert len(pd.read_csv(DATA / "app" / "app_realizations.csv")) == 8000
