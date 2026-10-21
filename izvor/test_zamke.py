# -*- coding: utf-8 -*-
"""Da li zamke koje je nasla nit Asistent PRO vaze i ovde: kolona na pocetku celije, desni klik na drugi red."""
import importlib.util, os, shutil, sys, tempfile, time
RAD = tempfile.mkdtemp(prefix="kat_pro_")
os.environ["KATASTAR_TEST"] = "1"
import mock_sajt
srv = mock_sajt.pokreni()
os.environ["KATASTAR_BASE"] = "http://127.0.0.1:%d/eKatastarPublic/" % srv.server_address[1]
shutil.copy("asistent_katastar.py", RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join("..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0]); ak = importlib.util.module_from_spec(spec); spec.loader.exec_module(ak)
class T:
    def __getattr__(self, i): return lambda *a, **k: True
ak.messagebox = T()
root = ak.tk.Tk(); root.tk.call("tk", "scaling", 96 / 72.0)
app = ak.App(root); root.geometry("1400x860+0+0")
for _ in range(10): root.update(); time.sleep(0.03)
t = app.tree_p; kp = app._kop_pretrage
for i in range(3):
    app._dodaj_red_pretrage({"ko": "ЖЕЛЕЗНИК", "broj": "1741/%d" % (i + 1)}, None, "proba %d" % i)
for _ in range(5): root.update()
VR = [1000]
def mis(w, seq, x, y, **kw):
    VR[0] += 700
    w.event_generate(seq, x=x, y=y, rootx=w.winfo_rootx() + x, rooty=w.winfo_rooty() + y, time=VR[0], **kw)
    root.update()
greske = 0
for kol in ("parcela", "status"):
    x, y, w, h = t.bbox("r1", kol)
    for dx in (1, 3):
        mis(t, "<Button-1>", x + dx, y + h // 2); mis(t, "<ButtonRelease-1>", x + dx, y + h // 2)
        dobio = kp.info and kp.info["kol"]
        print(("OK  " if dobio == kol else "PAO ") + "klik %d px od početka kolone %s -> polje na %s" % (dx, kol, dobio))
        greske += dobio != kol
x, y, w, h = t.bbox("r1", "parcela")
mis(t, "<Button-1>", x + 20, y + h // 2); mis(t, "<ButtonRelease-1>", x + 20, y + h // 2)
x2, y2, w2, h2 = t.bbox("r2", "parcela")
app.root.after(50, lambda: [m.unpost() for m in []])
orig = ak.tk.Menu.tk_popup
ak.tk.Menu.tk_popup = lambda self, *a, **k: None
mis(t, "<Button-3>", x2 + 20, y2 + h2 // 2)
ostalo = kp.e is not None and kp.info["iid"] not in t.selection()
print(("PAO " if ostalo else "OK  ") + "desni klik na drugi red: polje na starom redu ostalo=%s, izabran %s" % (ostalo, t.selection()))
greske += ostalo
# Ctrl+klik na drugi red dok je polje otvoreno: red se doda u izbor
mis(t, "<Button-1>", x + 20, y + h // 2); mis(t, "<ButtonRelease-1>", x + 20, y + h // 2)
x3, y3, w3, h3 = t.bbox("r3", "parcela")
mis(t, "<Control-Button-1>", x3 + 20, y3 + h3 // 2); mis(t, "<Control-ButtonRelease-1>", x3 + 20, y3 + h3 // 2)
dobro = set(t.selection()) == {"r1", "r3"} and kp.e is None
print(("OK  " if dobro else "PAO ") + "Ctrl+klik na drugi red: izabrano %s, polje zatvoreno %s" % (t.selection(), kp.e is None))
greske += not dobro
# Ctrl+klik na samo polje radi kao na listi (red se skida iz izbora), ne otvara detalje
mis(t, "<Button-1>", x + 20, y + h // 2); mis(t, "<ButtonRelease-1>", x + 20, y + h // 2)
mis(t, "<Control-Button-1>", x3 + 20, y3 + h3 // 2); mis(t, "<Control-ButtonRelease-1>", x3 + 20, y3 + h3 // 2)
mis(t, "<Button-1>", x + 20, y + h // 2); mis(t, "<ButtonRelease-1>", x + 20, y + h // 2)
time.sleep(0.6)
e = kp.e
otvoreno = []
app.detalji_pretrage = lambda *a: otvoreno.append(1)
kp.otvori = app.detalji_pretrage
mis(e, "<Control-Button-1>", 10, 5)
root.update()
dobro = "r1" not in t.selection() and kp.e is None and not otvoreno
print(("OK  " if dobro else "PAO ") + "Ctrl+klik na polje: izabrano %s, polje zatvoreno %s, detalji %s" %
      (t.selection(), kp.e is None, bool(otvoreno)))
greske += not dobro
# Shift+klik na polje: izbor od sidra do tog reda
t.selection_set("r3"); t.focus("r3"); root.update()
mis(t, "<Button-1>", x + 20, y + h // 2); mis(t, "<ButtonRelease-1>", x + 20, y + h // 2)
time.sleep(0.6)
mis(kp.e, "<Shift-Button-1>", 10, 5)
root.update()
print("     Shift+klik na polje: izabrano %s" % (t.selection(),))
print("UKUPNO GRESAKA: %d" % greske)
srv.shutdown()
