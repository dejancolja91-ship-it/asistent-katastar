# -*- coding: utf-8 -*-
"""v40 (Dejan: "daj mi opciju da postojeći unos promenim, npr. ako nešto upišem loše"): Izmeni - za jednu parcelu
i opština, KO i broj parcele. Ispravljena parcela gubi stanje i istoriju pogrešne, klijent/grupa/napomena ostaju,
nova se odmah proverava; parcela koja je već u praćenju se ne duplira; neispravan broj se ne prihvata."""
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_izmena_")
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
ODGOVOR = {"askyesno": True}


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


class Mb:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), ODGOVOR.get(ime, True))[1]


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


def svi(w):
    for c in w.winfo_children():
        yield c
        yield from svi(c)


def dijalog():
    return next((w for w in root.winfo_children() if isinstance(w, ak.tk.Toplevel) and
                 w.title().startswith("Izmeni")), None)


def u_dijalogu(radnja, slika=None, odustani=False):
    """Kao korisnik: kad se prozor Izmeni otvori, uradi radnju(polja) pa klik na U redu (ili Odustani)."""
    def posle():
        d = dijalog()
        if d is None:
            root.after(100, posle)
            return
        d.update()
        polja = {"entry": [w for w in svi(d) if w.winfo_class() == "TEntry"],
                 "combo": [w for w in svi(d) if w.winfo_class() == "TCombobox"], "d": d}
        if slika:
            subprocess.run(["import", "-window", "root", slika], check=False)
        dugme = {w.cget("text"): w for w in svi(d) if w.winfo_class() == "TButton"}
        radnja(polja)
        if odustani:
            dugme["Odustani"].invoke()
        else:
            dugme["U redu"].invoke()
            root.after(300, lambda: d.winfo_exists() and dugme["Odustani"].invoke())
    root.after(200, posle)


b = app.baza
b.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "10838", klijent="EURO ROAD", grupa="euroroad", napomena="ugovor 1")
b.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "4415", klijent="Drugi", grupa="drugi")
P = {p["broj"]: p for p in b.parcele()}
c = sqlite3.connect(b.path)
c.execute("UPDATE parcele SET snimak='{\"delovi\": []}', provereno='01.10.2026 10:00', promene='x' WHERE id=?",
          (P["10838"]["id"],))
c.execute("INSERT INTO istorija (parcela_id, vreme, tekst) VALUES (?, '01.10.2026 10:00', 'stara')", (P["10838"]["id"],))
c.commit()
c.close()
app.osvezi_listu()
meni = app.root.nametowidget(app.root["menu"])
parcela = meni.nametowidget(meni.entrycget(meni.index("Parcela"), "menu"))
ok("Izmeni (broj parcele, KO, klijent, grupa)..." in [parcela.entrycget(i, "label") for i in range(parcela.index("end") + 1)
                                                      if parcela.type(i) == "command"], "stavka u meniju Parcela")

# --- 1. pogrešan broj: 10838 -> 10383 ---
app.tree.selection_set(str(P["10838"]["id"]))


def broj(polja, novi="10383"):
    e = [w for w in polja["entry"] if w.get() == "10838" or w.get() == "10383"][0]
    e.delete(0, "end")
    e.insert(0, novi)


slika = "izmena_v40%s.png" % ("" if UVECANJE == 1 else "_150")
u_dijalogu(broj, slika)
app.izmeni()
cekaj(lambda: dijalog() is None, 10)
ok(any(x[0] == "askyesno" and "Umesto КУМОДРАЖ 10838 prati se КУМОДРАЖ 10383" in x[2] for x in PORUKE),
   "pita pre ispravke (stanje i istorija stare se brišu)")
p = b.parcela_po_mestu(703800, "10383")
ok(p and p["id"] == P["10838"]["id"] and not b.parcela_po_mestu(703800, "10838"), "parcela ispravljena, nije duplirana")
ok(p and p["klijent"] == "EURO ROAD" and p["grupa"] == "euroroad" and p["napomena"] == "ugovor 1",
   "klijent, grupa i napomena ostali")
ok(not b.istorija(p["id"]) and not p["promene"], "istorija i promene pogrešne parcele obrisane")
ok(cekaj(lambda: (b.parcela_po_mestu(703800, "10383") or {}).get("provereno") and app.posao is None, 120),
   "nova parcela odmah proverena")
ok(len(b.parcele()) == 2, "i dalje 2 parcele")

# --- 2. druga KO ---
app.tree.selection_set(str(p["id"]))


def ko(polja):
    cb_o, cb_k = polja["combo"][0], polja["combo"][1]
    vrednosti = list(cb_k.cget("values"))
    ok("ЗУЦЕ" in vrednosti, "u prozoru je spisak KO opštine: %s" % vrednosti[:4])
    cb_k.current(vrednosti.index("ЗУЦЕ"))


u_dijalogu(ko)
app.izmeni()
cekaj(lambda: dijalog() is None, 10)
p = b.parcele([p["id"]])[0]
ok(p["ko"] == "ЗУЦЕ" and str(p["ko_id"]) == "703753" and p["broj"] == "10383", "KO promenjena: %s %s" % (p["ko"], p["ko_id"]))
cekaj(lambda: app.posao is None, 120)

# --- 3. na parcelu koja je već u praćenju: ne duplira ---
app.tree.selection_set(str(p["id"]))
PORUKE.clear()


def na_4415(polja):
    cb_k = polja["combo"][1]
    cb_k.current(list(cb_k.cget("values")).index("КУМОДРАЖ"))
    broj(polja, "4415")


u_dijalogu(na_4415)
app.izmeni()
cekaj(lambda: dijalog() is None, 10)
ok(any(x[0] == "showwarning" and "već u praćenju" in x[2] for x in PORUKE), "upozorenje: već je u praćenju")
ok(b.parcele([p["id"]])[0]["ko"] == "ЗУЦЕ" and len(b.parcele()) == 2, "ništa promenjeno, bez duplikata")

# --- 4. neispravan broj: prozor ostaje, ništa se ne menja ---
PORUKE.clear()
u_dijalogu(lambda polja: broj(polja, "12a"))
app.izmeni()
cekaj(lambda: dijalog() is None, 10)
ok(any(x[0] == "showwarning" and "nije ispravan" in x[2] for x in PORUKE), "neispravan broj: upozorenje")
ok(b.parcele([p["id"]])[0]["broj"] == "10383", "neispravan broj: ništa promenjeno")

# --- 5. odustane na pitanju ---
ODGOVOR["askyesno"] = False
u_dijalogu(lambda polja: broj(polja, "10384"))
app.izmeni()
cekaj(lambda: dijalog() is None, 10)
ok(b.parcele([p["id"]])[0]["broj"] == "10383", "Ne na pitanju: ništa promenjeno")
ODGOVOR["askyesno"] = True

# --- 6. samo klijent (bez promene mesta): ne pita i ne briše stanje ---
PORUKE.clear()
pre = b.parcele([p["id"]])[0]


def klijent(polja):
    e = [w for w in polja["entry"] if w.get() == "EURO ROAD"][0]
    e.delete(0, "end")
    e.insert(0, "EURO ROAD 111")


u_dijalogu(klijent)
app.izmeni()
cekaj(lambda: dijalog() is None, 10)
posle = b.parcele([p["id"]])[0]
ok(posle["klijent"] == "EURO ROAD 111" and posle["snimak"] == pre["snimak"] and posle["provereno"] == pre["provereno"]
   and not any(x[0] == "askyesno" for x in PORUKE), "samo klijent: bez pitanja, stanje sačuvano")

# --- 7. više izabranih: nema polja za KO i broj ---
app.osvezi_listu()
app.tree.selection_set([str(x["id"]) for x in b.parcele()])
nadjeno = {}
u_dijalogu(lambda polja: nadjeno.update(n=len(polja["combo"]), e=len(polja["entry"])), odustani=True)
app.izmeni()
ok(nadjeno.get("n") == 1 and nadjeno.get("e") == 2, "više parcela: samo klijent, grupa, napomena (%s)" % nadjeno)

root.destroy()
srv.shutdown()
shutil.rmtree(RAD, ignore_errors=True)
print("UKUPNO GRESAKA: %d" % len(GRESKE))
for x in GRESKE:
    print("  -", x)
sys.stdout.flush()
os._exit(1 if GRESKE else 0)
