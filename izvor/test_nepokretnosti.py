# -*- coding: utf-8 -*-
"""v20 (logika posla, bez prozora; prozor u v21 testira test_izbor.py): zgrada sa 193 stana (kao parcela 13662 KO Земун): ucitavaju se SVI "Podaci o nepokretnosti" (do v19 samo
prvih 40), napredak "N od M", Prekini i pauza sajta cuvaju ucitano, "Ucitaj sa sajta" u praznom prozoru stavke
(trazena stavka prva i odmah prikazana), izvodi i snimak se ne gube pri delimicnom ucitavanju."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time

RAD = tempfile.mkdtemp(prefix="kat_nep_")
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


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def nadji_kod(svg):
    for k, v in mock_sajt.SVG.items():
        if v == svg:
            return mock_sajt.CAPTCHE[k]


Z = {"opstina_id": 70106, "opstina": "ВОЖДОВАЦ", "ko_id": 703800, "ko": "КУМОДРАЖ", "broj": "10383"}
MESTO = (703800, "КУМОДРАЖ", "10383")
stan = lambda d, i: next(k for k in d["nepokretnost"] if (", stan %d, " % i) in k)


def posao(prednost=None, strana=None, odgovor=nadji_kod):
    stanja, log, rez, kraj = [], [], [], threading.Event()
    pos = ak.Pretraga(None, True, "sve", lambda svg, opis: odgovor(svg), lambda m, t="": log.append((t, m)),
                      lambda p: kraj.set(), stanje=stanja.append)
    pos.prednost = prednost
    if strana:
        pos.strana = lambda ime, html: strana(pos, ime, html)
    pos.rezultat = lambda z, d, r: rez.append((z, d, r))
    n0 = len(mock_sajt.STANJE["nep_upiti"])
    pos.pokreni([dict(Z)])
    ok(kraj.wait(240), "posao završen")
    return pos, rez, log, stanja, mock_sajt.STANJE["nep_upiti"][n0:]


# 1. sve stavke, ne samo 40 (pauza izmedju stranica ovde iskljucena da test bude brz; u prozoru je ukljucena)
PAUZA = ak.Pretraga.pauza
ak.Pretraga.pauza = lambda self, raspon: None
t0 = time.time()
pos, rez, log, stanja, upiti = posao()
d = rez[0][1]
nep = d["nepokretnost"]
print("     %d stranica za %.1f s" % (len(nep), time.time() - t0))
ok(len(d["posebni"]) >= STANOVA, "rezultat ima %d posebnih delova" % len(d["posebni"]))
ok(all(any("ВЛАСНИК СТАНА %d" % i in r for r in nep[stan(d, i)]) for i in range(1, STANOVA + 1)),
   "učitani podaci za svih %d stanova (vlasnik svakog stana)" % STANOVA)
ok(len(nep) > 40 and len(nep) == len(d["nep_html"]) == len(d["nep_redosled"]),
   "stranica: %d (do v19 najviše 40)" % len(nep))
ok(sorted(u for u in upiti if u.startswith("S")) == ["S%03d=" % i for i in range(1, STANOVA + 1)],
   "svaki stan tražen tačno jednom")
ok(not any("ucitani za" in n for n in d["napomene"]), "nema napomene o delimičnom učitavanju: %s" % d["napomene"])
ok(d["nep_potpuno"] is True, "označeno kao potpuno učitano")
M = len(nep)
ok("%s %s: podaci o nepokretnosti 1 od %d" % (Z["ko"], Z["broj"], M) in stanja and
   "%s %s: podaci o nepokretnosti %d od %d" % (Z["ko"], Z["broj"], M, M) in stanja,
   "napredak u statusu: 1 od %d ... %d od %d" % (M, M, M))
REDOSLED = list(nep)
ok(REDOSLED[0] == "parcela" and REDOSLED.index(stan(d, 1)) < REDOSLED.index(stan(d, 2)) < REDOSLED.index(stan(d, 193)),
   "redosled kao na sajtu (parcela, objekti, stanovi)")

# 2. trazena stavka prva, strana javljena odmah, redosled u rezultatu ostaje kao na sajtu
stigle = []
k150 = stan(d, 150)
pos, rez, log, stanja, upiti = posao(prednost=k150, strana=lambda p, ime, html: stigle.append((ime, html)))
d2 = rez[0][1]
ok(upiti[0] == "S150=", "tražena stavka (stan 150) se učitava prva: %s" % upiti[:3])
ok(stigle and stigle[0][0] == k150 and "ВЛАСНИК СТАНА 150" in stigle[0][1], "prva javljena stranica je stan 150")
ok(len(stigle) == M and [s[0] for s in stigle][1:] == [k for k in REDOSLED if k != k150], "javljena svaka stranica (%d)" % len(stigle))
ok(list(d2["nepokretnost"]) == REDOSLED and list(d2["nep_html"]) == REDOSLED, "u rezultatu redosled kao na sajtu")
ok(d2["nep_potpuno"], "i tada potpuno")


# 3. Prekini posle 30 stranica: ucitano ostaje
def prekid30(p, ime, html, n=[0]):
    n[0] += 1
    if n[0] == 30:
        p.stop = True


pos, rez, log, stanja, upiti = posao(strana=prekid30)
d3 = rez[0][1] if rez else None
ok(d3 is not None and len(d3["nepokretnost"]) == 30, "Prekini: ostaje 30 učitanih stranica (%s)"
   % (len(d3["nepokretnost"]) if d3 else None))
ok(d3 is not None and "podaci o nepokretnosti ucitani za 30 od %d (prekinuto)" % M in d3["napomene"],
   "napomena o prekidu: %s" % (d3 or {}).get("napomene"))
ok(d3 is not None and d3["nep_potpuno"] is False and pos.stop, "označeno kao delimično")


# 4. sajt trazi pauzu (429 dva puta zaredom): staje se, ucitano ostaje
def pauza20(p, ime, html, n=[0]):
    n[0] += 1
    if n[0] == 20:
        mock_sajt.STANJE["429"] = 2


pos, rez, log, stanja, upiti = posao(strana=pauza20)
d4 = rez[0][1] if rez else None
ok(d4 is not None and len(d4["nepokretnost"]) == 20, "pauza sajta: ostaje 20 stranica (%s)"
   % (len(d4["nepokretnost"]) if d4 else None))
ok(d4 is not None and any("ucitani za 20 od %d - sajt je trazio pauzu" % M in n for n in d4["napomene"]),
   "napomena o pauzi: %s" % (d4 or {}).get("napomene"))
ok(pos.stop and any("sajt je trazio pauzu - ucitano 20 od %d" % M in m for t, m in log), "posao staje, poruka u dnevniku")
mock_sajt.STANJE["429"] = 0

# 5. izvodi: delimicno ucitavanje ne brise ranije sacuvane stranice
M5 = (1, "ТЕСТ", "1/1")
d5 = ak.dir_izvoda(*M5)
st = lambda x: "<html><body>%s</body></html>" % x
ind = lambda: json.load(open(os.path.join(d5, "indeks.json"), encoding="utf-8"))
html_u = lambda: sorted(f for f in os.listdir(d5) if f.endswith(".html"))
ak.sacuvaj_izvode(*M5, {"parcela": st("P"), "a": st("A"), "b": st("B"), "c": st("C")})
ok(list(ind()) == ["parcela", "a", "b", "c"] and len(html_u()) == 4, "potpuno: 4 stranice")
ok(ind()["a"]["fajl"] == ak.ime_izvoda("a") and ind()["parcela"]["fajl"] == "parcela.html", "ime fajla po stavci")
ak.dodaj_izvod(*M5, "d", st("D"))
ok(list(ind()) == ["parcela", "a", "b", "c", "d"] and len(html_u()) == 5, "dodaj_izvod: jedna stranica dodata, ostale ostaju")
ak.dodaj_izvod(*M5, "a", st("A2"))
ok(len(html_u()) == 5 and "A2" in ak.ucitaj_izvod(*M5, "a")[0], "dodaj_izvod iste stavke menja njen fajl")
ak.sacuvaj_izvode(*M5, {"a": st("A3"), "parcela": st("P2")}, False, ["parcela", "a", "b", "c", "d"])
ok(list(ind()) == ["parcela", "a", "b", "c", "d"] and len(html_u()) == 5, "delimično: stare stranice ostaju, redom kao na sajtu: %s" % list(ind()))
ok("A3" in ak.ucitaj_izvod(*M5, "a")[0] and "B" in ak.ucitaj_izvod(*M5, "b")[0], "nove zamenjene, stare čitljive")
ak.sacuvaj_izvode(*M5, {"parcela": st("P3"), "a": st("A4")}, True)
ok(list(ind()) == ["parcela", "a"] and len(html_u()) == 2, "potpuno: ostaje samo ono što sajt sada ima")
# stari oblik (n00.html ...) iz v18/v19
for f in os.listdir(d5):
    os.remove(os.path.join(d5, f))
for i, k in enumerate(("parcela", "x", "y")):
    open(os.path.join(d5, "n%02d.html" % i), "w", encoding="utf-8").write(st(k.upper()))
json.dump({k: {"fajl": "n%02d.html" % i, "vreme": "1.1.2026."} for i, k in enumerate(("parcela", "x", "y"))},
          open(os.path.join(d5, "indeks.json"), "w", encoding="utf-8"))
ak.sacuvaj_izvode(*M5, {"x": st("X2")}, False, ["parcela", "x", "y"])
ok(list(ind()) == ["parcela", "x", "y"] and "X2" in ak.ucitaj_izvod(*M5, "x")[0] and
   "Y" in ak.ucitaj_izvod(*M5, "y")[0] and "PARCELA" in ak.ucitaj_izvod(*M5, "parcela")[0],
   "izvodi iz v19 (n00.html) ostaju pri delimičnom učitavanju")
ok(html_u() == sorted(["n00.html", ak.ime_izvoda("x"), "n02.html"]), "stari fajl zamenjene stavke obrisan: %s" % html_u())

# 6. prozor: v21 (izbor stavki, skidanje samo izabranog) je u test_izbor.py
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
