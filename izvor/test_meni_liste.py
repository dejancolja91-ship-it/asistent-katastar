# -*- coding: utf-8 -*-
"""v25 (Dejan: "Ovo je ostalo" - desni klik u listi pracenja imao 13 stavki): kratak meni za parcelu, vise parcela,
grupu i prazno mesto; svaka stavka radi; izbaceno je i dalje dostupno (dvoklik/Enter = Detalji, Ctrl+C = ceo red,
meniji Parcela i Grupa)."""
import importlib.util
import os
import shutil
import sys
import tempfile

RAD = tempfile.mkdtemp(prefix="kat_meni_")
os.environ["KATASTAR_TEST"] = "1"
shutil.copy("asistent_katastar.py", RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join("..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
UVECANJE = float(os.environ.get("TEST_UVECANJE", "1.0"))
GRESKE = []


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: True


ak.messagebox = TihiMessagebox()


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


K56 = "poseban deo УСТАНИЧКА 1, ulaz 1, stan 56, evid. 56, СТАН"
b = ak.Baza()
b.postavi_podesavanje("auto_grupe_sredjeno", "v15")
for broj, kl, gr in (("10383", "Klijent A", "Zgrada"), ("10384", "Klijent A", "Zgrada"), ("500", "Klijent B", "")):
    b.dodaj(70106, "ВОЖДОВАЦ", 703800, "КУМОДРАЖ", broj, kl, gr)
P = {x["broj"]: x["id"] for x in b.parcele()}
with b._con() as c:
    c.execute("UPDATE parcele SET promene=? WHERE id=?", ("Promenjen vlasnik", P["10383"]))
b.postavi_stavke(P["10383"], [K56])

root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
app.nb.select(1)
root.update()
POZIVI = []
app.proveri = lambda samo, neaktivni=False: POZIVI.append(("proveri", samo, tuple(app.izabrani_ids())))
app.izmeni = lambda: POZIVI.append(("izmeni", tuple(app.izabrani_ids())))
app.promeni_grupu = lambda: POZIVI.append(("premesti", tuple(app.izabrani_ids())))
app.ukloni = lambda: POZIVI.append(("ukloni", tuple(app.izabrani_ids())))
app.preimenuj_grupu = lambda: POZIVI.append(("preimenuj",))
app.obrisi_grupu = lambda: POZIVI.append(("obrisi",))
app.pdf_pracenja = lambda ids=None, naziv=None: POZIVI.append(("pdf", tuple(ids or ()), naziv))   # v30


class Dog:
    def __init__(self, w, x, y):
        self.widget, self.x, self.y = w, x, y
        self.x_root, self.y_root = w.winfo_rootx() + x, w.winfo_rooty() + y


MENI = []


def meni(iid, prazno=False):
    """Desni klik na red (ili na prazno mesto ispod redova); vraca listu stavki menija."""
    MENI.clear()
    stari = ak.tk.Menu.tk_popup
    ak.tk.Menu.tk_popup = lambda self, *a: MENI.append(self)
    try:
        root.update()
        if prazno:
            app._meni_desni(Dog(app.tree, 30, app.tree.winfo_height() - 5))
        else:
            app.tree.see(iid)
            root.update()
            x, y, w, h = app.tree.bbox(iid, "#0") or app.tree.bbox(iid)
            app._meni_desni(Dog(app.tree, x + w // 2, y + h // 2))
    finally:
        ak.tk.Menu.tk_popup = stari
    m = MENI[0]
    return [("---" if m.type(i) == "separator" else m.entrycget(i, "label") + (" ▸" if m.type(i) == "cascade" else ""))
            for i in range(m.index("end") + 1)]


def izaberi(oznaka):
    m = MENI[0]
    for i in range(m.index("end") + 1):
        if m.type(i) == "command" and m.entrycget(i, "label") == oznaka:
            m.invoke(i)
            root.update()
            return True
    ok(False, "nema stavke %r" % oznaka)
    return False


def stavki(lst):
    return sum(1 for x in lst if x != "---")


s1, s2, s3 = str(P["10383"]), str(P["10384"]), str(P["500"])
ok(app.tree.exists(s1) and app.tree.exists("g:Zgrada"), "parcele i grupa u listi")

# jedna parcela: prati se samo stan 56, ima promena
app.tree.selection_set(s1)
lst = meni(s1)
print("     meni parcele:", lst)
ok(lst == ["Proveri ovu parcelu", "Sačuvaj kao PDF", "Kopiraj broj parcele", "Izmeni (klijent, grupa, napomena)...",
           "Označi kao pregledano", "Prati celu parcelu (sada samo: stan 56)", "---", "Odloži proveru ▸", "Arhiviraj",
           "---", "Ukloni iz praćenja"], "meni parcele: kratak (%d stavki umesto 13)" % stavki(lst))
for izbaceno in ("Detalji", "Kopiraj ćeliju", "Kopiraj ceo red", "Premesti u grupu", "Proveri izabrane"):
    ok(not any(x.startswith(izbaceno) for x in lst), "nema „%s“" % izbaceno)
izaberi("Proveri ovu parcelu")
ok(POZIVI[-1] == ("proveri", True, (P["10383"],)), "Proveri ovu parcelu: proverava samo nju %s" % (POZIVI[-1:],))
meni(s1)
root.clipboard_clear()
izaberi("Kopiraj broj parcele")
ok(root.clipboard_get().split()[-1] == "10383" and "\n" not in root.clipboard_get(),
   "Kopiraj broj parcele: %r" % root.clipboard_get())
meni(s1)
izaberi("Izmeni (klijent, grupa, napomena)...")
ok(POZIVI[-1] == ("izmeni", (P["10383"],)), "Izmeni: ta parcela")
meni(s1)
izaberi("Označi kao pregledano")
ok(not b.parcele([P["10383"]])[0]["promene"], "Označi kao pregledano: promena skinuta")
lst = meni(s1)
ok("Označi kao pregledano" not in lst, "posle toga te stavke nema u meniju")
izaberi("Arhiviraj")
ok(b.parcele([P["10383"]])[0]["arhivirano"] and not app.tree.exists(s1), "Arhiviraj: arhivirana (otišla u Arhivu)")
b.vrati_u_proveru([P["10383"]])
app.osvezi_listu()
app.odlozi([P["10383"]], meseci=1)
app.tree.selection_set(s1)
lst = meni(s1)
ok("Vrati u redovnu proveru" in lst and "Arhiviraj" in lst, "odložena: ima i „Vrati u redovnu proveru“ %s" % lst)
izaberi("Vrati u redovnu proveru")
ok(not b.parcele([P["10383"]])[0]["odlozeno_do"], "Vrati u redovnu proveru: vraćena")
app.tree.selection_set(s1)
meni(s1)
izaberi("Ukloni iz praćenja")
ok(POZIVI[-1] == ("ukloni", (P["10383"],)), "Ukloni iz praćenja: ta parcela")

# parcela bez promena i bez izabranih stavki
app.tree.selection_set(s2)
lst = meni(s2)
ok(lst == ["Proveri ovu parcelu", "Sačuvaj kao PDF", "Kopiraj broj parcele", "Izmeni (klijent, grupa, napomena)...", "---",
           "Odloži proveru ▸", "Arhiviraj", "---", "Ukloni iz praćenja"], "obična parcela: %d stavki %s" % (stavki(lst), lst))
# desni klik na neizabranu parcelu bira nju
app.tree.selection_set(s2)
meni(s3)
ok(app.tree.selection() == (s3,), "desni klik bira red pod mišem")

# vise izabranih
with b._con() as c:
    c.execute("UPDATE parcele SET promene=? WHERE id=?", ("Promenjen vlasnik", P["10384"]))
app.osvezi_listu()
app.tree.selection_set((s1, s2))
lst = meni(s2)
print("     meni za 2 parcele:", lst)
ok(lst == ["Proveri izabrane (2)", "Sačuvaj kao PDF (2)", "Kopiraj brojeve parcela (2)", "Premesti u grupu (2)...",
           "Označi kao pregledano (2)", "---", "Odloži proveru (2) ▸", "Arhiviraj (2)", "---", "Ukloni iz praćenja (2)"],
   "meni za više parcela")
izaberi("Proveri izabrane (2)")
ok(POZIVI[-1][:2] == ("proveri", True) and set(POZIVI[-1][2]) == {P["10383"], P["10384"]}, "Proveri izabrane (2)")
app.tree.selection_set((s1, s2))
meni(s2)
root.clipboard_clear()
izaberi("Kopiraj brojeve parcela (2)")
ok([r.split()[-1] for r in root.clipboard_get().splitlines()] == ["10383", "10384"], "kopirana oba broja: %r" % root.clipboard_get())
app.tree.selection_set((s1, s2))
meni(s2)
izaberi("Premesti u grupu (2)...")
ok(POZIVI[-1][0] == "premesti" and set(POZIVI[-1][1]) == {P["10383"], P["10384"]}, "Premesti u grupu (2)")

# grupa
app.tree.selection_set("g:Zgrada")
lst = meni("g:Zgrada")
print("     meni grupe:", lst)
ok(lst == ["Proveri ovu grupu", "Sačuvaj sve kao PDF (2 parcele)", "Označi grupu kao pregledanu", "---", "Odloži proveru grupe ▸",
           "Arhiviraj grupu (%s)" % ak.br_parcela(2), "---", "Preimenuj grupu...", "Obriši grupu (parcele ostaju)"],
   "meni grupe: %d stavki" % stavki(lst))
ok(not any(x.startswith("Kopiraj") or x == "Nova grupa..." for x in lst), "nema kopiranja ni „Nova grupa...“")
izaberi("Proveri ovu grupu")
ok(POZIVI[-1][:2] == ("proveri", True) and set(POZIVI[-1][2]) == {P["10383"], P["10384"]}, "Proveri ovu grupu")
app.tree.selection_set("g:Zgrada")
meni("g:Zgrada")
izaberi("Sačuvaj sve kao PDF (2 parcele)")
ok(POZIVI[-1][0] == "pdf" and set(POZIVI[-1][1]) == {P["10383"], P["10384"]} and POZIVI[-1][2] == "Zgrada",
   "v30: „Sačuvaj sve kao PDF“ za grupu: obe parcele, naziv grupe za folder")
app.tree.selection_set(s1)
meni(s1)
izaberi("Sačuvaj kao PDF")
ok(POZIVI[-1] == ("pdf", (P["10383"],), None), "v30: „Sačuvaj kao PDF“ za jednu parcelu")
ok(app.btn_pdf_pracenja.winfo_ismapped() and app.btn_pdf_pracenja.cget("text") == "Sačuvaj kao PDF",
   "v30: dugme „Sačuvaj kao PDF“ vidljivo u listi praćenja")
app.tree.selection_set("g:Zgrada")
meni("g:Zgrada")
izaberi("Označi grupu kao pregledanu")
ok(not any(p["promene"] for p in b.parcele([P["10383"], P["10384"]])), "grupa označena kao pregledana")
app.tree.selection_set("g:Zgrada")
lst = meni("g:Zgrada")
ok("Označi grupu kao pregledanu" not in lst, "posle toga te stavke nema")
izaberi("Preimenuj grupu...")
ok(POZIVI[-1] == ("preimenuj",), "Preimenuj grupu")
bez = "g:" + ak.BEZ_GRUPE
if app.tree.exists(bez):
    app.tree.selection_set(bez)
    lst = meni(bez)
    ok(lst == ["Proveri ovu grupu", "Sačuvaj sve kao PDF (1 parcela)", "---", "Odloži proveru grupe ▸", "Arhiviraj grupu (%s)" % ak.br_parcela(1)],
       "„bez grupe“: bez preimenovanja i brisanja %s" % lst)
else:
    print("     (nema reda „bez grupe“ - preskočeno)")

# prazno mesto
lst = meni(None, prazno=True)
ok(lst == ["Dodaj parcele u praćenje...", "Nova grupa..."], "prazno mesto: %s" % lst)

# izbaceno je i dalje dostupno
DET = []
app.detalji = lambda: DET.append(tuple(app.izabrani_ids()))    # v28: dvoklik = sačuvano stanje
app.tree.selection_set(s2)
app.tree.see(s2)
root.update()
x, y, w, h = app.tree.bbox(s2, "#0") or app.tree.bbox(s2)
ok("_dvoklik" in app.tree.bind("<Double-1>"), "dvoklik je vezan za listu")
app._dvoklik(Dog(app.tree, x + w // 2, y + h // 2))
root.update()
ok(DET and DET[-1] == (P["10384"],), "dvoklik na parcelu: Detalji")
ok(app.tree.bind("<Return>") and app.tree.bind("<Control-c>"), "Enter (Detalji) i Ctrl+C (ceo red) postoje")
mb = root.nametowidget(root["menu"])
meniji = {}
for i in range(mb.index("end") + 1):
    if mb.type(i) == "cascade":
        pod = root.nametowidget(mb.entrycget(i, "menu"))
        meniji[mb.entrycget(i, "label")] = [pod.entrycget(j, "label") for j in range(pod.index("end") + 1)
                                            if pod.type(j) in ("command", "cascade", "checkbutton")]
parc = " | ".join(meniji.get("Parcela", []))
grp = " | ".join(meniji.get("Grupa", []))
ok("Detalji" in parc and "Kopiraj" in parc and "Izmeni" in parc and "Sačuvaj kao PDF (izabrane parcele ili grupa)" in parc,
   "meni Parcela: Detalji, kopiranje, Izmeni, PDF")
ok("Nova grupa" in grp and "Premesti" in grp, "meni Grupa: Nova grupa, Premesti izabrane u grupu")
root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
