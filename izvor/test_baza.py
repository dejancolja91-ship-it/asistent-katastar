# -*- coding: utf-8 -*-
"""v36: baza - promene šeme po broju (PRAGMA user_version) sa rezervom pre promene, veze se zatvaraju, pretraga
sa pamćenjem teksta (isti pogoci kao ranije, brže), "Ukloni iz praćenja" ide u Arhivu, trajno brisanje samo odatle."""
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_baza_")
os.environ["KATASTAR_TEST"] = "1"
IZVOR = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(IZVOR, "asistent_katastar.py"), RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join(IZVOR, "..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
GRESKE = []


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


POSLEDNJA = len(ak.MIGRACIJE) and ak.MIGRACIJE[-1][0]

# --- nova baza: sve promene šeme, bez rezerve (nema podataka) ---
d1 = os.path.join(RAD, "nova")
os.makedirs(d1)
b = ak.Baza(os.path.join(d1, "katastar.db"))
c = sqlite3.connect(b.path)
ok(c.execute("PRAGMA user_version").fetchone()[0] == POSLEDNJA, "nova baza: šema %d" % POSLEDNJA)
ok([r[1] for r in c.execute("PRAGMA table_info(rok_grupe)")] == ["naziv", "dana"] and
   [r[1] for r in c.execute("PRAGMA table_info(grupe)")] == ["naziv"], "nova tabela rok_grupe, grupe nepromenjena")
c.close()
ok(not os.path.exists(os.path.join(d1, "rezerve")), "nova (prazna) baza: bez rezerve")

# --- baza iz v33 (šema 0, sa podacima): rezerva pre promene, podaci isti ---
d2 = os.path.join(RAD, "stara")
os.makedirs(d2)
put = os.path.join(d2, "katastar.db")
c = sqlite3.connect(put)
c.executescript("""
CREATE TABLE parcele (id INTEGER PRIMARY KEY AUTOINCREMENT, opstina_id INTEGER, opstina TEXT, ko_id INTEGER NOT NULL,
 ko TEXT, broj TEXT NOT NULL, klijent TEXT DEFAULT '', grupa TEXT DEFAULT '', napomena TEXT DEFAULT '', dodat TEXT,
 provereno TEXT, snimak TEXT, pokusaj TEXT, greska TEXT, promene TEXT, promena_vreme TEXT, arhivirano TEXT,
 odlozeno_do TEXT, stavke TEXT, UNIQUE(ko_id, broj));
CREATE TABLE istorija (id INTEGER PRIMARY KEY AUTOINCREMENT, parcela_id INTEGER, vreme TEXT, tekst TEXT);
CREATE TABLE grupe (naziv TEXT PRIMARY KEY);
CREATE TABLE podesavanja (kljuc TEXT PRIMARY KEY, vrednost TEXT);
INSERT INTO parcele (ko_id, ko, broj, klijent, grupa) VALUES (734195, 'ПОЖАРЕВАЦ', '20015', 'EURO ROAD', 'euroroad');
INSERT INTO grupe VALUES ('euroroad');
INSERT INTO istorija (parcela_id, vreme, tekst) VALUES (1, '01.01.2026 10:00', 'promena');
""")
c.commit()
c.close()
b2 = ak.Baza(put)
rez = os.path.join(d2, "rezerve", "katastar_pre_v36.db")
ok(os.path.exists(rez), "rezerva pre promene šeme: %s" % os.path.basename(rez))
c = sqlite3.connect(rez)
ok(c.execute("PRAGMA user_version").fetchone()[0] == 0 and
   c.execute("SELECT broj, klijent FROM parcele").fetchall() == [("20015", "EURO ROAD")], "rezerva ima stare podatke")
c.close()
ok([(p["broj"], p["grupa"]) for p in b2.parcele()] == [("20015", "euroroad")] and len(b2.istorija(1)) == 1,
   "podaci isti posle promene šeme")
vreme = os.path.getmtime(rez)
ak.Baza(put)
ok(os.path.getmtime(rez) == vreme and len(os.listdir(os.path.join(d2, "rezerve"))) == 1,
   "drugo pokretanje: nema nove promene ni nove rezerve")

# --- promena šeme koja pukne: ništa se ne upisuje, broj šeme ostaje ---
def losa(c):
    c.execute("UPDATE parcele SET klijent='POKVARENO'")
    raise RuntimeError("greška u promeni")


ak.MIGRACIJE.append((POSLEDNJA + 1, "v99", losa))
try:
    ak.Baza(put)
    puklo = False
except RuntimeError:
    puklo = True
ak.MIGRACIJE.pop()
c = sqlite3.connect(put)
ok(puklo and c.execute("PRAGMA user_version").fetchone()[0] == POSLEDNJA and
   c.execute("SELECT klijent FROM parcele").fetchone()[0] == "EURO ROAD", "loša promena šeme: vraćeno, podaci isti")
ok(os.path.exists(os.path.join(d2, "rezerve", "katastar_pre_v99.db")), "i za nju je napravljena rezerva")
c.close()

# --- veze se zatvaraju ---
otvorene = []
pravi = ak.sqlite3.connect


class Pracena:
    def __init__(self, *a, **k):
        self.c = pravi(*a, **k)
        otvorene.append(self.c)

    def __getattr__(self, ime):
        return getattr(self.c, ime)

    def __setattr__(self, ime, v):
        if ime == "c":
            object.__setattr__(self, ime, v)
        else:
            setattr(self.c, ime, v)

    def __enter__(self):
        self.c.__enter__()
        return self

    def __exit__(self, *a):
        return self.c.__exit__(*a)


ak.sqlite3.connect = Pracena
b2.parcele()
b2.podesavanje("x")
b2.izmeni(1, "EURO ROAD 111", "euroroad", "")
ak.sqlite3.connect = pravi


def zatvorena(c):
    try:
        c.execute("SELECT 1")
        return False
    except sqlite3.ProgrammingError:
        return True


ok(len(otvorene) >= 3 and all(zatvorena(c) for c in otvorene), "sve veze zatvorene (%d)" % len(otvorene))

# --- pretraga: isti pogoci kao ranije (bez obzira na pismo i kvačice), sa pamćenjem, brzo ---
d3 = os.path.join(RAD, "pretraga")
os.makedirs(d3)
b3 = ak.Baza(os.path.join(d3, "katastar.db"))


def snimak(n, ime):
    return {"ko": "КУМОДРАЖ", "opstina": "ВОЖДОВАЦ", "delovi": [["1", "500", "ПОТЕС", "ЊИВА 2. КЛАСЕ", "П"]],
            "objekti": [["1", "УЛИЦА", "5", "", "300", "СТАМБЕНА ЗГРАДА", "ИЗГРАЂЕН"]] if n else [],
            "posebni": [["УЛИЦА 5", str(i), "1", str(i), "", "СТАН", "55"] for i in range(n)],
            "nepokretnost": {"poseban deo %d" % i: {"vlasnici": [[ime, "СВОЈИНА", "1/1"]], "tereti": [["Х" * 300]]}
                             for i in range(n)}, "nep_v": 2}


for i in range(1000):
    b3.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", str(10000 + i), klijent="Klijent %d" % (i % 50),
             grupa="G%d" % (i % 30), napomena="Ђурђевић" if i == 7 else "",
             snimak=snimak(190 if i % 20 == 0 else 1, "ПЕТРОВИЋ ПЕТАР" if i % 40 == 0 else "НИКОЛИЋ МИЛИЦА"))


def stara_pretraga(upit):
    u = ak.lat(upit)
    return {p["id"] for p in b3.parcele() if any(u in ak.lat(x or "") for x in (
        p["broj"], p["ko"], p["opstina"], p["klijent"], p["grupa"], p["napomena"], p["promene"] or "", p["snimak"] or ""))}


t0 = time.perf_counter()
prvi = b3.pretrazi("petrovic")
t_prvi = time.perf_counter() - t0
t0 = time.perf_counter()
for upit in ("petrovic", "ПЕТРОВИЋ", "djurdjevic", "Ђурђ", "klijent 7", "10383", "g2", "nema ovoga"):
    b3.pretrazi(upit)
t_ost = (time.perf_counter() - t0) / 8
print("MERENJE: prva pretraga %.3f s, sledeće %.4f s (1000 parcela)" % (t_prvi, t_ost))
ok(t_ost < 0.1, "pretraga posle prve brza (%.4f s)" % t_ost)
for upit in ("petrovic", "ПЕТРОВИЋ", "djurdjevic", "Ђурђ", "klijent 7", "10383", "g2", "nema ovoga", "milica"):
    ok(b3.pretrazi(upit) == stara_pretraga(upit), "pretraga „%s“: isti pogoci kao ranije (%d)" % (
        upit, len(stara_pretraga(upit))))
pid = b3.parcela_po_mestu(703800, "10001")["id"]
b3.izmeni(pid, "Novi Klijent Ćirić", "G1", "")
ok(pid in b3.pretrazi("ciric"), "pretraga vidi izmenu klijenta odmah")
p = b3.parcela_po_mestu(703800, "10003")
ok(p["id"] in b3.pretrazi("nikolic milica"), "pre izmene snimka: nađena po vlasniku")
c = sqlite3.connect(b3.path)               # nov snimak iste dužine, isto vreme provere
novi = p["snimak"].replace("НИКОЛИЋ МИЛИЦА", "НИКОЛИЋ МИЛИНА")
ok(len(novi) == len(p["snimak"]) and novi != p["snimak"], "snimak iste dužine, drugačiji")
c.execute("UPDATE parcele SET snimak=? WHERE id=?", (novi, p["id"]))
c.commit()
c.close()
ok(p["id"] not in b3.pretrazi("nikolic milica") and p["id"] in b3.pretrazi("nikolic milina"),
   "pretraga vidi nov snimak odmah (i iste dužine)")

# --- Ukloni iz praćenja -> Arhiva; iz Arhive trajno ---
PORUKE = []


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), True)[1]


ak.messagebox = TihiMessagebox()
root = ak.tk.Tk()
app = ak.App(root)
root.update()
app.baza.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "10383", klijent="K")
app.osvezi_listu()
pid = app.baza.parcela_po_mestu(703800, "10383")["id"]
app.tree.selection_set(str(pid))
app.ukloni()
p = app.baza.parcela_po_mestu(703800, "10383")
ok(p is not None and p["arhivirano"] and not PORUKE, "Ukloni iz praćenja: parcela u Arhivi, bez pitanja, ništa obrisano")
app.prikaz_var.set(ak.PRIKAZI[6])
app.osvezi_listu()
app.tree.selection_set(str(pid))
app.ukloni()
ok(app.baza.parcela_po_mestu(703800, "10383") is None and PORUKE and PORUKE[-1][1] == "Obriši trajno",
   "iz Arhive: trajno brisanje uz potvrdu")
root.destroy()

shutil.rmtree(RAD, ignore_errors=True)
print("UKUPNO GRESAKA: %d" % len(GRESKE))
for x in GRESKE:
    print("  -", x)
os._exit(1 if GRESKE else 0)
