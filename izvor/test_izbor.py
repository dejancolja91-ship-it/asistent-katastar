# -*- coding: utf-8 -*-
"""v21: pretraga prvo samo prikaze sve stavke parcele (parcela, zgrade, 193 stana), u prozoru parcele se oznaci
sta se skida (kvadratic na pocetku reda), "Skini oznacene" / "Skini sve"; skida se preko sesije pretrage bez
captche, a kad sesija istekne parcela se trazi ponovo i skida se samo izabrano."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

RAD = tempfile.mkdtemp(prefix="kat_izbor_")
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
GRESKE = []
PORUKE = []
STANOVA = 193
mock_sajt.STANJE["stanova"] = STANOVA
mock_sajt.STANJE["nep_sesija"] = True          # nepID vazi samo u sesiji koja je videla rezultat


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def nadji_kod(svg):
    for k, v in mock_sajt.SVG.items():
        if v == svg:
            return mock_sajt.CAPTCHE[k]


def nep_upiti():
    return list(mock_sajt.STANJE["nep_upiti"])


def pretrage():
    return len([z for z in mock_sajt.STANJE["zahtevi"] if z[0] == "POST" and z[1] == "FindParcela.aspx"])


Z = {"opstina_id": 70106, "opstina": "ВОЖДОВАЦ", "ko_id": 703800, "ko": "КУМОДРАЖ", "broj": "10383"}
MESTO = (703800, "КУМОДРАЖ", "10383")


def posao(sa_nep=None, samo=None, direktno=None, strana=None):
    rez, kraj, log = [], threading.Event(), []
    pos = ak.Pretraga(None, True, sa_nep, lambda svg, opis: nadji_kod(svg), lambda m, t="": log.append(m),
                      lambda p: kraj.set())
    pos.samo, pos.direktno = samo, direktno
    stigle = []
    pos.strana = lambda ime, html: stigle.append(ime)
    pos.rezultat = lambda z, d, r: rez.append((z, d, r))
    pos.pokreni([dict(Z)])
    ok(kraj.wait(120), "posao završen")
    return pos, rez, stigle, log


# 1. logika posla
PAUZA = ak.Pretraga.pauza
ak.Pretraga.pauza = lambda self, raspon: None
n0, s0 = len(nep_upiti()), pretrage()
pos, rez, stigle, _ = posao()
d = rez[0][1]
M = len(d["nep_id"])
ok(M == STANOVA + 3 and not d["nepokretnost"] and len(nep_upiti()) == n0,
   "samo spisak: %d stavki poznato, ništa nije skinuto (%d zahteva)" % (M, len(nep_upiti()) - n0))
ok(list(d["nep_id"]) == d["nep_redosled"] and d["nep_redosled"][0] == "parcela", "spisak redom kao na sajtu")
stan = lambda i: next(k for k in d["nep_id"] if (", stan %d, " % i) in k)
izabrano = {stan(12), stan(150), "parcela"}
n0 = len(nep_upiti())
pos, rez, stigle, _ = posao(samo=izabrano)
d2 = rez[0][1]
ok(set(d2["nepokretnost"]) == izabrano and sorted(nep_upiti()[n0:]) == sorted(["S012=", "S150=", "g+3wBfRKrlQ="]),
   "samo izabrano (3): %s" % nep_upiti()[n0:])
ok(d2["nep_potpuno"] is False and set(stigle) == izabrano, "izabrano: nije 'potpuno', svaka stranica javljena")
# ista sesija: bez nove pretrage
ses = {"sajt": pos.sajt, "nid": d2["nep_id"], "naslov": "КУМОДРАЖ 10383"}
n0, s0 = len(nep_upiti()), pretrage()
pos3, rez3, stigle3, _ = posao(samo={stan(77)}, direktno=ses)
ok(pretrage() == s0 and nep_upiti()[n0:] == ["S077="] and stigle3 == [stan(77)] and not rez3,
   "ista sesija: bez pretrage i captche, samo stan 77 (%s)" % nep_upiti()[n0:])
# sesija istekla: nova pretraga, pa samo izabrano
mock_sajt.SESIJE.clear()
n0, s0 = len(nep_upiti()), pretrage()
pos4, rez4, stigle4, log4 = posao(samo={stan(88), stan(99)}, direktno=ses)
ok(pretrage() == s0 + 1, "istekla sesija: parcela ponovo tražena (jedna captcha)")
ok(nep_upiti()[n0] in ("S088=", "S099=") and sorted(nep_upiti()[n0 + 1:]) == ["S088=", "S099="],
   "posle neuspelog pokušaja skinuto samo izabrano: %s" % nep_upiti()[n0:])
ok(rez4 and set(rez4[0][1]["nepokretnost"]) == {stan(88), stan(99)} and set(stigle4) == {stan(88), stan(99)},
   "rezultat nove pretrage ima samo izabrano")
ok(any("sesija sa sajta vise ne vazi" in m for m in log4), "poruka da je sesija istekla")
ak.Pretraga.pauza = PAUZA

if not os.environ.get("DISPLAY"):
    print("\nUKUPNO GRESAKA:", len(GRESKE))
    sys.exit(1 if GRESKE else 0)


# 2. prozor
class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), True)[1]


ak.messagebox = TihiMessagebox()
ak.posalji_obavestenje = lambda naslov, redovi: None
root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: nadji_kod(svg)


def cekaj(uslov, sekundi=60):
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


def slikaj(ime, w=None):
    root.update()
    if UVECANJE != 1.0:
        ime = "u%d_%s" % (round(UVECANJE * 100), ime)
    subprocess.run(["import", "-window", "root", os.path.join(SLIKE, ime)], check=False)


def prozori():
    return [w for w in root.winfo_children() if isinstance(w, ak.tk.Toplevel) and w.winfo_exists()]


def tekst(w):
    return getattr(w, "_tekst", "") or ""


ok(app.nep_pretraga_var.get() == "spisak", "podrazumevano: pretraga samo prikaže stavke")
meni = [app.root.nametowidget(app.root["menu"])]
stavke_menija = []
for m in meni:
    for i in range(m.index("end") + 1):
        if m.type(i) == "cascade":
            sub = m.nametowidget(m.entrycget(i, "menu"))
            stavke_menija += [sub.entrycget(j, "label") for j in range(sub.index("end") + 1)
                              if sub.type(j) in ("radiobutton", "checkbutton", "command")]
ok(any("samo prikaži sve stavke" in x for x in stavke_menija) and any("odmah skini sve" in x for x in stavke_menija),
   "Alati: izbor 'samo prikaži sve stavke' / 'odmah skini sve'")

n0 = len(nep_upiti())
app._pokreni([dict(Z)], "pretraga")
ok(app.posao.sa_nep is None, "pretraga bez skidanja podataka o nepokretnosti")
ok(cekaj(lambda: app.posao is None, 120), "pretraga završena")
ok(len(nep_upiti()) == n0, "ništa nije skinuto sa sajta (%d)" % (len(nep_upiti()) - n0))
ok(("703800", "10383") in app._sesije and len(app._sesije[("703800", "10383")]["nid"]) == M, "sesija pretrage zapamćena")
ok("na sajtu %d stavki" % M in app.txt.get("1.0", "end"), "u porukama: koliko stavki ima na sajtu")
app.tree_p.selection_set("r1")
app.detalji_pretrage()
root.update()
p = app._panel
tp, to, tpos = p["tabele"]["parcela"], p["tabele"]["o"], p["tabele"]["p"]
img = {str(v): k for k, v in app._slike_izbora.items()}
slika = lambda tr, iid: img.get(str(tr.item(iid, "image")[0] if tr.item(iid, "image") else ""))
iid_stana = lambda i: next(x[0] for x in p["stavke"].values() if x[4] == stan(i))
ok(len(tpos.get_children("")) == STANOVA + 0 or len(tpos.get_children("")) >= STANOVA,
   "u prozoru svi stanovi objekta (%d)" % len(tpos.get_children("")))
ok(all(slika(tr, i) == "ne" for tr in (tp, to, tpos) for i in tr.get_children("") if i != "prazno"),
   "svi redovi: prazan kvadratić (nije skinuto)")
ok(str(p["btn_oznacene"].cget("state")) == "disabled" and p["btn_oznacene"].cget("text") == "Skini označene (0)",
   "Skini označene (0) isključeno")
ok(p["btn_sve"].cget("text") == "Skini sve (%d)" % M and str(p["btn_sve"].cget("state")) == "normal",
   "Skini sve (%d)" % M)


def klik_kvadrat(tr, iid):
    tr.see(iid)
    root.update()
    bb = tr.bbox(iid, "#0")
    tr.event_generate("<Button-1>", x=bb[0] + bb[2] // 2, y=bb[1] + bb[3] // 2)
    root.update()


i12 = iid_stana(12)
klik_kvadrat(tpos, i12)
ok(slika(tpos, i12) == "da" and p["btn_oznacene"].cget("text") == "Skini označene (1)"
   and str(p["btn_oznacene"].cget("state")) == "normal", "klik na kvadratić: stan 12 označen")
klik_kvadrat(tpos, i12)
ok(slika(tpos, i12) == "ne" and p["btn_oznacene"].cget("text") == "Skini označene (0)", "drugi klik: odznačen")
klik_kvadrat(tpos, i12)
klik_kvadrat(tp, "parcela_0")
ok(all(slika(tp, i) == "da" for i in tp.get_children("")), "parcela označena (svi delovi parcele)")
i150 = iid_stana(150)
tpos.see(i150)
tpos.focus(i150)
tpos.focus_set()
tpos.event_generate("<space>")
root.update()
ok(slika(tpos, i150) == "da" and p["btn_oznacene"].cget("text") == "Skini označene (3)", "razmak označava stan 150")
ok(PORUKE == [], "klik na kvadratić ne otvara ništa drugo")


class Dog:
    def __init__(self, x, y):
        self.x, self.y = x, y


bb = tpos.bbox(i150, "#0")
pre = set(prozori())
ok(app._otvori_iz_panela(p, "p", Dog(bb[0] + 3, bb[1] + 3)) == "break" and set(prozori()) == pre
   and slika(tpos, i150) == "ne", "brz drugi klik na kvadratić: odznači, ne otvara prozor")
app._otvori_iz_panela(p, "p", Dog(bb[0] + 3, bb[1] + 3))
ok(slika(tpos, i150) == "da", "i ponovo označi")
slikaj("izbor_stavki.png")
n0, s0 = len(nep_upiti()), pretrage()
p["btn_oznacene"].invoke()
root.update()
ok(app.posao is not None and str(p["btn_oznacene"].cget("state")) == "disabled", "Skini označene: skidanje u toku")
ok(cekaj(lambda: app.posao is None, 60), "skidanje završeno")
cekaj(lambda: False, 0.3)
ok(pretrage() == s0 and sorted(nep_upiti()[n0:]) == sorted(["S012=", "S150=", "g+3wBfRKrlQ="]),
   "bez nove pretrage i captche, skinuto samo označeno: %s" % nep_upiti()[n0:])
ok(slika(tpos, i12) == "ima" and slika(tpos, i150) == "ima" and slika(tp, "parcela_0") == "ima",
   "skinute stavke: zelena kvačica")
ok("ВЛАСНИК СТАНА 12" in tpos.item(i12, "values")[-1], "vlasnik stana 12 u tabeli: %s" % tpos.item(i12, "values")[-1])
ok(tp.item("parcela_0", "values")[-1] != "", "vlasnici parcele u tabeli")
ok(slika(tpos, iid_stana(13)) == "ne", "ostali stanovi nisu skinuti")
ok(p["stanje"].cget("text") == "Skinuto sa sajta: 3 od 3", "prozor: %s" % p["stanje"].cget("text"))
ok(app.lbl_opis.cget("text") == "Skinuto sa sajta: 3 od 3 (КУМОДРАЖ 10383)", "statusna linija: %s" % app.lbl_opis.cget("text"))
ok(p["btn_oznacene"].cget("text") == "Skini označene (0)" and not p["oznaceno"], "ništa više nije označeno")
z, dr, _ = app.rezultati["r1"]
ok(set(dr["nepokretnost"]) == {"parcela", stan(12), stan(150)} and app.tree_p.item("r1", "values")[7] != "",
   "red u rezultatima: skinuti podaci i vlasnici parcele")
dz = ak.dir_izvoda(*MESTO)
ok(set(json.load(open(os.path.join(dz, "indeks.json"), encoding="utf-8"))) == {"parcela", stan(12), stan(150)},
   "izvodi: 3 stranice")
x12 = p["stavke"][i12]
w12 = app._prozor_nepokretnosti(x12[2], x12[3], p["mesto"], x12[4])
ok("ВЛАСНИК СТАНА 12" in tekst(w12) and not hasattr(w12, "_dugme_ucitaj"), "stan 12 se otvara sa podacima")
w12.destroy()

# prozor stana koji nije skinut: "Skini sa sajta" skida samo njega
x77 = p["stavke"][iid_stana(77)]
w77 = app._prozor_nepokretnosti(x77[2], x77[3], p["mesto"], x77[4])
root.update()
ok(hasattr(w77, "_dugme_ucitaj") and w77._dugme_ucitaj.cget("text") == "Skini sa sajta" and "nisu skinuti" in tekst(w77),
   "stan 77: dugme „Skini sa sajta“")
n0 = len(nep_upiti())
w77._dugme_ucitaj.invoke()
ok(cekaj(lambda: any("ВЛАСНИК СТАНА 77" in tekst(w) for w in prozori()), 30), "stan 77 skinut i prikazan")
ok(cekaj(lambda: app.posao is None, 30) and nep_upiti()[n0:] == ["S077="], "samo stan 77: %s" % nep_upiti()[n0:])
ok(slika(tpos, iid_stana(77)) == "ima", "i u prozoru parcele stan 77 zelen")
for w in prozori():
    if w is not p["tabele"]["parcela"].winfo_toplevel():
        w.destroy()

# sesija istekla: nova pretraga (captcha), pa samo izabrano; red u rezultatima ostaje jedan
mock_sajt.SESIJE.clear()
klik_kvadrat(tpos, iid_stana(100))
n0, s0 = len(nep_upiti()), pretrage()
p["btn_oznacene"].invoke()
ok(cekaj(lambda: app.posao is None, 60), "skidanje posle istekle sesije završeno")
ok(pretrage() == s0 + 1 and nep_upiti()[n0:] == ["S100=", "S100="], "nova pretraga, pa samo stan 100: %s" % nep_upiti()[n0:])
cekaj(lambda: False, 0.3)
ok(slika(tpos, iid_stana(100)) == "ima" and slika(tpos, i12) == "ima", "stan 100 zelen, ranije skinuti ostaju zeleni")
ok(list(app.rezultati) == ["r1"], "u rezultatima i dalje jedan red")
ok(set(app.rezultati["r1"][1]["nepokretnost"]) >= {"parcela", stan(12), stan(150), stan(77), stan(100)},
   "red zadržava sve skinute stavke: %d" % len(app.rezultati["r1"][1]["nepokretnost"]))
ix = json.load(open(os.path.join(dz, "indeks.json"), encoding="utf-8"))
ok(set(ix) == {"parcela", stan(12), stan(150), stan(77), stan(100)}, "izvodi: 5 stranica (%d)" % len(ix))

# Prekini posle 3 od 10: neskinuto ostaje označeno
mock_sajt.STANJE["nep_kasni"] = 0.2
deset = [iid_stana(i) for i in range(20, 30)]
for i in deset:
    klik_kvadrat(tpos, i)
ok(p["btn_oznacene"].cget("text") == "Skini označene (10)", "označeno 10")
p["btn_oznacene"].invoke()
ok(cekaj(lambda: app._ceka_stavku and len(app._ceka_stavku["stigle"]) >= 3, 30), "stiglo 3")
pre = set(prozori())
tudji = app._prozor_nepokretnosti("Stan 1", [], (703621, "ВОЖДОВАЦ", "4415"), "poseban deo X, ulaz 1, stan 1, evid. 1, СТАН")
PORUKE.clear()
tudji._dugme_ucitaj.invoke()
ok(PORUKE and "U toku je" in PORUKE[-1][2], "dok traje skidanje druga stavka čeka: poruka")
tudji.destroy()
app._prekini()
ok(cekaj(lambda: app.posao is None, 30), "prekinuto")
mock_sajt.STANJE["nep_kasni"] = 0.0
cekaj(lambda: False, 0.3)
n_ima = sum(slika(tpos, i) == "ima" for i in deset)
ok(3 <= n_ima < 10 and sum(slika(tpos, i) == "da" for i in deset) == 10 - n_ima,
   "skinuto %d, ostalih %d i dalje označeno" % (n_ima, 10 - n_ima))
ok(p["btn_oznacene"].cget("text") == "Skini označene (%d)" % (10 - n_ima) and
   str(p["btn_oznacene"].cget("state")) == "normal", "dugme: %s" % p["btn_oznacene"].cget("text"))
ok(p["stanje"].cget("text").startswith("Skinuto %d od 10. Šta nije skinuto ostalo je označeno" % n_ima),
   "prozor: %s" % p["stanje"].cget("text"))
ok(app.lbl_opis.cget("text").startswith("Prekinuto - Skinuto sa sajta: %d od 10" % n_ima), "status: %s" % app.lbl_opis.cget("text"))
p["btn_oznacene"].invoke()
ok(cekaj(lambda: app.posao is None, 60) and all(slika(tpos, i) == "ima" for i in deset), "ponovo: skinuto ostalo")

# parcela u pracenju, sesija istekla: provera skida samo izabrano, snimak zadrzava sve
app._dijalog_podataka = lambda naslov, *a, **k: ("Klijent Zgrada", "", "")
app.tree_p.selection_set("r1")
app.dodaj_iz_pretrage()
root.update()
par = [x for x in app.baza.parcele() if x["broj"] == "10383"][0]
n_pre = len(json.loads(par["snimak"])["nepokretnost"])
ok(app._zadatak_za(MESTO)[1] == "provera" and n_pre == 15, "u praćenju, snimak sa %d skinutih stavki" % n_pre)
mock_sajt.SESIJE.clear()
klik_kvadrat(tpos, iid_stana(180))
p["btn_oznacene"].invoke()
root.update()
ok(app.rezim == "provera", "parcela u praćenju: provera")
ok(cekaj(lambda: app.posao is None, 60), "provera završena")
par = [x for x in app.baza.parcele() if x["broj"] == "10383"][0]
sn = json.loads(par["snimak"])
ok(len(sn["nepokretnost"]) == n_pre + 1 and stan(180) in sn["nepokretnost"], "snimak: %d stavki (+ stan 180)" % len(sn["nepokretnost"]))
ok(not app.sesija_novo.get(par["id"]), "bez lažne promene")
ok(slika(tpos, iid_stana(180)) == "ima", "stan 180 zelen")

# Skini sve
cekaj(lambda: False, 0.3)
n0, s0 = len(nep_upiti()), pretrage()
p["btn_sve"].invoke()
ok(cekaj(lambda: app.posao is None, 240), "Skini sve završeno")
ok(pretrage() == s0 and len(nep_upiti()) - n0 == M, "Skini sve: %d stranica, bez nove pretrage" % (len(nep_upiti()) - n0))
cekaj(lambda: False, 0.3)
ok(all(slika(tr, i) == "ima" for tr in (tp, to, tpos) for i in tr.get_children("") if i != "prazno"), "sve zeleno")
ix = json.load(open(os.path.join(dz, "indeks.json"), encoding="utf-8"))
ok(len(ix) == M and list(ix) == d["nep_redosled"], "izvodi: svih %d, redom kao na sajtu" % len(ix))
ok(p["stanje"].cget("text") == "Skinuto sa sajta: %d od %d" % (M, M), "prozor: %s" % p["stanje"].cget("text"))
slikaj("izbor_skinuto.png")

# novi prozor parcele (iz praćenja) vidi skinute stavke iz izvodi/
pre = set(prozori())
par = [x for x in app.baza.parcele() if x["broj"] == "10383"][0]
w = app._prozor_detalja("test", json.loads(par["snimak"]), [], p=par, mesto=MESTO)
root.update()
p2 = app._panel
ok(p2 is not p and p2["ucitano"] >= set(ix) and slika(p2["tabele"]["p"], iid_stana(5)) == "ima"
   and "ВЛАСНИК СТАНА 5" in p2["tabele"]["p"].item(iid_stana(5), "values")[-1],
   "novi prozor parcele: skinute stavke zelene, vlasnici iz izvoda")
w.destroy()

# podesavanje "odmah skini sve"
app.nep_pretraga_var.set("sve")
ok(app.baza.podesavanje("nep_pretraga") == "sve", "podešavanje se pamti")
app._pokreni([dict(Z)], "pretraga")
ok(app.posao.sa_nep == "sve", "'odmah skini sve': pretraga skida sve")
app._prekini()
cekaj(lambda: app.posao is None, 30)
app.nep_pretraga_var.set("spisak")
root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
