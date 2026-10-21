# -*- coding: utf-8 -*-
"""Sacuvaj sve kao PDF: sacuvani originali 'Подаци о непокретности' -> PDF preko pregledaca (ovde Chromium)."""
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_pdf_")
os.environ["KATASTAR_TEST"] = "1"
os.environ["KATASTAR_PREGLEDAC"] = "/opt/pw-browsers/chromium"
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
PORUKE = []


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: (PORUKE.append((ime,) + a), True)[1]


ak.messagebox = TihiMessagebox()
GRESKE = []


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


root = ak.tk.Tk()
app = ak.App(root)
root.geometry("1400x860+0+0")
for _ in range(5):
    root.update()

ok(ak.ime_fajla("ЖЕЛЕЗНИК 1741/1 - 2 objekat А:Б\"В?") == "ЖЕЛЕЗНИК 1741-1 - 2 objekat А-Б-В-", "naziv fajla bez / : \" ?")
ok(not app.log_prozor.winfo_viewable(), "okno sa porukama nije više na glavnom prozoru")
n = mock_sajt.nepokretnost
ak.sacuvaj_izvode(703702, "ЖЕЛЕЗНИК", "1741/1", {"parcela": n("zemljiste"),
                                                  "objekat МИЛАНА МИЈАЛКОВИЋА 1": n("zgrada"),
                                                  "poseban deo МИЛАНА МИЈАЛКОВИЋА 1, ulaz 1, stan 2": n("poseban")})
ak.sacuvaj_izvode(703702, "ЖЕЛЕЗНИК", "1741/2", {"parcela": n("zemljiste")})
for broj, nadjeno in (("1741/1", True), ("1741/2", True), ("999", False), ("1741/7", True)):
    z = {"ko_id": 703702, "ko": "ЖЕЛЕЗНИК", "broj": broj}
    app._dodaj_red_pretrage(z, None, "proba")
    iid = "r%d" % len(app.rezultati)
    if nadjeno:
        app.rezultati[iid] = (z, {"proba": 1}, "")
izlaz = os.path.join(RAD, "izlaz")
os.makedirs(izlaz)


def dugme(tekst):
    def sva(w):
        for d in w.winfo_children():
            if isinstance(d, ak.ttk.Button):
                yield d
            yield from sva(d)
    nadjena = [d for d in sva(root) if d.cget("text") == tekst]
    return nadjena[0] if len(nadjena) == 1 and nadjena[0].winfo_ismapped() else None


def pokreni_i_sacekaj(f):
    """Kao u programu: nit javlja napredak preko root.after, pa mora da radi mainloop."""
    kraj = time.time() + 240

    def provera():
        if getattr(app, "_pdf_radi", False) and time.time() < kraj:
            root.after(100, provera)
        else:
            root.quit()
    root.after(0, f)
    root.after(300, provera)
    root.mainloop()
    root.update()


PITANJA = []


def odgovor(folder):
    ak.filedialog.askdirectory = lambda **k: (PITANJA.append(k), folder)[1]


# podrazumevano: program pita pri svakom cuvanju (Dejan: svaka parcela ima svoj folder, drugi klijent)
ok(app.pdf_folder() is None, "podrazumevano: pita za folder pri svakom čuvanju")
klijent = os.path.join(RAD, "Klijent A")
os.makedirs(klijent)
with open(os.path.join(klijent, "ЖЕЛЕЗНИК 1741-1 - 1 parcela.pdf"), "wb") as fp:
    fp.write(b"STARI")                       # PDF od ranije u folderu klijenta
odgovor(klijent)
b_pdf = dugme("Sačuvaj sve kao PDF")
ok(b_pdf is not None and dugme("Folder za PDF...") is not None, "dugmad 'Sačuvaj sve kao PDF' i 'Folder za PDF...'")
app.tree_p.selection_set("r1")
t0 = time.time()
pokreni_i_sacekaj(b_pdf.invoke)
ok(len(PITANJA) == 1 and "Gde da sačuvam PDF" in PITANJA[0]["title"] and "3 parcele" in PITANJA[0]["title"],
   "pitao gde da sačuva: %s" % [p.get("title") for p in PITANJA])
fajlovi = sorted(os.listdir(klijent))
print("     %s (%.1f s)" % (fajlovi, time.time() - t0))
novi = ["ЖЕЛЕЗНИК 1741-1 - 1 parcela (2).pdf", "ЖЕЛЕЗНИК 1741-1 - 2 objekat МИЛАНА МИЈАЛКОВИЋА 1.pdf",
        "ЖЕЛЕЗНИК 1741-1 - 3 poseban deo МИЛАНА МИЈАЛКОВИЋА 1, ulaz 1, stan 2.pdf", "ЖЕЛЕЗНИК 1741-2 - 1 parcela.pdf"]
ok(fajlovi == sorted(novi + ["ЖЕЛЕЗНИК 1741-1 - 1 parcela.pdf"]),
   "PDF-ovi idu pravo u izabrani folder, bez podfoldera, redom")
with open(os.path.join(klijent, "ЖЕЛЕЗНИК 1741-1 - 1 parcela.pdf"), "rb") as fp:
    ok(fp.read() == b"STARI", "postojeći PDF u folderu nije presnimljen (novi je '... (2).pdf')")
for f in novi:
    put = os.path.join(klijent, f)
    with open(put, "rb") as fp:
        pocetak = fp.read(5)
    tekst = subprocess.run(["pdftotext", "-layout", put, "-"], capture_output=True, text=True).stdout
    ok(pocetak == b"%PDF-" and "Извод из базе података катастра непокретности" in tekst and "file:" not in tekst,
       "%s: pravi PDF, ćirilica kao na sajtu, bez putanje u zaglavlju" % f)
tekst = subprocess.run(["pdftotext", os.path.join(klijent, novi[2]), "-"], capture_output=True, text=True).stdout
ok(mock_sajt.STANJE["stan_vlasnik"] in tekst, "PDF posebnog dela ima vlasnika stana")
info = subprocess.run(["pdfinfo", os.path.join(klijent, novi[0])], capture_output=True, text=True).stdout
ok("(A4)" in info, "papir A4: %s" % [l for l in info.splitlines() if "size" in l])
log = app.txt.get("1.0", "end")
ok("PDF izvoda sačuvano: 4" in log and "bez sačuvanih originala: ЖЕЛЕЗНИК 1741/7" in log,
   "poruka: 4 PDF, za 1741/7 nema originala")
ok("PDF izvoda sačuvano: 4" in app.lbl_opis.cget("text") and klijent in app.lbl_opis.cget("text"),
   "ishod u statusnoj traci, sa folderom: %s" % app.lbl_opis.cget("text"))

# Odustani u izboru foldera: nista se ne pravi
odgovor("")
pokreni_i_sacekaj(b_pdf.invoke)
ok(len(PITANJA) == 2 and PITANJA[1]["initialdir"] == klijent and sorted(os.listdir(klijent)) == fajlovi
   and "nije sačuvan" in app.lbl_opis.cget("text"), "Odustani: ništa se ne čuva; dijalog počinje od poslednjeg foldera")

# vise izabranih redova = samo oni, u folder drugog klijenta
klijent_b = os.path.join(RAD, "Klijent B")
odgovor(klijent_b)
app.tree_p.selection_set(("r2", "r3"))
pokreni_i_sacekaj(b_pdf.invoke)
ok(os.path.isdir(klijent_b) and os.listdir(klijent_b) == ["ЖЕЛЕЗНИК 1741-2 - 1 parcela.pdf"]
   and "1 parcela" in PITANJA[-1]["title"], "izabrana 2 reda: samo pronađena 1741/2, u folder drugog klijenta")

# Folder za PDF...: stalni folder -> vise ne pita, svako cuvanje u nov podfolder
dugme("Folder za PDF...").invoke()
root.update()
dij = app._pdf_dijalog
ok(dij["nacin"].get() == "pitaj" and dij["prozor"].winfo_viewable(), "Folder za PDF... otvara izbor (sada: pita)")
odgovor(izlaz)
dij["izaberi"]()
ok(dij["nacin"].get() == "stalni" and dij["put"].get() == os.path.normpath(izlaz), "izabran stalni folder")
dij["ok"]()
ok(app.pdf_folder() == os.path.normpath(izlaz) and izlaz in app.lbl_opis.cget("text"),
   "stalni folder zapamćen i javljen: %s" % app.lbl_opis.cget("text"))
n_pitanja = len(PITANJA)
app.tree_p.selection_set("r1")
pokreni_i_sacekaj(b_pdf.invoke)
pokreni_i_sacekaj(b_pdf.invoke)
folderi = sorted(glob.glob(os.path.join(izlaz, "*")))
ok(len(PITANJA) == n_pitanja and len(folderi) == 2 and all("ЖЕЛЕЗНИК (3 parcele)" in f for f in folderi)
   and all(len(os.listdir(f)) == 4 for f in folderi),
   "stalni folder: ne pita, dva čuvanja = dva podfoldera, ništa se ne presnimava: %s" % [os.path.basename(f) for f in folderi])
dugme("Folder za PDF...").invoke()
root.update()
app._pdf_dijalog["nacin"].set("pitaj")
app._pdf_dijalog["ok"]()
ok(app.pdf_folder() is None and app.baza.podesavanje("pdf_folder") == os.path.normpath(izlaz),
   "vraćeno na 'pitaj pri svakom čuvanju' (stalni folder ostaje upamćen za izbor)")

# v18: jedna parcela, zgrada ili poseban deo -> "Sačuvaj kao PDF..." (desni klik u prozoru parcele i dugme u izvodu)
kp = "poseban deo МИЛАНА МИЈАЛКОВИЋА 1, ulaz 1, stan 2, evid. 5, СТАН"
ak.sacuvaj_izvode(703702, "ЖЕЛЕЗНИК", "1741/9", {"parcela": n("zemljiste"), "objekat МИЛАНА МИЈАЛКОВИЋА 1": n("zgrada"),
                                                  kp: n("poseban")})
sn9 = {"opstina": "ЧУКАРИЦА", "ko": "ЖЕЛЕЗНИК", "nepokretnost": {}, "napomene": [],
       "delovi": [["1", "500", "МИЛАНА МИЈАЛКОВИЋА", "ЗЕМЉИШТЕ ПОД ЗГРАДОМ", "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", ""]],
       "objekti": [["1", "МИЛАНА МИЈАЛКОВИЋА", "1", "", "120", "СТАМБЕНА ЗГРАДА", "ПРЕУЗЕТ"]],
       "posebni": [["МИЛАНА МИЈАЛКОВИЋА 1", "5", "1", "2", "", "СТАН", "55"],
                   ["МИЛАНА МИЈАЛКОВИЋА 1", "6", "1", "3", "", "СТАН", "60"]]}
app._prozor_detalja("ЧУКАРИЦА, KO ЖЕЛЕЗНИК, parcela 1741/9", sn9, [], mesto=(703702, "ЖЕЛЕЗНИК", "1741/9"))
root.update()
pan = app._panel
meniji = []
stari_popup = ak.tk.Menu.tk_popup
ak.tk.Menu.tk_popup = lambda self, *a: meniji.append(
    [self.entrycget(i, "label") for i in range(self.index("end") + 1) if self.type(i) == "command"])
tpos = pan["tabele"]["p"]
x, y, w_, h = tpos.bbox("p0")
tpos.event_generate("<Button-3>", x=x + 5, y=y + h // 2, rootx=tpos.winfo_rootx() + x + 5, rooty=tpos.winfo_rooty() + y + h // 2)
root.update()
ak.tk.Menu.tk_popup = stari_popup
ok(meniji and "Sačuvaj kao PDF..." in meniji[-1], "desni klik na stan: 'Sačuvaj kao PDF...': %s" % meniji[-1:])
jedan = os.path.join(RAD, "Klijent C")
odgovor(jedan)
n_pitanja = len(PITANJA)
pokreni_i_sacekaj(lambda: app._pdf_iz_panela(pan, "p"))
ime_stana = "ЖЕЛЕЗНИК 1741-9 - " + kp + ".pdf"
ok(len(PITANJA) == n_pitanja + 1 and ime_stana in PITANJA[-1]["title"] and os.path.isdir(jedan)
   and os.listdir(jedan) == [ime_stana], "stan: pita za folder i čuva samo taj PDF: %s" % (os.listdir(jedan) if os.path.isdir(jedan) else None))
if os.path.isfile(os.path.join(jedan, ime_stana)):
    tekst = subprocess.run(["pdftotext", "-layout", os.path.join(jedan, ime_stana), "-"], capture_output=True, text=True).stdout
    ok("Извод из базе података катастра непокретности" in tekst and mock_sajt.STANJE["stan_vlasnik"] in tekst,
       "PDF stana kao original sa eKatastra (vlasnik stana)")
pokreni_i_sacekaj(lambda: app._pdf_iz_panela(pan, "parcela"))
ok(sorted(os.listdir(jedan)) == sorted([ime_stana, "ЖЕЛЕЗНИК 1741-9 - parcela.pdf"]), "parcela: samo njen PDF")
wi = app._otvori_iz_panela(pan, "o")
root.update()
b = [d for d in wi.winfo_children()[0].winfo_children() if isinstance(d, ak.ttk.Button) and d.cget("text") == "Sačuvaj kao PDF..."]
ok(len(b) == 1, "prozor „Подаци о непокретности“ zgrade ima dugme 'Sačuvaj kao PDF...'")
if b:
    pokreni_i_sacekaj(b[0].invoke)
ok("ЖЕЛЕЗНИК 1741-9 - objekat МИЛАНА МИЈАЛКОВИЋА 1.pdf" in os.listdir(jedan), "zgrada iz prozora izvoda sačuvana")
pokreni_i_sacekaj(lambda: app._pdf_iz_panela(pan, "parcela"))
ok("ЖЕЛЕЗНИК 1741-9 - parcela (2).pdf" in os.listdir(jedan), "ponovo ista parcela: '(2)', ništa se ne presnimava")
wi.destroy()
# red bez sacuvanog originala: poruka
tpos.selection_set("p1")
tpos.focus("p1")
PORUKE.clear()
app._pdf_iz_panela(pan, "p")
ok(PORUKE and "nije sačuvana originalna stranica" in PORUKE[-1][2], "stan bez originala: jasna poruka")
# stalni folder: ne pita, PDF ide pravo u taj folder (bez podfoldera)
app.baza.postavi_podesavanje("pdf_nacin", "stalni")
stalni = os.path.join(RAD, "stalni")
app.baza.postavi_podesavanje("pdf_folder", stalni)
n_pitanja = len(PITANJA)
pokreni_i_sacekaj(lambda: app._pdf_iz_panela(pan, "parcela"))
ok(len(PITANJA) == n_pitanja and os.listdir(stalni) == ["ЖЕЛЕЗНИК 1741-9 - parcela.pdf"],
   "stalni folder: jedan PDF bez pitanja, bez podfoldera")
app.baza.postavi_podesavanje("pdf_nacin", "pitaj")
tpos.winfo_toplevel().destroy()
root.update()

# bez originala i bez pregledaca: poruka, nista se ne pravi
PORUKE.clear()
app.tree_p.selection_set(("r3", "r4"))
app.pdf_pretrage()
ok(PORUKE and "nema sačuvanih originala" in PORUKE[-1][2], "za parcele bez originala jasna poruka")
os.environ["KATASTAR_PREGLEDAC"] = "/nema/chrome"
PORUKE.clear()
app.tree_p.selection_set("r1")
app.pdf_pretrage()
ok(PORUKE and "Edge ni Google Chrome" in PORUKE[-1][2], "bez Edge/Chrome jasna poruka")
PORUKE.clear()
app.pdf_pracenja()
ok(PORUKE and "Izaberi parcele" in PORUKE[-1][2], "praćenje bez izbora: poruka")

# v30 (Dejan: "da celu grupu, npr za klijenta, SVE skinem kao pdf"): lista praćenja, grupa = klijent
os.environ["KATASTAR_PREGLEDAC"] = "/opt/pw-browsers/chromium"
app.baza.postavi_podesavanje("pdf_nacin", "pitaj")
for broj in ("1741/1", "1741/2", "1741/7"):
    app.baza.dodaj(70106, "ЧУКАРИЦА", 703702, "ЖЕЛЕЗНИК", broj, klijent="Klijent D", grupa="Klijent D")
app.osvezi_listu()
app.nb.select(1)
root.update()
b_pr = dugme("Sačuvaj kao PDF")
ok(b_pr is not None, "lista praćenja: vidljivo dugme „Sačuvaj kao PDF“")
gid = "g:Klijent D"
ok(app.tree.exists(gid) and len(app.tree.get_children(gid)) == 3, "grupa Klijent D sa 3 parcele u listi")
klijent_d = os.path.join(RAD, "Klijent D")
odgovor(klijent_d)
app.tree.selection_set(gid)
n_pitanja = len(PITANJA)
ids_d = [int(c) for c in app.tree.get_children(gid)]
pokreni_i_sacekaj(lambda: app.pdf_pracenja(ids_d, "Klijent D"))
ok(len(PITANJA) == n_pitanja + 1 and "3 parcele" in PITANJA[-1]["title"], "grupa: pita za folder, 3 parcele")
fd = sorted(os.listdir(klijent_d)) if os.path.isdir(klijent_d) else []
ok(len(fd) == 4 and all(f.endswith(".pdf") for f in fd) and any("1741-2" in f for f in fd),
   "cela grupa: 4 PDF-a (3 za 1741/1 + 1 za 1741/2) u folder klijenta: %s" % fd)
ok("bez sačuvanih originala: ЖЕЛЕЗНИК 1741/7" in app.txt.get("1.0", "end"), "parcela bez originala javljena")
# dugme sa izabranom grupom radi isto (preko izbora u listi)
klijent_e = os.path.join(RAD, "Klijent E")
odgovor(klijent_e)
app.tree.selection_set(gid)
pokreni_i_sacekaj(b_pr.invoke)
ok(os.path.isdir(klijent_e) and len(os.listdir(klijent_e)) == 4, "dugme sa izabranom grupom: ista 4 PDF-a")
# stalni folder: podfolder nosi ime grupe
app.baza.postavi_podesavanje("pdf_nacin", "stalni")
izlaz_g = os.path.join(RAD, "izlaz_grupa")
app.baza.postavi_podesavanje("pdf_folder", izlaz_g)
pokreni_i_sacekaj(lambda: app.pdf_pracenja(ids_d, "Klijent D"))
podf = os.listdir(izlaz_g) if os.path.isdir(izlaz_g) else []
ok(len(podf) == 1 and "Klijent D (3 parcele)" in podf[0], "stalni folder: podfolder sa imenom grupe: %s" % podf)
app.baza.postavi_podesavanje("pdf_nacin", "pitaj")

# captcha panel nestaje i kad prozor nije prikazan (umanjen) u trenutku zavrsetka
app._pokazi_captchu_panel()
root.update()
root.withdraw()
root.update()
app._sakrij_captchu_panel()
root.deiconify()
root.update()
ok(not app.captcha_frame.winfo_manager(), "captcha panel nestaje i kad je prozor bio umanjen")
print("UKUPNO GRESAKA: %d" % len(GRESKE))
srv.shutdown()
