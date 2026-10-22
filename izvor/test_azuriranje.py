# -*- coding: utf-8 -*-
"""v34: ažuriranje sa GitHub-a sa probnim startom. Pravi git repozitorijum (origin) i folder programa (kao na Dejanovom
računaru), pa na origin stavlja dobru, pokvarenu i verziju koja kvari bazu:
  - dobra verzija se preuzme i pokrene;
  - pokvarena (greška pri pokretanju ili pri promeni baze) ne prođe probni start: vraća se stara, prava baza ostaje
    netaknuta, a loša se ne preuzima ponovo dok na GitHub-u ne bude novija;
  - nova verzija koja pukne pri prvom pravom pokretanju vraća se na prethodnu;
  - bez mreže se ne čeka na git."""
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

IZVOR = os.path.dirname(os.path.abspath(__file__))
RAD = tempfile.mkdtemp(prefix="kat_azur_")
ORIGIN = os.path.join(RAD, "origin.git")
RADNI = os.path.join(RAD, "radni")               # kao Claude: odavde ide push na GitHub
RACUNAR = os.path.join(RAD, "Asistent_KATASTAR")  # kao Dejanov folder programa
GRESKE = []
os.environ.pop("KATASTAR_TEST", None)
os.environ.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                   "GIT_COMMITTER_EMAIL": "t@t"})


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def g(cwd, *a):
    r = subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("git %s: %s" % (a, r.stderr))
    return r.stdout.strip()


KOD = open(os.path.join(IZVOR, "asistent_katastar.py"), encoding="utf-8").read()


def objavi(kod, poruka):
    with open(os.path.join(RADNI, "asistent_katastar.py"), "w", encoding="utf-8") as f:
        f.write(kod)
    g(RADNI, "commit", "-qam", poruka)
    g(RADNI, "push", "-q", "origin", "main")
    return g(RADNI, "rev-parse", "HEAD")


# --- origin i dva klona ---
g(RAD, "init", "-q", "--bare", "-b", "main", ORIGIN)
g(RAD, "clone", "-q", ORIGIN, RADNI)
g(RADNI, "checkout", "-q", "-b", "main")
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join(IZVOR, "..", ime), RADNI)
with open(os.path.join(RADNI, ".gitignore"), "w") as f:
    f.write("*\n!/.gitignore\n!/asistent_katastar.py\n!/asistent_katastar_ikona.png\n!/asistent_katastar.ico\n")
with open(os.path.join(RADNI, "asistent_katastar.py"), "w", encoding="utf-8") as f:
    f.write(KOD)
g(RADNI, "add", ".")
g(RADNI, "commit", "-qm", "pocetna")
g(RADNI, "push", "-q", "-u", "origin", "main")
g(RAD, "clone", "-q", "-b", "main", ORIGIN, RACUNAR)
POCETNA = g(RACUNAR, "rev-parse", "HEAD")

# prava baza na "računaru"
BAZA = os.path.join(RACUNAR, "katastar.db")
c = sqlite3.connect(BAZA)
c.executescript("CREATE TABLE parcele (id INTEGER PRIMARY KEY AUTOINCREMENT, opstina_id INTEGER, opstina TEXT, "
                "ko_id INTEGER NOT NULL, ko TEXT, broj TEXT NOT NULL, klijent TEXT DEFAULT '', grupa TEXT DEFAULT '',"
                " napomena TEXT DEFAULT '', dodat TEXT, provereno TEXT, snimak TEXT, pokusaj TEXT, greska TEXT, "
                "promene TEXT, promena_vreme TEXT, UNIQUE(ko_id, broj));"
                "INSERT INTO parcele (ko_id, ko, broj, klijent) VALUES (703800, 'КУМОДРАЖ', '10383', 'Klijent');")
c.commit()
c.close()


def otisak_baze():
    c = sqlite3.connect(BAZA)
    r = c.execute("SELECT group_concat(broj || ko || klijent) FROM parcele").fetchone()[0]
    c.close()
    return r


OTISAK = otisak_baze()

# program na računaru, učitan kao modul (DIR = folder računara)
sys.argv = [os.path.join(RACUNAR, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
POKRENUTO = []


class Podproces:
    """subprocess bez Popen-a: novi program se ne pokreće stvarno, samo se beleži."""
    def __getattr__(self, ime):
        return getattr(subprocess, ime)

    @staticmethod
    def Popen(args, **k):
        POKRENUTO.append(args)


ak.subprocess = Podproces()
ak.mreza_dostupna = lambda *a, **k: True


def dnevnik():
    p = os.path.join(RACUNAR, "dnevnik.txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def glava():
    return g(RACUNAR, "rev-parse", "HEAD")


# 1) nema ničeg novog
ok(ak.azuriraj_sa_githuba() is False and glava() == POCETNA and not POKRENUTO, "nema nove verzije: radi postojeća")

# 2) dobra nova verzija
DOBRA = objavi(KOD.replace('VERZIJA = "', 'VERZIJA = "proba-'), "dobra")
t0 = time.time()
rez = ak.azuriraj_sa_githuba()
print("MERENJE: preuzimanje + probni start %.1f s" % (time.time() - t0))
ok(rez is True and glava() == DOBRA, "dobra verzija preuzeta")
ok(len(POKRENUTO) == 1 and "--bez-azuriranja" in POKRENUTO[0], "dobra verzija pokrenuta ponovo")
ok(os.path.exists(os.path.join(RACUNAR, "rezerve", "asistent_katastar_%s.py" % POCETNA[:8])), "stara verzija u rezerve/")
ok(open(os.path.join(RACUNAR, "rezerve", ak.NOVA_VERZIJA)).read().strip() == POCETNA,
   "zapamćeno na šta se vraća ako prvo pokretanje pukne")
ok("probni start prošao" in dnevnik(), "dnevnik: probni start prošao")
ok(otisak_baze() == OTISAK, "prava baza ista")
ak.nova_verzija_radi()
ok(not os.path.exists(os.path.join(RACUNAR, "rezerve", ak.NOVA_VERZIJA)), "posle 20 s rada nova verzija prihvaćena")

# 3) pokvarena: puca pri pokretanju
POKRENUTO.clear()
LOSA = objavi(KOD.replace("        self.root = root\n        napravi_rezervu_baze()",
                          "        self.root = root\n        raise RuntimeError('pokvarena verzija')", 1), "losa")
ok(LOSA != DOBRA, "pokvarena verzija objavljena")
rez = ak.azuriraj_sa_githuba()
ok(rez is False and glava() == DOBRA, "pokvarena verzija: ostaje prethodna (%s)" % glava()[:8])
ok(not POKRENUTO, "pokvarena verzija se ne pokreće")
ok("NE RADI" in dnevnik() and "pokvarena verzija" in dnevnik(), "dnevnik: zašto je vraćena")
ok(open(os.path.join(RACUNAR, "rezerve", ak.LOSA_VERZIJA)).read().strip() == LOSA, "loša verzija zapamćena")
ok(not g(RACUNAR, "status", "--porcelain"), "folder programa čist (sledeće preuzimanje može)")
t0 = time.time()
ok(ak.azuriraj_sa_githuba() is False and glava() == DOBRA and time.time() - t0 < 10,
   "ista loša verzija se ne proba ponovo (%.1f s)" % (time.time() - t0))

# 4) pokvarena promena baze: briše tabelu pa pukne - prava baza ne sme da se dira
KVARI = objavi(KOD.replace("        with self._con() as c:\n            c.executescript(\"\"\"",
                           "        with self._con() as c:\n            c.execute('DROP TABLE parcele')\n"
                           "            raise RuntimeError('greska u promeni baze')\n"
                           "            c.executescript(\"\"\"", 1), "kvari bazu")
rez = ak.azuriraj_sa_githuba()
ok(rez is False and glava() == DOBRA, "verzija koja kvari bazu: ostaje prethodna")
ok(otisak_baze() == OTISAK, "prava baza netaknuta posle loše promene baze")
ok(open(os.path.join(RACUNAR, "rezerve", ak.LOSA_VERZIJA)).read().strip() == KVARI, "i ona zapamćena kao loša")

# 5) novija dobra posle loše
NOVA = objavi(KOD.replace('VERZIJA = "', 'VERZIJA = "proba2-'), "ispravka")
ok(ak.azuriraj_sa_githuba() is True and glava() == NOVA, "novija ispravna verzija preuzeta")

# 6) nova verzija pukne pri prvom pravom pokretanju -> nazad
POKRENUTO.clear()
ok(ak.nova_verzija_ne_radi() is True and glava() == DOBRA, "prvo pokretanje puklo: vraćena prethodna verzija")
ok(len(POKRENUTO) == 1, "prethodna verzija pokrenuta")
ok(open(os.path.join(RACUNAR, "rezerve", ak.LOSA_VERZIJA)).read().strip() == NOVA, "ta verzija zapamćena kao loša")
ok(ak.nova_verzija_ne_radi() is False, "bez oznake nove verzije nema vraćanja")

# 7) bez mreže
ak.mreza_dostupna = lambda *a, **k: False
t0 = time.time()
ok(ak.azuriraj_sa_githuba() is False and time.time() - t0 < 1, "bez mreže: odmah radi postojeća")
ok("nema mreže" in dnevnik(), "dnevnik: nema mreže")

# 8) probni start ne dira pravi folder
pre = sorted(os.listdir(RACUNAR))
uspelo, razlog = ak.probni_start(os.path.join(RACUNAR, "asistent_katastar.py"))
ok(uspelo, "probni start trenutne verzije prolazi %s" % razlog)
ok(sorted(os.listdir(RACUNAR)) == pre, "probni start ne pravi ništa u folderu programa")

shutil.rmtree(RAD, ignore_errors=True)
print("UKUPNO GRESAKA:", len(GRESKE))
for x in GRESKE:
    print("  -", x)
