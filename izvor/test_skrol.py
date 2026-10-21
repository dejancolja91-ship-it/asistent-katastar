# -*- coding: utf-8 -*-
"""v23 (Dejan: "kada listam stanove, seta i taj segment stranice i cela stranica"): tockic misa iznad tabele koja
ima svoj klizac (npr. 60 stanova) pomera samo tu tabelu; iznad tabele koja stane cela, naslova sekcije ili praznog
dela pomera se cela stranica (prozor parcele i prozor izvoda)."""
import importlib.util
import os
import shutil
import sys
import tempfile

RAD = tempfile.mkdtemp(prefix="kat_skrol_")
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


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + opis, flush=True)
    if not uslov:
        GRESKE.append(opis)


root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * UVECANJE / 72.0)
app = ak.App(root)
root.geometry("%dx%d+0+0" % (round(1400 * UVECANJE), round(860 * UVECANJE)))
root.update()
N = 60
sn = {"opstina": "ЗЕМУН", "ko": "ЗЕМУН", "nepokretnost": {}, "napomene": [],
      "delovi": [["1", "500", "УЛИЦА", "ЗЕМЉИШТЕ ПОД ЗГРАДОМ", "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", ""],
                 ["2", "100", "УЛИЦА", "ЗЕМЉИШТЕ УЗ ЗГРАДУ", "ГРАДСКО ГРАЂЕВИНСКО ЗЕМЉИШТЕ", ""]],
      "objekti": [["1", "УЛИЦА", "1", "", "900", "СТАМБЕНА ЗГРАДА", "ПРЕУЗЕТ"]],
      "posebni": [["УЛИЦА 1", str(i), "1", str(i), "", "СТАН", str(40 + i)] for i in range(1, N + 1)]}
w = app._prozor_detalja("ЗЕМУН, KO ЗЕМУН, parcela 13662", sn, [], mesto=(1, "ЗЕМУН", "13662"))
w.geometry("%dx%d+0+0" % (round(1300 * UVECANJE), round(620 * UVECANJE)))   # v29: bez uputstva stranica je niža
root.update()
p = app._panel
tp, tpos = p["tabele"]["parcela"], p["tabele"]["p"]
cv = p["telo"].platno


def tocak(widget, dole=True, x=None, y=None):
    """Tockic misa iznad widget-a (kao na Windows-u: dogadjaj ide widget-u ispod kursora)."""
    root.update()
    x = widget.winfo_width() // 2 if x is None else x
    y = widget.winfo_height() // 2 if y is None else y
    widget.event_generate("<MouseWheel>", delta=-120 if dole else 120, x=x, y=y,
                          rootx=widget.winfo_rootx() + x, rooty=widget.winfo_rooty() + y)
    root.update()


ok(tpos.yview()[1] < 1.0, "tabela stanova ima svoj klizač (%d stanova, vidi se deo)" % N)
ok(cv.yview()[1] < 1.0, "stranica ima svoj klizač")
cv.yview_moveto(0)
s0, t0 = cv.yview()[0], tpos.yview()[0]
tocak(tpos)
ok(tpos.yview()[0] > t0, "točkić iznad tabele stanova: tabela se pomerila")
ok(cv.yview()[0] == s0, "... a stranica NE (%.3f -> %.3f)" % (s0, cv.yview()[0]))
for _ in range(3):
    tocak(tpos)
ok(cv.yview()[0] == s0, "ni posle više okreta")
tocak(tpos, dole=False)
ok(cv.yview()[0] == s0, "ni nagore")
tpos.yview_moveto(1.0)
root.update()
t1 = tpos.yview()[0]
tocak(tpos)
ok(tpos.yview()[0] == t1 and cv.yview()[0] == s0, "na kraju tabele: ništa se ne pomera (stranica ne kreće sama)")
# tabela koja stane cela (delovi parcele): pomera se stranica
ok(tp.yview() == (0.0, 1.0), "tabela delova parcele stane cela")
tocak(tp)
ok(cv.yview()[0] > s0, "točkić iznad nje: pomera se stranica (%.3f -> %.3f)" % (s0, cv.yview()[0]))
s1 = cv.yview()[0]
tocak(tp, dole=False)
ok(cv.yview()[0] < s1, "i nagore")
# naslov sekcije
cv.yview_moveto(0)
root.update()
naslov = next(c for c in p["telo"].winfo_children() if isinstance(c, ak.tk.Label) and "Посебни делови" in c.cget("text"))
tocak(naslov)
ok(cv.yview()[0] > 0, "točkić iznad naslova sekcije: pomera se stranica")
# Button-4/5 (Linux)
cv.yview_moveto(0)
tpos.yview_moveto(0)
root.update()
x, y = tpos.winfo_width() // 2, tpos.winfo_height() // 2
tpos.event_generate("<Button-5>", x=x, y=y, rootx=tpos.winfo_rootx() + x, rooty=tpos.winfo_rooty() + y)
root.update()
ok(cv.yview()[0] == 0, "Button-5 iznad tabele stanova: stranica se ne pomera")
# polje za kopiranje celije (preko tabele): pomera samo tabelu
iid = tpos.get_children("")[3]
tpos.see(iid)
tpos.yview_moveto(0)
root.update()
bb = tpos.bbox(iid, "4")
tpos.event_generate("<ButtonPress-1>", x=bb[0] + 5, y=bb[1] + 3)
tpos.event_generate("<ButtonRelease-1>", x=bb[0] + 5, y=bb[1] + 3)
root.update()
polje = [c for c in tpos.winfo_children() if isinstance(c, ak.tk.Entry) and c.winfo_ismapped()]
if polje:
    s0, t0 = cv.yview()[0], tpos.yview()[0]
    tocak(polje[0])
    ok(cv.yview()[0] == s0 and tpos.yview()[0] > t0, "točkić iznad polja ćelije: samo tabela")
else:
    print("     (polje ćelije se nije otvorilo - preskočeno)")

# prozor izvoda (jedan klizač): točkić pomera stranicu izvoda
wi = app._prozor_nepokretnosti("Stan 1", ["[Имаоци права на посебном делу] Назив: X; Удео: 1/1"] * 60, None, None)
wi.geometry("%dx%d+0+0" % (round(900 * UVECANJE), round(400 * UVECANJE)))
root.update()


def svi(x):
    for c in x.winfo_children():
        yield c
        yield from svi(c)


cvi = next(c for c in svi(wi) if getattr(c, "skrol", False))
ok(cvi.yview()[1] < 1.0, "izvod ima klizač")
dete = next(c for c in cvi.winfo_children()[0].winfo_children() if c.winfo_ismapped())
tocak(dete)
ok(cvi.yview()[0] > 0, "točkić u izvodu pomera izvod")
root.destroy()
print("\nUKUPNO GRESAKA:", len(GRESKE))
sys.exit(1 if GRESKE else 0)
