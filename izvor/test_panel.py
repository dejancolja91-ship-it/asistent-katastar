# -*- coding: utf-8 -*-
"""v17: prozor parcele kao na eKatastru - klik na deo parcele pokazuje samo objekte na tom delu, a klik na objekat
samo njegove posebne delove (primer Dejana: Vračar 2446)."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

RAD = tempfile.mkdtemp(prefix="kat_panel_")
os.environ["KATASTAR_TEST"] = "1"
IZVOR = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(IZVOR, "asistent_katastar.py"), RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join(IZVOR, "..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)
GRESKE = []


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


root = ak.tk.Tk()
app = ak.App(root)
root.geometry("1400x860+0+0")
root.update()

sn = {"opstina": "ВРАЧАР", "ko": "ВРАЧАР", "ukupno": "355",
      "delovi": [["1", "189", "ВЕЛЕ НИГРИНОВЕ", "ЗЕМЉИШТЕ ПОД ЗГРАДОМ И ДРУГИМ ОБЈЕКТОМ", "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", ""],
                 ["2", "17", "ВЕЛЕ НИГРИНОВЕ", "ЗЕМЉИШТЕ ПОД ЗГРАДОМ И ДРУГИМ ОБЈЕКТОМ", "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", ""],
                 ["3", "149", "ВЕЛЕ НИГРИНОВЕ", "ЗЕМЉИШТЕ УЗ ЗГРАДУ И ДРУГИ ОБЈЕКАТ", "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", ""]],
      "objekti": [["1", "ВЕЛЕ НИГРИНОВЕ", "10", "", "189", "СТАМБЕНА ЗГРАДА ЗА КОЛЕКТИВНО СТАНОВАЊЕ",
                   "ОБЈЕКАТ ПРЕУЗЕТ ИЗ ЗЕМЉИШНЕ КЊИГЕ"],
                  ["2", "ВЕЛЕ НИГРИНОВЕ", "", "", "17", "ПОРОДИЧНА СТАМБЕНА ЗГРАДА", "ОБЈЕКАТ ИЗГРАЂЕН БЕЗ ОДОБРЕЊА"]],
      "posebni": [["ВЕЛЕ НИГРИНОВЕ 10", str(i), "10", str(i - 1) if i > 1 else "1", "", "СТАН", "40"] for i in range(1, 9)],
      "nepokretnost": {}, "napomene": []}


def otvori(snimak):
    app._prozor_detalja("ВРАЧАР, KO ВРАЧАР, parcela 2446", snimak, [], mesto=("", "ВРАЧАР", "2446"))
    root.update()
    return app._panel


def klikni(tr, iid):
    """kao klik misem: red se izabere, a <<TreeviewSelect>> stigne posle"""
    tr.selection_set(iid)
    tr.focus(iid)
    for _ in range(3):
        root.update()


def redovi(tr):
    return tuple(tr.get_children(""))


for opis, snimak in (("stari snimak (uparivanje po adresi)", sn),
                     ("nov snimak (tačan objekat)", dict(sn, posebni_obj=[0] * 8))):
    p = otvori(snimak)
    tp, to, tpos = p["tabele"]["parcela"], p["tabele"]["o"], p["tabele"]["p"]
    sve8 = tuple("p%d" % j for j in range(8))
    ok(tp.selection() == ("parcela_0",) and redovi(to) == ("o0",) and to.selection() == ("o0",) and redovi(tpos) == sve8,
       "%s: na početku izabran deo 1, njegova zgrada i njenih 8 stanova" % opis)
    if opis.startswith("stari"):
        subprocess.run(["import", "-window", "root", os.path.join(IZVOR, "panel_deo1_v17.png")], check=False)
    klikni(tp, "parcela_1")
    ok(redovi(to) == ("o1",) and redovi(tpos) == ("prazno",),
       "%s: deo 2 -> samo druga zgrada, bez posebnih delova: %s / %s" % (opis, redovi(to), redovi(tpos)))
    if opis.startswith("stari"):
        subprocess.run(["import", "-window", "root", os.path.join(IZVOR, "panel_deo2_v17.png")], check=False)
    klikni(tp, "parcela_2")
    ok(redovi(to) == ("prazno",) and redovi(tpos) == ("prazno",), "%s: deo 3 (uz zgradu) -> bez objekata" % opis)
    klikni(tp, "parcela_0")
    ok(redovi(to) == ("o0",) and redovi(tpos) == sve8, "%s: nazad na deo 1 -> zgrada i stanovi" % opis)
    to.winfo_toplevel().destroy()
    root.update()

# vise objekata na istom delu: klik na objekat menja posebne delove
sn2 = dict(sn, objekti=[["1", "ВЕЛЕ НИГРИНОВЕ", "10", "", "189", "СТАМБЕНА ЗГРАДА", "ПРЕУЗЕТ"],
                        ["1, 2", "ВЕЛЕ НИГРИНОВЕ", "10", "", "18", "ПОМОЋНА ЗГРАДА - ГАРАЖА", "ПРЕУЗЕТ"]],
           posebni=sn["posebni"][:3] + [["ВЕЛЕ НИГРИНОВЕ 10", "9", "", "", "", "ГАРАЖНИ ПРОСТОР", "15"]],
           posebni_obj=[0, 0, 0, 1])
p = otvori(sn2)
tp, to, tpos = p["tabele"]["parcela"], p["tabele"]["o"], p["tabele"]["p"]
ok(redovi(to) == ("o0", "o1") and redovi(tpos) == ("p0", "p1", "p2"), "deo 1: obe zgrade, stanovi prve (izabrane)")
klikni(to, "o1")
ok(redovi(tpos) == ("p3",), "klik na garažu -> samo garažni prostor (iako je adresa ista)")
klikni(tp, "parcela_1")
ok(redovi(to) == ("o1",) and to.selection() == ("o1",) and redovi(tpos) == ("p3",),
   "deo 2 -> samo garaža (stoji na delovima 1 i 2) i njen poseban deo")
w = app._otvori_iz_panela(p, "o")
ok(w is not None, "dvoklik na zgradu i dalje otvara „Подаци о непокретности“")
w.destroy()
to.winfo_toplevel().destroy()
# pravi klik misem na red dela parcele
p = otvori(sn)
tp, to, tpos = p["tabele"]["parcela"], p["tabele"]["o"], p["tabele"]["p"]
x, y, w_, h = tp.bbox("parcela_1", "3")
for i, dog in enumerate(("<ButtonPress-1>", "<ButtonRelease-1>")):
    tp.event_generate(dog, x=x + 5, y=y + h // 2, rootx=tp.winfo_rootx() + x + 5, rooty=tp.winfo_rooty() + y + h // 2,
                      time=1000 + i * 50)
for _ in range(4):
    root.update()
ok(tp.selection() == ("parcela_1",) and redovi(to) == ("o1",) and redovi(tpos) == ("prazno",),
   "klik mišem na deo 2: %s %s %s" % (tp.selection(), redovi(to), redovi(tpos)))
to.winfo_toplevel().destroy()
print("UKUPNO GRESAKA: %d" % len(GRESKE))
