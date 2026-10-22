# -*- coding: utf-8 -*-
"""v39: uvoz spiska parcela (nalepljeno iz Excela ili CSV) - ide u praćenje kao zadatak (klijent i grupa po redu,
već praćene se preskaču); druga kopija rezerve baze u folder "rezerve baze" na Drive-u (poslednjih 10)."""
import datetime as dt
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_uvoz_")
os.environ["KATASTAR_TEST"] = "1"
import mock_sajt  # noqa: E402

srv = mock_sajt.pokreni()
os.environ["KATASTAR_BASE"] = "http://127.0.0.1:%d/eKatastarPublic/" % srv.server_address[1]
shutil.copy("asistent_katastar.py", RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join("..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
UVECANJE = float(os.environ.get("TEST_UVECANJE", "1.0"))
GRESKE, PORUKE = [], []


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


# --- čitanje spiska ---
p, lose = ak.procitaj_spisak("Opština\tKO\tParcela\tKlijent\tGrupa\tNapomena\n"
                             "Вождовац\tКумодраж\t10383\tEURO ROAD\teuroroad\tСпасић\n"
                             "ВОЖДОВАЦ\tКУМОДРАЖ\t100-102, 4415/1\tDrugi\t\t\n"
                             "\t\t\t\t\t\n"
                             "ВОЖДОВАЦ\t\t5\tX\t\t\n"
                             "ВОЖДОВАЦ\tКУМОДРАЖ\t12a\tX\t\t\n")
ok([(x["ko"], x["broj"], x.get("klijent"), x.get("grupa")) for x in p] ==
   [("Кумодраж", "10383", "EURO ROAD", "euroroad"), ("КУМОДРАЖ", "100", "Drugi", None),
    ("КУМОДРАЖ", "101", "Drugi", None), ("КУМОДРАЖ", "102", "Drugi", None), ("КУМОДРАЖ", "4415/1", "Drugi", None)],
   "Excel sa naslovom: kolone po nazivu, više brojeva u ćeliji: %s" % [(x["ko"], x["broj"]) for x in p])
ok([(x[0], x[2]) for x in lose] == [(5, "nema katastarske opštine"), (6, "neispravan broj parcele: 12a")],
   "loši redovi sa brojem reda i razlogom: %s" % lose)
p, lose = ak.procitaj_spisak("Парцела;Катастарска општина;Клијент\n20015;ПОЖАРЕВАЦ;EURO ROAD\n20016;ПОЖАРЕВАЦ;EURO ROAD\n")
ok([(x["ko"], x["broj"], x["klijent"]) for x in p] == [("ПОЖАРЕВАЦ", "20015", "EURO ROAD"),
                                                       ("ПОЖАРЕВАЦ", "20016", "EURO ROAD")] and not lose,
   "CSV sa ; i naslovom na ćirilici, drugi redosled kolona")
p, lose = ak.procitaj_spisak("КУМОДРАЖ,10383,Klijent A,napomena\nКУМОДРАЖ,4415\n")
ok([(x["ko"], x["broj"], x.get("klijent")) for x in p] == [("КУМОДРАЖ", "10383", "Klijent A"),
                                                           ("КУМОДРАЖ", "4415", None)] and not lose,
   "bez naslova: KO, broj, klijent, napomena")
ok(ak.procitaj_spisak("") == ([], []), "prazno")

# --- uvoz kroz prozor ---
ak.messagebox = type("M", (), {"__getattr__": lambda self, ime: lambda *a, **k: (PORUKE.append(ime), True)[1]})()
ak.posalji_obavestenje = lambda naslov, redovi: None
ak.Pretraga.pauza = lambda self, raspon: None
ak.ZADACI_TIK_MS = 300
root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: next(mock_sajt.CAPTCHE[k] for k, v in mock_sajt.SVG.items() if v == svg)


def cekaj(uslov, sekundi=120):
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


app.baza.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "4415", klijent="Stari", grupa="stara grupa")
app.osvezi_listu()
app.uvezi_spisak()
d = app._uvoz_prozor
root.update()
d._txt.insert("1.0", "Opština\tKO\tParcela\tKlijent\tGrupa\n"
                     "ВОЖДОВАЦ\tКУМОДРАЖ\t10383\tEURO ROAD\teuroroad\n"
                     "ВОЖДОВАЦ\tКУМОДРАЖ\t4415\tEURO ROAD\teuroroad\n"
                     "ВОЖДОВАЦ\tКУМОДРАЖ\t777\tDrugi Klijent\t\n")
d._grupa.set("")
root.update()
ak.subprocess.run(["import", "-window", "root", "uvoz_v39%s.png" % ("" if UVECANJE == 1 else "_150")], check=False)
d._uvezi()
Z = os.path.join(RAD, "zadaci", "izvestaji")
ok(cekaj(lambda: os.path.isdir(Z) and any(f.startswith("uvoz") and f.endswith(".json") for f in os.listdir(Z)), 300),
   "uvoz urađen kao zadatak")
izv = json.load(open(os.path.join(Z, next(f for f in os.listdir(Z) if f.endswith(".json"))), encoding="utf-8"))
print("   ", [x["stanje"] for x in izv["rezultat"]])
P = {x["broj"]: x for x in app.baza.parcele()}
ok(P["10383"]["klijent"] == "EURO ROAD" and P["10383"]["grupa"] == "euroroad", "10383: klijent i grupa iz reda")
ok(P["777"]["klijent"] == "Drugi Klijent" and P["777"]["grupa"] == "Drugi Klijent",
   "777: bez grupe u redu - grupa = klijent")
ok(P["4415"]["klijent"] == "Stari" and P["4415"]["grupa"] == "stara grupa" and izv["rezultat"][1].get("preskocena"),
   "4415 već praćena: preskočena, ništa promenjeno")
ok(len(app.baza.parcele()) == 3 and P["10383"]["provereno"], "bez duplikata, nove skinute sa sajta")

# --- druga kopija rezerve na Drive ---
DRIVE = os.path.join(RAD, "G", "My Drive", ak.DRIVE_FOLDER)
os.makedirs(os.path.join(DRIVE, "rezerve baze"))
for i in range(12):
    open(os.path.join(DRIVE, "rezerve baze", "katastar_202501%02d.db" % (i + 1)), "w").close()
app.baza.postavi_podesavanje("drive_folder", DRIVE)
ak.napravi_rezervu_baze()
app._rezerva_na_drive()
danas = "katastar_%s.db" % dt.date.today().strftime("%Y%m%d")
ok(cekaj(lambda: os.path.exists(os.path.join(DRIVE, "rezerve baze", danas)), 30), "današnja rezerva na Drive-u")
cekaj(lambda: len(os.listdir(os.path.join(DRIVE, "rezerve baze"))) == 10, 10)
f = sorted(os.listdir(os.path.join(DRIVE, "rezerve baze")))
ok(len(f) == 10 and f[-1] == danas and "katastar_20250101.db" not in f, "na Drive-u poslednjih 10: %s" % f[:2])
ok(os.path.getsize(os.path.join(DRIVE, "rezerve baze", danas)) == os.path.getsize(
    os.path.join(ak.REZERVE_DIR, danas)), "kopija iste veličine kao lokalna rezerva")
app.baza.postavi_podesavanje("drive_folder", "-")
os.remove(os.path.join(DRIVE, "rezerve baze", danas))
app._rezerva_na_drive()
cekaj(lambda: False, 1.0)
ok(not os.path.exists(os.path.join(DRIVE, "rezerve baze", danas)), "Drive isključen: nema kopije")

root.destroy()
srv.shutdown()
shutil.rmtree(RAD, ignore_errors=True)
print("UKUPNO GRESAKA: %d" % len(GRESKE))
for x in GRESKE:
    print("  -", x)
sys.stdout.flush()   # bez ovoga se poslednji redovi gube kad izlaz ide u fajl (CI)
os._exit(1 if GRESKE else 0)
