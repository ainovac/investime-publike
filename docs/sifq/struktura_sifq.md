# SIFQ — Struktura Logjike e të Dhënave

Companion i lexueshëm i `schema/sifq/sifq_schema.yaml` (citime të plota burimore aty). Ky
dokument mbulon VETËM SIFQ — AFMIS trajtohet veçmas te `struktura_afmis.md` (rregulli 4).

Burimet e lejuara:
- **PDF** = `Struktura_te_Dhenave_AFMIS_SIFQ.pdf`, §3
- **XLSX** = `Investime_Publike_Specifikim_te_dhenash_per_ekstraktim_v1.xlsx`, fleta `07_SIFQ_Thesar`
- **KPI** = `KPI (komente)- Menaxhimi i investimeve publike (1).docx`

Statusi: **CONFIRMED_LOGICAL** / **ASSUMED** — njësoj si te `struktura_afmis.md`.

---

## Entitetet dhe grain-i

| Entiteti | Grain (një rresht = ...) | Burimi kryesor |
|---|---|---|
| `angazhim_buxhetor` | një angazhim/rezervim fondesh | PDF §3.5 + XLSX 07_SIFQ_Thesar r.1-6 |
| `fature` | një faturë | PDF §3.5 + XLSX 07_SIFQ_Thesar r.7-14 |
| `pagese` | një urdhër shpenzimi/pagesë | PDF §3.5 + XLSX 07_SIFQ_Thesar r.15-19 |
| `dokument_shpenzimi` | një dokument shpenzimi (vetëm PDF; XLSX nuk e emërton veçmas) | PDF §3.5 |
| `furnitor` | një furnitor (sipas NIPT) | PDF §3.3 |

**40 fusha gjithsej: 39 CONFIRMED_LOGICAL, 1 ASSUMED** (`furnitor.emertimi` — PDF emërton
vetëm NIPT-in si identifikues, emri i furnitorit është shtesë strukturore e domosdoshme).

**Cikli i jetës (statuset, PDF §3.5):**
1. Regjistrimi i faturës/dokumentit të shpenzimit
2. Vlefshmëria dhe miratimi (pranuar / refuzuar)
3. Angazhimi / rezervimi i fondeve
4. Ekzekutimi i pagesës (urdhër-shpenzim)
5. Disbursimi real (data e pagesës)

---

## Çelësat

| Lidhja | Fusha(t) | Statusi | Burimi |
|---|---|---|---|
| **SIFQ ↔ AFMIS** | **çelës i përbërë**: `periudha_viti + kodi_institucioni + kodi_programi + kodi_projekti + kodi_llogarie_ekonomike` | Konceptual, JO PK teknik (rregulli 5) | PDF §3.9, §4.1; XLSX 07_SIFQ_Thesar r.3.0; XLSX 09_Celesat r.7.0 |
| SIFQ ↔ SMK/SPE | `numri_kontrates` | E propozuar, PLOTËSIMI I PAKONFIRMUAR | XLSX 07_SIFQ_Thesar r.2.0; XLSX 09_Celesat r.6.0 |
| SIFQ ↔ universal (DPT, AKPA, SPE) | `nipt_perfituesit` / `furnitor.nipt` | E propozuar, PLOTËSIMI I PAKONFIRMUAR | XLSX 09_Celesat r.9.0 "NIPT — i pranishëm në SPE, SMK, SIFQ, DPT, AKPA" |

**Vëmendje kritike (rregulli 5) — grain-et janë të ndryshme:** SIFQ është në granularitet
**transaksion** (një `angazhim_buxhetor` / `fature` / `pagese` për çdo veprim financiar);
AFMIS është në granularitet **buxhet-linjë** (një rresht për projekt × vit). Prandaj:

```
SIFQ.angazhim_buxhetor  (shumë rreshta për projekt × vit)
        │  GROUP BY kodi_projekti, periudha_viti, kodi_llogarie_ekonomike
        ▼
   një total i agreguar
        │  krahasohet me
        ▼
AFMIS.vlera_buxhetore_projekti  (një rresht për projekt × vit)
```

Ky NUK është një JOIN 1-me-1 mbi çelësin e përbërë — është 1-me-shumë, dhe kërkon agregim
paraprak. Çdo pipeline/testi që supozon 1-me-1 do të japë rezultate të gabuara.

---

## Boshllëqe (Gaps)

1. **Struktura fizike, ERD, layout i skedarëve `.txt`** — plotësisht e pakonfirmuar
   (PDF §3.9). Nuk modelohet këtu (do të ishte hamendësim).
2. **Cila datë fillon afatin 30-ditor të Ligjit 48/2016**: `fature.data_fatures` apo
   `fature.data_mberritjes_regjistrimit`? XLSX 07_SIFQ_Thesar r.10.0 e thotë shprehimisht
   të papërcaktuar: "duhet konfirmuar cila përdoret".
3. **`dokument_shpenzimi` vs `angazhim_buxhetor`** — PDF i trajton si dy entitete të
   ndryshme në cikël (dokumenti është regjistrimi fillestar, angazhimi është rezervimi i
   fondeve), por XLSX 07_SIFQ_Thesar nuk e përmend fare "dokumentin e shpenzimit" si
   entitet të veçantë — e trajton `angazhim_buxhetor` si rekordin kryesor transaksional.
   Të dyja modelohen (asnjë nuk hiqet), por raporti mes tyre (1-me-1? njëri zëvendëson
   tjetrin?) NUK është i qartë nga burimet.
4. **Lidhja SIFQ↔SMK** — PDF §3.9 e quan shprehimisht "e parealizuar": "statusi i faturës
   (pranuar/refuzuar) merret nga SIFQ, por vlera e kontratës nga SMK, pa lidhje automatike".
   SMK vetë NUK është dokumentuar këtu (jashtë fushëveprimit të PDF/XLSX-it të lejuar).
5. **AFMIS përfshin TVSH, SIFQ/SPE jo** (PDF §3.9) — çdo krahasim numerik SIFQ↔AFMIS
   kërkon trajtim të TVSH-së, siç shënohet edhe te `struktura_afmis.md`.

## Pyetje të hapura për pronarët e sistemit (ADS/AKSHI/MFE/Thesari)

1. `fature.data_fatures` apo `data_mberritjes_regjistrimit` — cila e nis afatin ligjor
   30-ditor? (shih Boshllëqe #2, kërkesë e drejtpërdrejtë nga XLSX vetë)
2. A janë `dokument_shpenzimi` (PDF) dhe `angazhim_buxhetor` (XLSX) i njëjti entitet me
   emra të ndryshëm, apo dy hapa të veçantë të ciklit? (Boshllëqe #3)
3. A ruhet realisht `numri_kontrates` në SIFQ si fushë e mbushur, apo është vetëm një
   referencë e pritshme/teorike drejt SMK?
4. Cili është formati real i `nivf_nslf` (identifikuesit e fiskalizimit) — a mund të
   përdoret si çelës shtesë drejt APP/KPP, apo është krejtësisht i pavarur prej tyre?
