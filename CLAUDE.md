# Asistent KATASTAR – pravila za rad

- Komunikacija na srpskom, latinicom, bez elementarnih objašnjenja.
- Program (Python 3, tkinter, requests) prati parcele na eKatastru (katastar.rgz.gov.rs/eKatastarPublic). Uvek ostavi ceo, ispravan program koji se pokreće.
- Ako pogrešiš, priznaj i ispravi direktno.

## Gde je kod
- Izvor je `izvor/izvor.py`. `asistent_katastar.py` u glavnom folderu se SASTAVLJA: `cd izvor && python napravi.py` (umeće `opstine.json` i `seme_min.json`). Nikad ne menjaj `asistent_katastar.py` ručno; posle svake izmene `izvor.py` pokreni `napravi.py` i commit-uj oba.
- `izvor/mock_sajt.py` je simulirani eKatastar sa pravim oblicima odgovora (`izvor/fix/`); testovi su `izvor/test_*.py`.

## Kako se radi
- Izmene se prave ovde (Claude Code na GitHub-u). Program na Dejanovom računaru (`C:\Users\LENOVO\Desktop\Asistent_KATASTAR`) pri svakom pokretanju sam uradi `git pull` sa grane `main`, staru verziju sačuva u `rezerve/asistent_katastar_<hash>.py` i ponovo se pokrene. Zato izmena važi tek kad je na `main`.
- Kad je izmena gotova i proverena: povećaj `VERZIJA` u `izvor.py`, dodaj komentar „# vN: …“ uz izmenjeni deo, sastavi program, commit (opis na srpskom, npr. „v34: ...“), pa push na `main`. Ako sesija mora da radi na posebnoj grani, otvori pull request ka `main` i reci Dejanu da ga spoji (Merge).
- Sajt eKatastra nije dostupan iz oblaka: sve se proverava na `mock_sajt.py`. Za novo ponašanje sajta traži od Dejana HAR; captchu nikad ne rešavaj umesto njega.
- Dejanov ekran je 1920x1080 na 150%; proveri i prikaz sa `TEST_UVECANJE=1.5`.
- Kratki meniji (desni klik do ~6-8 stavki), bez dugih uputstava u prozorima.

## Podaci se ne smeju izgubiti
- Prethodne verzije su u istoriji Git-a; na računaru ih program čuva i u `rezerve/`.
- `katastar.db` nikad ne menjaj direktno: radi na kopiji. Pre izmene šeme program pravi rezervu u `rezerve/` (npr. `katastar_pre_vN.db`); uradi isto pri svakoj promeni šeme.
- U oblaku nema baze ni podataka klijenata. Za proveru testovi prave probnu bazu.

## GitHub
- Na GitHub ide samo ono što je na spisku u `.gitignore` (lista dozvoljenih). Nikad ne dodaji bazu, `zadaci/`, `izvodi/`, `PDF/`, `dnevnik.txt`, `sifarnik_ko.json`, `uzorci_captcha.json`, rezerve ni bilo šta sa podacima klijenata; ne koristi `git add -f`.
- U `izvor/fix/` imena vlasnika su izmišljena (ПЕТРОВИЋ ПЕТАР, ЈОВАНОВИЋ (ЈОВАН) ЈЕЛЕНА, НИКОЛИЋ МИЛИЦА). Nova stranica sa sajta ide u `fix/` tek kad se imena, JMBG i adrese lica zamene izmišljenim.

## Provera pre isporuke
- `cd izvor && python napravi.py && python -m py_compile ../asistent_katastar.py`
- Testovi: `izvor/sve_testove.sh` (Xvfb na :98 1600x1000 i :97 2880x1620 za 150%, python3 sa tkinter i requests). Brzo: `cd izvor && xvfb-run -a python3 test_logika.py`; svaki test na kraju ispiše `UKUPNO GRESAKA`.
- Za novu funkciju dodaj test `izvor/test_<ime>.py` po uzoru na postojeće.
- Na kraju reci šta je izmenjeno i koja je verzija.
