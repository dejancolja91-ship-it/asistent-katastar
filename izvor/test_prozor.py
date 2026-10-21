# -*- coding: utf-8 -*-
"""Prozor pod Xvfb: pretraga dve parcele uz rucni unos captche, dodavanje u pracenje, provera, detalji."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

RAD = tempfile.mkdtemp(prefix="kat_gui_")
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
GRESKE = []
PORUKE = []


class TihiMessagebox:
    """Prozorcici sa porukom bi zaustavili test: belezi se sta bi bilo prikazano."""
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), True)[1]


ak.messagebox = TihiMessagebox()


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


UVECANJE = float(os.environ.get("TEST_UVECANJE", "1.0"))     # 1.5 = Windows uvecanje 150%


def slikaj(ime):
    root.update()
    if UVECANJE != 1.0:
        ime = "u%d_%s" % (round(UVECANJE * 100), ime)
    subprocess.run(["import", "-window", "root", os.path.join(SLIKE, ime)], check=False)


root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)      # kao Windows sa tim uvecanjem (DPI-aware program)
app = ak.App(root)
ok(app.nep_pretraga_var.get() == "spisak", "v21: pretraga podrazumevano samo prikaže stavke")
app.nep_pretraga_var.set("sve")       # ovaj test proverava i vlasnike u rezultatima ("odmah skini sve"; izbor: test_izbor.py)
ok(abs(ak.SKALA - UVECANJE) < 0.02, "uvećanje ekrana prepoznato: %s" % ak.SKALA)
ok(int(ak.ttk.Style().lookup("Treeview", "rowheight")) == ak.px(30), "visina reda prati uvećanje: %s" %
   ak.ttk.Style().lookup("Treeview", "rowheight"))
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))   # isti logicki prostor kao na 100%
mock_sajt.STANJE["captcha_red"] = ["b200c5be", "bc8b2524", "617fc8be", "2879ffa5", "31e71c1e"] * 3
# obavestenje kad treba upisati captchu (na Windows-u: zvuk, treptanje na taskbaru i Windows obavestenje)
OBAVESTENJA, ZVUCI, TREPTANJA, FOKUS = [], [], [], [False]
ak.posalji_obavestenje = lambda naslov, redovi: OBAVESTENJA.append((naslov, list(redovi)))
ak.zvuk_upozorenja = lambda r: ZVUCI.append(1)
ak.treperi_na_taskbaru = lambda r: TREPTANJA.append(1)
ak.prozor_u_fokusu = lambda r: FOKUS[0]
koraci = []


def korak(f, posle=300):
    koraci.append((f, posle))


def sledeci():
    if not koraci:
        return
    f, posle = koraci.pop(0)
    try:
        r = f()
    except Exception as e:
        import traceback
        traceback.print_exc()
        GRESKE.append("izuzetak u koraku %s: %r" % (f.__name__, e))
        r = None
    if r == "cekaj":                  # ponovi isti korak
        koraci.insert(0, (f, posle))
    root.after(posle, sledeci)


def kucaj(w, tekst):
    """Kucanje kao sa tastature: KeyPress (Entry upisuje znak) + KeyRelease (predlozi)."""
    w.focus_force()
    root.update()
    w.delete(0, "end")
    for ch in tekst:
        pre = w.get()
        ks = {"ž": "zcaron", "š": "scaron", "č": "ccaron", "ć": "cacute", "đ": "dstroke"}.get(ch, ch)
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


def kucaj_opstinu():
    o, k = app.cb_opstina, app.cb_ko
    ok(str(o.cget("state")) != "readonly" and list(o.cget("values")), "opština može da se kuca, spisak i dalje postoji")
    kucaj(o, "zem")
    ok(predlozi(o)[:1] == ["ЗЕМУН"], "'zem' -> predlog ЗЕМУН: %s" % predlozi(o)[:3])
    slikaj("ekran_0_predlozi.png")
    taster(o, "Return")
    ok(o.get() == "ЗЕМУН" and not o._predlozi.vidljiv(), "Enter bira ЗЕМУН: %s" % o.get())
    ok(o.focus_get() is k, "posle Entera fokus je u polju KO")
    kucaj(o, "xyzq")
    ok(predlozi(o) == ["nema takvog naziva"], "nepostojeći naziv: %s" % predlozi(o))
    taster(o, "Escape")
    ok(not o._predlozi.vidljiv(), "Esc sklanja predloge")


def kucaj_vozdovac():
    o, k = app.cb_opstina, app.cb_ko
    if str(k.cget("state")) == "disabled":
        return "cekaj"                # KO za Zemun se jos ucitavaju sa (lazne) stranice
    k.set("НЕШТО")
    kucaj(o, "vozd")
    ok(k.get() == "" and not list(k.cget("values") or ()), "kucanje druge opštine prazni KO")
    ok(predlozi(o)[:1] == ["ВОЖДОВАЦ"], "'vozd' -> ВОЖДОВАЦ: %s" % predlozi(o)[:3])
    taster(o, "Return")
    ok(o.get() == "ВОЖДОВАЦ" and "КУМОДРАЖ" in k.cget("values"), "Enter bira ВОЖДОВАЦ, KO učitane: %s" % (
        list(k.cget("values")),))
    kucaj(k, "kumo")
    ok(predlozi(k) == ["КУМОДРАЖ"], "KO 'kumo' -> КУМОДРАЖ: %s" % predlozi(k))
    taster(k, "Return")
    ok(k.get() == "КУМОДРАЖ" and app._izabrana_ko(o, k)[1] == "КУМОДРАЖ", "Enter bira KO КУМОДРАЖ")
    ok(k.focus_get() is app.txt_brojevi, "posle KO fokus je u brojevima parcela")
    kucaj(k, "r")
    ok(predlozi(k)[:2] == ["РАКОВИЦА СЕЛО", "РИПАЊ"], "'r' -> predlozi: %s" % predlozi(k))
    taster(k, "Down")
    taster(k, "Return")
    ok(k.get() == "РИПАЊ", "strelica dole + Enter bira drugi predlog: %s" % k.get())
    ok(k._predlozi._pomeri(1) is None, "bez predloga strelica otvara ceo spisak (klizni meni ostaje)")


def izaberi_ko():
    """Upisano, a ne izabrano (bez Entera), pa odmah Pretraži: program sam bira ВОЖДОВАЦ / ВОЖДОВАЦ."""
    app.auto_var.set(False)           # prvo rucno, da se vidi panel captche
    kucaj(app.cb_opstina, "vozdovac")
    kucaj(app.cb_ko, "Voždovac")
    app.txt_brojevi.delete("1.0", "end")
    app.txt_brojevi.insert("1.0", "4415, 999")
    app.pretrazi()
    ok(app.cb_opstina.get() == "ВОЖДОВАЦ" and app.cb_ko.get() == "ВОЖДОВАЦ",
       "upisani nazivi razrešeni pri pretrazi: %s / %s" % (app.cb_opstina.get(), app.cb_ko.get()))
    ok(app.posao is not None, "pretraga pokrenuta bez poruke: %s" % PORUKE[-1:])


def captcha_vidljiva():
    if str(app.e_cap.cget("state")) == "disabled":
        return "cekaj"
    ok(app.captcha_frame.winfo_ismapped(), "panel captche je prikazan")
    ok(len(app.cv.find_all()) > 20, "captcha nacrtana na platnu (%d oblika)" % len(app.cv.find_all()))
    ok("v  0  a  8  h" in app.lbl_predlog.cget("text"), "predlog citaca prikazan: %s" % app.lbl_predlog.cget("text"))
    ok(app.e_cap.get() == "v0a8h", "kod koji citac zna ceo je vec upisan (dovoljan je Enter): %s" % app.e_cap.get())
    slikaj("ekran_1_captcha.png")
    ok(len(OBAVESTENJA) == 1 and "upiši captchu" in OBAVESTENJA[0][0] and "[1/2]" in OBAVESTENJA[0][1][1]
       and "pokusaj" not in OBAVESTENJA[0][1][1] and ZVUCI and TREPTANJA,
       "captcha čeka unos, a radiš u drugom prozoru: zvuk, treptanje i obaveštenje: %s" % (OBAVESTENJA,))
    FOKUS[0] = True                   # sledeci put je program u prvom planu
    app.e_cap.delete(0, "end")
    app.e_cap.insert(0, "V0a8h")      # pogresno veliko slovo
    app._potvrdi()


def druga_captcha():
    if str(app.e_cap.cget("state")) == "disabled":
        return "cekaj"
    ok(len(OBAVESTENJA) == 1 and len(ZVUCI) == 2 and len(TREPTANJA) == 1,
       "program je u prvom planu: samo zvuk, bez obaveštenja (%d/%d/%d)" % (len(OBAVESTENJA), len(ZVUCI), len(TREPTANJA)))
    FOKUS[0] = False
    app.obavestenje_cap_var.set(False)
    app.e_cap.delete(0, "end")
    app.e_cap.insert(0, "SDYYP")
    app._potvrdi()


def treca_captcha():
    if str(app.e_cap.cget("state")) == "disabled":
        return "cekaj"
    ok(len(OBAVESTENJA) == 1 and len(ZVUCI) == 2 and app.baza.podesavanje("obavestenje_captcha", "1") == "0",
       "isključeno u meniju Alati: bez zvuka i obaveštenja")
    app.obavestenje_cap_var.set(True)
    app.e_cap.delete(0, "end")
    app.e_cap.insert(0, "r75NZ")
    app._potvrdi()


def kraj_pretrage():
    if app.posao:
        return "cekaj"
    ok(len(app.rezultati) == 2, "dva rezultata u tabeli")
    vals = [app.tree_p.item(i, "values") for i in app.tree_p.get_children("")]
    ok(vals[0][0] == "4415" and vals[0][2] == "425" and "nije pronađeno" in vals[1][-1], "redovi tabele: %s" % (vals,))
    ok(not app.captcha_frame.winfo_ismapped(), "panel captche sklonjen posle pretrage")
    root.update()
    ok(app.lbl_opis.cget("text").startswith("Rezultat pretrage - uspešno: 1 od 2, nije uspelo: 1") and app.lbl_opis.winfo_ismapped()
       and app.lbl_opis.winfo_rooty() + app.lbl_opis.winfo_height() <= root.winfo_rooty() + root.winfo_height(),
       "ishod u statusnoj traci glavnog prozora: %s" % app.lbl_opis.cget("text"))
    ok("ПЕТРОВИЋ ПЕТАР 1/4" in vals[0][7] and vals[0][8] == "Нема терета", "kolone vlasnici i tereti: %s | %s" % (vals[0][7], vals[0][8]))
    ok(vals[0][5] == "1" and vals[0][6] == "2", "kolone objekata i posebnih delova: %s %s" % (vals[0][5], vals[0][6]))
    root.update()
    # nema vise panela "Rezultat pretrazivanja parcela" ispod tabele: tabela zauzima ceo prostor
    rh = int(ak.ttk.Style().lookup("Treeview", "rowheight"))
    mesta = app.tree_p.winfo_height() // rh - 1
    ok(not hasattr(app, "panel_p") and not hasattr(app, "_pp") and mesta >= 12,
       "bez panela ispod rezultata, tabela ima mesta za %d redova" % mesta)
    z0 = app.rezultati["r1"][0]
    ind = os.path.join(ak.dir_izvoda(z0["ko_id"], z0["ko"], z0["broj"]), "indeks.json")
    ok(os.path.exists(ind), "originalne stranice sacuvane: %s" % ind)
    slikaj("ekran_2_pretraga.png")
    kopiranje_pretrage()
    # dvoklik na parcelu: delovi, zgrade i stanovi u posebnom prozoru (isto kao na eKatastru)
    app.tree_p.selection_set(app.tree_p.get_children("")[0])
    app.detalji_pretrage()
    root.update()
    pan = app._panel
    tp = pan["tabele"]
    ok(tp["parcela"].get_children("") and tp["o"].get_children("") == ("o0",) and tp["p"].get_children("") == ("p0", "p1"),
       "poseban prozor: delovi, zgrada i stan prikazani")
    ok("НИКОЛИЋ МИЛИЦА 1/1" in tp["p"].item("p0", "values")[-1], "panel: vlasnik stana u redu stana: %s" % (tp["p"].item("p0", "values"),))
    ok("ПЕТРОВИЋ ПЕТАР 1/4" in tp["o"].item("o0", "values")[-1], "panel: vlasnici zgrade u redu zgrade")
    for oznaka, ocek in (("p", ["НИКОЛИЋ МИЛИЦА", "3. Подаци о посебном делу објекта - В2 лист", "1. Подаци о парцели - А лист",
                                "Датум ажурности"]),
                         ("o", ["Имаоци права на објекту", "2. Подаци о зградама"]),
                         ("parcela", ["Имаоци права на парцели - Б лист", "Терети на парцели"])):
        tr = tp[oznaka]
        prvi = tr.get_children("")[0]
        tr.selection_set(prvi)
        tr.focus(prvi)
        w = app._otvori_iz_panela(pan, oznaka)
        root.update()
        tx = app._poslednji_izvod
        ok(w is not None and all(x in tx for x in ocek), "dvoklik na red (%s) otvara ceo izvod kao na sajtu: %s" % (
            oznaka, [x for x in ocek if x not in tx]))
        if oznaka == "p":
            w.geometry("940x860+420+0")
            root.update()
            slikaj("ekran_2c_dvoklik_stan.png")
        w.destroy()
    t_o = tp["o"]
    kp = next(k for k in app._kopiranja if k.tree is t_o)
    klik_na_celiju(t_o, "o0", "7")
    ok(kp.e is not None and "ПЕТРОВИЋ ПЕТАР" in kp.e.get(), "panel: klik na ćeliju vlasnika zgrade otvara polje")
    kp.zatvori()
    t_o.winfo_toplevel().destroy()
    # dodaj u pracenje bez dijaloga
    app._dijalog_podataka = lambda *a, **k: ("KLIJENT TEST", "GRUPA A", "")
    app.dodaj_iz_pretrage()
    ok(len(app.baza.parcele()) == 1, "parcela dodata u pracenje sa snimkom")
    # kao u Asistent PRO: dve parcele istog klijenta dodate iz Pretrage bez grupe -> grupa sa imenom klijenta
    z, podaci, _ = app.rezultati["r1"]
    for broj in ("4416", "4417"):
        app._dodaj_red_pretrage(dict(z, broj=broj), podaci, "")
    nove = [i for i in app.tree_p.get_children("") if app.tree_p.set(i, "parcela") in ("4416", "4417")]
    app.tree_p.selection_set(nove[:1])
    app._dijalog_podataka = lambda *a, **k: ("Jovanović Ana", "", "")
    app.dodaj_iz_pretrage()
    p1 = next(p for p in app.baza.parcele() if p["broj"] == "4416")
    ok(not p1["grupa"] and app.tree.parent(str(p1["id"])) == "", "jedna parcela klijenta ostaje bez grupe")
    app.tree_p.selection_set(nove[1:])
    app._dijalog_podataka = lambda *a, **k: ("JOVANOVIC ANA", "", "")
    app.dodaj_iz_pretrage()
    root.update()
    nove_p = [p for p in app.baza.parcele() if p["broj"] in ("4416", "4417")]
    ok(len(nove_p) == 2 and {p["grupa"] for p in nove_p} == {"Jovanović Ana"}
       and all(app.tree.parent(str(p["id"])) == "g:Jovanović Ana" for p in nove_p)
       and app.tree.item("g:Jovanović Ana", "open") and "grupisane" in app.lbl_opis.cget("text"),
       "druga parcela istog klijenta iz Pretrage: obe same u grupu klijenta: %s / %s" % (
           [(p["broj"], p["grupa"]) for p in nove_p], app.lbl_opis.cget("text")))
    # izmena: dve izabrane parcele, prva vec ima tog klijenta, druga dobija istog -> grupa
    app.baza.ukloni([p["id"] for p in nove_p])
    app.baza.obrisi_grupu("Jovanović Ana")
    for broj, kl in (("4416", "Marić Ivan"), ("4417", "")):
        app.baza.dodaj(z["opstina_id"], z["opstina"], z["ko_id"], z["ko"], broj, kl)
    ids = sorted(p["id"] for p in app.baza.parcele() if p["broj"] in ("4416", "4417"))
    app.osvezi_listu()
    app.tree.selection_set([str(i) for i in ids])
    app._dijalog_podataka = lambda *a, **k: ("Marić Ivan", "", "")
    app.izmeni()
    gr = {p["grupa"] for p in app.baza.parcele(ids)}
    ok(gr == {"Marić Ivan"}, "izmena više parcela: klijent dodat drugoj -> obe u grupu klijenta: %s" % gr)
    app.baza.ukloni(ids)
    app.baza.obrisi_grupu("Marić Ivan")
    app.tree_p.delete(*nove)
    for i in nove:
        app.rezultati.pop(i, None)
    app.osvezi_listu()


def mis(w, dogadjaj, x, y):
    w.event_generate(dogadjaj, x=x, y=y, rootx=w.winfo_rootx() + x, rooty=w.winfo_rooty() + y)


def klik_na_celiju(tree, iid, kol):
    tree.see(iid)
    root.update()
    x, y, w, h = tree.bbox(iid, kol)
    mis(tree, "<Button-1>", x + 8, y + h // 2)
    mis(tree, "<ButtonRelease-1>", x + 8, y + h // 2)
    root.update()


def snimak(w, x, y, sir, vis, ime):
    root.update()
    root.update_idletasks()
    put = os.path.join(RAD, ime)
    subprocess.run(["import", "-window", "root", "-crop", "%dx%d+%d+%d" % (sir, vis, w.winfo_rootx() + x,
                                                                          w.winfo_rooty() + y), put], check=False)
    return put


def razlika(a, b):
    r = subprocess.run(["compare", "-metric", "AE", "-fuzz", "6%", a, b, "null:"], capture_output=True, text=True)
    try:
        return int(float(r.stderr.split()[0]))
    except (ValueError, IndexError):
        return 10 ** 6


def nevidljivo_polje(tree, iid, kol, kop, opis, x_u_celiji=None):
    """Pritisak na celiju: polje za oznacavanje se otvori, a celija izgleda isto kao izabran red pre toga."""
    tree.see(iid)
    tree.selection_set(iid)
    root.update()
    x, y, w, h = tree.bbox(iid, kol)
    a = snimak(tree, x, y, w, h, "pre.png")
    mis(tree, "<Button-1>", x + (x_u_celiji or w // 2), y + h // 2)
    b = snimak(tree, x, y, w, h, "posle.png")
    d = razlika(a, b)
    ok(kop.e is not None and d <= 12, "polje se ne vidi, ćelija ista posle klika (%s): različitih piksela %d" % (opis, d))
    mis(tree, "<ButtonRelease-1>", x + (x_u_celiji or w // 2), y + h // 2)
    ok(kop.e is not None and not kop.e.selection_present(), "običan klik ništa ne označava (%s)" % opis)
    if d > 12:
        shutil.copy(a, os.path.join(SLIKE, "razlika_pre_%s.png" % opis))
        shutil.copy(b, os.path.join(SLIKE, "razlika_posle_%s.png" % opis))
    kop.zatvori()


def prevuci(w, x1, x2, y, kop, ocekivano, opis):
    """Jedan potez misem: pritisak, prevlacenje, pustanje -> oznacen deo teksta."""
    mis(w, "<Button-1>", x1, y)
    mis(w, "<B1-Motion>", (x1 + x2) // 2, y)
    mis(w, "<B1-Motion>", x2, y)
    mis(w, "<ButtonRelease-1>", x2, y)
    root.update()
    oznaceno = kop.tekst_izbora()
    ok(oznaceno == ocekivano, "jednim prevlačenjem označeno (%s): %r" % (opis, oznaceno))
    if kop.e is not None:
        kop.e.event_generate("<<Copy>>")
        ok(root.clipboard_get() == ocekivano, "Ctrl+C kopira samo označeni deo (%s)" % opis)


def kopiranje_pretrage():
    tp_ = app.tree_p
    st = app._sirine.get(str(tp_), {}).get("auto", {})
    ok(st.get("vlasnici", 0) > 200 and st.get("nacin") == ak.px(ak.MAX_KOLONE["nacin"]) and
       all(int(tp_.column(k, "width")) == w for k, w in st.items()),
       "širine kolona po sadržaju: %s" % st)
    r1 = tp_.get_children("")[0]
    kop = app._kop_pretrage
    klik_na_celiju(tp_, r1, "nacin")
    ok(kop.e is not None and kop.e.get() == tp_.set(r1, "nacin"), "klik na ćeliju otvara polje sa njenim tekstom")
    if kop.e is not None:
        kop.e.select_range(0, 8)
        kop.e.event_generate("<<Copy>>")
        ok(root.clipboard_get() == tp_.set(r1, "nacin")[:8], "Ctrl+C kopira označeni deo: %r" % root.clipboard_get())
        kop.e.selection_clear()
        kop.e.event_generate("<<Copy>>")
        ok(root.clipboard_get() == tp_.set(r1, "nacin"), "Ctrl+C bez oznake kopira celu ćeliju")
        slikaj("ekran_2d_kopiranje.png")
        taster(kop.e, "Escape")
        ok(kop.e is None, "Esc sklanja polje")
    # nevidljivo polje i oznacavanje jednim potezom
    for kol in ("nacin", "povrsina", "parcela", "#0"):
        nevidljivo_polje(tp_, r1, kol, kop, "pretraga " + kol)
    x, y, w, h = tp_.bbox(r1, "nacin")
    tekst = tp_.set(r1, "nacin")
    rec = tekst.split()[0]
    mera = ak.tkfont.Font(font=ak.FONT)
    x0 = x + kop.POMAK_TEKSTA
    prevuci(tp_, x0 + 1, x0 + mera.measure(rec) - 1, y + h // 2, kop, rec, "prva reč načina korišćenja")
    slikaj("ekran_2d_oznaceno.png")
    tekst_p = tp_.set(r1, "parcela")
    x, y, w, h = tp_.bbox(r1, "parcela")
    x0 = x + kop.POMAK_TEKSTA
    prevuci(tp_, x0 + mera.measure(tekst_p[:1]) + 1, x0 + mera.measure(tekst_p) + 6, y + h // 2, kop, tekst_p[1:],
            "broj parcele bez prve cifre")
    kop.zatvori()
    tp_.selection_set(tp_.get_children(""))
    taster(tp_, "Control-c")
    redovi = root.clipboard_get().split("\n")
    ok(len(redovi) == 2 and redovi[0].split("\t")[1] == "4415", "Ctrl+C u tabeli kopira izabrane redove: %r" % redovi[:1])
    kop.kopiraj_brojeve()
    ok(root.clipboard_get() == "4415\n999", "kopiraj brojeve parcela: %r" % root.clipboard_get())
    tp_.selection_set(r1)
    root.update()


def proveri_sve():
    app.auto_var.set(True)            # citac sad zna sve znakove sa prethodnih slika
    mock_sajt.STANJE["vlasnik"] = "НОВИ ВЛАСНИК, 1/1"
    app.proveri(False)


def kraj_provere():
    if app.posao:
        return "cekaj"
    p = app.baza.parcele()[0]
    ok(p["provereno"] and not p["greska"], "provera uspela: %s %s" % (p["provereno"], p["greska"]))
    ok(p["id"] in app.sesija_ok, "oznacena kao provereno u ovom otvaranju")
    app._otvorene.add("g:GRUPA A")
    app.osvezi_listu()
    root.update()
    ok(app.kartice["provereno"]["broj"].cget("text") == "1 / 1", "kartica provereno: %s" %
       app.kartice["provereno"]["broj"].cget("text"))
    ok(app._ikona_mala is not None, "nova ikonica u zaglavlju")
    slikaj("ekran_3_pracenje.png")


def druga_provera():
    mock_sajt.STANJE["vlasnik"] = "ДРУГИ ВЛАСНИК, 1/2"
    app.proveri(False)


def kraj_druge():
    if app.posao:
        return "cekaj"
    p = app.baza.parcele()[0]
    ok(p["promene"] and "ДРУГИ ВЛАСНИК" in p["promene"], "promena vlasnika oznacena: %s" % (p["promene"] or "")[:120])
    tag = app.tree.item(str(p["id"]), "tags")[0]
    ok(str(app.tree.tag_configure(tag, "background")) == ak.BG_PROMENA, "red jarko žut - promena u ovoj sesiji (%s)" %
       app.tree.tag_configure(tag, "background"))
    ok("bold" in str(app.tree.tag_configure(tag, "font")), "promena podebljana: %s" % (app.tree.tag_configure(tag, "font"),))
    ok(app.tree.item(str(p["id"]), "values")[-1].startswith("PROMENA u ovoj sesiji"), "kolona Provera: PROMENA u ovoj sesiji")
    ok(str(p["id"]) not in app._zelene, "promenjena parcela nema zelenu oznaku")
    ok(app.tree.item("g:GRUPA A", "tags") == ("grupa_novo",), "grupa sa promenom istaknuta")
    ks = app.kartice["sesija"]
    ok(ks["broj"].cget("text") == "1" and str(ks["okvir"].cget("bg")) == ak.BG_PROMENA, "kartica Promena u ovoj sesiji: 1, žuta")
    app.osvezi_listu()
    slikaj("ekran_4_promena.png")
    app.tree.selection_set(str(p["id"]))
    app.detalji()


def detalji_slika():
    slikaj("ekran_5_detalji.png")
    ok(not app.baza.parcele()[0]["promene"], "otvaranje detalja skida oznaku promene")
    for w in root.winfo_children():
        if isinstance(w, ak.tk.Toplevel) and w is not app.log_prozor:   # prozor sa porukama ostaje (sakriven)
            w.destroy()


def grupa_klijenta():
    for broj, kl in (("4415", "Petrović Marko"), ("10383", "PETROVIC MARKO")):
        app.baza.dodaj(70106, "ВОЖДОВАЦ", 1, "ВОЖДОВАЦ", broj, klijent=kl)
    ids = {p["broj"]: p["id"] for p in app.baza.parcele() if p["ko_id"] == 1}
    a, b = ids["4415"], ids["10383"]
    app.osvezi_listu()
    ok(app.tree.exists(str(a)) and app.tree.parent(str(a)) == "", "parcela bez grupe je u listi bez reda '(bez grupe)'")
    app._grupisi_klijenta("PETROVIC MARKO", "", b)
    g = next((x for x in app.baza.grupe() if ak.lat(x) == "petrovic marko"), "")
    ok(g and app.tree.parent(str(a)) == "g:" + g == app.tree.parent(str(b)),
       "druga parcela istog klijenta -> obe u grupu klijenta: %s" % app.baza.grupe())
    ok(g and app.tree.item("g:" + g, "open"), "nova grupa otvorena")
    app.tree.selection_set("g:" + g)
    app.proveri(True)
    STANJE_T.update(a=a, b=b, g=g)


STANJE_T = {}


def kraj_trece():
    if app.posao:
        return "cekaj"
    a, b, g = STANJE_T["a"], STANJE_T["b"], STANJE_T["g"]
    root.update()
    for pid in (a, b):
        z = app._zelene.get(str(pid))
        ok(z is not None and z.cget("text").startswith("✓ ") and z.winfo_ismapped(),
           "zelena ćelija Provera (provereno bez promene): %s" % (z.cget("text") if z else None))
    ok("g:" + g in app._zelene and app._zelene["g:" + g].winfo_ismapped(), "grupa u kojoj je sve provereno ima zelenu ćeliju")
    bb = app.tree.bbox(str(a), "provereno")
    ok(bb and bb[0] + bb[2] <= app.tree.winfo_width(), "kolona Provera se vidi bez pomeranja udesno: %s / %d" % (
        bb, app.tree.winfo_width()))
    slikaj("ekran_6_zelene.png")
    kp = app._kop_pracenja
    nevidljivo_polje(app.tree, str(a), "parcela", kp, "praćenje KO/parcela")
    nevidljivo_polje(app.tree, str(a), "#0", kp, "praćenje klijent", x_u_celiji=60)
    z = app._zelene[str(b)]
    app.tree.selection_set(str(b))
    root.update()
    zx, zy, zw, zh = z.winfo_x(), z.winfo_y(), z.winfo_width(), z.winfo_height()
    pre = snimak(app.tree, zx, zy, zw, zh, "zpre.png")
    mis(z, "<Button-1>", zw // 2, zh // 2)
    posle = snimak(app.tree, zx, zy, zw, zh, "zposle.png")
    d = razlika(pre, posle)
    ok(kp.e is not None and d <= 12, "zelena ćelija Provera ista posle klika: različitih piksela %d" % d)
    mis(z, "<ButtonRelease-1>", zw // 2, zh // 2)
    kp.zatvori()
    tz = z.cget("text")
    datum = tz.split()[1]
    pz = int(z.cget("bd")) + int(z.cget("padx"))
    mera = ak.tkfont.Font(font=ak.FONT)
    x1 = pz + mera.measure(tz[:2]) + 1
    prevuci(z, x1, x1 + mera.measure(datum) - 2, zh // 2, kp, datum, "datum u zelenoj ćeliji")
    kp.zatvori()
    app.odlozi([a], meseci=3)
    tag = app.tree.item(str(a), "tags")[0]
    ok(str(app.tree.tag_configure(tag, "foreground")) == ak.T_SIVO and
       "ODLOŽENO do" in app.tree.item(str(a), "values")[-1], "odložena parcela siva, 'ODLOŽENO do ...': %s" %
       app.tree.item(str(a), "values")[-1])
    ok("1 odloženo" in app.kartice["svi"]["dod"].cget("text"), "kartica: %s" % app.kartice["svi"]["dod"].cget("text"))
    app.arhiviraj([b])
    ok(not app.tree.exists(str(b)), "arhivirana parcela nije u običnom prikazu")
    app.prikaz_var.set(ak.PRIKAZI[6])
    app.osvezi_listu()
    ok(app.tree.exists(str(b)) and not app.tree.exists(str(a)), "Prikaz Arhiva: samo arhivirana")
    app.prikaz_var.set(ak.PRIKAZI[0])
    app.osvezi_listu()
    zadaci = []
    stari = app._pokreni
    app._pokreni = lambda z, r: zadaci.extend(z)
    app.proveri(False)
    app._pokreni = stari
    pids = [z["pid"] for z in zadaci]
    ok(pids and a not in pids and b not in pids, "Proveri sve preskače odložene i arhivirane: %s" % pids)
    app.vrati_u_proveru([b])
    ok(app.tree.exists(str(b)), "Vrati u redovnu proveru")
    klik_na_celiju(app.tree, str(a), "parcela")
    ok(app._kop_pracenja.e is not None and app._kop_pracenja.e.get() == "ВОЖДОВАЦ  4415",
       "praćenje: klik na ćeliju za kopiranje: %s" % (app._kop_pracenja.e.get() if app._kop_pracenja.e else None))
    app._kop_pracenja.zatvori()
    app.tree.selection_set(str(a))
    app.osvezi_listu()
    slikaj("ekran_7_odlozeno.png")
    root.destroy()


for f, t in ((kucaj_opstinu, 800), (kucaj_vozdovac, 600), (izaberi_ko, 600), (captcha_vidljiva, 300), (druga_captcha, 300),
             (treca_captcha, 300), (kraj_pretrage, 500), (proveri_sve, 500), (kraj_provere, 500),
             (druga_provera, 500), (kraj_druge, 800), (detalji_slika, 300), (grupa_klijenta, 500), (kraj_trece, 500)):
    korak(f, t)
root.after(1500, sledeci)
root.after(240000, root.destroy)
root.mainloop()
print("\nUKUPNO GRESAKA:", len(GRESKE))
for g in GRESKE:
    print("  -", g)
dn = os.path.join(RAD, "dnevnik.txt")
if os.path.exists(dn):
    print("--- dnevnik (kraj) ---")
    print(open(dn, encoding="utf-8").read()[-2500:])
sys.exit(1 if GRESKE else 0)
