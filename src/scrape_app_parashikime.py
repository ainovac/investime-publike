"""
Scraper for APP's "Regjistri i Parashikimeve" (annual procurement forecast/plan register):
https://www.app.gov.al/regjistri-i-parashikimeve/

Same site/pattern as scrape_app_realizations.py (identical HTML structure, confirmed by
inspection) - this register is the PRE-tender planning stage: same fields as Realizimeve
minus winner/contract-value/award-date (which only exist once a procedure concludes). Like
Realizimeve, it has NO ref_no/notification_no field, so it is kept as its own independent
real dataset, not force-joined to app_notices/kpp_appeal.

Usage:
    pip install requests beautifulsoup4 lxml pandas
    python scrape_app_parashikime.py                  # walk all pages
    python scrape_app_parashikime.py --max-pages 5     # quick test
"""
import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://www.app.gov.al"
URL = f"{BASE}/regjistri-i-parashikimeve/"

HEADERS = {
    "User-Agent": "I4A-public-investment-pilot/0.1",
    "Referer": URL,
    "Origin": BASE,
}

REQUEST_TIMEOUT = 45

RENAME = {
    "Autoriteti Kontraktues": "contracting_authority",
    "Burimi i financimit": "funding_source",
    "Fondi limit": "fund_limit_raw",
    "Data e publikimit": "publication_date",
    "Data e publikimit Ora": "publication_time",
    "Viti": "year",
    "Koha e zhvillimit": "execution_period",
    "Kodi CPV": "cpv_code_raw",
    "Tipi i Proçedurës": "procedure_type",
    "Anulluar": "cancelled_raw",
}

YES_NO = {"Po": True, "Jo": False}


def make_session():
    s = requests.Session()
    retry = Retry(
        total=5, connect=5, read=5, backoff_factor=2,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def parse_records(soup):
    items = soup.select("div.list-group-item.list-group-item-result")
    rows = []
    for it in items:
        strong = it.find("strong")
        subject = None
        if strong and strong.parent:
            full = strong.parent.get_text(" ", strip=True)
            label = strong.get_text(strip=True)
            subject = full[len(label):].strip() if full.startswith(label) else full

        ul = it.select_one("ul.list-inline")
        pairs, last_label = {}, None
        if ul:
            for b in ul.find_all("b"):
                label = b.get_text(strip=True).rstrip(":").strip()
                val_tag = b.find_next_sibling(["span", "small"])
                value = val_tag.get_text(" ", strip=True) if val_tag else None
                if label.lower().startswith("ora") and last_label:
                    label = f"{last_label} Ora"
                else:
                    last_label = label
                pairs[label] = value
        rows.append({"procurement_object": subject, **pairs})
    return rows


def find_next_form(soup):
    pag = soup.select_one("div.pagination-form")
    if not pag:
        return None
    for f in pag.select("form"):
        if f.select_one("button i.fa-angle-right"):
            token = f.find("input", {"name": "__RequestVerificationToken"})
            ufprt = f.find("input", {"name": "ufprt"})
            if not (token and ufprt):
                continue
            return {
                "action": f.get("action"),
                "__RequestVerificationToken": token["value"],
                "ufprt": ufprt["value"],
            }
    return None


def current_page_label(soup):
    m = re.search(r"Faqe\s+(\d+)\s+nga\s+(\d+)", soup.get_text(" ", strip=True))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def save_checkpoint(path, rows):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def extract_all(session, max_pages=None, sleep_s=1.0, checkpoint_path=None, checkpoint_every=50):
    r = session.get(URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    rows, total_pages, page_count = [], None, 0
    while True:
        page_num, total_pages = current_page_label(soup)
        batch = parse_records(soup)
        rows.extend(batch)
        page_count += 1
        print(f"page {page_num}/{total_pages}: {len(batch)} records (cumulative {len(rows)})", flush=True)

        if checkpoint_path and page_count % checkpoint_every == 0:
            save_checkpoint(checkpoint_path, rows)
            print(f"  checkpoint saved ({len(rows)} records) -> {checkpoint_path}", flush=True)

        if max_pages and page_count >= max_pages:
            break
        nxt = find_next_form(soup)
        if not nxt:
            break
        time.sleep(sleep_s)
        body = {"__RequestVerificationToken": nxt["__RequestVerificationToken"], "ufprt": nxt["ufprt"]}
        r = session.post(BASE + nxt["action"], data=body, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
    return rows, total_pages


def clean_money(v):
    if pd.isna(v) or not v:
        return None
    v = v.replace("Lekë", "").replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def transform(rows):
    df = pd.DataFrame(rows).rename(columns=RENAME)
    if "cancelled_raw" in df:
        df["cancelled"] = df["cancelled_raw"].map(YES_NO)
        df.drop(columns=["cancelled_raw"], inplace=True)
    if "fund_limit_raw" in df:
        df["fund_limit"] = df["fund_limit_raw"].map(clean_money)
        df.drop(columns=["fund_limit_raw"], inplace=True)
    if "cpv_code_raw" in df:
        df["cpv_code"] = df["cpv_code_raw"].astype("string").str.strip().str.rstrip(",").str.strip()
        df.drop(columns=["cpv_code_raw"], inplace=True)
    if "publication_date" in df and "publication_time" in df:
        combined = df["publication_date"].fillna("") + " " + df["publication_time"].fillna("")
        df["publication_datetime"] = pd.to_datetime(combined, format="%d-%m-%Y %H:%M", errors="coerce")
        df.drop(columns=["publication_date", "publication_time"], inplace=True)
    df["extracted_at"] = datetime.now(timezone.utc)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--sleep-s", type=float, default=1.0)
    ap.add_argument("--checkpoint-every", type=int, default=50)
    ap.add_argument("--out", default="../data/app")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out / "app_parashikime_checkpoint.json"

    with make_session() as s:
        rows, total_pages = extract_all(
            s, args.max_pages, args.sleep_s,
            checkpoint_path=checkpoint_path, checkpoint_every=args.checkpoint_every)

    df = transform(rows)
    df.to_csv(out / "app_parashikime.csv", index=False, encoding="utf-8-sig")
    checkpoint_path.unlink(missing_ok=True)
    print(f"Saved {len(df)} forecast records (of {total_pages} total pages seen) to {out}/")
