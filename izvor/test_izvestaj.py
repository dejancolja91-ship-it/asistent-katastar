# -*- coding: utf-8 -*-
"""v38: izveštaj o promenama za klijenta (grupa, od datuma do danas, PDF i CSV) i rok provere po grupi
(pri pokretanju program ponudi proveru parcela kojima je istekao rok)."""
import csv
import datetime as dt
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_izvestaj_")
os.environ["KATASTAR_TEST"] = "1"
os.environ["KATASTAR_PREGLEDAC"] = os.environ.get("KATASTAR_PREGLEDAC") or "/opt/pw-browsers/chromium"
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
S = mock_sajt.STANJE


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


# --- datumi i rok (bez prozora) ---
ok(ak.datum_iz_vremena("07.01.2026 10:15") == dt.date(2026, 1, 7) and ak.datum_iz_vremena("7.1.2026.") ==
   dt.date(2026, 1, 7) and ak.datum_iz_vremena("31.02.2026 10:00") is None and ak.datum_iz_vremena(None) is None,
   "datum_iz_vremena")
ok(ak.citaj_datum("2027-01-07") == dt.date(2027, 1, 7) and ak.citaj_datum("07.01.27.") == dt.date(2027, 1, 7),
   "citaj_datum (Odloži proveru) nepromenjen")
danas = dt.date(2026, 10, 22)
ok(ak.istekao_rok({"provereno": "12.10.2026 10:00"}, 7, danas) and not ak.istekao_rok(
    {"provereno": "20.10.2026 10:00"}, 7, danas) and ak.istekao_rok({"provereno": None}, 7, danas), "istekao_rok")

ODGOVORI = {"askyesno": True}


class Mb:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), ODGOVORI.get(ime, True))[1]


ak.messagebox = Mb()
ak.posalji_obavestenje = lambda naslov, redovi: None
ak.Pretraga.pauza = lambda self, raspon: None
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


def proveri_sve():
    app.txt.delete("1.0", "end")
    app.proveri(False)
    ok(cekaj(lambda: app.posao is None and "Rezultat provere" in app.txt.get("1.0", "end")), "provera završena")


b = app.baza
b.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "4415", klijent="EURO ROAD", grupa="euroroad", napomena="Спасић")
b.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "10383", klijent="EURO ROAD", grupa="euroroad")
b.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "777", klijent="Drugi", grupa="drugi")
app.osvezi_listu()
proveri_sve()
S["vlasnik"] = "ЈОВАНОВИЋ (ЈОВАН) ЈЕЛЕНА"
app.tree.selection_set(str(b.parcela_po_mestu(703800, "4415")["id"]))
app.txt.delete("1.0", "end")
app.proveri(True)
ok(cekaj(lambda: app.posao is None and "Rezultat provere" in app.txt.get("1.0", "end")), "druga provera 4415")
P = {p["broj"]: p for p in b.parcele()}
ok(b.istorija(P["4415"]["id"]), "4415: promena vlasnika u istoriji")
c = sqlite3.connect(b.path)                  # stara promena (pre perioda izveštaja) ne ide u izveštaj
c.execute("INSERT INTO istorija (parcela_id, vreme, tekst) VALUES (?, '01.01.2020 10:00', 'STARA PROMENA')",
          (P["10383"]["id"],))
c.commit()
c.close()

# --- izveštaj iz menija grupe ---
izlaz = os.path.join(RAD, "Klijent EURO ROAD")
os.makedirs(izlaz)
ak.simpledialog.askstring = lambda *a, **k: (dt.date.today() - dt.timedelta(days=30)).strftime("%d.%m.%Y")
ak.filedialog.asksaveasfilename = lambda **k: (PORUKE.append(("sacuvaj", k.get("initialfile"))),
                                              os.path.join(izlaz, k["initialfile"]))[1]
app.tree.selection_set("g:euroroad")
app.izvestaj_promena()
ok(cekaj(lambda: "Izveštaj o promenama: " in app.txt.get("1.0", "end"), 120), "izveštaj napravljen")
ime = "Promene euroroad od %s" % (dt.date.today() - dt.timedelta(days=30)).strftime("%d.%m.%Y")
ok(("sacuvaj", ime + ".pdf") in PORUKE, "predložen naziv fajla: %s.pdf" % ime)
pdf = os.path.join(izlaz, ime + ".pdf")
ok(os.path.exists(pdf) and os.path.getsize(pdf) > 3000 and open(pdf, "rb").read(5) == b"%PDF-", "PDF izveštaja")
redovi = list(csv.reader(open(os.path.join(izlaz, ime + ".csv"), encoding="utf-8-sig"), delimiter=";"))
print("   ", redovi[:4])
ok(redovi[0] == ak.IZVESTAJ_CSV_ZAGLAVLJE, "CSV zaglavlje")
r4415 = [r for r in redovi[1:] if r[2] == "4415"]
ok(r4415 and any("ПЕТРОВИЋ ПЕТАР" in r[6] and "ЈОВАНОВИЋ" in r[7] for r in r4415),
   "4415: staro ПЕТРОВИЋ ПЕТАР, novo ЈОВАНОВИЋ")
r10383 = [r for r in redovi[1:] if r[2] == "10383"]
ok(len(r10383) == 1 and r10383[0][6] == "bez promena" and r10383[0][8], "10383: bez promena u periodu (stara ne ulazi)")
ok(not [r for r in redovi[1:] if r[2] == "777"], "druga grupa nije u izveštaju")
html, _, n = ak.izvestaj_promena(b.parcele([P["4415"]["id"], P["10383"]["id"]]),
                                 {i: b.istorija(i) for i in (P["4415"]["id"], P["10383"]["id"])},
                                 dt.date(2019, 1, 1), "euroroad")
ok(n == 2 and "STARA PROMENA" in html, "sa ranijim datumom ulazi i stara promena")

# --- rok provere ---
ak.simpledialog.askinteger = lambda *a, **k: 7
app.tree.selection_set("g:euroroad")
app.rok_grupe()
ok(b.rokovi() == {"euroroad": 7}, "rok 7 dana za euroroad")
app.osvezi_listu()
ok("rok: 7 d" in app.tree.item("g:euroroad", "values")[6], "u redu grupe piše rok")
ok(not app.parcele_isteklog_roka(), "upravo provereno: rok nije istekao")
staro = (dt.date.today() - dt.timedelta(days=10)).strftime("%d.%m.%Y 09:00")
c = sqlite3.connect(b.path)
c.execute("UPDATE parcele SET provereno=?", (staro,))
c.commit()
c.close()
b.arhiviraj([P["10383"]["id"]])
ist = app.parcele_isteklog_roka()
ok([p["broj"] for p in ist] == ["4415"], "istekao rok: samo aktivna parcela grupe sa rokom (%s)" %
   [p["broj"] for p in ist])
app.txt.delete("1.0", "end")
app._ponudi_rok()
ok(any(x[0] == "askyesno" and x[1] == "Rok provere" for x in PORUKE), "ponuđena provera")
ok(cekaj(lambda: app.posao is None and "Rezultat provere" in app.txt.get("1.0", "end")), "provera isteklih urađena")
ok(not app.parcele_isteklog_roka() and b.parcela_po_mestu(703800, "777")["provereno"] == staro,
   "proverena samo parcela sa isteklim rokom")
b.preimenuj_grupu("euroroad", "EURO ROAD 111")
ok(b.rokovi() == {"EURO ROAD 111": 7}, "preimenovana grupa zadržava rok")
b.obrisi_grupu("EURO ROAD 111")
ok(b.rokovi() == {}, "obrisana grupa: nema roka")

root.destroy()
srv.shutdown()
shutil.rmtree(RAD, ignore_errors=True)
print("UKUPNO GRESAKA: %d" % len(GRESKE))
for x in GRESKE:
    print("  -", x)
os._exit(1 if GRESKE else 0)
