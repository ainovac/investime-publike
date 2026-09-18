# SIFQ — Struktura Logjike e të Dhënave

Companion i lexueshëm i `schema/sifq/sifq_schema.yaml` (citime të plota burimore aty). Ky
dokument mbulon VETËM SIFQ — AFMIS trajtohet veçmas te `struktura_afmis.md` (rregulli 4).

Burimet e lejuara:
- **PDF** — `Struktura_te_Dhenave_AFMIS_SIFQ.pdf`, §3
- **XLSX** — `Investime_Publike_Specifikim_te_dhenash_per_ekstraktim_v1.xlsx`, fleta `07_SIFQ_Thesar`
- **KPI** — `KPI (komente)- Menaxhimi i investimeve publike (1).docx`
- **INTEGR** — `Manual_teknik_Integrimi_i_SPE_me_AFMIS.pdf` ("Manual Teknik — Integrimi i
  Sistemit të Prokurimit Elektronik me AFMIS", 13 faqe) — ecuria reale e krijimit të dosjes
  së tenderit në SPE, e para nga fillimi
- **UDHEZ** — `Udhezuesi i Perdoruesit per BI Qendror formatuar.doc.pdf` (263 faqe) +
  `Moduli Buxhetit, i UB dhe te Pagueshmeve.docx` (22 tabela reale fushash) — i njëjti
  dokument burimor ("Udhëzuesi i Përdoruesit — Sistemi Informatik Financiar i Qeverisë"),
  dy formate; docx-ja citohet për fusha (tabelat ekstraktohen saktë), PDF-ja për prozë

Statusi: **CONFIRMED_LOGICAL** / **ASSUMED** — njësoj si te `struktura_afmis.md`.
**97 fusha gjithsej: 95 CONFIRMED_LOGICAL, 2 ASSUMED.**

---

## ⚠ Gjetje e rëndësishme: kufiri AFMIS/SIFQ mund të mos jetë aq i qartë sa modeli ynë

Dokumenti PDF fillestar (§2) thotë shprehimisht se AFMIS emërtohet ligjërisht "SIMF" dhe
është sistem i ndarë nga SIFQ. Por **UDHEZ — titulluar vetë "Sistemi Informatik Financiar i
Qeverisë" (pra SIFQ) — dokumenton një MODUL TË PLOTË BUXHETOR** ("Detajimi Fillestar i
Buxhetit", "Rishikimi i Buxhetit") — funksione që ky projekt ia kishte atribuar tërësisht
AFMIS-it. INTEGR gjithashtu i referohet vazhdimisht institucioneve që aksesojnë "sistemin
SIMF **dhe** SIFQ" së bashku, nëpërmjet të njëjtit Web Portal, sikur të ishin çift i lidhur
ngushtë, jo dy sisteme plotësisht të pavarura.

Kjo ngre mundësinë reale që AFMIS/SIMF dhe SIFQ të jenë shumë më të lidhura (ose madje e
njëjta platformë Oracle EBS nën dy emra) sesa supozon modeli ynë logjik i ndarë. **Rregulli
4 (mos i bashko kurrë) vazhdon të zbatohet këtu** — entitetet e reja buxhetore (p.sh.
`rishikim_buxhetor`) janë vendosur te SIFQ specifikisht sepse aty i gjetëm, jo sepse jemi të
sigurt se aty i përkasin. Kjo është zgjedhje modelimi nën pasiguri reale, jo fakt i zgjidhur
— duhet konfirmuar nga zotëruesit e sistemit para se kufiri AFMIS/SIFQ të trajtohet si i
qëndrueshëm.

---

## Platforma: Oracle E-Business Suite (konfirmuar)

UDHEZ e emërton shprehimisht platformën: "Oracle", "Flexfield", përgjegjësi si "GoA
[institucion] PO Commitments". Plani i Llogarive është një **Accounting Flexfield me 12
segmente**: Entiteti Qeverisës, Ministria e Linjës, Institucioni (=Njësia Shpenzuese),
Kapitulli, Programi/Funksioni, Llogaria Ekonomike, Nën-Llogaria, Zyra e Thesarit (TDO),
Projekti — plus 3 segmente të tjera që nuk u lexuan brenda fushëveprimit të kësaj sesioni.

**Formate reale kodesh, me shembuj konkretë** (UDHEZ docx Tabela 1, PDF f.7-10):

| Fusha | Format | Shembull |
|---|---|---|
| `kodi_institucioni` | 7 shifra: {1=Qendrore/2=Lokale}{3-shifror ministri/ent lokal}{3-shifror sekuencial njësi shpenzuese} | `1011001` (Ministria e Arsimit, NJQ 1); `2101001` (Bashkia Tiranë, NJQ 1) |
| `kodi_projekti` | 7 karaktere: {G=Grant / K ose L=Kredi (burimet nuk pajtohen për këtë shkronjë — shih pyetjet e hapura) / pa prefiks për projekte të brendshme}{3-shifror kod ministrie/enti lokal}{3-4 shifror sekuencial} | `GM11001` |
| `numri_kerkeses` (PR) | Kodi i Institucionit Buxhetor - Viti Aktual - Numër rendor | — |
| `numri_kuponi` (faturë) | {kodi_institucioni}-{VV}{numër rendor} | `1003001-1200025` |

---

## Entitetet dhe grain-i

| Entiteti | Grain (një rresht = ...) | Burimi kryesor |
|---|---|---|
| `kerkese_blerje` | një kërkesë blerje (PR) | UDHEZ — **e re këtë sesion** |
| `angazhim_buxhetor` | një kontratë/urdhër blerje (PO) | XLSX + PDF §3.5, tani i pasuruar nga UDHEZ |
| `leshimi` | një lëshim/skedulim dorëzimi kundrejt një PO-je | UDHEZ — **e re këtë sesion** |
| `fature` | një faturë | PDF §3.5 + XLSX, tani shumë i pasuruar nga UDHEZ |
| `pagese` | një pagesë | PDF §3.5 + XLSX + UDHEZ |
| `dokument_shpenzimi` | një dokument shpenzimi (vetëm PDF) | PDF §3.5 |
| `furnitor` | një furnitor (sipas NIPT) | PDF §3.3, tani i pasuruar nga UDHEZ |
| `rishikim_buxhetor` | një transaksion rishikimi buxhetor | UDHEZ — **e re këtë sesion** |

### Cikli i jetës i vërtetuar (PR → PO → Lëshim → Faturë → Pagesë)

UDHEZ konfirmon një zinxhir shumë më të saktë se sa e kishim modeluar:

1. **Kërkesa për Blerje (PR)** — momenti i identifikimit të nevojës; furnitori ende i
   panjohur; fondet rezervohen ("ngurtësohen") kundrejt buxhetit vjetor.
2. **Urdhëri i Blerjes/Kontrata (PO)** — momenti i kontraktimit; **DUHET të regjistrohet
   kundrejt një PR ekzistuese dhe të aprovuar — sistemi refuzon regjistrimin e një PO pa PR
   përkatëse.** "Një Kontratë mund të lidhet vetëm me një Kërkesë për Blerje. Nga e njëjta
   kërkesë, mund të krijohen disa Kontrata/PO" → **1 PR : shumë PO, jo 1:1.**
3. **Lëshimi** — skedulimi/marrja në dorëzim, për kontrata me shumë faza.
4. **Fatura** — kërkesa për pagesë; DY LLOJE: e lidhur me PO (investime, shpenzime
   operative) ose e palidhur (rroga, utilitete).
5. **Pagesa** — ekzekutimi real nga Thesari.

**Rregulla vlefshmërie REALE, të verifikuara (jo hamendësime tona):**
- "Sasitë dhe çmimi për njësi i Kontratës/UB nuk mund të tejkalohet nga sasitë dhe çmimi i
  faturës" — vlera e faturës kontrollohet automatikisht kundrejt PO-së.
- "Data e Faturës nuk mund të jetë më e hershme se sa data e kontratës."
- "Shuma e kontratës/PO kontrollohet automatikisht në sistem kundrejt vlerës së PR."
- Furnitorët regjistrohen **në mënyrë të centralizuar vetëm nga Thesari** — institucionet
  nuk mund të krijojnë/ndryshojnë furnitorë vetë.
- Zinxhiri i miratimit është **i njëjtë në PR, PO dhe Faturë**: Specialisti IB (rezervim
  fondesh) → Nëpunësi Zbatues (niveli 1) → Nëpunësi Autorizues (niveli 2) → Përgjegjësi i
  Thesarit (kontrolli final i klasifikimit buxhetor).
- **Dy faza validimi të ndara** për faturat: (1) buxheti vjetor, në regjistrim; (2) plani i
  thesarit (likuiditet), në momentin e pagesës — një proces automatik ditor i veçantë me
  status D=Dështoi / R=Kaloi.

---

## Çelësat

| Lidhja | Fusha(t) | Statusi | Burimi |
|---|---|---|---|
| **SIFQ ↔ AFMIS** | çelës i përbërë: `periudha_viti + kodi_institucioni + kodi_programi + kodi_projekti + kodi_llogarie_ekonomike` | Konceptual, JO PK teknik (rregulli 5). UDHEZ rrit besueshmërinë e FORMATIT (kodi_projekti/kodi_institucioni janë segmente reale Flexfield me format konkret), por NUK jep të dhëna reale AFMIS për verifikim | PDF §3.9, §4.1; XLSX; UDHEZ |
| **SIFQ ↔ SPE** (`numri_transaksionit`) | `numri_transaksionit` | **NGRITUR** nga "e pakonfirmuar" në "aktivisht e validuar në prodhim" — INTEGR tregon rrjedhën reale të UI-t: SPE refuzon vlerën nëse statusi SIMF/SIFQ s'është "Aprovuar", me mesazhe gabimi konkrete | INTEGR f.10-13 |
| SIFQ ↔ SMK/SPE | `numri_kontrates` | E propozuar, PLOTËSIMI I PAKONFIRMUAR | XLSX |
| SIFQ ↔ universal | `nipt_perfituesit` / `furnitor.nipt` | E propozuar, PLOTËSIMI I PAKONFIRMUAR | XLSX |

**Vëmendje kritike — grain-et janë të ndryshme (pa ndryshim nga më parë):** SIFQ është
transaksion-grain; AFMIS është buxhet-linjë-grain. Kërkon agregim, jo JOIN 1-me-1.

---

## Boshllëqe (Gaps)

1. **Kufiri real AFMIS/SIFQ** — shih gjetjen e re në krye të dokumentit.
2. **Struktura fizike, ERD, layout i skedarëve `.txt`** — ende e pakonfirmuar (PDF §3.9).
3. **Cila datë fillon afatin 30-ditor të Ligjit 48/2016**: `fature.data_fatures` apo
   `fature.data_mberritjes_regjistrimit`? UDHEZ NUK e zgjidh këtë — konfirmon vetëm një
   rregull tjetër (fatura nuk mund të jetë para kontratës).
4. **`dokument_shpenzimi` vs `angazhim_buxhetor`** — ende e paqartë nëse janë i njëjti
   entitet apo dy hapa të veçantë (shih më poshtë, pyetja #2).
5. **Lidhja SIFQ↔SMK** — ende "e parealizuar" (PDF §3.9); SMK jashtë fushëveprimit.
6. **AFMIS përfshin TVSH, SIFQ/SPE jo** (pa ndryshim).
7. **`fature.statusi` (pranuar/refuzuar) kundrejt statusit real 3-dimensional** — UDHEZ
   tregon që sistemi real ka `statusi_real_i_sistemit` + `statusi_miratimit` +
   `kontabilizuar` të ndarë, ku "Refuzuar" jeton te `statusi_miratimit`, jo te `statusi`.
   Të dyja janë ruajtur, jo bashkuar — shih `open_question` te skema.
8. **`fature.kushtet_pageses_dite` kundrejt `pagese.afati_aplikueshem_dite`** — dy burime
   (UDHEZ, XLSX) e vendosin të njëjtin koncept (ditët e afatit të pagesës) te entitete të
   ndryshme. Të dyja u ruajtën, me referencë të kryqëzuar, në vend që të zgjidhej njëra.
9. **Shkronja e kategorisë "Kredi" në `kodi_projekti`** — UDHEZ PDF (f.9) thotë 'K', por
   UDHEZ docx Tabela 1 tregon 'L' në shembujt konkretë. Burim i vetëm, kontradiktë e
   brendshme — nuk u zgjodh njëra anë.

## Pyetje të hapura për pronarët e sistemit (ADS/AKSHI/MFE/Thesari)

1. **A janë AFMIS/SIMF dhe SIFQ dy sisteme vërtet të ndara, apo e njëjta platformë Oracle
   EBS e aksesuar nën dy emra/role?** (gjetja kryesore e re e këtij sesioni)
2. `fature.data_fatures` apo `data_mberritjes_regjistrimit` — cila e nis afatin 30-ditor?
3. A janë `dokument_shpenzimi` (PDF) dhe `angazhim_buxhetor`/`kerkese_blerje` (UDHEZ) i
   njëjti hap i ciklit me emra të ndryshëm, apo diçka tjetër krejtësisht?
4. A ruhet realisht `numri_kontrates` në SIFQ si fushë e mbushur?
5. 'K' apo 'L' për kategorinë "Kredi" të `kodi_projekti` — cila është e sakta?
6. A përdor AFMIS të njëjtin format kodesh (`kodi_institucioni` 7-shifror,
   `kodi_projekti` 7-karakterësh) të konfirmuar këtu për SIFQ, apo një skemë tjetër
   kodifikimi krejtësisht të vetën?
