# -*- coding: utf-8 -*-
"""v27 (Dejan: "da mogu da pratim i po izboru celu parcelu, sve sto je izaslo. Dakle ili sve, ili samo odredjeno kad
kliknem, ali da ima dugme za sve"): dugme „Prati celu parcelu“ u prozoru parcele; desni klik i dalje prati samo
izabrani stan; prelaz stan <-> cela parcela; provera cele parcele javlja promenu bilo kog stana."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_cela_")
os.environ["KATASTAR_TEST"] = "1"
import mock_sajt

srv = mock_sajt.pokreni()
os.environ["KATASTAR_BASE"] = "http://127.0.0.1:%d/eKatastarPublic/" % srv.server_address[1]
shutil.copy("asistent_katastar.py", RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join("..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
SLIKE = os.path.dirname(os.path.abspath(__file__))
UVECANJE = float(os.environ.get("TEST_UVECANJE", "1.0"))
GRESKE, PORUKE = [], []
S = mock_sajt.STANJE
S["stanova"] = 30
S["nep_sesija"] = True
Z = {"opstina_id": 70106, "opstina": "ВОЖДОВАЦ", "ko_id": 703800, "ko": "КУМОДРАЖ", "broj": "10383"}


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def nadji_kod(svg):
    for k, v in mock_sajt.SVG.items():
        if v == svg:
            return mock_sajt.CAPTCHE[k]


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), True)[1]


ak.messagebox = TihiMessagebox()
ak.posalji_obavestenje = lambda naslov, redovi: None
ak.Pretraga.pauza = lambda self, raspon: None
root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: nadji_kod(svg)
DIJALOZI = []
app._dijalog_podataka = lambda naslov, *a, **k: (DIJALOZI.append(naslov), ("Klijent Cela", "", ""))[1]


def cekaj(uslov, sekundi=60):
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


def slikaj(ime):
    root.update()
    if UVECANJE != 1.0:
        ime = "u%d_%s" % (round(UVECANJE * 100), ime)
    subprocess.run(["import", "-window", "root", os.path.join(SLIKE, ime)], check=False)


def red_baze():
    return next((x for x in app.baza.parcele() if x["broj"] == "10383"), None)


def vidljivo(w):
    root.update()
    return bool(w.winfo_manager()) and w.winfo_ismapped()


app._pokreni([dict(Z)], "pretraga")
ok(cekaj(lambda: app.posao is None, 120), "pretraga završena")
app.tree_p.selection_set("r1")
app.detalji_pretrage()
root.update()
p = app._panel
d = app.rezultati["r1"][1]
stan = lambda i: next(k for k in d["nep_id"] if (", stan %d, " % i) in k)
b = p["btn_prati_celu"]
ok(vidljivo(b) and b.cget("text") == "Prati celu parcelu", "prozor parcele (nije u praćenju): dugme „Prati celu parcelu“")
ok(red_baze() is None, "parcela još nije u praćenju")
slikaj("prati_celu_dugme.png")

# dugme: prati se cela parcela
PORUKE.clear()
b.invoke()
root.update()
r = red_baze()
ok(DIJALOZI and "Prati celu parcelu" in DIJALOZI[-1], "pita za klijenta: %s" % DIJALOZI[-1:])
ok(r is not None and ak.pracene_stavke(r) == [] and r["klijent"] == "Klijent Cela", "u bazi: cela parcela (bez izbora stavki)")
sn = json.loads(r["snimak"])
ok(len(sn["posebni"]) == len(d["posebni"]) >= 30 and len(sn["objekti"]) == len(d["objekti"]) >= 1, "snimak: svi delovi, zgrade i %d posebnih delova" % len(sn["posebni"]))
info = [x for x in PORUKE if x[0] == "showinfo"]
ok(info and "cela parcela" in info[-1][2] and ("%d posebnih delova" % len(d["posebni"])) in info[-1][2] and "svaku promenu" in info[-1][2],
   "poruka: %s" % (info[-1][2].replace("\n", " ") if info else ""))
ok(p["lbl_prati"].cget("text") == "U praćenju: cela parcela", "natpis: %s" % p["lbl_prati"].cget("text"))
ok(not vidljivo(b), "dugme se sklanja kad se prati cela parcela")
ok("[prati se samo" not in app.tree.item(str(r["id"]), "text"), "lista praćenja: cela parcela (%s)" %
   app.tree.item(str(r["id"]), "text"))

# provera cele parcele: javlja promenu bilo kog stana
app.proveri(False)
ok(cekaj(lambda: app.posao is None, 120), "prva provera")
S["vlasnik_stana"][7] = "НОВИ ВЛАСНИК 7"
app.sesija_novo.clear()
n0 = len(S["nep_upiti"])
app.proveri(False)
ok(cekaj(lambda: app.posao is None, 120), "druga provera")
pr = app.sesija_novo.get(r["id"]) or []
ok(len(S["nep_upiti"]) - n0 >= 30, "provera cele parcele skida sve stavke (%d)" % (len(S["nep_upiti"]) - n0))
ok(any("НОВИ ВЛАСНИК 7" in x for x in pr), "promena vlasnika stana 7 se javlja: %s" % pr[:2])

# desni klik i dalje: samo izabrani stan
PORUKE.clear()
app._prati(p, [stan(12)])
cekaj(lambda: app.posao is None, 60)
r = red_baze()
ok(any(x[0] == "askyesno" and "prati se cela parcela" in x[2] for x in PORUKE) and ak.pracene_stavke(r) == [stan(12)],
   "„Prati samo ovu stavku“: pita, pa prati samo stan 12")
ok(vidljivo(b) and p["lbl_prati"].cget("text") == "U praćenju: samo stan 12", "dugme „Prati celu parcelu“ se vraća")

# dugme kad se prati samo stan: pita, pa cela parcela
PORUKE.clear()
b.invoke()
root.update()
r = red_baze()
ok(any(x[0] == "askyesno" and "cela parcela" in x[2] and "stan 12" in x[2] for x in PORUKE) and
   ak.pracene_stavke(r) == [], "dugme posle stana: pita, pa cela parcela")
ok(not vidljivo(b) and p["lbl_prati"].cget("text") == "U praćenju: cela parcela", "natpis: cela parcela, dugme sklonjeno")

# odgovor „Ne“: ostaje samo stan
app._prati(p, [stan(12)])
cekaj(lambda: app.posao is None, 60)
ak.messagebox = type("M", (), {"__getattr__": lambda self, ime: lambda *a, **k: (PORUKE.append((ime,) + a), ime != "askyesno")[1]})()
b.invoke()
root.update()
ok(ak.pracene_stavke(red_baze()) == [stan(12)], "na pitanje „Ne“: i dalje samo stan 12")
ak.messagebox = TihiMessagebox()

# prozor iz liste praćenja (samo praćeno, v26): isto dugme
for w in [w for w in root.winfo_children() if isinstance(w, ak.tk.Toplevel) and w is not app.log_prozor]:
    w.destroy()
app.detalji(red_baze()["id"])
root.update()
w = [w for w in root.winfo_children() if isinstance(w, ak.tk.Toplevel) and hasattr(w, "panel")][-1]
pn = w.panel
ok(pn["filter_prikazan"] and vidljivo(pn["btn_prati_celu"]), "prozor iz liste (samo stan 12): ima „Prati celu parcelu“")
slikaj("prati_celu_iz_liste.png")
pn["btn_prati_celu"].invoke()
root.update()
ok(ak.pracene_stavke(red_baze()) == [] and not pn["filter_prikazan"] and len(pn["tabele"]["p"].get_children("")) >= 30
   and not vidljivo(pn["btn_prati_celu"]) and not vidljivo(pn["btn_filter"]),
   "posle dugmeta: cela parcela u prikazu, bez dugmadi za izbor")
root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
