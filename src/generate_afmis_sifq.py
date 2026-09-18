"""
Step 3 — synthetic AFMIS + SIFQ data generator.

Reads REAL data (data/app/, data/kpp/) as backbone, generates synthetic AFMIS/SIFQ rows
around it, and writes output/afmis/*.csv, output/sifq/*.csv, output/_truth_links.csv.

Every generated table's columns are validated against schema/afmis/afmis_schema.yaml and
schema/sifq/sifq_schema.yaml at write time - the script will refuse to write a column that
isn't declared in the approved schema (rule: "only generate fields that exist in the
approved schema files").

IMPORTANT - what this does NOT do, and why (see docs/afmis/struktura_afmis.md and
docs/sifq/struktura_sifq.md "Gaps" sections for the full reasoning):

  - Does not generate programi_buxhetor, tavan_buxhetor, deklarata_politikes_programit,
    tregues_performance, emp_anetar, roli_perdoruesi, zeri_ekonomik_230_231 (AFMIS), or
    kerkese_blerje, leshimi, rishikim_buxhetor (SIFQ - added to the schema in the second
    session from UDHEZ/INTEGR, but none are tied to a KPI code either). None of these were
    part of the real-data-backbone flow the user described for Step 3; fabricating them
    would mean inventing structure with no real anchor. kodi_programi is left null
    everywhere (it's a NICE-TO-HAVE field per XLSX 02_AFMIS row 7, not MUST).
    kerkese_blerje.numri_kerkeses is a partial exception: angazhim_buxhetor.numri_kerkeses_blerje
    is populated (UDHEZ confirms this FK is mandatory) even though the kerkese_blerje table
    itself isn't generated - see build_sifq_chain.
  - There is NO real link between a specific procurement procedure (app_notices) and a
    specific contract award (app_realizations) - Regjistri i Realizimeve has no ref_no
    (confirmed by inspection, user decided against forced/probabilistic matching). So the
    AFMIS project<->SIFQ contract pairing below is a SYNTHETIC RANDOM SAMPLE: real winner
    NIPT/contract value/award date, attached to a real procedure that was NOT verified to
    be the actual procedure that produced that contract. output/_truth_links.csv marks
    every row `contract_link_is_real_match=False` for exactly this reason - never treat it
    as ground truth about which contract belongs to which procedure.
  - "Contract signing date" has no dedicated field in the approved SIFQ schema (PDF/XLSX
    describe it as an APP/SPE-side date, §04_APP_SPE row 17, not a SIFQ field) and
    Realizimeve itself has no separate signing date - only `Data e prokurimit` (award/
    procurement date). That field is used as the signing-date proxy throughout.
  - Law 48/2016's 30-day clock is anchored on `fature.data_fatures`, not
    `data_mberritjes_regjistrimit` - this is an explicit, documented pick of one option
    from an open question the source docs themselves leave unresolved (XLSX 07_SIFQ_Thesar
    row 10.0: "duhet konfirmuar cila përdoret").

Usage:
    pip install pandas pyyaml numpy
    python generate_afmis_sifq.py
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
SEED = 42
TODAY = date(2026, 9, 18)

VAT_RATE = 0.20                      # AFMIS values include VAT; SPE fund_limit doesn't (PDF §3.9)
OBP_THRESHOLD_ALL = 1_000_000        # kerkesa_obp only for procedures >= this (PDF §2.6)
NEVER_PROCURED_RATE = 0.40           # extra AFMIS projects with no real procedure, for KPI F5.3
BUDGET_REVISION_RATE = 0.25          # share of projects whose vlera_miratuar_aktuale differs from planned
REVISION_DELTA_RANGE = (-0.15, 0.25) # revision size as a fraction of the initial planned value

N_INVOICES_PER_COMMITMENT = (1, 3)   # inclusive range, uniform
P_MISSING_CONTRACT_NUMBER = 0.10     # angazhim_buxhetor.numri_kontrates left blank
P_INVOICE_REJECTED = 0.08            # fature.statusi = 'refuzuar'
P_PAYMENT_LATE = 0.15                # pagese beyond the 30-day Law 48/2016 deadline
LEGAL_PAYMENT_DAYS = 30

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMA = ROOT / "schema"
OUT = ROOT / "output"

rng = np.random.default_rng(SEED)

REJECTION_REASONS = [
    "Mospërputhje me kontratën", "Mungesë dokumentacioni mbështetës",
    "Gabim në shumën e faturuar", "Fiskalizim i pavlefshëm",
]
FUNDING_SOURCES = ["Buxheti i Shtetit", "Të ardhura të trashiguara", "Financim i huaj"]
MINISTRITE = [
    "Ministria e Financave dhe Ekonomisë", "Ministria e Shëndetësisë dhe Mbrojtjes Sociale",
    "Ministria e Arsimit dhe Sportit", "Ministria e Infrastruktures dhe Energjisë",
    "Ministria e Bujqësisë dhe Zhvillimit Rural", "Ministria e Brendshme",
]
KAPITUJT = [f"Kapitulli {i}" for i in range(1, 8)]
ENTITETE_QEVERISESE = ["Qendrore", "Vendore", "SHA"]
DEGET_THESARIT = ["Tiranë", "Durrës", "Vlorë", "Shkodër", "Elbasan", "Korçë", "Fier"]
TIPE_BUXHETI = ["Buxheti i Shtetit", "Të ardhura të trashiguara", "Financim i huaj"]
CONTRACT_TYPE_TO_LLOJ_FATURE = {"Mallra": "mall", "Shërbime": "sherbim", "Punë": "pune"}


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
def load_schema(system):
    path = SCHEMA / system / f"{system}_schema.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def entity_fields(schema, entity_name):
    for e in schema["entities"]:
        if e["name"] == entity_name:
            return [f["name"] for f in e["fields"]]
    raise KeyError(f"entity {entity_name!r} not found in schema")


def write_validated(df, system, entity_name, schema):
    declared = entity_fields(schema, entity_name)
    extra = set(df.columns) - set(declared)
    if extra:
        raise ValueError(f"{system}.{entity_name}: columns not in approved schema: {sorted(extra)}")
    for col in declared:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[declared]
    out_dir = OUT / system
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{entity_name}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  {system}/{entity_name}.csv: {len(df)} rows, {len(declared)} cols")
    return df


def clip_to_today(d):
    if pd.isna(d):
        return d
    d = pd.Timestamp(d)
    return min(d, pd.Timestamp(TODAY))


# ---------------------------------------------------------------------------
# Load real data (read-only - never written back to)
# ---------------------------------------------------------------------------
def load_real_data():
    app_notices = pd.read_csv(DATA / "app" / "app_notices.csv", parse_dates=["open_datetime", "close_datetime"])
    kpp_appeal = pd.read_csv(DATA / "kpp" / "kpp_appeal.csv")
    app_realizations = pd.read_csv(
        DATA / "app" / "app_realizations.csv", parse_dates=["procurement_date", "publication_datetime"])
    return app_notices, kpp_appeal, app_realizations


def norm_name(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())


# ---------------------------------------------------------------------------
# AFMIS: institucioni + NIPT mapping
# ---------------------------------------------------------------------------
def build_institucioni(app_notices, kpp_appeal, app_realizations):
    names = pd.concat([
        app_notices["contracting_authority"],
        app_realizations["contracting_authority"],
    ]).dropna().unique()
    kpp_lookup = (
        kpp_appeal.dropna(subset=["ak_name"])
        .assign(_norm=lambda d: d["ak_name"].map(norm_name))
        .drop_duplicates("_norm")
        .set_index("_norm")[["ak_nipt", "ak_name"]]
    )

    rows, mapping_rows = [], []
    for i, name in enumerate(sorted(names), start=1):
        kodi = f"INST-{i:04d}"
        rows.append({"kodi_institucioni": kodi, "emertimi": name})
        m = kpp_lookup.loc[norm_name(name)] if norm_name(name) in kpp_lookup.index else None
        mapping_rows.append({
            "kodi_institucioni": kodi,
            "emertimi": name,
            "real_nipt": m["ak_nipt"] if m is not None else pd.NA,
            "nipt_source": "kpp_appeal.ak_nipt (name-matched)" if m is not None else "unknown - not seen in KPP",
        })
    institucioni = pd.DataFrame(rows)
    mapping = pd.DataFrame(mapping_rows)
    matched = mapping["real_nipt"].notna().sum()
    print(f"  institucion NIPT mapping: {matched}/{len(mapping)} authorities matched to a real NIPT via KPP")
    return institucioni, mapping


# ---------------------------------------------------------------------------
# AFMIS: projekt_investimi + vlera_buxhetore_projekti + kerkesa_obp
# ---------------------------------------------------------------------------
def build_afmis_projects(app_notices, institucioni_map):
    name_to_kodi = dict(zip(institucioni_map["emertimi"], institucioni_map["kodi_institucioni"]))

    projects, budget_rows, obp_rows = [], [], []
    pid = 1
    for _, row in app_notices.iterrows():
        kodi_projekti = f"PRJ-{pid:06d}"
        pid += 1
        kodi_inst = name_to_kodi.get(row["contracting_authority"])
        llogari = rng.choice(["230", "231"])
        viti = int(row["open_datetime"].year) if pd.notna(row["open_datetime"]) else rng.integers(2023, 2027)

        projects.append({
            "kodi_projekti": kodi_projekti,
            "emertimi": row["tender_object"],
            "kodi_institucioni": kodi_inst,
            "kodi_programi": pd.NA,
            "viti_fiskal": viti,
            "kodi_llogarie_ekonomike": llogari,
            "burimi_i_financimit": rng.choice(FUNDING_SOURCES),
        })

        fund_limit = row["fund_limit"]
        if pd.notna(fund_limit):
            planned = round(fund_limit * (1 + VAT_RATE), 2)
            revised = rng.random() < BUDGET_REVISION_RATE
            if revised:
                delta = rng.uniform(*REVISION_DELTA_RANGE)
                approved = round(planned * (1 + delta), 2)
                approval_date = row["open_datetime"] - timedelta(days=int(rng.integers(30, 91)))
                revision_date = approval_date + timedelta(days=int(rng.integers(15, 180)))
                revision_date = clip_to_today(min(revision_date, row["open_datetime"] - timedelta(days=1)))
            else:
                approved = planned
                approval_date = row["open_datetime"] - timedelta(days=int(rng.integers(30, 91)))
                revision_date = pd.NA
            budget_rows.append({
                "kodi_projekti": kodi_projekti,
                "viti_fiskal": viti,
                "vlera_planifikuar_fillestare": planned,
                "vlera_miratuar_aktuale": approved,
                "perfshin_tvsh": True,
                "vlera_disbursuar": pd.NA,  # filled post-hoc from SIFQ payments below
                "data_miratimit_buxhetit": approval_date,
                "data_rishikimit_fundit": revision_date,
            })
        else:
            # real fund_limit was null (16.7% of app_notices) - propagate the gap rather
            # than fabricating a budget figure with no real anchor
            budget_rows.append({
                "kodi_projekti": kodi_projekti, "viti_fiskal": viti,
                "vlera_planifikuar_fillestare": pd.NA, "vlera_miratuar_aktuale": pd.NA,
                "perfshin_tvsh": pd.NA, "vlera_disbursuar": pd.NA,
                "data_miratimit_buxhetit": pd.NA, "data_rishikimit_fundit": pd.NA,
            })

        if pd.notna(fund_limit) and fund_limit >= OBP_THRESHOLD_ALL:
            send_date = row["open_datetime"] - timedelta(days=int(rng.integers(5, 30)))
            # numri_transaksionit format follows UDHEZ's confirmed PR-number convention
            # (kodi_institucioni-viti-numer_rendor) since INTEGR describes it as the SAME
            # transaction number registered in SIMF/SIFQ that SPE validates against.
            numri_transaksionit = f"{kodi_inst}-{viti}-{pid:06d}" if pd.notna(kodi_inst) else pd.NA
            obp_rows.append({
                "kodi_projekti": kodi_projekti,
                "referenca_kerkeses_obp": f"REQ-{pid:06d}",
                "statusi_kerkeses": "Aprovuar",
                "data_dergimit_kerkeses": send_date,
                "numri_procedures_prokurimit": row["ref_no"],
                "numri_transaksionit": numri_transaksionit,
            })

    return (
        pd.DataFrame(projects), pd.DataFrame(budget_rows), pd.DataFrame(obp_rows),
    )


def add_never_procured_projects(projects_df, budget_df, institucioni_df, rate):
    n_real = len(projects_df)
    n_extra = int(round(n_real * rate / (1 - rate)))
    start_pid = len(projects_df) + 1

    inst_kodi = institucioni_df["kodi_institucioni"].tolist()
    extra_projects, extra_budget = [], []
    for i in range(n_extra):
        kodi_projekti = f"PRJ-{start_pid + i:06d}"
        viti = int(rng.integers(2023, 2027))
        extra_projects.append({
            "kodi_projekti": kodi_projekti,
            "emertimi": f"Investim i planifikuar (pa dalë ende në prokurim) {i + 1}",
            "kodi_institucioni": rng.choice(inst_kodi),
            "kodi_programi": pd.NA,
            "viti_fiskal": viti,
            "kodi_llogarie_ekonomike": rng.choice(["230", "231"]),
            "burimi_i_financimit": rng.choice(FUNDING_SOURCES),
        })
        planned = round(rng.uniform(500_000, 30_000_000), 2)
        max_month = TODAY.month if viti == TODAY.year else 12
        approval_date = pd.Timestamp(viti, int(rng.integers(1, max_month + 1)), int(rng.integers(1, 28)))
        approval_date = min(approval_date, pd.Timestamp(TODAY))
        extra_budget.append({
            "kodi_projekti": kodi_projekti, "viti_fiskal": viti,
            "vlera_planifikuar_fillestare": planned, "vlera_miratuar_aktuale": planned,
            "perfshin_tvsh": True, "vlera_disbursuar": pd.NA,
            "data_miratimit_buxhetit": approval_date, "data_rishikimit_fundit": pd.NA,
        })
    print(f"  never-procured extra AFMIS projects: {n_extra} (target rate {rate:.0%}, "
          f"actual {n_extra / (n_real + n_extra):.1%})")
    return (
        pd.concat([projects_df, pd.DataFrame(extra_projects)], ignore_index=True),
        pd.concat([budget_df, pd.DataFrame(extra_budget)], ignore_index=True),
    )


# ---------------------------------------------------------------------------
# SIFQ: furnitor, angazhim_buxhetor, dokument_shpenzimi, fature, pagese
# ---------------------------------------------------------------------------
def build_furnitor(app_realizations):
    suppliers = app_realizations.dropna(subset=["winner_nipt"]).drop_duplicates("winner_nipt")
    rows = []
    for i, (_, r) in enumerate(suppliers.iterrows(), start=1):
        rows.append({
            "nipt": r["winner_nipt"],
            "numri_furnitorit": f"FURN-{i:06d}",  # UDHEZ: system-assigned, distinct from NIPT
            "emertimi": r["winner_name"],
            "iban": "AL" + "".join(str(int(rng.integers(0, 10))) for _ in range(26)),
            "numri_llogarise_bankare": str(rng.integers(10**9, 10**10 - 1)),
            "adresa_bankes": rng.choice(["Tiranë", "Durrës", "Vlorë", "Shkodër"]),
        })
    return pd.DataFrame(rows)


def sample_real_procedure_type(app_notices, kodi_projekti_to_ref_no, kodi_projekti):
    ref_no = kodi_projekti_to_ref_no.get(kodi_projekti)
    if ref_no is None:
        return None
    match = app_notices.loc[app_notices["ref_no"] == ref_no, "contract_type"]
    return match.iloc[0] if len(match) else None


MIN_PUBLICATION_TO_AWARD_GAP_DAYS = 14  # a contract can't be awarded right at/before publication
VALUE_MATCH_SCAN_WINDOW = 500           # how many chronologically-later candidates to scan for a value fit


def match_projects_to_realizations(obp_df, app_notices, app_realizations):
    """Chronologically- AND financially-constrained greedy match: project<->contract
    pairing is still SYNTHETIC (no real key exists - see module docstring), but requiring
    both (a) the sampled contract's real award date to fall after the project's real
    publication date, and (b) its real contract value to fit under a conservative
    worst-case reading of that project's own AFMIS budget ceiling (see comment below)
    keeps the resulting chain internally consistent - date-ordered AND payments-never-
    exceed-budget - instead of pairing two unrelated real events at random."""
    ref_no_to_open = dict(zip(app_notices["ref_no"], app_notices["open_datetime"]))
    ref_no_to_fund_limit = dict(zip(app_notices["ref_no"], app_notices["fund_limit"]))

    proj_info = []
    for _, row in obp_df.iterrows():
        ref_no = row["numri_procedures_prokurimit"]
        open_dt = ref_no_to_open.get(ref_no)
        fund_limit = ref_no_to_fund_limit.get(ref_no)
        if pd.isna(open_dt) or pd.isna(fund_limit):
            continue
        # Worst-case AFMIS approved value after the generator's own revision logic
        # (VAT_RATE, REVISION_DELTA_RANGE) still applies below this - guarantees
        # contract_value <= vlera_miratuar_aktuale no matter how that project's
        # budget gets revised later in build_afmis_projects.
        worst_case_ceiling = fund_limit * (1 + VAT_RATE) * (1 + REVISION_DELTA_RANGE[0])
        proj_info.append((row["kodi_projekti"], open_dt, worst_case_ceiling))
    proj_info.sort(key=lambda t: t[1])  # ascending publication date

    pool = app_realizations.dropna(subset=["procurement_date"]).sort_values("procurement_date")
    pool_dates = pool["procurement_date"].tolist()
    pool_rows = pool.to_dict("records")

    import bisect
    used = [False] * len(pool_rows)
    pairs = []
    for kodi_projekti, open_dt, ceiling in proj_info:
        threshold = open_dt + timedelta(days=MIN_PUBLICATION_TO_AWARD_GAP_DAYS)
        start = bisect.bisect_left(pool_dates, threshold)
        match_idx = None
        for idx in range(start, min(start + VALUE_MATCH_SCAN_WINDOW, len(pool_rows))):
            if used[idx]:
                continue
            if pool_rows[idx]["contract_value"] <= ceiling:
                match_idx = idx
                break
        if match_idx is None:
            continue  # no chronologically- and financially-plausible contract left
        used[match_idx] = True
        pairs.append((kodi_projekti, pool_rows[match_idx]))
    return pairs


def build_sifq_chain(projects_df, obp_df, app_notices, app_realizations, furnitor_df):
    # Only real, procured projects (i.e. present in obp_df, meaning fund_limit >= threshold
    # AND published) are eligible to receive a sampled real contract - a never-procured
    # project can't have a commitment, and a real procedure below the OBP threshold isn't
    # given a purchase-request/transaction number either, matching the spec.
    pairs = match_projects_to_realizations(obp_df, app_notices, app_realizations)
    print(f"  chronologically-plausible project<->contract pairs: {len(pairs)} "
          f"(of {len(obp_df)} eligible projects, {len(app_realizations)} real contracts)")

    kodi_projekti_to_ref_no = dict(zip(obp_df["kodi_projekti"], obp_df["numri_procedures_prokurimit"]))
    proj_lookup = projects_df.set_index("kodi_projekti")
    nipt_to_numri_furnitori = dict(zip(furnitor_df["nipt"], furnitor_df["numri_furnitorit"]))

    angazhime, dokumente, faturat, pagesat, truth_rows = [], [], [], [], []
    kid = aid = fid = pid_ = did = 1

    for kodi_projekti, real in pairs:
        proj = proj_lookup.loc[kodi_projekti]
        signing_proxy = real["procurement_date"]  # best available real proxy - see module docstring

        # kerkese_blerje (PR) - UDHEZ: a PO cannot be registered without an approved PR;
        # not generated as its own output table (no KPI ties it - see module docstring),
        # but a numri_kerkeses is still needed as angazhim_buxhetor's mandatory FK.
        numri_kerkeses = f"{proj['kodi_institucioni']}-{signing_proxy.year}-{kid:06d}"
        kid += 1

        numri_angazhimit = f"ANG-{aid:07d}"
        id_dokumenti = f"DOC-{did:07d}"
        aid += 1
        did += 1
        has_contract_number = rng.random() >= P_MISSING_CONTRACT_NUMBER
        numri_kontrates = f"KontratëNr-{aid:07d}" if has_contract_number else pd.NA

        dokumente.append({"id_dokumenti_financiar": id_dokumenti, "statusi": "regjistruar"})

        angazhime.append({
            "numri_angazhimit": numri_angazhimit,
            "numri_kerkeses_blerje": numri_kerkeses,
            "numri_kontrates": numri_kontrates,
            "lloji_ub": rng.choice(["Standarte", "e_Planifikuar"], p=[0.7, 0.3]),
            "blerësi": f"Blerës {rng.integers(1, 200)}",
            "data_krijimit": clip_to_today(pd.Timestamp(signing_proxy)),
            "statusi": "Aprovuar",
            "kodi_projekti": kodi_projekti,
            "kodi_llogarie_ekonomike": proj["kodi_llogarie_ekonomike"],
            "kodi_institucioni": proj["kodi_institucioni"],
            "nipt_perfituesit": real["winner_nipt"],
            "vlera_angazhuar": real["contract_value"],
            "statusi_aprovuar": "Po",
            "periudha_muaji": signing_proxy.month,
            "periudha_viti": signing_proxy.year,
            "kodi_ministrie_linje": rng.choice(MINISTRITE),
            "kodi_kapitulli": rng.choice(KAPITUJT),
            "kodi_programi": pd.NA,
            "kodi_entitet_qeverises": rng.choice(ENTITETE_QEVERISESE),
            "kodi_thesar_dege": rng.choice(DEGET_THESARIT),
            "kodi_tip_buxheti": rng.choice(TIPE_BUXHETI),
        })

        contract_type = sample_real_procedure_type(app_notices, kodi_projekti_to_ref_no, kodi_projekti)
        lloj_fature = CONTRACT_TYPE_TO_LLOJ_FATURE.get(contract_type, rng.choice(["mall", "sherbim", "pune"]))

        n_inv = int(rng.integers(N_INVOICES_PER_COMMITMENT[0], N_INVOICES_PER_COMMITMENT[1] + 1))
        remaining_value = float(real["contract_value"])
        splits = rng.dirichlet(np.ones(n_inv)) * remaining_value

        cursor = pd.Timestamp(signing_proxy) + timedelta(days=int(rng.integers(5, 20)))
        for k in range(n_inv):
            if cursor.date() > TODAY:
                break
            numri_fatures = f"FAT-{fid:07d}"
            numri_kuponi = f"{proj['kodi_institucioni']}-{cursor.year % 100:02d}{fid:05d}"
            fid += 1
            nivf = f"NIVF-{rng.integers(10**9, 10**10 - 1)}"
            data_fatures = clip_to_today(cursor)
            data_mberritjes = clip_to_today(data_fatures + timedelta(days=int(rng.integers(0, 5))))
            rejected = rng.random() < P_INVOICE_REJECTED
            statusi = "refuzuar" if rejected else "pranuar"
            data_ndryshimit = clip_to_today(data_mberritjes + timedelta(days=int(rng.integers(1, 10))))
            vlera_fatures = round(float(splits[k]), 2)

            faturat.append({
                "numri_fatures": numri_fatures,
                "numri_kuponi": numri_kuponi,
                "numri_angazhimit": numri_angazhimit,
                "eshte_e_lidhur_me_kontrate": True,  # this generator only produces PO-matched invoices
                "nivf_nslf": nivf,
                "data_fatures": data_fatures,
                "data_mberritjes_regjistrimit": data_mberritjes,
                "vlera_fatures": vlera_fatures,
                "statusi": statusi,
                "statusi_real_i_sistemit": "Kerkon_Rivleftesim" if rejected else "E_Vleftesuar",
                "statusi_miratimit": "Refuzuar" if rejected else "Miratuar",
                "kontabilizuar": "Jo" if rejected else "Pjesshem",  # upgraded to "Po" below once paid
                "statusi_rezervimit_planit_thesarit": pd.NA if rejected else "R_Kaloi",
                "data_ndryshimit_statusit": data_ndryshimit,
                "arsyeja_refuzimit": rng.choice(REJECTION_REASONS) if rejected else pd.NA,
                "furnitor_nipt": real["winner_nipt"],
                "numri_furnitorit": nipt_to_numri_furnitori.get(real["winner_nipt"]),
                "kodi_lloj_fature": lloj_fature,
                "kushtet_pageses_dite": LEGAL_PAYMENT_DAYS,
            })

            payment_row = None
            if not rejected:
                order_date = clip_to_today(data_ndryshimit + timedelta(days=int(rng.integers(1, 8))))
                late = rng.random() < P_PAYMENT_LATE
                if late:
                    exec_date = data_fatures + timedelta(days=int(rng.integers(LEGAL_PAYMENT_DAYS + 1, LEGAL_PAYMENT_DAYS + 45)))
                else:
                    exec_date = data_fatures + timedelta(days=int(rng.integers(1, LEGAL_PAYMENT_DAYS)))
                exec_date = clip_to_today(max(exec_date, order_date))
                numri_urdher = f"URDH-{pid_:07d}"
                pid_ += 1
                faturat[-1]["kontabilizuar"] = "Po"  # accrual + cash both posted once paid, per UDHEZ
                payment_row = {
                    "numri_urdherit_shpenzimit": numri_urdher,
                    "numri_fatures": numri_fatures,
                    "menyra_pageses": "Elektronike",
                    "numri_dokumentit_pageses": f"DOK-{pid_:07d}",
                    "data_urdherit_shpenzimit": order_date,
                    "data_ekzekutimit_pageses": exec_date,
                    "vlera_paguar_faktikisht": vlera_fatures,
                    "anulluar": False,
                    "afati_aplikueshem_dite": LEGAL_PAYMENT_DAYS,
                }
                pagesat.append(payment_row)

            truth_rows.append({
                "kodi_projekti": kodi_projekti,
                "real_ref_no": kodi_projekti_to_ref_no.get(kodi_projekti),
                "numri_angazhimit": numri_angazhimit,
                "numri_kontrates": numri_kontrates,
                "real_winner_nipt": real["winner_nipt"],
                "real_contract_value": real["contract_value"],
                "numri_fatures": numri_fatures,
                "fature_statusi": statusi,
                "numri_urdherit_shpenzimit": payment_row["numri_urdherit_shpenzimit"] if payment_row else pd.NA,
                "contract_link_is_real_match": False,
            })
            cursor = data_fatures + timedelta(days=int(rng.integers(20, 60)))

    return (
        pd.DataFrame(dokumente), pd.DataFrame(angazhime), pd.DataFrame(faturat),
        pd.DataFrame(pagesat), pd.DataFrame(truth_rows),
    )


def build_truth_links(projects_df, obp_df, angazhime_df, chain_truth_df):
    base = projects_df[["kodi_projekti"]].merge(
        obp_df[["kodi_projekti", "referenca_kerkeses_obp", "numri_procedures_prokurimit"]],
        on="kodi_projekti", how="left")
    invoiced_projects = set(chain_truth_df["kodi_projekti"]) if len(chain_truth_df) else set()
    committed_projects = set(angazhime_df["kodi_projekti"]) if len(angazhime_df) else set()
    base["chain_status"] = np.select(
        [
            base["kodi_projekti"].isin(invoiced_projects),
            base["kodi_projekti"].isin(committed_projects),
            base["referenca_kerkeses_obp"].notna(),
        ],
        ["procured_and_contracted", "contracted_no_invoices_yet", "procured_no_contract"],
        default="never_procured",
    )

    # commitment-level detail (present for every committed project, even the ~32 with zero
    # invoices yet - not just the ones that made it into the invoice-grain chain_truth_df)
    if len(angazhime_df):
        commitment_detail = angazhime_df[
            ["kodi_projekti", "numri_angazhimit", "numri_kontrates", "nipt_perfituesit", "vlera_angazhuar"]
        ].rename(columns={"nipt_perfituesit": "real_winner_nipt", "vlera_angazhuar": "real_contract_value"})
        base = base.merge(commitment_detail, on="kodi_projekti", how="left")
    else:
        for c in ["numri_angazhimit", "numri_kontrates", "real_winner_nipt", "real_contract_value"]:
            base[c] = pd.NA

    if len(chain_truth_df):
        invoice_detail = chain_truth_df[
            ["kodi_projekti", "numri_fatures", "fature_statusi", "numri_urdherit_shpenzimit",
             "contract_link_is_real_match"]
        ]
        merged = base.merge(invoice_detail, on="kodi_projekti", how="left")
    else:
        merged = base
        for c in ["numri_fatures", "fature_statusi", "numri_urdherit_shpenzimit", "contract_link_is_real_match"]:
            merged[c] = pd.NA
    merged["contract_link_is_real_match"] = merged["contract_link_is_real_match"].where(
        merged["numri_angazhimit"].isna(), False)
    merged = merged.rename(columns={"numri_procedures_prokurimit": "real_ref_no"})
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    afmis_schema = load_schema("afmis")
    sifq_schema = load_schema("sifq")

    print("Loading real data...")
    app_notices, kpp_appeal, app_realizations = load_real_data()
    print(f"  app_notices: {len(app_notices)}, kpp_appeal: {len(kpp_appeal)}, "
          f"app_realizations: {len(app_realizations)}")

    print("\nAFMIS: institucioni")
    institucioni_df, institucion_mapping = build_institucioni(app_notices, kpp_appeal, app_realizations)

    print("\nAFMIS: projekt_investimi / vlera_buxhetore_projekti / kerkesa_obp")
    projects_df, budget_df, obp_df = build_afmis_projects(app_notices, institucion_mapping)
    projects_df, budget_df = add_never_procured_projects(projects_df, budget_df, institucioni_df, NEVER_PROCURED_RATE)

    print("\nSIFQ: furnitor")
    furnitor_df = build_furnitor(app_realizations)

    print("\nSIFQ: angazhim_buxhetor / dokument_shpenzimi / fature / pagese")
    dokumente_df, angazhime_df, faturat_df, pagesat_df, chain_truth_df = build_sifq_chain(
        projects_df, obp_df, app_notices, app_realizations, furnitor_df)
    print(f"  contracts sampled: {angazhime_df['numri_angazhimit'].nunique() if len(angazhime_df) else 0}")

    # post-hoc: fill vlera_disbursuar on vlera_buxhetore_projekti from actual payments
    if len(pagesat_df) and len(faturat_df) and len(angazhime_df):
        pay_by_commitment = (
            faturat_df.merge(pagesat_df, on="numri_fatures", how="inner")
            .merge(angazhime_df[["numri_angazhimit", "kodi_projekti"]], on="numri_angazhimit", how="left")
            .groupby("kodi_projekti")["vlera_paguar_faktikisht"].sum()
        )
        budget_df = budget_df.set_index("kodi_projekti")
        budget_df.loc[pay_by_commitment.index, "vlera_disbursuar"] = pay_by_commitment.values
        budget_df = budget_df.reset_index()

    print("\nValidating against approved schema and writing output...")
    write_validated(institucioni_df, "afmis", "institucioni", afmis_schema)
    write_validated(projects_df, "afmis", "projekt_investimi", afmis_schema)
    write_validated(budget_df, "afmis", "vlera_buxhetore_projekti", afmis_schema)
    write_validated(obp_df, "afmis", "kerkesa_obp", afmis_schema)

    write_validated(dokumente_df, "sifq", "dokument_shpenzimi", sifq_schema)
    write_validated(furnitor_df, "sifq", "furnitor", sifq_schema)
    write_validated(angazhime_df, "sifq", "angazhim_buxhetor", sifq_schema)
    write_validated(faturat_df, "sifq", "fature", sifq_schema)
    write_validated(pagesat_df, "sifq", "pagese", sifq_schema)

    # Non-schema support artifacts (clearly named, not presented as approved-schema tables)
    (OUT / "afmis").mkdir(parents=True, exist_ok=True)
    institucion_mapping.to_csv(OUT / "afmis" / "_institucion_nipt_mapping.csv", index=False, encoding="utf-8-sig")
    print(f"  afmis/_institucion_nipt_mapping.csv: {len(institucion_mapping)} rows (support artifact, not a schema entity)")

    truth_links = build_truth_links(projects_df, obp_df, angazhime_df, chain_truth_df)
    truth_links.to_csv(OUT / "_truth_links.csv", index=False, encoding="utf-8-sig")
    print(f"  _truth_links.csv: {len(truth_links)} rows")
    print(truth_links["chain_status"].value_counts().to_string())

    print("\nDone.")


if __name__ == "__main__":
    main()
