# -*- coding: utf-8 -*-
"""v15: parcele istog klijenta bez grupe idu u grupu i one koje su ranije dodate iz Pretrage (jednom, pri prvom
pokretanju v15); posle toga se rucno "bez grupe" postuje. Opcioni argument: kopija prave baze (ispisuju se samo brojevi)."""
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile

RAD = tempfile.mkdtemp(prefix="kat_grupe_")
os.environ["KATASTAR_TEST"] = "1"
IZVOR = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(IZVOR, "asistent_katastar.py"), RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join(IZVOR, "..", ime), RAD)
PRAVA = sys.argv[1] if len(sys.argv) > 1 else None
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
GRESKE = []


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: True


ak.messagebox = TihiMessagebox()


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


def pokreni():
    root = ak.tk.Tk()
    app = ak.App(root)
    root.update()
    return root, app


# baza kao kod Dejana posle v8-v14: grupisanje pri pokretanju vec obavljeno, pa dodate 2 parcele iz Pretrage bez grupe
b = ak.Baza()
b.postavi_podesavanje("auto_grupe_sredjeno", "1")
for broj, kl, gr in (("1741/1", "Petrović Jovan", ""), ("1741/2", "PETROVIC JOVAN", ""), ("1741/3", "Drugi Klijent", ""),
                     ("100", "Treći", "Moja grupa"), ("101", "Treći", "")):
    b.dodaj(1, "ЧУКАРИЦА", 703702, "ЖЕЛЕЗНИК", broj, kl, gr)
root, app = pokreni()
p = {x["broj"]: x for x in app.baza.parcele()}
ok(p["1741/1"]["grupa"] == p["1741/2"]["grupa"] == "Petrović Jovan" and not p["1741/3"]["grupa"]
   and p["101"]["grupa"] == "Moja grupa", "prvo pokretanje v15: ranije dodate parcele istog klijenta grupisane: %s" %
   [(k, v["grupa"]) for k, v in sorted(p.items())])
ok(app.tree.parent(str(p["1741/1"]["id"])) == "g:Petrović Jovan" and app.tree.item("g:Petrović Jovan", "open"),
   "grupa je u listi i otvorena")
ok("grupisane" in app.lbl_opis.cget("text") or "grupisane" in app.txt.get("1.0", "end"),
   "javljeno: %s" % app.lbl_opis.cget("text"))
ok(app.baza.podesavanje("auto_grupe_sredjeno") == "v15", "sređivanje zapamćeno")
# rucno izbacena iz grupe ostaje bez grupe i posle ponovnog pokretanja
app.baza.izmeni(p["1741/2"]["id"], p["1741/2"]["klijent"], "", "")
root.destroy()
root, app = pokreni()
ok(not app.baza.parcele([p["1741/2"]["id"]])[0]["grupa"], "drugo pokretanje: ručno 'bez grupe' se poštuje")
root.destroy()

if PRAVA:
    pr = tempfile.mkdtemp(prefix="kat_prava_")
    shutil.copy(PRAVA, os.path.join(pr, "katastar.db"))
    os.chmod(os.path.join(pr, "katastar.db"), 0o644)
    shutil.copy(os.path.join(RAD, "asistent_katastar.py"), pr)
    import subprocess
    kod = ("import importlib.util,sys,os,sqlite3;sys.argv=[os.path.join(%r,'asistent_katastar.py')];"
           "s=importlib.util.spec_from_file_location('ak',sys.argv[0]);ak=importlib.util.module_from_spec(s);"
           "s.loader.exec_module(ak);ak.messagebox=type('M',(),{'__getattr__':lambda s,n:(lambda *a,**k:True)})();"
           "r=ak.tk.Tk();app=ak.App(r);r.update();ps=app.baza.parcele();"
           "print('     prava baza: %%d parcela, u grupi %%d, grupa %%d' %% (len(ps), sum(1 for x in ps if x['grupa']),"
           " len(app.baza.grupe())))" % pr)
    c = sqlite3.connect(os.path.join(pr, "katastar.db"))
    pre = c.execute("SELECT count(*), sum(grupa<>'') FROM parcele").fetchone()
    c.close()
    print("     prava baza pre: %d parcela, u grupi %d" % pre)
    r = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, env=dict(os.environ))
    print(r.stdout.strip() or r.stderr[-1500:])
print("UKUPNO GRESAKA: %d" % len(GRESKE))
