# -*- coding: utf-8 -*-
"""v37: okrnjen odgovor sajta (nema vlasnika, nema delova, nestali svi stanovi) ne postaje promena: stanje ostaje
staro, parcela je označena "sumnjiv odgovor sajta - proveri ponovo". Isti odgovor u dve uzastopne provere se
prihvata kao pravo stanje (npr. stanovi stvarno obrisani)."""
import importlib.util
import os
import shutil
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_sumnjivo_")
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
GRESKE, PORUKE = [], []
S = mock_sajt.STANJE


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


# --- pravila (bez sajta) ---
st = {"delovi": [["1", "500", "П", "ЊИВА", "П"]], "objekti": [["1", "У", "5", "", "300", "З", "И"]],
      "posebni": [["У 5", str(i), "1", str(i), "", "СТАН", "55"] for i in range(5)], "nep_v": 2,
      "nepokretnost": {"parcela": ["[Имаоци права на парцели - Б лист] Назив: ПЕТРОВИЋ ПЕТАР; Удео: 1/1"]}}
ok(ak.sumnjiv_snimak(st, dict(st)) is None, "isto stanje: nije sumnjivo")
ok("delove parcele" in (ak.sumnjiv_snimak(st, dict(st, delovi=[])) or ""), "nestali svi delovi: sumnjivo")
ok("posebnog dela" in (ak.sumnjiv_snimak(st, dict(st, posebni=[])) or ""), "zgrada bez ijednog stana: sumnjivo")
ok(ak.sumnjiv_snimak(st, dict(st, posebni=[], objekti=[])) is None, "srušena zgrada (i objekti nestali): nije sumnjivo")
ok(ak.sumnjiv_snimak(st, dict(st, posebni=st["posebni"][:2])) is None, "manje stanova: nije sumnjivo (promena)")
bez = dict(st, nepokretnost={"parcela": ["[Имаоци права на парцели - Б лист]"]})
ok("vlasnika" in (ak.sumnjiv_snimak(st, bez, {"parcela": []}) or ""), "skinut list bez vlasnika: sumnjivo")
ok(ak.sumnjiv_snimak(st, bez, {}) is None, "vlasnici nisu skidani u ovoj proveri: nije sumnjivo")
ok(ak.sumnjiv_snimak(None, st) is None, "prva provera: nije sumnjivo")

# --- u programu ---
ak.messagebox = type("M", (), {"__getattr__": lambda self, ime: lambda *a, **k: (PORUKE.append(ime), True)[1]})()
ak.posalji_obavestenje = lambda naslov, redovi: None
ak.Pretraga.pauza = lambda self, raspon: None
root = ak.tk.Tk()
app = ak.App(root)
root.update()
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: next(ak_k for k, v in mock_sajt.SVG.items() if v == svg
                                                     for ak_k in [mock_sajt.CAPTCHE[k]])


def cekaj(uslov, sekundi=120):
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


def proveri():
    app.proveri(False)
    ok(cekaj(lambda: app.posao is None and "Rezultat provere" in app.txt.get("1.0", "end")[-3000:]),
       "provera završena")


app.baza.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", "4415", klijent="Klijent")
app.osvezi_listu()
proveri()
p = app.baza.parcela_po_mestu(703800, "4415")
ok(p["snimak"] and ak.vlasnici_tereti(ak.json.loads(p["snimak"]))[0].startswith("ПЕТРОВИЋ ПЕТАР"),
   "prva provera: vlasnik ПЕТРОВИЋ ПЕТАР")
pre = p["snimak"]

S["bez_vlasnika"] = True
app.txt.delete("1.0", "end")
proveri()
p = app.baza.parcela_po_mestu(703800, "4415")
ok(p["snimak"] == pre and not p["promene"], "okrnjen odgovor: snimak isti, nema promene")
ok("sumnjiv odgovor sajta" in (p["greska"] or ""), "parcela označena: %s" % p["greska"])
log = app.txt.get("1.0", "end")
ok("sumnjiv odgovor sajta: nema vlasnika parcele" in log and "PROMENA" not in log, "poruka: sumnjiv odgovor, bez PROMENA")
ok("nije uspelo: 1" in log, "u rezultatu provere vodi se kao neuspela")

S["bez_vlasnika"] = False
app.txt.delete("1.0", "end")
proveri()
p = app.baza.parcela_po_mestu(703800, "4415")
ok(p["snimak"] == pre or not p["promene"], "sajt ponovo ispravan: bez promene")
ok(not p["greska"], "oznaka sumnjivog skinuta")

S["bez_vlasnika"] = True                 # dva puta zaredom isto: prihvata se
proveri()
ok("sumnjiv" in (app.baza.parcela_po_mestu(703800, "4415")["greska"] or ""), "prvi put: sumnjivo")
app.txt.delete("1.0", "end")
proveri()
p = app.baza.parcela_po_mestu(703800, "4415")
ok(not p["greska"] and p["promene"] and "ПЕТРОВИЋ" in p["promene"],
   "isti odgovor drugi put zaredom: prihvaćen kao promena (%s)" % (p["promene"] or "")[:80])
S["bez_vlasnika"] = False

root.destroy()
srv.shutdown()
print("UKUPNO GRESAKA: %d" % len(GRESKE))
for x in GRESKE:
    print("  -", x)
sys.stdout.flush()   # bez ovoga se poslednji redovi gube kad izlaz ide u fajl (CI)
os._exit(1 if GRESKE else 0)
