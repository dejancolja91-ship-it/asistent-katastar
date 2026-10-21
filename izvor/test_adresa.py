# -*- coding: utf-8 -*-
"""v19: pretraga po adresi (opstina, ulica sa spiska sajta, kucni broj) na simuliranom eKatastru sa stranicama
iz Dejanovog HAR-a. Prvo sajt i pozadinski posao, pa prozor pod Xvfb."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

RAD = tempfile.mkdtemp(prefix="kat_adresa_")
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


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def nadji_kod(svg):
    for k, v in mock_sajt.SVG.items():
        if v == svg:
            return mock_sajt.CAPTCHE[k]


def postovi(ime):
    return [z for z in mock_sajt.STANJE["zahtevi"] if z[0] == "POST" and z[1] == ime]


P = "ctl00$ContentPlaceHolder1$"
VOJVODE = "БЕОГРАД (ВОЖДОВАЦ), ВОЈВОДЕ СТЕПЕ"

# 1. rezultat po adresi sa pravog sajta (HAR)
r = ak.parsiraj_adresu(mock_sajt.rd("adresa_rez.html"))
ok(r == [{"kbr": "5", "ko": "ЧУКАРИЦА", "broj": "10572/2", "deo": "2", "povrsina": "133",
          "vrsta": "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", "nacin": "ЗЕМЉИШТЕ ПОД ЗГРАДОМ И ДРУГИМ ОБЈЕКТОМ"}],
   "pravi rezultat po adresi (ГРУЈЕ МИШКОВИЋА 5): %s" % r)
ok(ak.parsiraj_adresu(mock_sajt.rd("rez_4415.html")) is None, "rezultat po broju parcele nije rezultat po adresi")
ok(ak.raspakuj_kucne("5, 7 12a;123456\n9") == (["5", "7", "12a", "9"], ["123456"]), "kućni brojevi se raspakuju")
ok(ak.kratka_ulica(VOJVODE) == "ВОЈВОДЕ СТЕПЕ", "kratak naziv ulice")

# 2. sajt: predlozi ulica, obrazac, losa i dobra captcha, nepostojeca adresa
s = ak.Sajt()
u = s.ulice(70254, "miš")
ok(u == [("БЕОГРАД (ЧУКАРИЦА), ГРУЈЕ МИШКОВИЋА", "791113003725"), ("БЕОГРАД (ЧУКАРИЦА), ЈАНКА МИШИЋА", "791113033258")],
   "predlozi ulica kao na sajtu ('miš'): %s" % u)
ok(mock_sajt.STANJE["ulice_upiti"][-1] == {"prefixText": "miš", "count": 10, "contextKey": "70254"},
   "upit za ulice kao iz pregledača: %s" % mock_sajt.STANJE["ulice_upiti"][-1])
ok(("GET", "FindAdresa.aspx", "OpstinaID=70254") in mock_sajt.STANJE["zahtevi"], "pre predloga otvorena stranica opštine")
n_get = len([z for z in mock_sajt.STANJE["zahtevi"] if z[1] == "FindAdresa.aspx"])
s.ulice(70254, "ја")
ok(len([z for z in mock_sajt.STANJE["zahtevi"] if z[1] == "FindAdresa.aspx"]) == n_get,
   "sledeći predlozi iste opštine bez ponovnog otvaranja stranice")
obr = s.otvori_adresu(70106)
ok(obr.svg and obr.polja.get("__VIEWSTATE") and P + "ucAdresa$hdnUlicaID" in obr.polja, "obrazac po adresi otvoren")
vrsta, odg = s.posalji_adresu(obr, VOJVODE, "791106000101", "5", "pogresno")
ok(vrsta == "captcha" and obr.svg, "pogrešna captcha: nova slika (%s)" % vrsta)
pd = postovi("FindAdresa.aspx")[-1][2]
ok(pd.get(P + "ucAdresa$txtUlica") == VOJVODE and pd.get(P + "ucAdresa$hdnUlicaID") == "791106000101"
   and pd.get(P + "ucAdresa$txtKucniBroj") == "5" and pd.get("__ASYNCPOST") == "true",
   "šalje ulicu, ID ulice i kućni broj kao sajt")
vrsta, odg = s.posalji_adresu(obr, VOJVODE, "791106000101", "5", nadji_kod(obr.svg))
ok(vrsta == "ok" and ak.parsiraj_adresu(odg)[0]["broj"] == "4415", "dobra captcha: rezultat po adresi (%s)" % vrsta)
vrsta, odg = s.posalji_adresu(obr, VOJVODE, "791106000101", "99", nadji_kod(obr.svg))
ok(vrsta == "nema" and "Нема података" in odg, "nepostojeći kućni broj: poruka sajta (%s)" % odg)

# 3. pozadinski posao: adresa -> parcele -> obicna pretraga parcele
def pokreni(zadaci, ko_za=None):
    rez, kraj, log, sacuvano = [], threading.Event(), [], []
    pos = ak.Pretraga(None, True, None, lambda svg, opis: nadji_kod(svg), lambda m, t="": log.append((t, m)),
                      lambda p: kraj.set())
    pos.ko_za = ko_za
    pos.sacuvaj_ko = lambda oid, lista: sacuvano.append((oid, lista))
    pos.rezultat = lambda z, d, r: rez.append((z, d, r))
    pos.pokreni(zadaci)
    ok(kraj.wait(90), "posao završen")
    return pos, rez, log, sacuvano


A = lambda ulica, uid, kbr, oid=70106, op="ВОЖДОВАЦ": {
    "opstina_id": oid, "opstina": op, "ulica": ulica, "ulica_id": uid, "kbr": kbr,
    "adresa": "%s %s" % (ak.kratka_ulica(ulica), kbr)}
SIF = {"70106": ak.KO_UGRADJENE["70106"]}
n_par = len(postovi("FindParcela.aspx"))
pos, rez, log, sac = pokreni([A(VOJVODE, "791106000101", "5"), A(VOJVODE, "791106000101", "7"),
                              A(VOJVODE, "791106000101", "99"), A("БЕОГРАД (ВОЖДОВАЦ), ВОЈИСЛАВА ИЛИЋА", "791106000102", "3")],
                             ko_za=lambda oid: SIF.get(str(oid)))
opis = [(z["ko"], z["broj"], d is not None) for z, d, r in rez]
ok(opis == [("ВОЖДОВАЦ", "4415", True), ("ВОЖДОВАЦ", "4415", True), ("КУМОДРАЖ", "10383", True),
            ("ВОЖДОВАЦ", "ВОЈВОДЕ СТЕПЕ 99", False), ("ЗЕМУН", "10383", False)], "redosled rezultata: %s" % opis)
z0, d0, _ = rez[0]
ok(z0["ko_id"] == 703621 and z0["opstina_id"] == 70106 and z0["adresa"] == "ВОЈВОДЕ СТЕПЕ 5",
   "parcela sa adrese dobija KO ID iz šifarnika: %s" % z0)
ok(len(d0["delovi"]) == 4, "pun rezultat parcele: %d delova (adresa je na jednom)" % len(d0["delovi"]))
ok(rez[2][0]["ko_id"] == 703800, "druga KO na istoj adresi (КУМОДРАЖ): %s" % rez[2][0]["ko_id"])
ok([r_ for z, d, r_ in rez if d is None][0].startswith("adresa nije pronadjena") and "Нема података" in rez[3][2],
   "nepostojeća adresa: %s" % rez[3][2])
ok("nije u spisku" in rez[4][2], "KO koja nije u opštini: %s" % rez[4][2])
ok(pos.ok == 3 and len(pos.neuspeli) == 2, "brojanje: uspešno %d, nije uspelo %d" % (pos.ok, len(pos.neuspeli)))
ok(len(sac) == 1, "sajt pitan za KO samo kad je nema u šifarniku (ЗЕМУН): %d" % len(sac))
ok(len(postovi("FindParcela.aspx")) - n_par == 2, "parcele sa adrese tražene običnom pretragom parcele, 4415 samo "
   "jednom (kućni brojevi 5 i 7): %d" % (len(postovi("FindParcela.aspx")) - n_par))
ok(rez[1][1] is rez[0][1], "isti podaci za 4415 i na adresi 7, bez nove pretrage")
_, rez_p, _, _ = pokreni([{"opstina_id": 70106, "opstina": "ВОЖДОВАЦ", "ko_id": 703621, "ko": "ВОЖДОВАЦ", "broj": "4415"}])
ok(ak.napravi_snimak(rez_p[0][1]) == ak.napravi_snimak(d0), "isti rezultat kao pretraga po broju parcele")
# KO nema u sifarniku -> ucitava se sa sajta i cuva
pos, rez, log, sac = pokreni([A(VOJVODE, "791106000101", "5")], ko_za=lambda oid: None)
ok(rez and rez[0][1] is not None and rez[0][0]["ko_id"] == 703621, "KO učitane sa sajta kad ih nema u šifarniku")
ok(sac and sac[0][0] == 70106 and [703621, "ВОЖДОВАЦ"] in sac[0][1], "KO sa sajta idu u šifarnik")
# prekid
kraj2 = threading.Event()
pos2 = ak.Pretraga(None, True, None, lambda svg, opis: False, lambda m, t="": None, lambda p: kraj2.set())
rez2 = []
pos2.rezultat = lambda z, d, r: rez2.append(1)
pos2.pokreni([A(VOJVODE, "791106000101", "5")])
ok(kraj2.wait(30) and not rez2 and pos2.stop, "prekid na captchi adrese: bez rezultata")

# 4. prozor
if not os.environ.get("DISPLAY"):
    print("\nUKUPNO GRESAKA:", len(GRESKE))
    sys.exit(1 if GRESKE else 0)


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), True)[1]


ak.messagebox = TihiMessagebox()
root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()


def cekaj(uslov, sekundi=30):
    """Kratki mainloop-ovi: pozadinske niti programa javljaju rezultat preko root.after (kao u pravom radu)."""
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


def kucaj(w, tekst):
    w.focus_force()
    root.update()
    w.delete(0, "end")
    for ch in tekst:
        pre = w.get()
        ks = {"ž": "zcaron", "š": "scaron", "č": "ccaron", "ć": "cacute", "đ": "dstroke", " ": "space"}.get(ch, ch)
        w.event_generate("<KeyPress>", keysym=ks)
        if w.get() == pre:
            w.insert("insert", ch)
        w.event_generate("<KeyRelease>", keysym=ks)
        root.update()


def taster(w, ime):
    w.focus_force()
    root.update()
    w.event_generate("<%s>" % ime)
    root.update()


def predlozi(w):
    pr = w._predlozi
    return [pr.lb.get(i) for i in range(pr.lb.size())] if pr.vidljiv() else []


def slikaj(ime):
    root.update()
    if UVECANJE != 1.0:
        ime = "u%d_%s" % (round(UVECANJE * 100), ime)
    subprocess.run(["import", "-window", "root", os.path.join(SLIKE, ime)], check=False)


vid = lambda w: bool(w.winfo_ismapped())
ok(app.nacin_var.get() == "parcela" and vid(app.cb_ko) and vid(app.txt_brojevi) and not vid(app.cb_ulica)
   and not vid(app.txt_kbr), "podrazumevano: pretraga po broju parcele (opština, KO, brojevi)")
visina = app.txt_brojevi.master.winfo_height()
app._radio_nacina["adresa"].invoke()
root.update()
ok(vid(app.cb_ulica) and vid(app.txt_kbr) and not vid(app.cb_ko) and not vid(app.txt_brojevi),
   "Traži po adresi: polja ulica i kućni brojevi umesto KO i brojeva parcela")
ok(app._naslovi_pretrage[1].cget("text").startswith("Ulica") and
   app._naslovi_pretrage[2].cget("text").startswith("Kućni brojevi"), "naslovi polja za adresu")
ok(app.baza.podesavanje("nacin_pretrage") == "adresa", "izbor načina pretrage se pamti")
ok(abs(app.txt_kbr.master.winfo_height() - visina) <= 2, "obrazac iste visine u oba načina (%d / %d)"
   % (visina, app.txt_kbr.master.winfo_height()))
app.cb_opstina.set("")
root.update()
kucaj(app.cb_ulica, "vo")
ok(predlozi(app.cb_ulica) == ["prvo izaberi opštinu"], "ulica bez opštine: %s" % predlozi(app.cb_ulica))
taster(app.cb_ulica, "Escape")
kucaj(app.cb_opstina, "vozd")
taster(app.cb_opstina, "Return")
ok(app.cb_opstina.get() == "ВОЖДОВАЦ" and app.cb_opstina.focus_get() is app.cb_ulica,
   "Enter na opštini vodi u polje ulice")
n_upita = len(mock_sajt.STANJE["ulice_upiti"])
kucaj(app.cb_ulica, "v")
ok(predlozi(app.cb_ulica) == ["upiši bar 2 slova naziva ulice"], "1 slovo: %s" % predlozi(app.cb_ulica))
kucaj(app.cb_ulica, "voj")
ok(cekaj(lambda: VOJVODE in predlozi(app.cb_ulica)), "predlozi ulica sa sajta: %s" % predlozi(app.cb_ulica))
ok(predlozi(app.cb_ulica) == [VOJVODE, "БЕОГРАД (ВОЖДОВАЦ), ВОЈИСЛАВА ИЛИЋА"], "obe ulice: %s" % predlozi(app.cb_ulica))
ok(len(mock_sajt.STANJE["ulice_upiti"]) == n_upita + 1 and mock_sajt.STANJE["ulice_upiti"][-1]["contextKey"] == "70106",
   "jedan upit posle kucanja (ne za svako slovo): %s" % mock_sajt.STANJE["ulice_upiti"][n_upita:])
slikaj("adresa_predlozi.png")
taster(app.cb_ulica, "Return")
ok(app.cb_ulica.get() == VOJVODE and app.cb_ulica.focus_get() is app.txt_kbr, "Enter bira ulicu, fokus u kućnim brojevima")
app.txt_kbr.insert("1.0", "5, 7, 99")
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: nadji_kod(svg)
OBAV = []
ak.posalji_obavestenje = lambda naslov, redovi: OBAV.append(naslov)
app.pretrazi()
ok(app.posao is not None, "pretraga po adresi pokrenuta: %s" % PORUKE[-1:])
ok(cekaj(lambda: app.posao is None, 120), "pretraga po adresi završena")
redovi = [(app.tree_p.item(i, "text"),) + tuple(app.tree_p.item(i, "values")[:1]) + (app.tree_p.item(i, "values")[-1],)
          for i in app.tree_p.get_children("")]
print("     redovi:", redovi)
ok([x[:2] for x in redovi] == [("ВОЖДОВАЦ", "4415"), ("ВОЖДОВАЦ", "4415"), ("КУМОДРАЖ", "10383"),
                               ("ВОЖДОВАЦ", "ВОЈВОДЕ СТЕПЕ 99")], "redovi u rezultatima: %s" % [x[:2] for x in redovi])
ok(redovi[0][2] == "pronađeno po adresi ВОЈВОДЕ СТЕПЕ 5" and redovi[2][2] == "pronađeno po adresi ВОЈВОДЕ СТЕПЕ 7",
   "status kaže adresu: %s / %s" % (redovi[0][2], redovi[2][2]))
ok(redovi[3][2].startswith("nije pronađeno: adresa nije pronadjena") and "Нема података" in redovi[3][2],
   "nepostojeća adresa u tabeli: %s" % redovi[3][2])
ok(app.lbl_opis.cget("text") == "Rezultat pretrage - uspešno: 3 od 4, nije uspelo: 1",
   "statusna linija: %s" % app.lbl_opis.cget("text"))
ok(float(app.napredak.cget("maximum")) >= 4, "traka napretka prati parcele sa adrese")
z, d, r_ = app.rezultati["r1"]
ok(z["ko_id"] == 703621 and d and len(d["delovi"]) == 4, "red sa adrese ima pun rezultat parcele")
pre = set(root.winfo_children())
app.tree_p.selection_set("r1")
app.detalji_pretrage()
root.update()
novi = [w for w in root.winfo_children() if w not in pre and isinstance(w, ak.tk.Toplevel)]
ok(novi and "4415" in novi[0].title(), "dvoklik otvara prozor parcele: %s" % (novi[0].title() if novi else None))
for w in novi:
    w.destroy()
app._dijalog_podataka = lambda naslov, *a, **k: ("Klijent Adresa", "", "")
app.tree_p.selection_set(("r1", "r3"))
app.dodaj_iz_pretrage()
root.update()
pr = {(p["ko_id"], p["broj"]): p for p in app.baza.parcele()}
ok(sorted(pr) == [(703621, "4415"), (703800, "10383")] and all(p["opstina_id"] == 70106 for p in pr.values()),
   "parcele sa adrese dodate u praćenje (KO ID, broj): %s" % sorted(pr))
ok(pr[(703621, "4415")]["grupa"] == "Klijent Adresa", "2 parcele istog klijenta -> grupa (kao PRO)")
app.nb.select(0)

# provere unosa
PORUKE.clear()
kucaj(app.cb_ulica, "nepostojeca")
taster(app.cb_ulica, "Escape")
app.pretrazi()
ok(app.posao is None and PORUKE and "izaberi ulicu sa spiska" in PORUKE[-1][2], "ulica koja nije izabrana: poruka")
app.cb_ulica.set(VOJVODE)
app.txt_kbr.delete("1.0", "end")
app.pretrazi()
ok(app.posao is None and "kućni broj" in PORUKE[-1][2], "bez kućnog broja: poruka")
app.txt_kbr.insert("1.0", "123456")
app.pretrazi()
ok(app.posao is None and "Neispravni kućni brojevi: 123456" in PORUKE[-1][2], "predugačak kućni broj: poruka")
kucaj(app.cb_opstina, "cukar")
taster(app.cb_opstina, "Return")
ok(app.cb_opstina.get() == "ЧУКАРИЦА" and app.cb_ulica.get() == "" and not app._ulice_po_nazivu,
   "druga opština briše izabranu ulicu")
kucaj(app.cb_ulica, "miš")
ok(cekaj(lambda: "БЕОГРАД (ЧУКАРИЦА), ГРУЈЕ МИШКОВИЋА" in predlozi(app.cb_ulica)),
   "latinica sa kvačicama ('miš'): %s" % predlozi(app.cb_ulica))
kucaj(app.cb_ulica, "xq")
ok(cekaj(lambda: predlozi(app.cb_ulica) == ["nema takve ulice u opštini ЧУКАРИЦА"]),
   "nepostojeća ulica: %s" % predlozi(app.cb_ulica))
taster(app.cb_ulica, "Escape")
slikaj("adresa_rezultati.png")

app._radio_nacina["parcela"].invoke()
root.update()
ok(vid(app.cb_ko) and vid(app.txt_brojevi) and not vid(app.cb_ulica) and app.baza.podesavanje("nacin_pretrage") == "parcela",
   "nazad na pretragu po broju parcele")
ok(app._naslovi_pretrage[1].cget("text") == "Katastarska opština", "naslovi za parcelu vraćeni")
kucaj(app.cb_opstina, "vozd")
taster(app.cb_opstina, "Return")
ok(app.cb_opstina.focus_get() is app.cb_ko, "u pretrazi po parceli Enter na opštini vodi u KO")
app._radio_nacina["adresa"].invoke()
root.update()
ok(app.baza.podesavanje("nacin_pretrage") == "adresa", "pamti se poslednji izbor (adresa)")

root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
