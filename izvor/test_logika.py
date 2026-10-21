# -*- coding: utf-8 -*-
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading

RAD = tempfile.mkdtemp(prefix="kat_test_")
os.environ["KATASTAR_TEST"] = "1"
import mock_sajt

srv = mock_sajt.pokreni()
os.environ["KATASTAR_BASE"] = "http://127.0.0.1:%d/eKatastarPublic/" % srv.server_address[1]
shutil.copy("asistent_katastar.py", RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
assert ak.DIR == RAD

GRESKE = []


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis)
    if not uslov:
        GRESKE.append(opis)


# 1. brojevi
b, lose = ak.raspakuj_brojeve("10383, 10384/1\n100-102 ; abc 12/1234")
ok(b == ["10383", "10384/1", "100", "101", "102"] and lose == ["abc", "12/1234"], "raspakivanje brojeva %r %r" % (b, lose))

# 2. citac: seme se cita samo sebe, ponovljeni znaci se prepoznaju iz drugih uzoraka
c = ak.CitacCaptche(os.path.join(RAD, "uzorci_captcha.json"))
for k, lab in mock_sajt.CAPTCHE.items():
    t, siguran = c.procitaj(mock_sajt.SVG[k])
    ok(t == lab and siguran, "citac na poznatoj slici %s -> %s (%s)" % (lab, t, siguran))
# leave-one-out: citac bez slike ndZaS mora da prepozna a, Z, S iz drugih slika, a n/d ne sme da pogodi pogresno
seme_bez = [x for x in ak.SEME_CAPTCHE]
stari = ak.SEME_CAPTCHE
idx = list(mock_sajt.CAPTCHE).index("31e71c1e")
ak.SEME_CAPTCHE = stari[:idx * 5] + stari[idx * 5 + 5:]
c2 = ak.CitacCaptche(os.path.join(RAD, "nema.json"))
t, siguran = c2.procitaj(mock_sajt.SVG["31e71c1e"])
ok(t == "??ZaS" and not siguran, "bez uzorka ndZaS: procitano %s, siguran=%s (ocekivano ??ZaS, nesiguran)" % (t, siguran))
n = c2.nauci(mock_sajt.SVG["31e71c1e"], "ndZaS")
t, siguran = c2.procitaj(mock_sajt.SVG["31e71c1e"])
ok(n == 2 and t == "ndZaS" and siguran, "posle ucenja: novih %d, procitano %s" % (n, t))
c3 = ak.CitacCaptche(os.path.join(RAD, "nema.json"))
ok(c3.procitaj(mock_sajt.SVG["31e71c1e"])[0] == "ndZaS", "nauceno se cuva u fajlu i ucitava ponovo")
ak.SEME_CAPTCHE = stari

# 3. rupe za crtanje: 0 sa crtom ima 2 rupe, a ima 1
p = ak.parsiraj_svg(mock_sajt.SVG["b200c5be"])
ok([len(ak.rupe(g["poligoni"])) for g in p["znaci"]] == [0, 2, 1, 2, 0], "rupe u znacima v0a8h")

# 4. sajt: opstine i KO
s = ak.Sajt()
op = s.opstine()
ok(len(op) == 168 and [70106, "ВОЖДОВАЦ"] in op, "opstine sa sajta: %d" % len(op))
ko = s.ko(70106)
ok([703621, "ВОЖДОВАЦ"] in ko and len(ko) == 8, "KO Vozdovac: %d" % len(ko))
zad = [z for z in mock_sajt.STANJE["zahtevi"] if z[0] == "POST"][-1]
ok(zad[2].get("ctl00$ContentPlaceHolder1$getOpstinaKO$dropOpstina") == "70106", "POST za KO salje izabranu opstinu")


# 5. pretraga vise parcela: rucni unos (sa jednom greskom), automatsko citanje, nepostojeca parcela
def nadji_kod(svg):
    for k, v in mock_sajt.SVG.items():
        if v == svg:
            return mock_sajt.CAPTCHE[k]


def pokreni(zadaci, citac, odgovori, detaljno=True, nep=False):
    rez, kraj = [], threading.Event()
    log = []

    def trazi(svg, opis):
        o = odgovori(svg)
        log.append(("captcha", opis, o))
        return o
    pos = ak.Pretraga(citac, detaljno, nep, trazi, lambda m, t="": log.append((t, m)), lambda p: kraj.set())
    pos._citac_za_ucenje = citac
    pos.rezultat = lambda z, d, r: rez.append((z, d, r))
    pos.pokreni(zadaci)
    ok(kraj.wait(60), "posao zavrsen")
    return pos, rez, log


Z = lambda broj, ko_id=716065, ko="ЗЕМУН": {"opstina_id": 70157, "opstina": "ЗЕМУН", "ko_id": ko_id, "ko": ko, "broj": broj}
greska_jednom = {"n": 0}


def odgovor_sa_greskom(svg):
    kod = nadji_kod(svg)
    if greska_jednom["n"] == 0:
        greska_jednom["n"] = 1
        return kod.swapcase()          # kao Dejanov prvi pokusaj (V umesto v)
    return kod


mock_sajt.STANJE["captcha_red"] = ["bc8b2524", "b200c5be", "617fc8be", "2879ffa5", "31e71c1e"]
pos, rez, log = pokreni([Z("10383"), Z("4415", 703621, "ВОЖДОВАЦ"), Z("999")], None, odgovor_sa_greskom)
ok([r[1] is not None for r in rez] == [True, True, False], "rezultati: pronadjeno, pronadjeno, nije")
ok("nije pronadjena" in (rez[2][2] or "") and "Парцела није пронађена" in rez[2][2], "razlog za nepostojecu: %s" % rez[2][2])
d0 = rez[0][1]
sn = ak.napravi_snimak(d0)
ok(len(sn["delovi"]) == 5 and sn["ukupno"] == "801", "10383: 5 delova, ukupno 801")
ok(len(sn["objekti"]) == 3 and sn["objekti"][0][0] == "1, 4, 5" and any("ГАРАЖА" in o[5] for o in sn["objekti"])
   and any("ДЕО 3" in o[5] for o in sn["objekti"]),
   "objekti sa svih delova (izbor dela radi): %s" % [o[5] for o in sn["objekti"]])
ok(len(sn["posebni"]) == 2 and any(x[5] == "ГАРАЖНИ ПРОСТОР" for x in sn["posebni"]), "posebni delovi bez ponavljanja: %s" % sn["posebni"])
# v17: kao na sajtu, deo parcele -> objekti na tom delu -> posebni delovi izabranog objekta
gi = next(i for i, o in enumerate(sn["objekti"]) if "ГАРАЖА" in o[5])
di = next(i for i, o in enumerate(sn["objekti"]) if "ДЕО 3" in o[5])
gp = next(j for j, x in enumerate(sn["posebni"]) if x[5] == "ГАРАЖНИ ПРОСТОР")
ok(ak.objekti_dela(sn, "1") == [0] and ak.objekti_dela(sn, "2") == [gi] and ak.objekti_dela(sn, "3") == [di]
   and ak.objekti_dela(sn, "5") == [0], "objekti po delu parcele: %s" % [o[0] for o in sn["objekti"]])
ok(len(sn["posebni_obj"]) == 2 and sn["posebni_obj"][gp] == gi and ak.posebni_objekta(sn, gi) == [gp]
   and ak.posebni_objekta(sn, 0) == [1 - gp] and ak.posebni_objekta(sn, di) == [],
   "posebni delovi po objektu, i kad objekti imaju istu adresu: %s" % sn["posebni_obj"])
ok(ak.poredi(dict(sn, posebni_obj=None), sn) == [], "veza poseban deo -> objekat ne pravi lažnu promenu u praćenju")
# snimak pre v17 (bez veze): uparuje se po ulici i kucnom broju (primer Dejana, Vračar 2446)
star = {"delovi": [["1", "189"], ["2", "17"], ["3", "149"]],
        "objekti": [["1", "ВЕЛЕ НИГРИНОВЕ", "10", "", "189", "СТАМБЕНА ЗГРАДА", "ОБЈЕКАТ ПРЕУЗЕТ"],
                    ["2", "ВЕЛЕ НИГРИНОВЕ", "", "", "17", "ПОРОДИЧНА СТАМБЕНА ЗГРАДА", "ОБЈЕКАТ ИЗГРАЂЕН БЕЗ ОДОБРЕЊА"]],
        "posebni": [["ВЕЛЕ НИГРИНОВЕ 10", str(i), "10", str(i), "", "СТАН", "40"] for i in range(1, 9)]}
ok(ak.objekti_dela(star, "1") == [0] and ak.objekti_dela(star, "2") == [1] and ak.objekti_dela(star, "3") == []
   and ak.posebni_objekta(star, 0) == list(range(8)) and ak.posebni_objekta(star, 1) == [],
   "stari snimak: stanovi samo uz zgradu Vele Nigrinove 10, druga zgrada i treći deo bez njih")
ok(pos.rucno == 3 and len([l for l in log if l[0] == "captcha"]) == 4, "rucni unosi: 3 prihvacena, 1 odbijen")
ok(any("velika i mala" in l[1] for l in log if l[0] == "info"), "poruka o pogresnom kodu")
izbori = [z for z in mock_sajt.STANJE["zahtevi"] if z[0] == "POST" and z[1] == "FindParcelaResult.aspx"]
ok(len(izbori) >= 4, "zahtevi za izbor delova: %d" % len(izbori))

# 6. citac uci tokom rada: sada zna sve znakove sa 5 slika -> automatski
mock_sajt.STANJE["captcha_red"] = ["31e71c1e", "2879ffa5"]
pos, rez, log = pokreni([Z("10383"), Z("4415")], c, lambda svg: None, detaljno=False)
ok(pos.auto_ok == 2 and pos.rucno == 0 and all(r[1] for r in rez), "automatsko citanje: %d auto, %d rucno" % (pos.auto_ok, pos.rucno))

# 7. nepoznata slika -> citac nije siguran -> nova slika -> rucno posle 3
c_prazan = ak.CitacCaptche(os.path.join(RAD, "prazan.json"))
c_prazan.uzorci = {}
mock_sajt.STANJE["captcha_red"] = ["b200c5be"] * 4 + ["bc8b2524"]
pos, rez, log = pokreni([Z("4415")], c_prazan, nadji_kod, detaljno=False)
ok(pos.rucno == 1 and rez[0][1] is not None, "nesiguran citac -> 3 nove slike pa rucni unos")
ok(c_prazan.procitaj(mock_sajt.SVG["b200c5be"]) == ("v0a8h", True), "naucio iz rucnog unosa")
# 7b. posle rucnog unosa koji sajt odbije, nova slika koju citac zna se salje sama (ne trazi se opet rucno)
mock_sajt.STANJE["captcha_red"] = ["bc8b2524"] * 4 + ["b200c5be"]
rucni = []
pos, rez, log = pokreni([Z("4415")], c_prazan, lambda svg: rucni.append(1) or "XXXXX", detaljno=False)
ok(rez[0][1] is not None and pos.auto_ok == 1 and len(rucni) == 1,
   "posle rucnog pokusaja citac sam salje sliku koju zna: auto %d, rucno trazeno %d" % (pos.auto_ok, len(rucni)))

# 8. preskoci i prekini
pos, rez, log = pokreni([Z("4415"), Z("10383")], None, lambda svg: None, detaljno=False)
ok(len(rez) == 2 and all(r[1] is None and "preskoceno" in r[2] for r in rez), "preskoci parcelu")
pos, rez, log = pokreni([Z("4415"), Z("10383")], None, lambda svg: False, detaljno=False)
ok(len(rez) == 0 and pos.stop, "prekini")

# 9. 429: jednom ceka pa nastavlja
mock_sajt.STANJE["429"] = 1
pos, rez, log = pokreni([Z("4415")], None, nadji_kod, detaljno=False)
ok(rez and rez[0][1] is not None and any("pauzu" in l[1] for l in log if l[0] == "info"), "429 -> pauza pa uspeh")
mock_sajt.STANJE["429"] = 5
pos, rez, log = pokreni([Z("4415"), Z("10383")], None, nadji_kod, detaljno=False)
ok(len(rez) == 1 and rez[0][1] is None and pos.stop, "uporno 429 -> prekid: %s" % (rez[0][2] if rez else rez))
mock_sajt.STANJE["429"] = 0

# 10. "Podaci o nepokretnosti": citanje pravih stranica (HAR 07.10.2026)
sek = ak.parsiraj_nepokretnost(open(os.path.join(mock_sajt.D, "nep_zemljiste.html"), encoding="utf-8").read())
red = ak.redovi_nepokretnosti(sek)
ok(any(r.startswith("[Имаоци права на парцели - Б лист] Назив: ПЕТРОВИЋ ПЕТАР;") and "Удео: 1/4" in r for r in red),
   "vlasnik parcele sa udelom: %s" % [r for r in red if "Имаоци" in r][:1])
ok(sum(1 for r in red if r.startswith("[Имаоци права на парцели")) == 3, "tri vlasnika parcele")
ok("[Терети на парцели - Г лист] Нема терета" in red, "nema tereta")
ok(sum(1 for r in red if r.startswith("[Напомене на парцели]")) == 4 and any("952-02-7-016-6493/2022" in r for r in red),
   "4 napomene (zabelezbe zahteva)")
ok(sum(1 for r in red if r.startswith("[Подаци о деловима парцеле]")) == 5, "5 delova parcele")
ok(not any("ажурности" in r or "Матични" in r or "521457ff" in r or "више информација" in r for r in red),
   "bez azurnosti, maticnih brojeva, GUID-a i linka")
ok(any("Лице уписано са матичним бројем: НЕ;" in r for r in red), "НЕ bez '(vise informacija)'")
v, t = ak.vlasnici_tereti({"nepokretnost": {"parcela": red}})
ok(v == "ПЕТРОВИЋ ПЕТАР 1/4; ЈОВАНОВИЋ (ЈОВАН) ЈЕЛЕНА 1/4; РЕПУБЛИКА СРБИЈА 2/4" and t == "Нема терета",
   "kratko: vlasnici %r, tereti %r" % (v, t))
red_z = ak.tekst_nepokretnosti(open(os.path.join(mock_sajt.D, "nep_zgrada.html"), encoding="utf-8").read())
ok(red_z[0].startswith("[2. Подаци о зградама") and not any("парцели" in r for r in red_z) and
   any(r.startswith("[Имаоци права на објекту]") for r in red_z), "zgrada: samo V1 list i njeni vlasnici")
red_p = ak.tekst_nepokretnosti(open(os.path.join(mock_sajt.D, "nep_poseban.html"), encoding="utf-8").read())
ok(red_p[0].startswith("[3. Подаци о посебном делу") and
   "[Имаоци права на посебном делу] Назив: НИКОЛИЋ МИЛИЦА; Лице уписано са матичним бројем: НЕ; Врста права: СВОЈИНА; "
   "Облик својине: ПРИВАТНА; Удео: 1/1" in red_p and "[Напомене на посебном делу објекта] Нема напомена" in red_p,
   "poseban deo: stan i vlasnik: %s" % red_p)
ok("Корисна пов. m²: 106" in red_p[0], "korisna povrsina stana")
ok(ak.tekst_nepokretnosti("<html><body><table><tr><td>Нешто</td><td>друго</td></tr></table></body></html>") == ["Нешто | друго"],
   "nepoznat oblik -> sav tekst")

# 11. pracenje: baza, prvi snimak, bez promene, promena vlasnika, tereta, napomene, povrsine
baza = ak.Baza(os.path.join(RAD, "katastar.db"))
ok(baza.dodaj(70157, "ЗЕМУН", 716065, "ЗЕМУН", "10383", "KLIJENT A", "GRUPA 1"), "dodata parcela")
ok(not baza.dodaj(70157, "ЗЕМУН", 716065, "ЗЕМУН", "10383"), "duplikat se ne dodaje")
p = baza.parcele()[0]


def provera(nep="sve"):
    p = baza.parcele()[0]
    pos, rez, log = pokreni([dict(Z("10383"), pid=p["id"], p=p)], c, lambda svg: nadji_kod(svg), detaljno=True, nep=nep)
    return baza.obradi(p, ak.napravi_snimak(rez[0][1])), rez[0][1]


mock_sajt.STANJE["nep_upiti"] = []
(prva, prom), d = provera()
ok(prva and not prom and set(d["nepokretnost"]) >= {"parcela"} and any(k.startswith("objekat") for k in d["nepokretnost"])
   and any(k.startswith("poseban deo") for k in d["nepokretnost"]), "prva provera: parcela, objekat, poseban deo: %s" % list(d["nepokretnost"]))
ok(len(mock_sajt.STANJE["nep_upiti"]) == len(set(mock_sajt.STANJE["nep_upiti"])) == 3,
   "svaki prozor ucitan jednom: %s" % mock_sajt.STANJE["nep_upiti"])
ok(any("ПЕТРОВИЋ ПЕТАР" in r for r in d["nepokretnost"]["parcela"]), "vlasnik u podacima o nepokretnosti")
(prva, prom), d = provera()
ok(not prva and not prom, "druga provera bez promena (vreme izvoda, azurnost, ViewState i ID se ne porede): %s" % prom)
mock_sajt.STANJE["vlasnik"] = "МАРКОВИЋ МАРКО"
mock_sajt.STANJE["stan_vlasnik"] = "ЈОВАНОВИЋ ЈОВАН"
mock_sajt.STANJE["teret"] = "ХИПОТЕКА у корист БАНКА"
mock_sajt.STANJE["napomena"] = "ЗАБЕЛЕЖБА ПРИЈЕМА ЗАХТЕВА БРОЈ 952-02-1/2026"
mock_sajt.STANJE["dodat_deo"] = True
(prva, prom), d = provera()
ok(any("МАРКОВИЋ" in x and "novo" in x for x in prom) and any("ПЕТРОВИЋ ПЕТАР" in x and "uklonjeno" in x for x in prom),
   "promena vlasnika uocena")
ok(any("ЈОВАНОВИЋ" in x and x.startswith("poseban deo") for x in prom), "promena vlasnika stana uocena")
ok(any("ХИПОТЕКА" in x and "novo" in x for x in prom) and any("Нема терета" in x and "uklonjeno" in x for x in prom),
   "novi teret uocen")
ok(any("952-02-1/2026" in x for x in prom), "nova napomena (zabelezba zahteva) uocena")
ok(any("125" in x for x in prom), "promena povrsine dela uocena")
p = baza.parcele()[0]
ok(p["promene"] and p["promena_vreme"] and len(baza.istorija(p["id"])) == 1, "promena upisana u bazu i istoriju")
baza.oznaci_pregledano([p["id"]])
ok(not baza.parcele()[0]["promene"], "oznaci pregledano")
ok(baza.pretrazi("markovic") == {p["id"]} and baza.pretrazi("ЦАРА ДУШАНА") == {p["id"]} and not baza.pretrazi("zzz"),
   "pretraga bez obzira na pismo")
pr = ak.prikaz_nepokretnosti(d["nepokretnost"])
ok("=== parcela ===" in pr and "\nИмаоци права на парцели - Б лист\n    Назив: МАРКОВИЋ МАРКО  |" in pr, "prikaz u Detaljima")

# 12. nepokretnost trazi captchu -> preskace se, provera uspe; snimak iz v1 se ne poredi
mock_sajt.STANJE["nep_captcha"] = True
(prva, prom), d = provera()
ok(not d["nepokretnost"] and any("captch" in n for n in d["napomene"]), "nepokretnost sa captchom se preskace")
ok(not prom, "bez lazne promene kad nepokretnost izostane: %s" % prom[:3])
mock_sajt.STANJE["nep_captcha"] = False
stari_v1 = {"delovi": [], "objekti": [], "posebni": [], "nepokretnost": {"parcela": ["Имаоци права | ПЕТРОВИЋ ПЕТАР"]}}
novi_v2 = dict(stari_v1, nepokretnost={"parcela": ["[Имаоци права на парцели - Б лист] Назив: X"]}, nep_v=2)
ok(ak.poredi(stari_v1, novi_v2) == [], "snimak iz prethodne verzije ne pravi lazne promene")
ok(ak.poredi(novi_v2, dict(novi_v2, nepokretnost={"parcela": ["[Имаоци права на парцели - Б лист] Назив: Y"]})) != [],
   "ista verzija se poredi")

# 13. pretraga sa vlasnicima (parcela, zgrade, posebni delovi) i CSV
mock_sajt.STANJE["nep_upiti"] = []
mock_sajt.STANJE["zahtevi"] = []
put = os.path.join(RAD, "izvoz.csv")
pos, rez, log = pokreni([Z("10383"), Z("999")], c, nadji_kod, nep="sve")
kljucevi = list(rez[0][1]["nepokretnost"])
ok(kljucevi[0] == "parcela" and any(k.startswith("objekat") for k in kljucevi)
   and any(k.startswith("poseban deo") for k in kljucevi), "pretraga: parcela, zgrade i posebni delovi: %s" % kljucevi)
vo = ak.vlasnici_objekata(ak.napravi_snimak(rez[0][1]))
ok(mock_sajt.STANJE["stan_vlasnik"] + " 1/1" in vo and "СТАН" in vo and "objekat" in vo, "vlasnici zgrada i stanova: %s" % vo[:300])
ok(ak.kratko_ime_nep("poseban deo ЦАРА ДУШАНА 200, ulaz 1, stan 5, evid. 7, СТАН") == "СТАН 5 (ЦАРА ДУШАНА 200)",
   "kratko ime posebnog dela")
dugmad = [next((k[:-2] for k in z[2] if k.endswith(".x")), "") for z in mock_sajt.STANJE["zahtevi"]
          if z[0] == "POST" and z[1] == "FindParcelaResult.aspx"]
i3 = next((i for i, d in enumerate(dugmad) if "GridView1$ctl04" in d), None)
ok(i3 is not None and any("GridView2" in d for d in dugmad[i3 + 1:]),
   "deo bez izabranog objekta: objekat se klikne da bi se videli posebni delovi: %s" % dugmad)
sn13 = ak.napravi_snimak(rez[0][1])
st = ak.stablo_nepokretnosti(sn13)
ok(st[0][0] == "parcela" and any("Имаоци права на парцели" in r for r in st[0][3]), "stablo: parcela sa vlasnicima")
zgrade = [x for x in st if x[0].startswith("o")]
stanovi = [x for x in st if re.match(r"p\d", x[0])]
ok(len(zgrade) == len(sn13["objekti"]) and zgrade[0][2].startswith("Zgrada 1:"), "stablo: zgrade %s" % [x[2] for x in zgrade])
ok(stanovi and stanovi[0][1] == "o0" and stanovi[0][2].startswith("Стан")
   and any(mock_sajt.STANJE["stan_vlasnik"] in r for r in stanovi[0][3]), "stablo: stan ispod zgrade 1 sa vlasnikom: %s" % (stanovi[:1],))
ok(not [x for x in st if x[0].startswith("x")], "stablo: svi podaci upareni sa stavkama")
g = ak.grupisi_redove(stanovi[0][3])
ok(any(sek.startswith("Имаоци права на посебном делу") and dict(z[0]).get("Удео") == "1/1" for sek, z in g),
   "grupisanje sekcija za prikaz")
n = ak.izvezi_csv(put, rez)
sadrzaj = open(put, encoding="utf-8-sig").read()
ok(n == 6 and "ГАРАЖА" in sadrzaj and "nije pronađeno" in sadrzaj and sadrzaj.startswith("Opština;KO"), "CSV izvoz %d redova" % n)
ok("МАРКОВИЋ МАРКО 1/4; ЈОВАНОВИЋ (ЈОВАН) ЈЕЛЕНА 1/4" in sadrzaj and "ХИПОТЕКА у корист БАНКА" in sadrzaj
   and "Vlasnici parcele (udeo);Tereti na parceli;Vlasnici zgrada i stanova;Status" in sadrzaj
   and mock_sajt.STANJE["stan_vlasnik"] in sadrzaj, "CSV ima vlasnike, terete i vlasnike stanova")

# 14. captcha 9pYch iz HAR-a 07.10.2026 i znakovi sa Dejanovog racunara su u pocetnom znanju
c9 = ak.CitacCaptche(os.path.join(RAD, "nema.json"))
ok(c9.procitaj(open(os.path.join(mock_sajt.D, "9pYch.svg"), encoding="utf-8").read()) == ("9pYch", True), "cita 9pYch")
ok(len(c9.poznati_znaci()) == 29 and {"2", "F", "M", "T", "U", "g", "s", "9", "c"} <= set(c9.poznati_znaci()),
   "pocetno znanje: %d znakova" % len(c9.poznati_znaci()))

# 15. rezervna kopija baze
ak.DB_PATH = os.path.join(RAD, "katastar.db")
ak.REZERVE_DIR = os.path.join(RAD, "rezerve")
ak.napravi_rezervu_baze()
rez_f = os.listdir(ak.REZERVE_DIR)
ok(len(rez_f) == 1 and ak.sqlite3.connect(os.path.join(ak.REZERVE_DIR, rez_f[0])).execute("select count(*) from parcele").fetchone()[0] == 1,
   "rezervna kopija baze napravljena")

# 16. v8: arhiva i odlaganje, grupe po klijentu, pomocne funkcije (kao Asistent PRO)
ok([ak.br_parcela(n) for n in (1, 2, 5, 11, 21, 22, 25)] ==
   ["1 parcela", "2 parcele", "5 parcela", "11 parcela", "21 parcela", "22 parcele", "25 parcela"], "br_parcela")
ok(ak.citaj_datum("7.1.2027") == ak.dt.date(2027, 1, 7) and ak.citaj_datum("07.01.27.") == ak.dt.date(2027, 1, 7)
   and ak.citaj_datum("2027-01-07") == ak.dt.date(2027, 1, 7) and ak.citaj_datum("32.1.2027") is None, "citaj_datum")
ok(ak.dodaj_mesece(ak.dt.date(2026, 1, 31), 1) == ak.dt.date(2026, 2, 28) and
   ak.dodaj_mesece(ak.dt.date(2026, 10, 7), 12) == ak.dt.date(2027, 10, 7), "dodaj_mesece")
sutra = (ak.dt.date.today() + ak.dt.timedelta(days=1)).isoformat()
danas = ak.dt.date.today().isoformat()
ok(ak.odlozen({"odlozeno_do": sutra}) and not ak.odlozen({"odlozeno_do": danas}) and
   not ak.aktivan({"arhivirano": danas}) and ak.aktivan({}), "odlozen / arhiviran / aktivan")
# baza iz v7 (bez kolona arhivirano, odlozeno_do) se dopunjuje bez gubitka podataka
staro = os.path.join(RAD, "v7.db")
con = ak.sqlite3.connect(staro)
con.executescript("""
CREATE TABLE parcele (id INTEGER PRIMARY KEY AUTOINCREMENT, opstina_id INTEGER, opstina TEXT, ko_id INTEGER NOT NULL,
    ko TEXT, broj TEXT NOT NULL, klijent TEXT DEFAULT '', grupa TEXT DEFAULT '', napomena TEXT DEFAULT '', dodat TEXT,
    provereno TEXT, snimak TEXT, pokusaj TEXT, greska TEXT, promene TEXT, promena_vreme TEXT, UNIQUE(ko_id, broj));
CREATE TABLE istorija (id INTEGER PRIMARY KEY AUTOINCREMENT, parcela_id INTEGER, vreme TEXT, tekst TEXT);
CREATE TABLE grupe (naziv TEXT PRIMARY KEY);
CREATE TABLE podesavanja (kljuc TEXT PRIMARY KEY, vrednost TEXT);
INSERT INTO parcele (opstina_id, opstina, ko_id, ko, broj, klijent, grupa, napomena, snimak)
    VALUES (70106, 'ВОЖДОВАЦ', 703621, 'ВОЖДОВАЦ', '4415', 'Petar Petrović', '', 'stara', '{"delovi": []}');
INSERT INTO parcele (opstina_id, opstina, ko_id, ko, broj, klijent, grupa) VALUES (70106, 'ВОЖДОВАЦ', 703621, 'ВОЖДОВАЦ', '4416', 'PETAR PETROVIC', '');
INSERT INTO parcele (opstina_id, opstina, ko_id, ko, broj, klijent, grupa) VALUES (70106, 'ВОЖДОВАЦ', 703621, 'ВОЖДОВАЦ', '4417', 'Ana', 'GRUPA X');
INSERT INTO parcele (opstina_id, opstina, ko_id, ko, broj, klijent, grupa) VALUES (70106, 'ВОЖДОВАЦ', 703621, 'ВОЖДОВАЦ', '4418', 'ана', '');
INSERT INTO parcele (opstina_id, opstina, ko_id, ko, broj, klijent, grupa) VALUES (70106, 'ВОЖДОВАЦ', 703621, 'ВОЖДОВАЦ', '4419', 'Jedini', '');
INSERT INTO grupe VALUES ('GRUPA X');
""")
con.commit()
con.close()
bz = ak.Baza(staro)
pp = bz.parcele()
ok(len(pp) == 5 and pp[0]["napomena"] in ("stara", "") and all("arhivirano" in p and "odlozeno_do" in p for p in pp)
   and [p for p in pp if p["broj"] == "4415"][0]["napomena"] == "stara", "baza iz v7 dopunjena, podaci ostali")
p1 = [p for p in pp if p["broj"] == "4415"][0]["id"]
bz.odlozi([p1], ak.dt.date.today() + ak.dt.timedelta(days=30))
ok(ak.odlozen(bz.parcele([p1])[0]) and not ak.aktivan(bz.parcele([p1])[0]), "odlozi")
bz.arhiviraj([p1])
x = bz.parcele([p1])[0]
ok(ak.arhiviran(x) and not x["odlozeno_do"], "arhiviraj brise odlaganje")
bz.vrati_u_proveru([p1])
ok(ak.aktivan(bz.parcele([p1])[0]), "vrati u redovnu proveru")
with bz._con() as c:
    c.execute("UPDATE parcele SET odlozeno_do=? WHERE id=?", (danas, p1))
ok(not ak.Baza(staro).parcele([p1])[0]["odlozeno_do"], "isteklo odlaganje se brise pri otvaranju")
# grupe po klijentu: Petar (2 bez grupe, razlicito pisanje) -> nova grupa; ana -> u postojecu GRUPA X; Jedini se ne dira
rez = bz.grupisi_po_klijentu()
gr = {p["broj"]: p["grupa"] for p in bz.parcele()}
ok(gr["4415"] == gr["4416"] == "Petar Petrović" and gr["4418"] == "GRUPA X" and gr["4419"] == "" and
   ("Petar Petrović", 2, True) in rez and ("GRUPA X", 1, False) in rez, "grupisanje po klijentu: %s %s" % (rez, gr))
ok(bz.dodaj_grupu("grupa x") == "GRUPA X" and bz.grupe().count("GRUPA X") == 1, "grupa bez obzira na velika/mala slova")
bz.dodaj(70106, "ВОЖДОВАЦ", 703621, "ВОЖДОВАЦ", "4420", "Jedini", "", "")
ok(bz.grupisi_po_klijentu("JEDINI") == [("Jedini", 2, True)], "drugi predmet istog klijenta pravi grupu")
# precica: napravi_precicu.ps1 se upisuje pored programa (na Windowsu ga pokrece PowerShell)
odg = []
ak.napravi_precicu(lambda ok_, poruka: odg.append((ok_, poruka)))
ps1 = os.path.join(RAD, "napravi_precicu.ps1")
tx = open(ps1, encoding="ascii").read()
ok(os.path.exists(ps1) and "asistent_katastar.ico" in tx and "AK_PYTHONW" in tx and "advokatcolja.asistentkatastar" in tx
   and odg and odg[0][0] is False, "napravi_precicu.ps1 upisan: %s" % (odg,))

print("\nUKUPNO GRESAKA:", len(GRESKE))
for g in GRESKE:
    print("  -", g)
sys.exit(1 if GRESKE else 0)
