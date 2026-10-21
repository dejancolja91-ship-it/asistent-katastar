# -*- coding: utf-8 -*-
"""v26 (Dejan: "u odabrane neka se prikaze samo ono sto pratim... ako je stan, samo stan. I kad pritisnem na taj
unos, neka odmah povuce sa sajta... I pretraga vise parcela, nema potrebe ovoliko polje, i kad pritisnem enter, neka
ide na pretragu"):
- lista praćenja: površina, način korišćenja i zgrada samo praćenog stana;
- v28 (Dejan: "kada kliknem dva puta... samo otvori, a neka bude tu dugme osveži"): dvoklik / Enter otvara sačuvano
  stanje odmah, bez sajta; dugme „Osveži sa sajta“ u prozoru proverava parcelu (samo praćene stavke) i prikazuje
  trenutno stanje u istom prozoru (natpis: promena / bez promena / nije preuzeto - sačuvano); prozor prikazuje samo
  praćeno, dugme za celu parcelu;
- pretraga: polje za brojeve u jednom redu, Enter = Pretraži, nalepljen spisak iz više redova se spaja."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_sveze_")
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
S["stanova"] = 60
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
ak.posalji_obavestenje = lambda naslov, redovi: PORUKE.append(("obavestenje", naslov))
ak.Pretraga.pauza = lambda self, raspon: None
root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: nadji_kod(svg)
app._dijalog_podataka = lambda naslov, *a, **k: ("Klijent Stan", "", "")


def cekaj(uslov, sekundi=60):
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


def slikaj(ime, prozor=None):
    root.update()
    if UVECANJE != 1.0:
        ime = "u%d_%s" % (round(UVECANJE * 100), ime)
    subprocess.run(["import", "-window", "root", os.path.join(SLIKE, ime)], check=False)


def prozori():
    return [w for w in root.winfo_children() if isinstance(w, ak.tk.Toplevel) and hasattr(w, "panel")]


def zatvori_prozore():
    for w in prozori():
        w.destroy()
    root.update()


class Dog:
    def __init__(self, w, x, y):
        self.widget, self.x, self.y = w, x, y
        self.x_root, self.y_root = w.winfo_rootx() + x, w.winfo_rooty() + y


def dvoklik(iid):
    app.nb.select(1)
    app.tree.selection_set(iid)
    app.tree.see(iid)
    root.update()
    x, y, w, h = app.tree.bbox(iid, "#0")
    app._dvoklik(Dog(app.tree, x + w // 2, y + h // 2))
    root.update()


# --- 3. pretraga: polje u jednom redu, Enter ---
app.nb.select(0)
root.update()
t = app.txt_brojevi
ok(int(t.cget("height")) == 1, "polje za brojeve parcela: jedan red (bilo 3)")
ok(abs(t.winfo_height() - app.cb_ko.winfo_height()) <= ak.px(10),
   "visina polja kao padajuća lista KO (%d / %d px)" % (t.winfo_height(), app.cb_ko.winfo_height()))
ok("Enter = Pretraži" in app._naslovi_pretrage[2].cget("text"), "natpis: %s" % app._naslovi_pretrage[2].cget("text"))
POZIVI = []
stari_pretrazi = app.pretrazi
app.pretrazi = lambda: POZIVI.append(t.get("1.0", "end").strip())
t.focus_force()
t.insert("1.0", "10383, 4415")
root.update()
t.event_generate("<Return>")
root.update()
ok(POZIVI == ["10383, 4415"] and "\n" not in t.get("1.0", "end-1c"), "Enter pokreće pretragu (bez novog reda u polju)")
t.event_generate("<KP_Enter>")
root.update()
ok(len(POZIVI) == 2, "i Enter na numeričkoj tastaturi")
t.delete("1.0", "end")
root.clipboard_clear()
root.clipboard_append("10383\n4415/2\r\n\n100-102\n")
t.event_generate("<<Paste>>")
root.update()
ok(t.get("1.0", "end-1c") == "10383, 4415/2, 100-102", "nalepljen spisak iz više redova: %r" % t.get("1.0", "end-1c"))
ok(ak.raspakuj_brojeve(t.get("1.0", "end"))[0][:2] == ["10383", "4415/2"], "brojevi se čitaju isto")
t.delete("1.0", "end")
app.nacin_var.set("adresa")
app._nacin_pretrage(sacuvaj=False)
root.update()
ok(int(app.txt_kbr.cget("height")) == 1, "kućni brojevi: jedan red")
app.txt_kbr.insert("1.0", "5, 7")
app.txt_kbr.event_generate("<Return>")
root.update()
ok(POZIVI[-1] == "" and len(POZIVI) == 3, "Enter u kućnim brojevima pokreće pretragu")
app.txt_kbr.delete("1.0", "end")
app.nacin_var.set("parcela")
app._nacin_pretrage(sacuvaj=False)
app.pretrazi = stari_pretrazi
root.update()
slikaj("pretraga_v26.png")

# --- priprema: pretraga parcele, prati se samo stan 56 ---
app._pokreni([dict(Z)], "pretraga")
ok(cekaj(lambda: app.posao is None, 120), "pretraga završena")
app.tree_p.selection_set("r1")
app.detalji_pretrage()
root.update()
p = app._panel
d = app.rezultati["r1"][1]
stan = lambda i: next(k for k in d["nep_id"] if (", stan %d, " % i) in k)
K56 = stan(56)
app._prati(p, [K56])
ok(cekaj(lambda: app.posao is None, 60), "praćenje stana 56: skinut")
ok(not p["filter_prikazan"] and len(p["tabele"]["p"].get_children("")) >= 50,
   "prozor iz pretrage: i dalje cela parcela (%d stanova)" % len(p["tabele"]["p"].get_children("")))
ok(p["btn_filter"].winfo_manager() and p["btn_filter"].cget("text") == "Prikaži samo praćeno",
   "dugme „Prikaži samo praćeno“ (%r)" % p["btn_filter"].cget("text"))
zatvori_prozore()
r = next(x for x in app.baza.parcele() if x["broj"] == "10383")
pid = str(r["id"])

# --- 1. lista: samo stan 56 ---
sn = json.loads(r["snimak"])
red56 = next(x for x in sn["posebni"] if x[3] == "56")
vals = dict(zip(("parcela", "opstina", "povrsina", "nacin", "objekti", "promena", "provereno"),
                app.tree.item(pid, "values")))
ok(vals["povrsina"] == red56[6] and vals["nacin"] == red56[5], "lista: površina i način stana 56 (%s m², %s), ne parcele"
   % (vals["povrsina"], vals["nacin"]))
ok(vals["objekti"] == " ".join(("zgrada " + red56[0]).split()), "lista: zgrada stana (%s)" % vals["objekti"])
ok(vals["parcela"] == "КУМОДРАЖ  10383" and "[prati se samo: stan 56]" in app.tree.item(pid, "text"),
   "KO / parcela i oznaka praćenja ostaju")
ok(ak.kratak_opis_stavki(sn, []) == ak.kratak_opis(sn), "bez praćenih stavki: cela parcela kao ranije")
ok(ak.kratak_opis_stavki(sn, [K56, stan(12)])[0] == "%s + %s" % (red56[6], next(x for x in sn["posebni"]
                                                                                  if x[3] == "12")[6]),
   "dva stana: obe površine")
ok("nema na sajtu" in ak.kratak_opis_stavki(sn, ["poseban deo X, ulaz 1, stan 999, evid. 999, СТАН"])[1],
   "stan kog nema u snimku: „nema na sajtu“")

# --- 2. dvoklik: odmah sačuvano stanje (bez sajta); „Osveži sa sajta“ u istom prozoru ---
S["vlasnik_stana"][56] = "НОВИ ВЛАСНИК 56"
S["vlasnik_stana"][57] = "ДРУГИ 57"
n0, z0 = len(S["nep_upiti"]), len(S["zahtevi"])
PORUKE.clear()
dvoklik(pid)
ok(app.posao is None and len(prozori()) == 1, "dvoklik: prozor odmah otvoren, bez sajta")
cekaj(lambda: False, 0.3)
ok(len(S["zahtevi"]) == z0, "nijedan upit sajtu (%d)" % (len(S["zahtevi"]) - z0))
w = prozori()[-1]
pn = w.panel
tpos, to, tp = pn["tabele"]["p"], pn["tabele"]["o"], pn["tabele"]["parcela"]
redovi = tpos.get_children("")
ok(pn["filter_prikazan"] and len(redovi) == 1 and tpos.item(redovi[0], "values")[3] == "56",
   "prozor: samo stan 56 (%d red)" % len(redovi))
ok("ВЛАСНИК СТАНА 56" in tpos.item(redovi[0], "values")[-1], "sačuvan vlasnik (%s)" % tpos.item(redovi[0], "values")[-1])
ok(w.btn_osvezi.cget("text") == "Osveži sa sajta" and str(w.btn_osvezi.cget("state")) == "normal",
   "dugme „Osveži sa sajta“")
ok(w.poruka.cget("text") == "Sačuvano stanje sa poslednje provere." and not w.poruka_naslov.winfo_manager(),
   "natpis kratak: %s" % w.poruka.cget("text"))


def svi_natpisi(x):
    out = [x.cget("text")] if isinstance(x, ak.tk.Label) else []
    for d in x.winfo_children():
        out += svi_natpisi(d)
    return out


ok(not any("Dvoklik" in s or "Desni klik" in s for s in svi_natpisi(w)), "v29: bez plavog uputstva u prozoru")
ok(len(to.get_children("")) == 1 and not tp.winfo_ismapped(), "samo zgrada stana; delovi parcele sakriveni")
ok(pn["btn_filter"].cget("text") == "Prikaži celu parcelu", "dugme „Prikaži celu parcelu“")
istorija0 = len(app.baza.istorija(r["id"]))
w.btn_osvezi.invoke()
root.update()
ok(app.posao is not None and str(w.btn_osvezi.cget("state")) == "disabled", "Osveži: ide na sajt, dugme čeka")
ok("Preuzimam trenutno stanje" in w.poruka.cget("text"), "natpis: %s" % w.poruka.cget("text"))
w.btn_osvezi.invoke()
dvoklik(pid)
ok(len(prozori()) == 2, "dvoklik dok se osvežava: otvara se sačuvano (ne čeka)")
prozori()[-1].destroy()
ok(cekaj(lambda: app.posao is None, 120), "osveženo")
root.update()
ok(S["nep_upiti"][n0:] == ["S056="], "skinut samo stan 56 (%s)" % S["nep_upiti"][n0:])
ok(len(prozori()) == 1 and prozori()[0] is w, "isti prozor (ne otvara novi)")
ok(w.poruka_naslov.cget("text") == "PROMENA - upravo preuzeto sa sajta" and w.poruka_naslov.winfo_ismapped(),
   "naslov trake: %s" % w.poruka_naslov.cget("text"))
tab = w.tabela_promena


def celija(red, kol):
    return next(c for c in tab.celije if int(c.grid_info()["row"]) == red and int(c.grid_info()["column"]) == kol)


def oznaceno(c, tag):
    r = c.tag_ranges(tag)
    return ["".join(c.get(r[i], r[i + 1])) for i in range(0, len(r), 2)]


ok(tab is not None and tab.winfo_ismapped() and not w.poruka.winfo_ismapped(), "v31: u traci tabela, bez dugog teksta")
ok([celija(0, k).get("1.0", "end-1c") for k in (1, 2)] == ["Staro stanje", "Novo stanje"], "zaglavlje: Staro / Novo stanje")
ok(len(tab.celije) == 6 and celija(1, 0).get("1.0", "end-1c") == "stan 56 · Имаоци права",
   "jedan red promene: %s" % celija(1, 0).get("1.0", "end-1c"))
ok(celija(1, 1).get("1.0", "end-1c") == "ВЛАСНИК СТАНА 56" and celija(1, 2).get("1.0", "end-1c") == "НОВИ ВЛАСНИК 56",
   "staro / novo: %s | %s" % (celija(1, 1).get("1.0", "end-1c"), celija(1, 2).get("1.0", "end-1c")))
ok(oznaceno(celija(1, 1), "izmena_staro") == ["СТАНА"] and oznaceno(celija(1, 2), "izmena_novo") == ["НОВИ"],
   "tačno označena izmena: %s / %s" % (oznaceno(celija(1, 1), "izmena_staro"), oznaceno(celija(1, 2), "izmena_novo")))
ok(str(celija(1, 1).tag_cget("izmena_staro", "background")) == ak.BG_STARO and
   str(celija(1, 2).tag_cget("izmena_novo", "background")) == ak.BG_NOVO_IZM, "staro crveno, novo zeleno")
ok(all(tuple(float(x) for x in c.yview()) == (0.0, 1.0) for c in tab.celije) and
   tab.winfo_x() + tab.winfo_width() <= w.okvir_poruke.winfo_width(), "ćelije cele vidljive, tabela u prozoru")
ok(str(w.poruka_naslov.cget("bg")) == ak.BG_PROMENA, "naslov promene na žutom")
ok(not any(x[0] == "obavestenje" for x in PORUKE), "bez Windows obaveštenja za osvežavanje")
redovi = tpos.get_children("")
ok(pn["filter_prikazan"] and len(redovi) == 1 and "НОВИ ВЛАСНИК 56" in tpos.item(redovi[0], "values")[-1],
   "u istom prozoru: trenutni vlasnik (%s)" % tpos.item(redovi[0], "values")[-1])
ok(w.btn_osvezi.cget("text") == "Osveži sa sajta" and str(w.btn_osvezi.cget("state")) == "normal", "dugme opet spremno")
ok(w.nb.tab(w.f2, "text").strip() == "Istorija promena (%d)" % (istorija0 + 1) and
   "stan 56 · Имаоци права | staro: ВЛАСНИК СТАНА 56 | novo: НОВИ ВЛАСНИК 56" in w.istorija.tekst and
   "Лице уписано" not in w.istorija.tekst and any(hasattr(x, "celije") for x in w.istorija.winfo_children()),
   "kartica Istorija promena osvežena, jasno: %s" % w.nb.tab(w.f2, "text").strip())
ok(app.baza.parcele([r["id"]])[0]["provereno"] in w.lbl_provera.cget("text"), "naslov: %s" % w.lbl_provera.cget("text"))
ok(not app.baza.parcele([r["id"]])[0]["promene"], "promena viđena u prozoru: pregledana")
slikaj("sveze_samo_stan.png")
pn["btn_filter"].invoke()
root.update()
ok(not pn["filter_prikazan"] and len(tpos.get_children("")) >= 50 and tp.winfo_ismapped(),
   "„Prikaži celu parcelu“: delovi, zgrade i svi stanovi (%d)" % len(tpos.get_children("")))
ok("prati" in tpos.item(next(i for i in tpos.get_children("") if tpos.item(i, "values")[3] == "56"), "tags"),
   "stan 56 podebljan u celoj parceli")
pn["btn_filter"].invoke()
root.update()
ok(pn["filter_prikazan"] and len(tpos.get_children("")) == 1, "„Prikaži samo praćeno“: opet samo stan 56")

# bez promene
w.btn_osvezi.invoke()
ok(cekaj(lambda: app.posao is None, 120), "drugo osvežavanje")
root.update()
ok("bez promena" in w.poruka.cget("text") and str(w.poruka.cget("bg")) == ak.BG_ZELENO and
   not w.poruka_naslov.winfo_manager(), "natpis: %s" % w.poruka.cget("text"))

# sajt ne odgovara: ostaje sačuvano, uz napomenu
app._trazi_odgovor_iz_niti = lambda svg, opis: None
w.btn_osvezi.invoke()
ok(cekaj(lambda: app.posao is None, 120), "sajt ne odgovara")
root.update()
txt = w.poruka.cget("text")
ok("nije preuzeto" in txt and "poslednje sačuvano" in txt, "natpis: %s" % txt)
ok("НОВИ ВЛАСНИК 56" in tpos.item(tpos.get_children("")[0], "values")[-1], "prikazano sačuvano stanje")
ok("nije uspeo" in w.lbl_provera.cget("text"), "naslov: poslednji pokušaj nije uspeo")
app._trazi_odgovor_iz_niti = lambda svg, opis: nadji_kod(svg)

# prekid
w.btn_osvezi.invoke()
app._prekini()
ok(cekaj(lambda: app.posao is None, 60), "Prekini")
root.update()
ok("prekinuto" in w.poruka.cget("text") and str(w.btn_osvezi.cget("state")) == "normal", "natpis: %s" %
   w.poruka.cget("text"))

# provera u toku: Osveži javlja da sačeka
app.tree.selection_set(pid)
app.proveri(True)
w.btn_osvezi.invoke()
ok("u toku" in w.poruka.cget("text"), "provera u toku: %s" % w.poruka.cget("text"))
cekaj(lambda: app.posao is None, 120)

# prozor zatvoren pre kraja osvežavanja: ništa se ne otvara
w.btn_osvezi.invoke()
w.destroy()
ok(cekaj(lambda: app.posao is None, 120) and not prozori(), "zatvoren prozor: posle osvežavanja ništa se ne otvara")

# „Ne prati više“ u prikazu samo praćenog: poslednja stavka -> cela parcela
dvoklik(pid)
pn = prozori()[-1].panel
tpos = pn["tabele"]["p"]
iid = tpos.get_children("")[0]
app._ne_prati(pn, app._kljuc_reda(pn, iid))
root.update()
ok(ak.pracene_stavke(app.baza.parcele([r["id"]])[0]) == [] and not pn["filter_prikazan"]
   and len(tpos.get_children("")) >= 50 and not pn["btn_filter"].winfo_manager(),
   "„Ne prati više“ poslednju stavku: cela parcela, bez dugmeta")
w = prozori()[-1]
ok("sačuvano stanje" in w.poruka.cget("text").lower(), "natpis: %s" %
   w.poruka.cget("text"))
w.btn_osvezi.invoke()
ok(cekaj(lambda: app.posao is None, 120), "cela parcela: osveženo")
root.update()
ok(not pn["filter_prikazan"] and len(pn["tabele"]["p"].get_children("")) >= 50, "cela parcela: svi stanovi")
vals = app.tree.item(pid, "values")
ok(vals[2] == ak.kratak_opis(json.loads(app.baza.parcele([r["id"]])[0]["snimak"]))[0], "lista: površina parcele")
zatvori_prozore()

# v29: redovna provera - u listi i dnevniku jasan red promene
S["vlasnik_stana"][57] = "ТРЕЋИ 57"
app.proveri(False)
ok(cekaj(lambda: app.posao is None, 120), "redovna provera cele parcele")
root.update()
vals = app.tree.item(pid, "values")
ok(vals[5].endswith(": stan 57 · Имаоци права | staro: ДРУГИ 57 | novo: ТРЕЋИ 57"), "lista, Poslednja promena: %s" % vals[5])
log = app.txt.get("1.0", "end")
ok("stan 57 · Имаоци права   staro: ДРУГИ 57   novo: ТРЕЋИ 57" in log and
   "Лице уписано" not in log.split("ТРЕЋИ 57")[0][-300:], "dnevnik: staro i novo stanje")
r = app.txt.tag_ranges("log_staro"), app.txt.tag_ranges("log_novo")
ok(app.txt.get(*r[0][-2:]) == "ДРУГИ" and app.txt.get(*r[1][-2:]) == "ТРЕЋИ", "dnevnik: izmena označena bojom")

# meni Parcela: jedno „Detalji“
mb = root.nametowidget(root["menu"])
lab = []
for i in range(mb.index("end") + 1):
    if mb.type(i) == "cascade" and mb.entrycget(i, "label") == "Parcela":
        pod = root.nametowidget(mb.entrycget(i, "menu"))
        lab = [pod.entrycget(j, "label") for j in range(pod.index("end") + 1) if pod.type(j) == "command"]
ok("Detalji" in lab and not any("sa sajta" in x or "bez sajta" in x for x in lab), "meni Parcela: Detalji")
root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
