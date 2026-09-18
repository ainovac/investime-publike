# AFMIS — Struktura Logjike e të Dhënave

Companion i lexueshëm i `schema/afmis/afmis_schema.yaml` (aty gjenden citimet e plota burimore
fjalë-për-fjalë për çdo fushë). Ky dokument mbulon VETËM AFMIS. SIFQ trajtohet veçmas te
`struktura_sifq.md` — nuk bashkohen tabela apo entitete mes dy sistemeve (rregulli 4).

Burimet e lejuara:
- **PDF** = `Struktura_te_Dhenave_AFMIS_SIFQ.pdf` (I4A, Shtator 2026)
- **XLSX** = `Investime_Publike_Specifikim_te_dhenash_per_ekstraktim_v1.xlsx`, fleta `02_AFMIS`
- **KPI** = `KPI (komente)- Menaxhimi i investimeve publike (1).docx`

⚠ Të dyja burimet parësore (PDF §1, XLSX fleta `01_Permbledhje`) thonë shprehimisht se
struktura FIZIKE (ERD, emrat e tabelave, endpoint-et API) nuk është konfirmuar zyrtarisht.
Çdo gjë më poshtë është strukturë LOGJIKE.

Statusi i çdo fushe:
- **CONFIRMED_LOGICAL** — emri/koncepti vjen drejtpërdrejt nga një burim
- **ASSUMED** — fushë teknike e domosdoshme (surrogate key, FK, lloj i thjeshtë) që ne e
  kemi shtuar sepse tabela të funksionojë, jo sepse burimi e emërton kështu

---

## Entitetet dhe grain-i

| Entiteti | Grain (një rresht = ...) | Burimi kryesor |
|---|---|---|
| `institucioni` | një institucion buxhetor | PDF §2.3 + XLSX 02_AFMIS r.3-4 |
| `programi_buxhetor` | një program buxhetor | PDF §2.3 + XLSX 02_AFMIS r.7 |
| `projekt_investimi` | një projekt investimi | PDF §2.3 + XLSX 02_AFMIS r.1-8 |
| `vlera_buxhetore_projekti` | projekt × vit fiskal | XLSX 02_AFMIS r.9-14 (grain ndryshe nga `tavan_buxhetor`!) |
| `kerkesa_obp` | një kërkesë e dërguar te OBP | XLSX 02_AFMIS r.15-18 |
| `tavan_buxhetor` | program × vit × lloj (indikativ/i pandryshueshëm) | PDF §2.3 |
| `deklarata_politikes_programit` | një program | PDF §2.3 |
| `tregues_performance` | një tregues brenda një programi | PDF §2.3 + §2.5 |
| `emp_anetar` | (program, përdorues) | PDF §2.3 + §2.5 |
| `roli_perdoruesi` | një rol (5 rreshta fikse) | PDF §2.5 |
| `zeri_ekonomik_230_231` | (zëri 230/231, projekt, vit) | PDF §2.3 |

**Shënim mbi grain-in:** `vlera_buxhetore_projekti` (XLSX, niveli projekt) dhe
`tavan_buxhetor` (PDF, niveli program) përshkruajnë koncepte të lidhura por JO identike —
janë mbajtur si entitete të veçanta sepse burimet i përshkruajnë në granularitete të
ndryshme, jo sepse duam ndarje artificiale.

Fusha të plota, statusi dhe kodet KPI: shih `schema/afmis/afmis_schema.yaml`.
**46 fusha gjithsej: 39 CONFIRMED_LOGICAL, 7 ASSUMED** (asnjë ASSUMED nuk është koncept
biznesi i shpikur — janë vetëm surrogate/FK/vlera teknike të domosdoshme).

---

## Çelësat

**Çelësi primar (logjik) i secilit entitet** — shih kolonën `primary_key` në YAML; të
gjithë janë çelësa logjikë (asnjë PK teknik i konfirmuar, siç thekson PDF §2.7/§3.9).

**Çelësat drejt sistemeve të tjera:**

| Lidhja | Fusha(t) | Statusi | Burimi |
|---|---|---|---|
| AFMIS → OBP | `kodi_projekti` | E propozuar, PLOTËSIMI I PAKONFIRMUAR | XLSX 09_Celesat r.1.0 |
| AFMIS → SPE (direkt) | `kodi_projekti` | E propozuar, nëpërmjet OBP | XLSX 09_Celesat r.3.0 |
| **AFMIS ↔ SIFQ** | **çelës i përbërë**: `viti_fiskal + kodi_institucioni + kodi_programi + kodi_projekti + kodi_llogarie_ekonomike` | Konceptualisht i mbështetur nga PDF/XLSX, POR JO teknikisht i verifikuar si PK (rregulli 5 i kërkesës; PDF §3.9 "no primary key AFMIS/Thesar") | PDF §4.1, §3.9; XLSX 07_SIFQ_Thesar r.3.0; XLSX 09_Celesat r.7.0 |

**Vëmendje kritike (rregulli 5):** AFMIS është në granularitet **buxhet-linjë** (projekt ×
vit), SIFQ është në granularitet **transaksion** (angazhim/faturë/pagesë). Lidhja SIFQ→AFMIS
është shumë-me-një (many SIFQ rows → 1 AFMIS budget-line row), jo një-me-një. Çdo krahasim
numerik (p.sh. shuma e pagesave kundrejt tavanit buxhetor) kërkon `GROUP BY` mbi SIFQ përpara
krahasimit me AFMIS — kjo NUK është modeluar si një JOIN i thjeshtë.

---

## Boshllëqe (Gaps) — fusha të kërkuara nga KPI por PA burim të dokumentuar

Asnjë nga fushat MUST/NICE-TO-HAVE e listuara në `02_AFMIS` mungon pa burim — çdo fushë e
kërkuar aty ka një hyrje përkatëse në schema. Boshllëqet reale janë strukturore, jo fusha:

1. **Struktura fizike (ERD, tabela, API)** — plotësisht e pakonfirmuar (PDF §2.7, §5).
2. **Çelësi teknik AFMIS↔SIFQ** — nuk ekziston (PDF §3.9). Çelësi i përbërë më sipër është
   hipotezë pune, jo fakt i verifikuar.
3. **Fill-rate i çelësave** (`09_Celesat`, kolonat "A ekziston?" / "Sa % e mbushur") — të
   gjitha bosh në XLSX. Nuk dimë ende sa % e rasteve reale kanë `kodi_projekti` të mbushur
   në OBP/SPE.
4. **Marrëdhënia `programi_buxhetor` ↔ `institucioni`** (FK e supozuar 1-shumë) — asnjë
   burim nuk e thotë shprehimisht këtë kardinalitet.

## Pyetje të hapura për pronarët e sistemit (ADS/AKSHI/MFE/Thesari)

1. A është `kodi_projekti` në AFMIS FAKTIKISHT i pranishëm dhe i mbushur në OBP/SPE si
   fushë e ruajtur (jo vetëm konceptualisht i propozuar si çelës)?
2. Cili është formati real i `Numri i procedurës së prokurimit` kur ruhet në AFMIS (r.18
   e `02_AFMIS`) — a përputhet me `REF-xxxxx-...` ose `CN/xxxxx/...` që shohim në
   APP/KPP, apo është një numër tjetër i brendshëm?
3. A ekziston vërtet fusha "Programi buxhetor" si atribut i drejtpërdrejtë i projektit, apo
   projekti lidhet me programin vetëm tërthorazi (nëpërmjet produktit)? PDF §2.3 e vendos
   produktin "brenda programit buxhetor", jo projektin drejtpërdrejt — kjo krijon një
   mospërputhje delikate me XLSX r.7.0 që e liston "Programi buxhetor" si fushë të
   drejtpërdrejtë të projektit.
4. Konfirmim i kardinalitetit `programi_buxhetor` → `institucioni` (shih Boshllëqe #4).
