# Asistent KATASTAR

Program (Python 3 / tkinter / requests) za pretragu i praćenje parcela na eKatastru (katastar.rgz.gov.rs/eKatastarPublic): pretraga više parcela odjednom, praćenje sa poređenjem stanja (staro / novo), podaci o nepokretnosti (A, B, V, G list), PDF izveštaji, zadaci iz foldera `zadaci`, captcha koju program sam čita i uči.

## Pokretanje i ažuriranje

`pokreni.bat` ili prečica koju pravi `napravi_precicu.bat`.

Izmene se rade na GitHub-u (grana `main`). Pri svakom pokretanju program sam preuzme novu verziju (`git pull`), staru sačuva u `rezerve/` i ponovo se pokrene. Bez mreže ili kad ima lokalnih izmena radi postojeća verzija (razlog u `dnevnik.txt`). `--bez-azuriranja` preskače proveru. `preuzmi_sa_github.bat` preuzima ručno.

Prvo povezivanje postojećeg foldera: `povezi_sa_github.bat` (jednom).

## Izvor i testovi

`izvor/izvor.py` je izvor; `asistent_katastar.py` se sastavlja sa `cd izvor && python napravi.py`. `izvor/mock_sajt.py` simulira eKatastar, testovi su `izvor/test_*.py` (`izvor/sve_testove.sh` pokreće sve).

## Šta NIJE u repozitorijumu

Namerno se ne čuva na GitHub-u (vidi `.gitignore`): `katastar.db`, `rezerve/`, `dnevnik.txt`, `zadaci/`, `izvodi/`, `PDF/`, `sifarnik_ko.json`, `uzorci_captcha.json`. Posle `git clone` na drugom računaru te fajlove treba prekopirati ručno.
