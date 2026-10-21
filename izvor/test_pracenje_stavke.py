# -*- coding: utf-8 -*-
"""v22: pracenje samo izabranih stavki parcele (Dejan: "samo stan 56, ne cela parcela ni ostali stanovi").
Desni klik u prozoru parcele > "Prati samo ovu stavku" / "Prati samo oznacene"; provera trazi parcelu, skida samo
pracene stavke i javlja samo njihove promene; stavka koja na sajtu promeni naziv (nacin koriscenja) se i dalje prati;
"Ne prati vise ovu stavku", "Prati celu parcelu"; stara baza dobija kolonu stavke."""
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

RAD = tempfile.mkdtemp(prefix="kat_prati_")
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
S = mock_sajt.STANJE
S["stanova"] = STANOVA
S["nep_sesija"] = True


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def nadji_kod(svg):
    for k, v in mock_sajt.SVG.items():
        if v == svg:
            return mock_sajt.CAPTCHE[k]


def nep_upiti():
    return list(S["nep_upiti"])


Z = {"opstina_id": 70106, "opstina": "ВОЖДОВАЦ", "ko_id": 703800, "ko": "КУМОДРАЖ", "broj": "10383"}
MESTO = (703800, "КУМОДРАЖ", "10383")

# 1. kljucevi i nazivi stavki
K56 = "poseban deo УСТАНИЧКА 1, ulaz 1, stan 56, evid. 56, СТАН"
nacin = lambda k, n: k.rsplit(", ", 1)[0] + ", " + n          # isti ključ, drugi način korišćenja
ok(ak.opis_stavke(K56) == "stan 56", "naziv: %s" % ak.opis_stavke(K56))
ok(ak.opis_stavke("poseban deo X 2, ulaz 2, stan 3, evid. 9, ГАРАЖНИ ПРОСТОР") == "гаражни простор 3, ulaz 2",
   "naziv garaže: %s" % ak.opis_stavke("poseban deo X 2, ulaz 2, stan 3, evid. 9, ГАРАЖНИ ПРОСТОР"))
ok(ak.opis_stavke("parcela") == "parcela" and ak.opis_stavke("objekat УСТАНИЧКА 1") == "zgrada УСТАНИЧКА 1",
   "naziv parcele i zgrade")
ok(ak.opis_stavke("poseban deo X, ulaz , stan , evid. 7,") == "poseban deo evid. 7", "bez broja stana: evid.")
ok(ak.nadji_kljuc(K56, ["parcela", K56]) == K56, "isti ključ")
k56b = nacin(K56, "ПОСЛОВНИ ПРОСТОР")
ok(ak.nadji_kljuc(K56, ["parcela", k56b, K56.replace("stan 56, evid. 56", "stan 57, evid. 57")]) == k56b,
   "promenjen način korišćenja: nađen po objektu i evid. broju")
k_br = K56.replace("stan 56", "stan 56A")
ok(ak.nadji_kljuc(K56, [k_br]) == k_br, "prenumerisan stan, isti evid. broj")
k99 = nacin(K56.replace("evid. 56", "evid. 99"), "СТАН1")
ok(ak.nadji_kljuc(K56, [k99, nacin(K56.replace("stan 56, evid. 56", "stan 5, evid. 5"), "Б")]) == k99,
   "nov evid. broj: nađen po ulazu i stanu")
ok(ak.nadji_kljuc(K56, [nacin(K56.replace("УСТАНИЧКА 1", "УСТАНИЧКА 3"), "С")]) is None,
   "druga zgrada: nije ista stavka")
dva = [nacin(K56, "А"), nacin(K56, "Б")]
ok(ak.nadji_kljuc(K56, dva) is None, "dve moguće stavke: ne pogađa se")
ok(ak.nadji_kljuc("objekat УСТАНИЧКА 1", ["objekat УСТАНИЧКА 1 А"]) is None, "zgrada: samo isti ključ")
ok(ak.nadji_kljuc(K56 + " (2)", [K56, K56 + " (2)"]) == K56 + " (2)", "dupli naziv (2)")
ok(ak.pracene_stavke({"stavke": None}) == [] and ak.pracene_stavke({"stavke": "nije json"}) == [] and
   ak.pracene_stavke({"stavke": json.dumps([K56])}) == [K56], "čitanje praćenih stavki iz baze")

# stara baza (v21, bez kolone stavke): kolona se doda, podaci ostaju
staro = os.path.join(RAD, "stara.db")
c = sqlite3.connect(staro)
c.executescript("""CREATE TABLE parcele (id INTEGER PRIMARY KEY AUTOINCREMENT, opstina_id INTEGER, opstina TEXT,
    ko_id INTEGER NOT NULL, ko TEXT, broj TEXT NOT NULL, klijent TEXT DEFAULT '', grupa TEXT DEFAULT '',
    napomena TEXT DEFAULT '', dodat TEXT, provereno TEXT, snimak TEXT, pokusaj TEXT, greska TEXT, promene TEXT,
    promena_vreme TEXT, arhivirano TEXT, odlozeno_do TEXT, UNIQUE(ko_id, broj));
    INSERT INTO parcele (opstina, ko_id, ko, broj, klijent) VALUES ('O', 1, 'K', '5', 'Neko');""")
c.commit()
c.close()
b = ak.Baza(staro)
ok([p["klijent"] for p in b.parcele()] == ["Neko"] and "stavke" in b.parcele()[0] and b.parcele()[0]["stavke"] is None,
   "stara baza: dodata kolona stavke, parcela ostala")


# 2. posao: prate se samo izabrane stavke
def posao(stavke=None, samo=None, sa_nep="sve"):
    rez, kraj, log = [], threading.Event(), []
    pos = ak.Pretraga(None, False, sa_nep, lambda svg, opis: nadji_kod(svg), lambda m, t="": log.append(m),
                      lambda p: kraj.set())
    pos.samo = samo
    pos.rezultat = lambda z, d, r: rez.append((z, d, r))
    z = dict(Z)
    if stavke:
        z["stavke"] = list(stavke)
    n0 = len(nep_upiti())
    pos.pokreni([z])
    ok(kraj.wait(120), "posao završen")
    return rez[0][1], nep_upiti()[n0:]


PAUZA = ak.Pretraga.pauza
ak.Pretraga.pauza = lambda self, raspon: None
d0, upiti = posao(sa_nep=None)
stan = lambda d, i: next(k for k in d["nep_id"] if (", stan %d, " % i) in k)
k56 = stan(d0, 56)
d1, upiti = posao([k56])
ok(upiti == ["S056="], "praćenje stana 56 (i kad je 'skini sve' uključeno): skida se samo stan 56 (%s)" % upiti[:5])
ok(list(d1["nepokretnost"]) == [k56] and d1["nep_potpuno"] is False, "u rezultatu samo stan 56, nije 'potpuno'")
ok(len(d1["posebni"]) >= STANOVA, "tabele cele parcele i dalje učitane (%d posebnih delova)" % len(d1["posebni"]))
sn1 = ak.napravi_snimak(d1)
S["vlasnik_stana"][57] = "ДРУГИ ВЛАСНИК 57"
S["povrsina_stana"][60] = 99
VLASNIK = S["vlasnik"]
S["vlasnik"] = "НОВИ ВЛАСНИК ПАРЦЕЛЕ"
d2, upiti = posao([k56])
sn2 = ak.napravi_snimak(d2)
mapa = {k56: ak.nadji_kljuc(k56, d2["nep_redosled"])}
ok(ak.poredi_stavke(sn1, sn2, mapa) == [], "promene drugih stanova i parcele se ne javljaju: %s" % ak.poredi_stavke(sn1, sn2, mapa))
ok(any("99" in x for x in ak.poredi(sn1, sn2)), "(cela parcela bi javila promenu stana 60)")
S["vlasnik_stana"][56] = "НОВИ ВЛАСНИК 56"
d3, upiti = posao([k56])
sn3 = ak.napravi_snimak(d3)
pr = ak.poredi_stavke(sn2, sn3, {k56: ak.nadji_kljuc(k56, d3["nep_redosled"])})
ok(any("НОВИ ВЛАСНИК 56" in x and x.startswith(k56 + ": novo") for x in pr) and
   any("ВЛАСНИК СТАНА 56" in x and ": uklonjeno" in x for x in pr), "nov vlasnik stana 56 se javlja: %s" % pr)
S["nacin_stana"][56] = "ПОСЛОВНИ ПРОСТОР"
d4, upiti = posao([k56])
k56n = ak.nadji_kljuc(k56, d4["nep_redosled"])
ok(k56n and k56n != k56 and "ПОСЛОВНИ ПРОСТОР" in k56n and upiti == ["S056="],
   "promenjen način korišćenja: stavka nađena i skinuta (%s)" % upiti)
pr = ak.poredi_stavke(ak.napravi_snimak(d3), ak.napravi_snimak(d4), {k56: k56n})
ok(any(x.startswith("novo - poseban deo") and "ПОСЛОВНИ ПРОСТОР" in x for x in pr) and
   any(x.startswith("uklonjeno - poseban deo") and "СТАН" in x for x in pr) and len(pr) == 2,
   "javlja se promena reda u tabeli: %s" % pr)
S["bez_stana"].add(56)
d5, upiti = posao([k56n])
ok(ak.nadji_kljuc(k56n, d5["nep_redosled"]) is None and "S056=" not in upiti, "stana 56 više nema: ne skida se")
pr = ak.poredi_stavke(ak.napravi_snimak(d4), ak.napravi_snimak(d5), {k56n: None})
ok(len(pr) == 1 and "više nije na sajtu" in pr[0] and "пословни простор 56" in pr[0], "javlja se: %s" % pr)
ok(ak.poredi_stavke(ak.napravi_snimak(d5), ak.napravi_snimak(d5), {k56n: None}) == [], "i samo jednom")
for k in ("vlasnik_stana", "povrsina_stana", "nacin_stana"):
    S[k].clear()
S["bez_stana"].clear()
S["vlasnik"] = VLASNIK
ak.Pretraga.pauza = PAUZA

if not os.environ.get("DISPLAY"):
    print("\nUKUPNO GRESAKA:", len(GRESKE))
    sys.exit(1 if GRESKE else 0)


# 3. prozor
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
app._dijalog_podataka = lambda naslov, *a, **k: (PORUKE.append(("dijalog", naslov)), ("Klijent Stan", "", ""))[1]


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


MENI = []


def desni_klik(tr, iid):
    """Desni klik na red: vraca [(natpis, meni, indeks)] stavki menija."""
    MENI.clear()
    stari = ak.tk.Menu.tk_popup
    ak.tk.Menu.tk_popup = lambda self, *a: MENI.extend(
        (self.entrycget(i, "label"), self, i) for i in range(self.index("end") + 1) if self.type(i) == "command")
    tr.see(iid)
    root.update()
    x, y, w_, h = tr.bbox(iid, "0")             # prva kolona posle kvadratića (Објекат)
    tr.event_generate("<Button-3>", x=x + 10, y=y + h // 2, rootx=tr.winfo_rootx() + x + 10,
                      rooty=tr.winfo_rooty() + y + h // 2)
    root.update()
    ak.tk.Menu.tk_popup = stari
    return [m[0] for m in MENI]


def izaberi(pocetak):
    m = next((m for m in MENI if m[0].startswith(pocetak)), None)
    if m:
        m[1].invoke(m[2])
        root.update()
    return m is not None


def red_baze():
    return next(x for x in app.baza.parcele() if x["broj"] == "10383")


def proveri_sve():
    n0 = len(nep_upiti())
    app.proveri(False)
    ok(cekaj(lambda: app.posao is None, 120), "provera završena")
    cekaj(lambda: False, 0.2)
    return nep_upiti()[n0:]


app._pokreni([dict(Z)], "pretraga")
ok(cekaj(lambda: app.posao is None, 120), "pretraga završena")
app.tree_p.selection_set("r1")
app.detalji_pretrage()
root.update()
p = app._panel
tp, tpos = p["tabele"]["parcela"], p["tabele"]["p"]
d = app.rezultati["r1"][1]
iid_stana = lambda i: next(x[0] for x in p["stavke"].values() if x[4] == stan(d, i))
ok(p["lbl_prati"].cget("text") == "", "parcela nije u praćenju: bez natpisa")
meni = desni_klik(tpos, iid_stana(56))
ok("Prati samo ovu stavku (stan 56)" in meni and not any(m.startswith(("Ne prati", "Prati celu")) for m in meni),
   "desni klik na stan 56: „Prati samo ovu stavku (stan 56)“ (%s)" % meni)
ok(meni == ["Skini sa sajta", "Prati samo ovu stavku (stan 56)", "Kopiraj „Објекат“"],
   "v24: kratak meni za neskinut stan (3 stavke): %s" % meni)
n0 = len(nep_upiti())
izaberi("Prati samo ovu stavku")
ok(PORUKE and PORUKE[0][0] == "dijalog" and "stan 56" in PORUKE[0][1], "pita za klijenta: %s" % PORUKE[:1])
ok(cekaj(lambda: app.posao is None, 30), "skidanje stana 56 završeno")
cekaj(lambda: False, 0.3)
ok(nep_upiti()[n0:] == ["S056="], "odmah skinut samo stan 56 (bez captche): %s" % nep_upiti()[n0:])
info = [x for x in PORUKE if x[0] == "showinfo"]
ok(info and "prati se samo stan 56" in info[-1][2] and "upravo skidaju" in info[-1][2], "poruka: %s" % (info[-1:],))
r = red_baze()
sn = json.loads(r["snimak"])
ok(ak.pracene_stavke(r) == [stan(d, 56)] and r["klijent"] == "Klijent Stan", "u bazi: prati se samo stan 56")
ok(stan(d, 56) in sn["nepokretnost"] and any("ВЛАСНИК СТАНА 56" in x for x in sn["nepokretnost"][stan(d, 56)]),
   "snimak ima podatke stana 56 (osnova za poređenje)")
ok(p["lbl_prati"].cget("text") == "U praćenju: samo stan 56", "prozor parcele: %s" % p["lbl_prati"].cget("text"))
ok("prati" in tpos.item(iid_stana(56), "tags") and "prati" not in tpos.item(iid_stana(57), "tags"),
   "stan 56 podebljan, ostali ne")
ok("[prati se samo: stan 56]" in app.tree.item(str(r["id"]), "text"), "lista praćenja: %s" % app.tree.item(str(r["id"]), "text"))
ok(app.tree.item(str(r["id"]), "values")[0] == "КУМОДРАЖ  10383", "kolona KO / parcela ostaje (Kopiraj broj parcele)")
tpos.yview_moveto((tpos.index(iid_stana(56)) - 4) / len(tpos.get_children("")))
tpos.selection_set(iid_stana(56))
slikaj("prati_stan.png")

# promene drugih stanova i parcele se ne javljaju; skida se samo stan 56
S["vlasnik_stana"][57] = "ДРУГИ ВЛАСНИК 57"
S["povrsina_stana"][60] = 99
upiti = proveri_sve()
ok(upiti == ["S056="], "provera: skinut samo stan 56 (%s)" % upiti[:5])
ok(not app.sesija_novo.get(r["id"]), "promena stanova 57 i 60: ne javlja se")
log = app.txt.get("1.0", "end")
ok("10383 (prati se samo: stan 56): provereno, bez promena" in log, "u porukama: provereno, bez promena")
S["vlasnik_stana"][56] = "НОВИ ВЛАСНИК 56"
upiti = proveri_sve()
pr = app.sesija_novo.get(r["id"]) or []
ok(upiti == ["S056="] and any("НОВИ ВЛАСНИК 56" in x for x in pr) and not any("57" in x or "99" in x for x in pr),
   "nov vlasnik stana 56: PROMENA (%s)" % pr)
ok(red_baze()["promene"] and app.baza.istorija(r["id"]), "promena upisana u istoriju")
S["nacin_stana"][56] = "ПОСЛОВНИ ПРОСТОР"
app.sesija_novo.clear()
upiti = proveri_sve()
r = red_baze()
pr = app.sesija_novo.get(r["id"]) or []
ok(upiti == ["S056="] and any("ПОСЛОВНИ ПРОСТОР" in x for x in pr), "promenjen način korišćenja: javlja se (%s)" % pr)
ok(len(ak.pracene_stavke(r)) == 1 and "ПОСЛОВНИ ПРОСТОР" in ak.pracene_stavke(r)[0],
   "i dalje se prati, pod novim nazivom: %s" % ak.pracene_stavke(r))
ok("[prati se samo: пословни простор 56]" in app.tree.item(str(r["id"]), "text"), "lista: %s" % app.tree.item(str(r["id"]), "text"))
sn = json.loads(r["snimak"])
ok(stan(d, 56) not in sn["nepokretnost"] and ak.pracene_stavke(r)[0] in sn["nepokretnost"],
   "u snimku podaci pod novim nazivom (stari naziv uklonjen)")
app.sesija_novo.clear()
upiti = proveri_sve()
ok(upiti == ["S056="] and not app.sesija_novo.get(r["id"]), "sledeća provera: bez lažne promene")

# vise stavki: Prati samo oznacene
app._oznaci(p, stan(d, 12))
app._oznaci(p, stan(d, 150))
PORUKE.clear()
meni = desni_klik(tpos, iid_stana(12))
ok("Prati samo označene (2)" in meni, "meni: Prati samo označene (2)")
n0 = len(nep_upiti())
izaberi("Prati samo označene")
ok(cekaj(lambda: app.posao is None, 30), "skidanje završeno")
ok(not any(x[0] in ("askyesno", "dijalog") for x in PORUKE), "parcela već prati stavke: ne pita")
r = red_baze()
ok(len(ak.pracene_stavke(r)) == 3 and stan(d, 12) in ak.pracene_stavke(r) and stan(d, 150) in ak.pracene_stavke(r),
   "prati se: %s" % [ak.opis_stavke(k) for k in ak.pracene_stavke(r)])
ok(sorted(nep_upiti()[n0:]) == ["S012=", "S150="], "skinuti stan 12 i 150: %s" % nep_upiti()[n0:])
upiti = proveri_sve()
ok(sorted(upiti) == ["S012=", "S056=", "S150="], "provera: samo 3 praćena stana (%s)" % upiti)
meni = desni_klik(tpos, iid_stana(12))
ok("Ne prati više ovu stavku" in meni, "na praćenom stanu: „Ne prati više ovu stavku“")
ok(meni == ["Sačuvaj kao PDF...", "Ne prati više ovu stavku", "Kopiraj „Објекат“"],
   "v24: skinut stan - PDF umesto „Skini sa sajta“: %s" % meni)
izaberi("Ne prati više")
r = red_baze()
ok(len(ak.pracene_stavke(r)) == 2 and stan(d, 12) not in ak.pracene_stavke(r), "stan 12 se više ne prati")
ok("prati" not in tpos.item(iid_stana(12), "tags") and "prati" in tpos.item(iid_stana(150), "tags"), "stan 12 nije podebljan")

# Prati celu parcelu (lista pracenja, desni klik)
MENI.clear()
stari = ak.tk.Menu.tk_popup
ak.tk.Menu.tk_popup = lambda self, *a: MENI.extend(
    (self.entrycget(i, "label"), self, i) for i in range(self.index("end") + 1) if self.type(i) == "command")
app.nb.select(1)
root.update()
x_, y_, w_, h_ = app.tree.bbox(str(r["id"])) or (0, 0, 0, 0)


class Dog:
    def __init__(self, w, x, y):
        self.widget, self.x, self.y, self.x_root, self.y_root = w, x, y, x, y


app._meni_desni(Dog(app.tree, x_ + 5, y_ + 3), str(r["id"]))
ak.tk.Menu.tk_popup = stari
ok(any(m[0].startswith("Prati celu parcelu (sada samo: ") for m in MENI), "lista: „Prati celu parcelu (sada samo: ...)“")
PORUKE.clear()
izaberi("Prati celu parcelu")
r = red_baze()
ok(ak.pracene_stavke(r) == [] and any(x[0] == "askyesno" for x in PORUKE), "posle potvrde prati se cela parcela")
ok("[prati" not in app.tree.item(str(r["id"]), "text") and p["lbl_prati"].cget("text") == "U praćenju: cela parcela",
   "lista i prozor: cela parcela (%r, %r)" % (app.tree.item(str(r["id"]), "text"), p["lbl_prati"].cget("text")))

# cela parcela -> samo jedan stan: pita
PORUKE.clear()
desni_klik(tpos, iid_stana(33))
izaberi("Prati samo ovu stavku")
cekaj(lambda: app.posao is None, 30)
ok(any(x[0] == "askyesno" and "prati se cela parcela" in x[2] for x in PORUKE), "pita da li samo stan 33 umesto cele parcele")
r = red_baze()
ok(ak.pracene_stavke(r) == [stan(d, 33)], "prati se samo stan 33")
S["bez_stana"].add(33)
app.sesija_novo.clear()
proveri_sve()
pr = app.sesija_novo.get(r["id"]) or []
ok(len(pr) == 1 and "stan 33: više nije na sajtu" in pr[0], "stana 33 više nema: javlja se (%s)" % pr)
app.sesija_novo.clear()
proveri_sve()
ok(not app.sesija_novo.get(red_baze()["id"]), "i samo jednom")
S["bez_stana"].clear()

# poslednja pracena stavka: "Ne prati vise" pita da li cela parcela
PORUKE.clear()
desni_klik(tpos, iid_stana(33))
izaberi("Ne prati više")
ok(any(x[0] == "askyesno" and "jedina stavka" in x[2] for x in PORUKE) and ak.pracene_stavke(red_baze()) == [],
   "poslednja stavka: pita, pa cela parcela")
root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
