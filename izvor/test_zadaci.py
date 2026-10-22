# -*- coding: utf-8 -*-
"""v32 (Dejan: "kada ti ubacim ugovor i kazem izvuci sve parcele"): Claude ostavi zadatak (JSON) u folderu zadaci,
program ga sam preuzme: parcele u praćenje u grupu klijenta (stan iz ugovora = prati se samo on), skine listove sa
sajta, sačuva PDF bez pitanja, ostavi izveštaj i pomeri zadatak u obradjeni."""
import glob
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

RAD = tempfile.mkdtemp(prefix="kat_zadaci_")
os.environ["KATASTAR_TEST"] = "1"
PREGLEDAC = os.environ.get("KATASTAR_PREGLEDAC") or "/opt/pw-browsers/chromium"   # v34: u CI-u drugi put
os.environ["KATASTAR_PREGLEDAC"] = PREGLEDAC
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
S = mock_sajt.STANJE
S["stanova"] = 60
S["nep_sesija"] = True


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
ak.filedialog.askdirectory = lambda **k: (PORUKE.append(("pitanje_folder",)), "")[1]
ak.ZADACI_TIK_MS = 300                  # u testu češće (u programu 5 s)
root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()
app.auto_var.set(False)
app._trazi_odgovor_iz_niti = lambda svg, opis: nadji_kod(svg)
Z = os.path.join(RAD, "zadaci")


def cekaj(uslov, sekundi=60):
    kraj = time.time() + sekundi
    while time.time() < kraj:
        root.after(40, root.quit)
        root.mainloop()
        if uslov():
            return True
    return False


def ostavi(ime, sadrzaj):
    """Kao Claude: upiše .tmp pa preimenuje u .json (program nikad ne vidi pola fajla)."""
    put = os.path.join(Z, ime)
    with open(put + ".tmp", "w", encoding="utf-8") as f:
        f.write(sadrzaj if isinstance(sadrzaj, str) else json.dumps(sadrzaj, ensure_ascii=False))
    os.replace(put + ".tmp", put)


def izvestaj(ime):
    put = os.path.join(Z, "izvestaji", ime + ".json")
    return json.load(open(put, encoding="utf-8")) if os.path.exists(put) else None


ok(os.path.isdir(Z), "folder zadaci napravljen pri pokretanju")

# --- opterećenje: prazan folder ---
t0, n = time.perf_counter(), 2000
for _ in range(n):
    app._proveri_zadatke()
po_proveri = (time.perf_counter() - t0) / n * 1000
print("MERENJE: jedna provera praznog foldera %.4f ms (na svakih %d s)" % (po_proveri, 5))
ok(po_proveri < 1.0, "provera foldera traje manje od 1 ms (%.4f ms)" % po_proveri)

# --- neispravan zadatak ---
ostavi("los.json", "{ovo nije json")
ok(cekaj(lambda: izvestaj("los") is not None, 20), "neispravan zadatak: izveštaj")
ok("neispravan zadatak" in (izvestaj("los") or {}).get("greska", "") and
   os.path.exists(os.path.join(Z, "obradjeni", "los.json")) and not os.path.exists(os.path.join(Z, "los.json")),
   "neispravan zadatak pomeren u obradjeni, uz razlog")
ostavi("bez_broja.json", {"klijent": "X", "parcele": [{"ko": "КУМОДРАЖ", "broj": "12a"}]})
ok(cekaj(lambda: izvestaj("bez_broja") is not None, 20) and "neispravan broj" in izvestaj("bez_broja")["greska"],
   "neispravan broj parcele: zadatak se ne izvršava")
ok(not app.baza.parcele(), "ništa nije dodato u praćenje")

# --- ugovor: dva stana u istoj zgradi, cela parcela, nepoznata KO, opština čije KO se učitavaju sa sajta ---
druga_opstina = next(o for o in ak.OPSTINE_UGRADJENE if str(o[0]) not in ak.KO_UGRADJENE)
ok(app.sif.ko_za(druga_opstina[0]) is None, "KO opštine %s još nisu poznate" % druga_opstina[1])
izlaz = os.path.join(RAD, "Klijent folder")
ugovor = {"naziv": "Ugovor Klijent Ugovor", "klijent": "Klijent Ugovor", "folder": izlaz, "parcele": [
    {"opstina": "Voždovac", "ko": "Kumodraž", "broj": "10383", "stan": "56"},
    {"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "10383", "stan": "57"},
    {"ko": "КУМОДРАЖ", "broj": "4415"},
    {"opstina": "ВОЖДОВАЦ", "ko": "НЕПОСТОЈЕЋА", "broj": "1"},
    {"opstina": "ВОЖДОВАЦ", "ko": "ЗУЦЕ", "broj": "777"}]}
ostavi("ugovor.json", ugovor)
ok(cekaj(lambda: app._zadatak is not None or izvestaj("ugovor"), 20), "zadatak preuzet")
ok(not os.path.exists(os.path.join(Z, "ugovor.json")) and
   os.path.exists(os.path.join(Z, "u radu", "ugovor.json")), "dok traje: zadatak u folderu „u radu“")
# drugi zadatak čeka dok prvi ne završi
ostavi("ponovo.json", dict(ugovor, naziv="Ponovo", pdf=False))
ok(cekaj(lambda: izvestaj("ugovor") is not None, 400), "zadatak završen")
r = izvestaj("ugovor") or {"rezultat": [], "pdf_rez": None}
for x in r["rezultat"]:
    print("   ", x)
ok(r.get("greska") is None, "bez greške zadatka: %s" % r.get("greska"))
par = {p["broj"]: p for p in app.baza.parcele()}
ok(set(par) == {"10383", "4415", "777"} and all(p["grupa"] == "Klijent Ugovor" and p["klijent"] == "Klijent Ugovor"
                                                 for p in par.values()), "parcele u grupi klijenta: %s" % sorted(par))
st = ak.pracene_stavke(par.get("10383"))
ok(sorted(ak.opis_stavke(k) for k in st) == ["stan 56", "stan 57"] and all(k.startswith("poseban deo ") for k in st),
   "10383: prate se samo stan 56 i stan 57 (pravi ključevi sa sajta): %s" % st)
ok(ak.pracene_stavke(par.get("4415")) == [], "4415: prati se cela parcela")
rez = r["rezultat"]
ok([x["stanje"].split(",")[0] for x in rez] == ["dodata u praćenje", "ista parcela kao gore", "dodata u praćenje",
                                                "nije dodata - KO НЕПОСТОЈЕЋА nije pronađena u opštini ВОЖДОВАЦ",
                                                "dodata u praćenje"], "stanje po parceli")
ok([x.get("provera") for x in rez][:3] == ["skinuto sa sajta"] * 3 and "nije pronadjena" in (rez[4].get("provera") or ""),
   "provera: 10383 i 4415 skinute, 777 nije na sajtu (%s)" % rez[4].get("provera"))
pdf = r.get("pdf_rez") or {}
folderi = glob.glob(os.path.join(izlaz, "*"))
ok(len(folderi) == 1 and folderi[0] == pdf.get("folder") and os.path.basename(folderi[0]).endswith(
    "Klijent Ugovor (2 parcele)"), "PDF u folderu iz zadatka, podfolder klijenta: %s" % [os.path.basename(f) for f in folderi])
pdfovi = sorted(os.listdir(folderi[0])) if folderi else []
print("    PDF:", pdfovi)
ok(pdf.get("sacuvano") == len(pdfovi) and pdfovi and not pdf.get("nije"), "PDF sačuvano: %d" % len(pdfovi))
ok(sum(x.startswith("КУМОДРАЖ 10383") for x in pdfovi) == 2 and any("stan 56" in x for x in pdfovi) and
   any("stan 57" in x for x in pdfovi), "10383: samo listovi stana 56 i 57")
ok(sum(x.startswith("КУМОДРАЖ 4415") for x in pdfovi) >= 2, "4415: svi listovi parcele (%d)" %
   sum(x.startswith("КУМОДРАЖ 4415") for x in pdfovi))
ok(not any(x[0] in ("pitanje_folder", "showinfo", "showwarning", "askyesno") for x in PORUKE),
   "nijedan prozor ni pitanje tokom zadatka (%s)" % PORUKE[:3])
txt = open(os.path.join(Z, "izvestaji", "ugovor.txt"), encoding="utf-8").read()
print(txt)
ok(txt.startswith("Zadatak: Ugovor Klijent Ugovor") and "PDF: sačuvano %d" % len(pdfovi) in txt, "izveštaj za čitanje")
ok(os.path.exists(os.path.join(Z, "obradjeni", "ugovor.json")) and not os.listdir(os.path.join(Z, "u radu")) or
   os.listdir(os.path.join(Z, "u radu")) == ["ponovo.json"], "zadatak pomeren u obradjeni")
log = app.txt.get("1.0", "end")
ok("--- Zadatak: Ugovor Klijent Ugovor (5 parcela) ---" in log and "--- Zadatak Ugovor Klijent Ugovor: skinuto 3 od 5" in log,
   "poruke: početak i kraj zadatka")

# --- isti ugovor ponovo (bez PDF): ništa se ne duplira ---
ok(cekaj(lambda: izvestaj("ponovo") is not None, 400), "drugi zadatak preuzet tek posle prvog i završen")
r2 = izvestaj("ponovo") or {"rezultat": []}
ok(len(app.baza.parcele()) == 3 and r2["rezultat"][0]["stanje"].startswith("već je bila u praćenju") and
   r2.get("pdf_rez") is None, "ponovljen ugovor: već u praćenju, bez PDF: %s" % [x["stanje"] for x in r2["rezultat"]])
ok(sorted(ak.opis_stavke(k) for k in ak.pracene_stavke(app.baza.parcele([par["10383"]["id"]])[0])) ==
   ["stan 56", "stan 57"], "postojećoj parceli se praćenje ne menja")

# --- opština čije KO program još ne zna: spisak KO sa sajta (bez captche); ista KO u dve opštine ---
ostavi("ada.json", {"klijent": "Klijent Ada", "pdf": False, "parcele": [
    {"opstina_id": druga_opstina[0], "ko": "ЗУЦЕ", "broj": "10383"}, {"ko": "ЗУЦЕ", "broj": "4415"}]})
ok(cekaj(lambda: izvestaj("ada") is not None, 300), "zadatak sa novom opštinom završen")
ra = (izvestaj("ada") or {"rezultat": [{}, {}]})["rezultat"]
ok(app.sif.ko_za(druga_opstina[0]) and ra[0].get("provera") == "skinuto sa sajta",
   "KO opštine %s učitane sa sajta i zapamćene, parcela skinuta" % druga_opstina[1])
ok(ra[1].get("stanje") == "nije dodata - KO ЗУЦЕ postoji u više opština - treba navesti opštinu",
   "KO bez opštine koja postoji u dve opštine: ne pogađa, javlja: %s" % ra[1].get("stanje"))

# --- zadatak dok traje ručna provera: čeka ---
app.tree.selection_set(str(par["4415"]["id"]))
app.proveri(True)
ostavi("dok_radi.json", {"klijent": "Treći", "pdf": False, "parcele": [{"ko": "КУМОДРАЖ", "broj": "4415"}]})
root.after(40, root.quit)
root.mainloop()
cekaj(lambda: False, 1.0)
ok(os.path.exists(os.path.join(Z, "dok_radi.json")) or app.posao is None, "dok traje ručna provera zadatak čeka")
ok(cekaj(lambda: izvestaj("dok_radi") is not None, 300), "posle ručne provere zadatak urađen")

# --- program zatvoren usred zadatka: pri pokretanju zadatak se vraća u red ---
os.makedirs(os.path.join(Z, "u radu"), exist_ok=True)
with open(os.path.join(Z, "u radu", "prekinut.json"), "w", encoding="utf-8") as f:
    json.dump({"klijent": "Četvrti", "pdf": False, "parcele": [{"ko": "КУМОДРАЖ", "broj": "4415"}]}, f)
app._pokreni_zadatke()
ok(os.path.exists(os.path.join(Z, "prekinut.json")) or app._zadatak is not None, "prekinut zadatak vraćen u red")
ok(cekaj(lambda: izvestaj("prekinut") is not None, 300), "prekinut zadatak završen posle ponovnog pokretanja")

# --- v35: parcele koje su već u praćenju (Dejan: "neke su već u aplikaciji, neću duplikate") ---
ok(all(x.get("preskocena") and not x.get("provera") for x in r2["rezultat"] if "već je bila" in x["stanje"]) and
   not any(x.get("provera") for x in r2["rezultat"]),
   "ponovljen ugovor: postojeće parcele se podrazumevano ne proveravaju ponovo")
ok("(nije ponovo proverena)" in open(os.path.join(Z, "izvestaji", "ponovo.txt"), encoding="utf-8").read(),
   "izveštaj: piše da nije ponovo proverena")
ok("već u praćenju 3" in app.txt.get("1.0", "end"), "poruka: koliko je već bilo u praćenju")
broj_pre = len(app.baza.parcele())
ostavi("proveri.json", {"klijent": "Peti", "grupa": "Druga", "pdf": False, "postojece": "proveri",
                        "parcele": [{"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "4415"}]})
ok(cekaj(lambda: izvestaj("proveri") is not None, 300), "postojece=proveri: završen")
rp = (izvestaj("proveri") or {"rezultat": [{}]})["rezultat"][0]
ok(rp.get("provera") == "skinuto sa sajta" and not rp.get("preskocena") and
   app.baza.parcela_po_mestu(par["4415"]["ko_id"], "4415")["grupa"] == "Klijent Ugovor",
   "postojece=proveri: provereno, grupa ista (%s)" % rp)
ostavi("premesti.json", {"klijent": "Peti", "grupa": "euroroad", "pdf": False, "postojece": "premesti",
                         "parcele": [{"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "4415"}, {"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "10383"}]})
ok(cekaj(lambda: izvestaj("premesti") is not None, 300), "postojece=premesti: završen")
rm = (izvestaj("premesti") or {"rezultat": [{}, {}]})["rezultat"]
ok(all("premeštena u grupu euroroad" in x.get("stanje", "") and x.get("preskocena") for x in rm) and
   {p["grupa"] for p in app.baza.parcele()} >= {"euroroad"} and
   app.baza.parcela_po_mestu(par["4415"]["ko_id"], "4415")["grupa"] == "euroroad",
   "postojece=premesti: premeštene u grupu zadatka, bez provere: %s" % [x.get("stanje") for x in rm])
ok(len(app.baza.parcele()) == broj_pre and (izvestaj("premesti") or {}).get("greska") is None,
   "nijedan duplikat, bez greške kad su sve već u praćenju")
ostavi("lose_postojece.json", {"klijent": "X", "postojece": "dupliraj", "parcele": [{"ko": "КУМОДРАЖ", "broj": "1"}]})
ok(cekaj(lambda: izvestaj("lose_postojece") is not None, 30) and
   "postojece mora biti" in izvestaj("lose_postojece")["greska"], "neispravno postojece: zadatak odbijen")

# --- v35: zadatak preko Drive-a (folder ASISTENT KATASTAR/zadaci), izveštaj nazad na Drive ---
DRIVE = os.path.join(RAD, "G", "My Drive", ak.DRIVE_FOLDER)
os.makedirs(DRIVE)
os.environ["KATASTAR_DRIVE"] = DRIVE
ok(ak.nadji_drive_folder() == DRIVE, "Drive folder pronađen")
ok(app.drive_folder() is None, "u testu bez podešavanja Drive se ne koristi sam od sebe pre izbora")
app.baza.postavi_podesavanje("drive_folder", DRIVE)
DZ = os.path.join(DRIVE, "zadaci")
ok(app.drive_zadaci() == DZ and os.path.isdir(DZ), "folder zadaci na Drive-u napravljen")
with open(os.path.join(DZ, "sa_drive.json"), "w", encoding="utf-8") as f:
    json.dump({"klijent": "Drive Klijent", "grupa": "euroroad", "pdf": False,
               "parcele": [{"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "4415"}, {"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "20015"}]}, f)
ok(cekaj(lambda: os.path.exists(os.path.join(DZ, "izvestaji", "sa_drive.txt")), 300),
   "zadatak sa Drive-a urađen, izveštaj vraćen na Drive")
ok(not os.path.exists(os.path.join(DZ, "sa_drive.json")) and
   os.path.exists(os.path.join(Z, "obradjeni", "sa_drive.json")), "zadatak sklonjen sa Drive-a u obradjeni")
rd = json.load(open(os.path.join(DZ, "izvestaji", "sa_drive.json"), encoding="utf-8"))
ok(rd["rezultat"][0].get("preskocena") and rd["rezultat"][1]["stanje"].startswith("dodata u praćenje") and
   app.baza.parcela_po_mestu(par["4415"]["ko_id"], "20015")["grupa"] == "euroroad",
   "sa Drive-a: postojeća preskočena, nova dodata u grupu: %s" % [x["stanje"] for x in rd["rezultat"]])
app.baza.postavi_podesavanje("drive_folder", "-")
with open(os.path.join(DZ, "iskljuceno.json"), "w", encoding="utf-8") as f:
    json.dump({"klijent": "X", "parcele": [{"opstina": "ВОЖДОВАЦ", "ko": "КУМОДРАЖ", "broj": "4415"}]}, f)
cekaj(lambda: False, 3.0)
ok(os.path.exists(os.path.join(DZ, "iskljuceno.json")), "Drive isključen: zadatak se ne uzima")

subprocess = __import__("subprocess")
subprocess.run(["import", "-window", "root", "zadatak_v32%s.png" % ("" if UVECANJE == 1 else "_150")], check=False)
root.destroy()
srv.shutdown()
print("\nUKUPNO GRESAKA: %d" % len(GRESKE))
os._exit(1 if GRESKE else 0)
