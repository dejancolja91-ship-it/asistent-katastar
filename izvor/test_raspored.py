# -*- coding: utf-8 -*-
"""Raspored Pretrage na malim ekranima (laptop 1920x1080 na 150%, 1366x768...): koliko redova tabele
rezultata se vidi (od v14 nema panela ispod nje), i dok je captcha otvorena. Svaka postavka ide u svom procesu."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

POSTAVKE = [  # ekran (DISPLAY), Windows uvecanje, velicina prikaza, ocekivana SKALA, najmanje mesta u tabeli
    (":96", 1920, 1080, 1.5, "auto", 1.25, 10),
    (":96", 1920, 1080, 1.5, "windows", 1.5, 7),
    (":96", 1920, 1080, 1.25, "auto", 1.25, 10),
    (":96", 1920, 1080, 1.0, "auto", 1.0, 15),
    (":95", 1366, 768, 1.0, "auto", 1.0, 8),
]

if len(sys.argv) == 1:
    ukupno = 0
    for d, sw, sh, u, vel, ocek, redova in POSTAVKE:
        env = dict(os.environ, DISPLAY=d)
        r = subprocess.run([sys.executable, __file__, str(sw), str(sh), str(u), vel, str(ocek), str(redova)],
                           env=env, capture_output=True, text=True, timeout=300)
        print(r.stdout, end="")
        if r.returncode != 0:
            print(r.stderr[-3000:])
            ukupno += 1
        ukupno += r.stdout.count("PAO  ")
    print("UKUPNO GRESAKA: %d" % ukupno)
    sys.exit(0)

SW, SH, U, VEL, OCEK, REDOVA = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), sys.argv[4], \
    float(sys.argv[5]), int(sys.argv[6])
IME = "%dx%d_%d_%s" % (SW, SH, round(U * 100), VEL)
RAD = tempfile.mkdtemp(prefix="kat_ras_")
os.environ["KATASTAR_TEST"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mock_sajt  # noqa: E402

srv = mock_sajt.pokreni()
os.environ["KATASTAR_BASE"] = "http://127.0.0.1:%d/eKatastarPublic/" % srv.server_address[1]
IZVOR = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(IZVOR, "asistent_katastar.py"), RAD)
for ime in ("asistent_katastar_ikona.png", "asistent_katastar.ico"):
    shutil.copy(os.path.join(IZVOR, "..", ime), RAD)
sys.argv = [os.path.join(RAD, "asistent_katastar.py")]
spec = importlib.util.spec_from_file_location("ak", sys.argv[0])
ak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ak)


class TihiMessagebox:
    def __getattr__(self, ime):
        return lambda *a, **k: True


ak.messagebox = TihiMessagebox()


def ok(uslov, opis):
    print(("OK   " if uslov else "PAO  ") + "[%s] %s" % (IME, opis), flush=True)


def osvezi(n=4):
    for _ in range(n):
        root.update()
        time.sleep(0.05)


root = ak.tk.Tk()
root.tk.call("tk", "scaling", 96.0 * U / 72.0)
if VEL != "auto":
    ak.Baza().postavi_podesavanje("velicina", VEL)
app = ak.App(root)
ok(abs(ak.SKALA - OCEK) < 0.02 and abs(ak.SKALA_WINDOWS - U) < 0.02,
   "program crta na %s (Windows %s)" % (ak.SKALA, ak.SKALA_WINDOWS))
# kao uvecan prozor u Windowsu: ceo ekran bez trake zadataka (48), naslova prozora (31) i menija
root.geometry("%dx%d+0+0" % (SW, 600))
osvezi(4)
MENI = root.winfo_rooty()
VIS = SH - round(48 * U) - round(31 * U) - MENI
root.geometry("%dx%d+0+0" % (SW, VIS))
osvezi(8)
t = app.tree_p
for i in range(6):
    app._dodaj_red_pretrage({"ko": "ЖЕЛЕЗНИК", "broj": "1741/%d" % (i + 1)}, None, "proba")
t.see("r1")
osvezi()
RH = int(ak.ttk.Style().lookup("Treeview", "rowheight"))


def vidljivih():
    root.update_idletasks()
    n = 0
    for iid in t.get_children(""):
        bb = t.bbox(iid)
        if bb and bb[1] + bb[3] <= t.winfo_height():
            n += 1
    return n


def mesta():
    """koliko redova staje u tabelu (bez naslova kolona)"""
    root.update_idletasks()
    return t.winfo_height() // RH - 1


def slika(ime):
    subprocess.run(["import", "-window", "root", "-crop", "%dx%d+0+0" % (SW, MENI + VIS),
                    os.path.join(IZVOR, ime)], check=False)


n, m = vidljivih(), mesta()
print("     [%s] vidi se %d od 6 redova, tabela ima mesta za %d, prozor %dx%d" % (IME, n, m, SW, VIS))
ok(n == 6 and m >= REDOVA, "tabela rezultata: svih 6 redova, mesta za bar %d: %d" % (REDOVA, m))
ok(not hasattr(app, "panel_p") and not app.log_prozor.winfo_viewable() and "Spremno" in app.txt.get("1.0", "end"),
   "nema panela ni poruka ispod tabele (poruke: Alati > Prikaži sve poruke)")
lo = app.lbl_opis
ok(lo.winfo_ismapped() and lo.winfo_rooty() + lo.winfo_height() <= root.winfo_rooty() + root.winfo_height(),
   "statusna linija sa ishodom je vidljiva na dnu prozora")
slika("raspored_%s.png" % IME)

# captcha se pojavi iznad tabele
app.captcha_frame.winfo_ismapped = lambda: False
app._pokazi_captchu_panel()
del app.captcha_frame.winfo_ismapped
osvezi(8)
n2 = vidljivih()
print("     [%s] dok je captcha otvorena: %d redova" % (IME, n2))
ok(n2 >= min(6, max(2, REDOVA - 6)), "dok je captcha otvorena tabela i dalje ima redove: %d" % n2)
slika("raspored_%s_captcha.png" % IME)
app._sakrij_captchu_panel()
osvezi(8)
ok(vidljivih() == n and mesta() == m, "posle captche tabela je ista kao pre: %d" % vidljivih())
srv.shutdown()
root.destroy()
