# -*- coding: utf-8 -*-
"""
Asistent KATASTAR v1 - pretraga i pracenje parcela na eKatastru (katastar.rgz.gov.rs/eKatastarPublic)

- radi direktno sa sajtom (requests), bez Chrome-a
- pretraga vise parcela odjednom (spisak brojeva za izabranu katastarsku opstinu), izvoz u Excel (CSV)
- pracenje izabranih parcela: svaka provera se poredi sa prethodnom i promene se oznacavaju
- captcha (SVG, 5 znakova, razlikuje velika i mala slova): program je cita sam kad je siguran,
  inace je upisujes ti; svaki prihvacen odgovor ga uci novim znakovima
- azuriranje sa GitHub-a (v33): pri pokretanju program sam preuzme novu verziju (git pull), staru sacuva u rezerve/
- v34: nova verzija se pre pokretanja proba na kopiji podataka; ako ne radi, ostaje stara

Potrebno: Python 3.9+ i paket requests  (py -m pip install requests)
"""
import base64
import contextlib
import csv
import datetime as dt
import hashlib
import html as htmlmod
import json
import os
import pathlib
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.parse
import tkinter as tk
from collections import Counter
from tkinter import ttk, messagebox, simpledialog, filedialog
import tkinter.font as tkfont

import requests

# ----------------------------------------------------------------------
# Konfiguracija
# ----------------------------------------------------------------------
VERZIJA = "v37"
BASE = os.environ.get("KATASTAR_BASE", "https://katastar.rgz.gov.rs/eKatastarPublic/")
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
PAUZA_IZMEDJU_PARCELA = (3.0, 6.0)    # sekunde izmedju dve parcele
PAUZA_ZAHTEVA = (1.0, 2.0)            # izmedju dodatnih zahteva iste parcele (delovi, objekti)
MAX_POKUSAJA = 3                      # rucnih unosa captche po parceli
AUTO_POKUSAJA = 3                     # novih slika kad citac nije siguran
CEKANJE_429 = 60
# Dejan (v20): ucitavaju se SVI "Podaci o nepokretnosti" (parcela, objekti, svi posebni delovi), i za zgradu sa 190+
# stanova; ovo je samo zastita od greske na sajtu (do v19 je bilo 40)
MAX_NEPOKRETNOSTI = 3000
NEP_VERZIJA = 2                       # oblik zapisa podataka o nepokretnosti u snimku
BEZ_GRUPE = "(bez grupe)"
# Prikaz liste pracenja (kao u Asistent PRO); kartice iznad liste biraju isto
PRIKAZI = ("Sve parcele", "Promena u ovoj sesiji", "Nepregledano (promena od ranije)",
           "Nije provereno / nije uspelo", "Provereno u ovoj sesiji", "Odložena provera", "Arhiva")
MAX_SIRINA_KOLONE = 900               # automatska sirina kolone ne ide preko ovoga (rucno moze sire)
MAX_KOLONE = {"nacin": 340, "objekti": 300, "vlasnici": 460, "status": 320, "promena": 460, "provereno": 380}
BOJA_OK, BOJA_NEUSPEH = "#17663a", "#c21f1f"
# kao u Asistent PRO: jarko zuto = promena nadjena u ovoj sesiji (ceo red, dok je program otvoren);
# podebljano bez boje = promena od ranije, nepregledana; zelena celija "Provera" = provereno u ovoj sesiji
BG_PROMENA, BG_ZELENO, BG_NOVO, BG_PAR = "#ffe066", "#dcf3e4", "#fff4c2", "#f7f9fc"
MAX_PROMENA_TRAKA = 5          # v31: toliko promena u traci prozora, ostale u kartici Istorija promena
# izgled: ista svetla tema kao Asistent PRO (ttk "clam", bez dodatnih paketa)
T_POZADINA = "#eef1f6"
T_POVRSINA = "#ffffff"
T_IVICA = "#d8dee8"
T_TEKST = "#1f2937"
T_SIVO = "#6b7280"
T_AKCENT = "#2457c5"
T_AKCENT_TAMNO = "#1c4399"
T_ZAGLAVLJE = "#173a7a"
T_GRUPA = "#e6ecf6"
T_IZBOR = "#cfe0ff"
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
# prozor "Подаци о непокретности" kao na eKatastru (boje sa stranice izvoda)
EK_NASLOV = "#29325b"
EK_SEKCIJA = "#dde3ee"
EK_PODSEKCIJA = "#eef1f6"
EK_TACKE = "#9a9a9a"
TEST_REZIM = os.environ.get("KATASTAR_TEST") == "1"

# v34: KATASTAR_DIR = privremeni folder za probni start nove verzije (radi na kopiji baze, ne dira prave podatke)
DIR = os.environ.get("KATASTAR_DIR") or os.path.dirname(os.path.abspath(sys.argv[0]))
DB_PATH = os.path.join(DIR, "katastar.db")
REZERVE_DIR = os.path.join(DIR, "rezerve")
SIFARNIK_PATH = os.path.join(DIR, "sifarnik_ko.json")
UZORCI_PATH = os.path.join(DIR, "uzorci_captcha.json")
DNEVNIK_PATH = os.path.join(DIR, "dnevnik.txt")
IZVODI_DIR = os.path.join(DIR, "izvodi")        # poslednje preuzete stranice "Podaci o nepokretnosti"
ZADACI_DIR = os.path.join(DIR, "zadaci")          # v32: zadaci koje ostavi Claude (spisak parcela iz ugovora)
ZADACI_TIK_MS = 5000                                # koliko često program pogleda folder zadaci
PDF_DIR = os.path.join(DIR, "PDF")              # podrazumevani folder za "Sacuvaj PDF izvoda"

# Opstine (preuzeto sa eKatastra 05.10.2026); program osvezava spisak sa sajta.
OPSTINE_UGRADJENE = json.loads(r"""[[80012,"АДА"],[70017,"АЛЕКСАНДРОВАЦ"],[70025,"АЛЕКСИНАЦ"],[80039,"АЛИБУНАР"],[80047,"АПАТИН"],[70033,"АРАНЂЕЛОВАЦ"],[70041,"АРИЉЕ"],[70050,"БАБУШНИЦА"],[70068,"БАЈИНА БАШТА"],[70092,"БАРАЈЕВО"],[70076,"БАТОЧИНА"],[80055,"БАЧ"],[80063,"БАЧКА ПАЛАНКА"],[80071,"БАЧКА ТОПОЛА"],[80080,"БАЧКИ ПЕТРОВАЦ"],[70084,"БЕЛА ПАЛАНКА"],[80098,"БЕЛА ЦРКВА"],[80101,"БЕОЧИН"],[80110,"БЕЧЕЈ"],[70262,"БЛАЦЕ"],[70289,"БОГАТИЋ"],[70297,"БОЈНИК"],[70319,"БОЉЕВАЦ"],[70327,"БОР"],[70335,"БОСИЛЕГРАД"],[70343,"БРУС"],[70351,"БУЈАНОВАЦ"],[70360,"ВАЉЕВО"],[70378,"ВАРВАРИН"],[70386,"ВЕЛИКА ПЛАНА"],[70394,"ВЕЛИКО ГРАДИШТЕ"],[70408,"ВЛАДИМИРЦИ"],[70416,"ВЛАДИЧИН ХАН"],[70424,"ВЛАСОТИНЦЕ"],[70106,"ВОЖДОВАЦ"],[70432,"ВРАЊЕ"],[71358,"ВРАЊСКА БАЊА"],[70114,"ВРАЧАР"],[80462,"ВРБАС"],[70459,"ВРЊАЧКА БАЊА"],[80128,"ВРШАЦ"],[70467,"ГАЏИН ХАН"],[70475,"ГОЛУБАЦ"],[70483,"ГОРЊИ МИЛАНОВАЦ"],[70122,"ГРОЦКА"],[70491,"ДЕСПОТОВАЦ"],[70505,"ДИМИТРОВГРАД"],[70513,"ДОЉЕВАЦ"],[80136,"ЖАБАЉ"],[70521,"ЖАБАРИ"],[70530,"ЖАГУБИЦА"],[80144,"ЖИТИШТЕ"],[70548,"ЖИТОРАЂА"],[70556,"ЗАЈЕЧАР"],[70149,"ЗВЕЗДАРА"],[70157,"ЗЕМУН"],[80152,"ЗРЕЊАНИН"],[70564,"ИВАЊИЦА"],[80179,"ИНЂИЈА"],[80187,"ИРИГ"],[71048,"ЈАГОДИНА"],[80195,"КАЊИЖА"],[80209,"КИКИНДА"],[70572,"КЛАДОВО"],[70599,"КНИЋ"],[70602,"КЊАЖЕВАЦ"],[80217,"КОВАЧИЦА"],[80225,"КОВИН"],[70629,"КОСЈЕРИЋ"],[71340,"КОСТОЛАЦ"],[70637,"КОЦЕЉЕВА"],[70645,"КРАГУЈЕВАЦ"],[70653,"КРАЉЕВО"],[70661,"КРУПАЊ"],[70670,"КРУШЕВАЦ"],[80233,"КУЛА"],[70688,"КУРШУМЛИЈА"],[70696,"КУЧЕВО"],[70165,"ЛАЗАРЕВАЦ"],[70700,"ЛАЈКОВАЦ"],[71277,"ЛАПОВО"],[70718,"ЛЕБАНЕ"],[70726,"ЛЕСКОВАЦ"],[70734,"ЛОЗНИЦА"],[70742,"ЛУЧАНИ"],[70769,"ЉИГ"],[70777,"ЉУБОВИЈА"],[70785,"МАЈДАНПЕК"],[70793,"МАЛИ ЗВОРНИК"],[80241,"МАЛИ ИЂОШ"],[70807,"МАЛО ЦРНИЋЕ"],[70815,"МЕДВЕЂА"],[71331,"МЕДИЈАНА"],[70823,"МЕРОШИНА"],[70831,"МИОНИЦА"],[70173,"МЛАДЕНОВАЦ"],[70840,"НЕГОТИН"],[71285,"НИШКА БАЊА"],[70866,"НОВА ВАРОШ"],[80250,"НОВА ЦРЊА"],[70181,"НОВИ БЕОГРАД"],[80268,"НОВИ БЕЧЕЈ"],[80276,"НОВИ КНЕЖЕВАЦ"],[70874,"НОВИ ПАЗАР"],[89010,"НОВИ САД"],[70190,"ОБРЕНОВАЦ"],[80292,"ОПОВО"],[70882,"ОСЕЧИНА"],[80306,"ОЏАЦИ"],[70203,"ПАЛИЛУЛА (БЕОГРАД)"],[71323,"ПАЛИЛУЛА (НИШ)"],[71307,"ПАНТЕЛЕЈ"],[80314,"ПАНЧЕВО"],[70904,"ПАРАЋИН"],[70912,"ПЕТРОВАЦ НА МЛАВИ"],[80322,"ПЕЋИНЦИ"],[70939,"ПИРОТ"],[80349,"ПЛАНДИШТЕ"],[70947,"ПОЖАРЕВАЦ"],[70955,"ПОЖЕГА"],[70963,"ПРЕШЕВО"],[70971,"ПРИБОЈ"],[70980,"ПРИЈЕПОЉЕ"],[70998,"ПРОКУПЉЕ"],[71005,"РАЖАЊ"],[70211,"РАКОВИЦА"],[71013,"РАЧА"],[71021,"РАШКА"],[71030,"РЕКОВАЦ"],[80357,"РУМА"],[70220,"САВСКИ ВЕНАЦ"],[71056,"СВИЛАЈНАЦ"],[71064,"СВРЉИГ"],[71366,"СЕВОЈНО"],[80365,"СЕНТА"],[80373,"СЕЧАЊ"],[71072,"СЈЕНИЦА"],[71099,"СМЕДЕРЕВО"],[71102,"СМЕДЕРЕВСКА ПАЛАНКА"],[71129,"СОКОБАЊА"],[80381,"СОМБОР"],[70238,"СОПОТ"],[80390,"СРБОБРАН"],[80403,"СРЕМСКА МИТРОВИЦА"],[80411,"СРЕМСКИ КАРЛОВЦИ"],[80420,"СТАРА ПАЗОВА"],[70246,"СТАРИ ГРАД"],[80438,"СУБОТИЦА"],[71137,"СУРДУЛИЦА"],[71293,"СУРЧИН"],[80446,"ТЕМЕРИН"],[80454,"ТИТЕЛ"],[71153,"ТОПОЛА"],[71161,"ТРГОВИШТЕ"],[71170,"ТРСТЕНИК"],[71188,"ТУТИН"],[71196,"ЋИЋЕВАЦ"],[71200,"ЋУПРИЈА"],[71218,"УБ"],[71145,"УЖИЦЕ"],[71315,"ЦРВЕНИ КРСТ"],[71226,"ЦРНА ТРАВА"],[71234,"ЧАЈЕТИНА"],[71242,"ЧАЧАК"],[80489,"ЧОКА"],[70254,"ЧУКАРИЦА"],[71269,"ШАБАЦ"],[80497,"ШИД"]]""")
# Katastarske opstine koje su vec poznate; ostale program ucitava sa sajta kad izaberes opstinu.
KO_UGRADJENE = {
    "70106": [[703494, "БЕЛИ ПОТОК"], [703621, "ВОЖДОВАЦ"], [703753, "ЗУЦЕ"], [703761, "ЈАЈИНЦИ"],
              [703800, "КУМОДРАЖ"], [703915, "ПИНОСАВА"], [703931, "РАКОВИЦА СЕЛО"], [703958, "РИПАЊ"]],
}
# Znakovi captche procitani sa poznatih slika (pocetno znanje citaca).
SEME_CAPTCHE = json.loads(r"""[["v","MLLLLLLz",[[17.44,42.11],[21.01,42.63],[29.35,22.24],[24.76,22.67],[20.82,37.94],[14.21,22.18],[10.23,22.7]]],["0","MCCCCzMCLCCzMCCLCz",[[41.31,42.73],[47.65,44.26],[52.37,37.68],[51.78,29.37],[52.57,21.2],[47.52,15.53],[40.85,16.26],[35.03,15.05],[31.29,20.09],[31.07,29.79],[30.31,39.22],[35.27,43.5],[41.03,44.23],[35.13,28.8],[34.63,26.72],[35.78,25.43],[34.95,24.03],[45.64,39.52],[44.41,39.59],[43.72,40.12],[40.66,40.79],[36.74,40.17],[34.43,36.26],[35.67,29.58],[41.96,19.17],[46.53,17.64],[48.68,22.37],[47.95,29.33],[48.38,31.72],[48.78,33.98],[47.67,34.5],[38.3,19.97],[39.18,18.81],[39.26,18.22],[41.62,18.95]]],["a","MCLLCLCCLCCCCzMLCCCz",[[63.88,42.7],[66.7,42.58],[68.77,41.96],[69.64,39.86],[69.9,43.46],[74.48,42.15],[73.19,41.34],[73.31,39.5],[72.11,35.95],[73.03,31.43],[72.9,25.61],[70.81,23.61],[65.89,23.47],[61.84,21.77],[58.47,23.55],[56.75,27.85],[59.73,27.45],[61.65,26.39],[62.34,25.25],[65.59,25.95],[69.13,24.48],[69.17,28.13],[69.86,30.13],[61.63,31.12],[56.46,33.84],[55.49,37.43],[56.51,41.54],[58.41,42.83],[62.93,43.68],[69.09,33.78],[70.16,34.39],[70.47,38.52],[66.98,40.19],[62.82,40.62],[62.02,40.16],[59.88,39.74],[60.79,38.12],[60.59,34.78],[63.56,34.4],[69.31,33.68]]],["8","MCCCCCCCCzMCCCCzMCCCCz",[[77.53,35.16],[77.71,40.51],[83.01,43.88],[88.82,43.14],[94.24,43.42],[98.65,40.82],[97.36,34.42],[97.0,31.94],[95.24,28.65],[92.55,28.03],[93.63,26.16],[94.99,24.86],[95.04,22.95],[95.0,19.71],[92.44,15.91],[88.51,16.18],[83.7,15.57],[80.61,18.44],[79.79,22.53],[80.27,25.66],[81.14,27.24],[83.14,27.88],[79.63,30.1],[77.78,32.78],[78.4,35.04],[81.22,34.95],[81.45,32.91],[84.14,29.4],[86.89,31.02],[90.9,29.78],[93.88,31.31],[94.47,34.81],[94.63,37.76],[91.28,40.99],[88.0,41.0],[83.99,41.11],[82.27,38.45],[80.86,35.31],[83.66,21.99],[82.79,20.66],[84.81,18.55],[87.31,18.39],[89.93,18.6],[91.88,20.58],[93.04,22.57],[91.7,24.58],[89.7,26.21],[87.82,26.71],[84.57,26.94],[83.8,24.63],[83.74,22.99]]],["h","MLLLCCLLLCCLz",[[102.77,16.88],[103.81,42.67],[106.36,43.65],[106.86,31.15],[106.54,28.7],[109.03,25.56],[110.93,26.34],[116.12,25.08],[116.75,27.71],[116.56,31.74],[116.71,42.23],[119.42,42.45],[119.61,30.9],[118.38,26.47],[117.5,22.0],[112.71,23.52],[108.44,22.82],[106.65,23.79],[106.33,26.86],[105.37,16.03]]],["S","MCCCCCCLCCCCCCz",[[12.29,37.18],[14.81,41.52],[18.49,43.61],[23.21,43.73],[27.98,43.86],[34.23,40.94],[33.18,34.99],[33.6,30.11],[27.85,28.24],[22.64,27.45],[19.45,27.07],[16.07,26.5],[15.88,23.61],[16.84,19.2],[20.34,18.94],[21.8,19.61],[24.75,18.83],[28.39,18.93],[28.15,21.93],[31.81,20.55],[29.43,17.6],[27.0,15.72],[23.22,15.64],[17.38,16.52],[13.61,18.28],[13.67,22.66],[13.52,29.24],[18.44,30.15],[22.27,30.03],[27.56,32.2],[28.45,33.34],[29.92,36.16],[29.5,37.79],[25.79,41.07],[22.48,40.35],[19.75,40.48],[17.94,38.97],[15.93,36.05]]],["D","MLCCLzMLCCLz",[[38.71,43.11],[46.12,43.0],[53.63,43.08],[59.03,39.45],[60.07,29.9],[58.89,19.55],[54.55,15.8],[45.49,15.52],[37.13,16.61],[41.38,19.14],[45.84,20.11],[51.46,19.67],[55.34,20.14],[56.32,29.02],[55.25,38.07],[50.52,39.23],[44.79,38.71],[42.08,40.24]]],["Y","MLLLLLLLLz",[[61.47,17.0],[71.2,32.41],[71.87,42.71],[75.01,43.61],[74.62,32.8],[84.17,16.92],[81.89,15.39],[73.75,28.49],[65.67,17.11]]],["Y","MLLLLLLLLz",[[86.29,17.12],[96.01,32.05],[95.34,42.09],[100.2,43.53],[98.81,32.29],[108.5,16.7],[104.4,17.0],[97.73,29.81],[89.17,15.49]]],["P","MLLLCCLzMCCLLz",[[112.49,43.61],[116.94,42.69],[116.55,31.3],[121.09,32.29],[127.02,32.8],[131.6,29.86],[132.32,23.67],[131.03,17.32],[126.99,16.56],[119.92,16.87],[112.54,15.28],[121.17,19.66],[124.38,19.92],[128.27,19.32],[127.81,23.33],[127.6,27.64],[124.14,28.66],[121.44,28.55],[115.37,28.39],[115.77,19.59]]],["n","MLLLCCLLLCCLz",[[13.12,23.6],[13.0,43.6],[17.42,42.58],[16.84,31.3],[17.34,27.14],[19.68,25.46],[22.32,25.06],[26.57,25.74],[26.23,28.73],[27.17,31.75],[26.49,43.66],[30.35,42.86],[29.18,30.81],[30.64,25.54],[28.68,22.19],[22.61,21.72],[20.89,23.35],[17.85,24.38],[16.28,26.86],[15.84,23.21]]],["d","MCLLCLLLCCCzMCCCCz",[[42.47,43.19],[45.37,42.39],[48.49,41.46],[49.66,39.83],[49.67,42.08],[53.82,43.61],[51.95,39.84],[53.55,36.18],[52.05,35.54],[53.38,16.85],[49.53,17.02],[49.22,25.79],[47.37,24.52],[46.22,22.92],[43.82,21.75],[38.42,22.29],[34.3,25.68],[34.25,33.86],[34.81,39.71],[39.01,43.88],[42.07,42.85],[43.07,25.64],[47.22,24.84],[50.17,27.48],[50.2,32.07],[49.29,37.66],[46.32,40.27],[44.76,40.12],[41.33,41.14],[38.95,38.61],[38.4,32.1],[38.17,27.68],[40.54,25.41],[43.59,24.62]]],["Z","MLLLLLLLLLz",[[56.76,41.85],[77.97,43.06],[78.45,38.75],[62.18,39.28],[77.91,20.18],[77.94,17.09],[58.47,16.13],[58.2,20.23],[73.1,18.48],[56.61,38.71]]],["a","MCLLCLCCLCCCCzMLCCCz",[[87.25,42.53],[92.41,44.07],[93.93,42.87],[94.07,39.21],[96.08,43.75],[99.58,42.05],[98.77,41.67],[98.65,39.47],[98.01,36.03],[98.37,29.73],[98.21,25.48],[95.65,21.84],[89.16,23.54],[85.7,21.95],[83.22,24.62],[82.7,27.55],[85.12,28.16],[87.02,25.91],[86.84,25.66],[91.01,26.14],[94.19,25.81],[94.92,27.92],[95.52,31.01],[86.0,30.52],[81.6,33.52],[81.06,38.11],[80.9,40.67],[84.1,43.21],[88.16,44.05],[95.55,33.75],[95.45,33.52],[95.31,38.51],[91.57,40.47],[89.56,40.37],[87.21,40.86],[85.59,40.11],[85.7,38.16],[84.06,35.63],[87.92,34.32],[94.12,32.95]]],["S","MCCCCCCLCCCCCCz",[[102.67,36.18],[103.59,41.34],[107.48,44.04],[111.92,44.29],[118.7,43.29],[123.23,39.91],[123.59,34.99],[122.16,30.63],[116.99,28.29],[113.32,27.49],[110.29,27.43],[105.6,25.14],[107.41,23.11],[107.17,20.23],[108.58,18.79],[111.97,19.52],[115.13,18.81],[116.28,20.16],[118.34,21.05],[122.63,20.61],[119.43,18.03],[115.94,15.52],[113.31,15.92],[106.52,15.99],[102.99,17.55],[103.37,23.03],[101.97,28.83],[108.09,30.43],[111.18,30.44],[117.28,31.97],[119.99,33.3],[119.67,35.31],[118.19,39.15],[115.82,39.78],[112.02,39.97],[109.54,40.78],[106.62,37.87],[105.42,36.74]]],["r","MLLLCLCLz",[[13.42,22.88],[13.88,42.72],[17.87,42.36],[17.2,34.56],[16.21,29.48],[19.3,26.05],[25.3,27.07],[23.61,23.54],[21.77,22.65],[19.54,23.93],[17.31,26.28],[17.11,23.7]]],["7","MLLLLLLz",[[28.82,42.74],[31.73,43.4],[43.8,19.43],[43.3,15.13],[24.72,15.63],[24.94,19.42],[40.35,18.59]]],["5","MCCCCLLLLLLCCCCz",[[46.72,36.79],[48.05,40.7],[50.26,42.67],[55.87,43.6],[60.76,42.89],[65.77,40.75],[66.09,33.9],[65.33,27.68],[61.92,23.86],[57.09,25.21],[55.26,24.65],[52.02,25.96],[50.41,26.82],[52.02,19.69],[64.21,19.75],[65.01,16.27],[48.94,16.58],[47.3,29.55],[51.92,31.37],[51.03,29.88],[53.75,26.95],[55.78,28.36],[58.83,28.29],[63.14,30.44],[62.84,33.08],[62.67,37.92],[58.61,39.58],[56.21,41.27],[52.57,40.92],[51.29,39.07],[51.01,36.02]]],["N","MLLLLLLLLLz",[[71.27,16.17],[71.76,43.62],[75.28,43.63],[74.57,20.66],[87.08,43.31],[93.55,43.33],[92.02,16.27],[88.43,15.78],[88.93,38.36],[77.09,16.1]]],["Z","MLLLLLLLLLz",[[98.44,42.21],[117.45,42.29],[118.5,38.96],[101.73,39.27],[116.94,18.72],[117.28,16.11],[99.19,15.13],[98.56,19.77],[112.64,19.21],[97.05,38.62]]],["f","MLLLLLLLLCLLLCLLz",[[11.16,26.03],[14.13,26.59],[15.7,42.73],[17.81,43.6],[18.37,25.07],[22.89,25.6],[22.33,22.93],[18.2,22.4],[18.7,20.19],[18.87,17.3],[19.13,18.08],[20.89,18.18],[21.74,16.96],[22.25,13.84],[21.15,13.93],[15.07,15.17],[15.9,15.65],[15.87,19.36],[14.47,22.13],[11.43,23.44]]],["t","MLLLCLLLCLLLLLLLz",[[25.18,22.59],[23.82,26.43],[28.12,25.96],[27.41,37.41],[27.78,41.44],[28.7,43.81],[32.12,42.01],[35.79,42.76],[35.62,39.31],[33.62,40.1],[30.15,39.13],[31.85,39.08],[30.12,38.2],[30.93,24.88],[34.83,25.24],[35.69,23.26],[30.32,22.11],[30.36,17.9],[27.66,18.78],[26.82,23.02]]],["f","MLLLLLLLLCLLLCLLz",[[37.71,24.96],[40.42,26.11],[40.47,42.11],[43.45,43.62],[43.42,25.67],[47.33,24.76],[47.35,23.61],[44.09,23.69],[43.42,20.86],[44.31,18.61],[43.34,17.05],[46.27,17.05],[47.4,18.4],[48.45,14.33],[46.45,14.69],[42.1,13.64],[39.57,15.55],[40.87,20.83],[40.55,22.46],[37.61,23.9]]],["p","MLLLCCCCLzMCCCCz",[[51.78,23.2],[52.14,48.32],[54.07,50.08],[54.74,39.59],[55.93,41.67],[57.52,43.52],[60.64,42.89],[65.68,43.42],[69.73,38.97],[69.83,33.15],[69.62,25.44],[64.97,23.3],[61.57,22.13],[59.19,23.6],[55.31,24.62],[54.51,25.36],[53.33,23.69],[54.42,33.11],[55.03,28.74],[56.7,25.31],[60.77,25.42],[64.95,25.62],[66.09,27.94],[67.04,33.64],[67.07,37.12],[63.98,40.18],[61.15,39.9],[57.4,40.58],[55.1,38.6],[54.83,33.62]]],["w","MLLLLLLLLLLLLz",[[78.13,42.67],[79.88,42.99],[83.76,27.84],[88.83,42.35],[91.03,43.45],[98.63,23.31],[94.94,22.12],[91.18,38.48],[85.33,22.96],[82.57,22.46],[78.49,36.91],[74.12,23.7],[71.05,23.77]]],["9","MCCLCCCCCzMCCCCz",[[23.19,34.02],[24.35,34.43],[25.21,35.6],[24.42,34.99],[23.21,37.59],[18.56,42.86],[19.46,42.66],[23.48,43.24],[28.6,37.49],[31.68,29.28],[32.05,28.45],[32.36,26.96],[33.03,26.5],[31.59,25.57],[32.33,19.01],[27.89,15.07],[22.25,16.25],[18.16,14.86],[12.51,19.43],[12.61,25.84],[13.79,30.93],[17.95,35.34],[22.69,35.52],[22.19,19.73],[26.39,19.74],[28.61,21.31],[28.62,25.23],[30.03,28.3],[26.54,31.75],[23.08,31.15],[20.38,31.42],[16.46,28.8],[17.62,25.84],[16.57,22.22],[19.86,18.7],[23.25,19.45]]],["p","MLLLCCCCLzMCCCCz",[[38.16,23.76],[37.37,50.11],[41.38,49.83],[41.59,40.63],[42.07,41.37],[43.7,43.47],[48.19,42.46],[52.97,43.58],[56.74,39.34],[56.07,32.72],[56.39,26.86],[52.86,22.01],[47.31,21.71],[45.16,22.76],[42.27,23.89],[40.43,25.49],[39.53,23.09],[41.03,32.71],[40.39,27.32],[43.63,26.16],[47.51,25.88],[49.04,25.96],[52.04,28.75],[52.81,33.64],[53.0,38.19],[50.72,39.92],[47.23,40.01],[42.25,39.46],[41.93,37.03],[41.04,33.28]]],["Y","MLLLLLLLLz",[[58.75,15.55],[67.4,33.41],[66.66,43.77],[71.14,42.43],[71.46,32.7],[80.83,16.78],[77.27,16.56],[69.33,28.07],[62.5,15.54]]],["c","MCLCCCCLCCCz",[[92.69,43.65],[95.14,42.44],[98.93,41.96],[100.21,39.75],[96.74,38.56],[96.15,39.25],[94.17,39.44],[92.24,39.48],[90.09,40.8],[86.04,37.03],[86.87,32.79],[86.21,27.9],[88.78,25.14],[91.84,24.66],[94.34,24.79],[96.72,27.66],[96.48,28.8],[99.7,27.87],[98.46,25.39],[96.11,22.96],[92.24,21.86],[86.75,22.66],[83.39,26.17],[82.33,32.79],[82.55,39.31],[87.07,43.73],[92.63,43.67]]],["h","MLLLCCLLLCCLz",[[104.23,15.87],[103.8,43.4],[108.1,42.71],[107.44,32.24],[107.34,27.47],[108.6,25.65],[112.17,25.82],[116.94,25.85],[117.46,27.38],[116.49,31.52],[117.42,43.0],[121.16,43.55],[120.91,29.72],[119.53,26.57],[119.07,23.43],[113.44,21.99],[110.04,22.93],[108.09,25.11],[107.59,26.22],[106.61,15.32]]],["F","MLLLLLLLLLz",[[-7.61,15.27],[-8.73,42.07],[-5.36,41.86],[-5.72,29.98],[9.33,30.29],[9.11,26.62],[-4.53,27.15],[-4.49,19.67],[8.83,18.62],[9.15,16.96]]],["M","MLLLLLLLLLLLLz",[[-13.2,15.36],[-13.93,43.66],[-9.44,43.2],[-9.83,19.19],[-2.21,43.65],[1.62,42.14],[10.04,19.65],[10.37,42.73],[13.81,42.91],[13.32,15.29],[6.66,15.19],[-0.24,38.16],[-6.96,16.1]]],["g","MCLCCCLCCCLLLCCCzMCCCCz",[[-2.05,41.54],[1.55,43.42],[3.59,40.37],[4.35,39.7],[4.72,42.3],[5.95,45.76],[3.96,45.86],[1.84,47.52],[0.72,48.0],[0.08,46.93],[-0.02,47.31],[-1.86,47.67],[-3.93,47.6],[-5.04,45.12],[-8.96,46.84],[-7.39,49.51],[-4.2,51.21],[0.34,51.43],[0.74,50.04],[1.68,49.64],[3.13,49.65],[9.11,48.18],[7.7,44.03],[7.68,41.71],[7.5,22.51],[5.21,23.19],[4.11,26.59],[3.31,24.53],[1.89,23.25],[-1.31,22.92],[-5.06,22.85],[-9.08,25.98],[-9.66,32.21],[-9.18,38.8],[-5.83,42.42],[-1.64,43.06],[-0.06,26.53],[3.33,25.03],[4.94,26.61],[4.95,32.42],[5.42,37.46],[2.6,40.18],[0.25,40.04],[-3.5,39.49],[-5.89,36.22],[-6.16,32.66],[-5.52,28.09],[-4.0,25.98],[-0.29,25.78]]],["T","MLLLLLLLz",[[-10.86,20.0],[-0.6,19.55],[-2.23,43.34],[1.24,42.8],[1.82,20.21],[11.59,19.6],[10.28,15.97],[-11.24,16.46]]],["s","MCCCCCLCCCCCz",[[-7.59,37.44],[-7.45,40.8],[-3.07,43.45],[-0.83,43.17],[4.4,42.51],[8.54,40.65],[8.71,37.36],[8.61,28.9],[-4.58,33.47],[-3.83,27.13],[-4.06,26.65],[-2.56,24.57],[-0.96,25.64],[2.23,25.75],[3.67,25.81],[4.25,28.79],[6.45,26.36],[6.29,23.15],[2.93,22.62],[-0.11,23.12],[-3.61,22.79],[-6.97,23.77],[-8.84,28.75],[-7.55,36.77],[4.04,31.68],[4.02,37.2],[4.87,38.54],[3.28,39.94],[0.12,39.91],[-1.68,39.67],[-4.18,39.4],[-4.54,36.85]]],["2","MLLCCCLCCCLz",[[8.93,43.33],[8.18,39.7],[-5.1,40.04],[2.59,35.3],[7.64,28.04],[7.76,21.93],[8.56,17.98],[3.72,15.59],[0.58,14.81],[-5.02,15.37],[-9.06,17.63],[-9.5,21.01],[-6.14,22.77],[-5.14,19.32],[-2.35,18.41],[-1.11,18.06],[3.47,18.68],[4.89,19.89],[5.06,22.49],[3.72,27.86],[-1.1,32.26],[-10.99,39.82],[-9.57,43.45]]],["U","MCLLLCCLLLCz",[[0.28,42.6],[7.33,42.87],[10.27,39.59],[11.84,31.47],[10.34,15.53],[6.85,15.28],[6.3,31.76],[6.28,37.46],[4.72,40.51],[1.13,40.98],[-5.32,39.16],[-6.25,37.72],[-6.28,32.37],[-7.73,17.0],[-9.63,17.0],[-11.35,32.48],[-11.27,39.64],[-6.91,43.17],[-0.61,43.25]]]]""")


def upisi_dnevnik(poruka):
    try:
        if os.path.exists(DNEVNIK_PATH) and os.path.getsize(DNEVNIK_PATH) > 2_000_000:
            with open(DNEVNIK_PATH, encoding="utf-8", errors="replace") as f:
                rep = f.read()[-1_000_000:]
            with open(DNEVNIK_PATH, "w", encoding="utf-8") as f:
                f.write(rep)
        with open(DNEVNIK_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), poruka))
    except OSError:
        pass


def sada():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M")


_AZBUKA = {ch: i for i, ch in enumerate("АБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ")}


def srpski_kljuc(tekst):
    return [200 + _AZBUKA[ch] if ch in _AZBUKA else (ord(ch) if ord(ch) < 128 else 1000 + ord(ch))
            for ch in (tekst or "").upper()]


def broj_kljuc(broj):
    """10383/2 -> (10383, 2) za sortiranje."""
    d = [int(x) for x in re.findall(r"\d+", broj or "")]
    return d + [0] * (2 - len(d))


_CIR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e", "ж": "z", "з": "z", "и": "i",
        "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "ћ": "c", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "c", "џ": "dz", "ш": "s"}
_CIR_TAB = str.maketrans(_CIR)


def lat(t):
    """Za pretragu: bez obzira na pismo i kvacice."""
    t = (t or "").lower().translate(_CIR_TAB).replace("đ", "dj")
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def cist(t):
    """HTML celija -> tekst."""
    t = re.sub(r"<br\s*/?>", " ", t or "", flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t).replace("\xa0", " ")
    return " ".join(t.split())


BROJ_RE = re.compile(r"^[0-9]{1,6}(/[0-9]{1,3})?$")    # isti format koji trazi sajt


def raspakuj_brojeve(tekst):
    """'10383, 10384/1 100-103' -> ['10383', '10384/1', '100', '101', '102', '103'], plus lista neispravnih."""
    brojevi, lose = [], []
    for deo in re.split(r"[\s,;]+", tekst or ""):
        if not deo:
            continue
        m = re.match(r"^(\d{1,6})-(\d{1,6})$", deo)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b and b - a <= 500:
                brojevi.extend(str(x) for x in range(a, b + 1))
            else:
                lose.append(deo)
        elif BROJ_RE.match(deo):
            brojevi.append(deo)
        else:
            lose.append(deo)
    return list(dict.fromkeys(brojevi)), lose


def raspakuj_kucne(tekst):
    """'5, 7 12a' -> ['5', '7', '12a'] plus lista neispravnih (sajt prima najvise 5 znakova)."""
    brojevi, lose = [], []
    for deo in re.split(r"[\s,;]+", tekst or ""):
        if deo:
            (brojevi if len(deo) <= 5 else lose).append(deo)
    return list(dict.fromkeys(brojevi)), lose


def kratka_ulica(naziv):
    """'БЕОГРАД (ЧУКАРИЦА), ГРУЈЕ МИШКОВИЋА' -> 'ГРУЈЕ МИШКОВИЋА' (naselje je vec u nazivu opstine)."""
    return naziv.split(", ", 1)[1].strip() if ", " in (naziv or "") else (naziv or "").strip()


# ----------------------------------------------------------------------
# SVG captcha
# ----------------------------------------------------------------------
_TOK = re.compile(r"[MLCZz]|-?\d+(?:\.\d+)?")


def _putanja(d):
    """'M x,y L x,y C ... z' -> (potpis komandi, lista tacaka, podputanje kao poligoni za crtanje)."""
    toks = _TOK.findall(d)
    potpis, tacke, poligoni, tren = [], [], [], []
    i, kom = 0, None
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            kom = t
            potpis.append(t)
            i += 1
            if t in "Zz":
                if tren:
                    poligoni.append(tren)
                tren = []
            continue
        if kom == "M":
            x, y = float(toks[i]), float(toks[i + 1])
            i += 2
            if tren:
                poligoni.append(tren)
            tren = [(x, y)]
            tacke.append((x, y))
        elif kom == "L":
            x, y = float(toks[i]), float(toks[i + 1])
            i += 2
            tren.append((x, y))
            tacke.append((x, y))
        elif kom == "C":
            v = [float(z) for z in toks[i:i + 6]]
            i += 6
            p0 = tren[-1] if tren else (v[4], v[5])
            for k in range(1, 9):                       # kriva -> 8 duzi
                s = k / 8.0
                a, b, c, e = (1 - s) ** 3, 3 * s * (1 - s) ** 2, 3 * s * s * (1 - s), s ** 3
                tren.append((a * p0[0] + b * v[0] + c * v[2] + e * v[4], a * p0[1] + b * v[1] + c * v[3] + e * v[5]))
            tacke.extend([(v[0], v[1]), (v[2], v[3]), (v[4], v[5])])
        else:
            i += 1
    if tren:
        poligoni.append(tren)
    return "".join(potpis), tacke, poligoni


def parsiraj_svg(svg):
    """Vraca {'sum': [poligonske linije], 'znaci': [{'potpis','tacke','poligoni'}]} ili None."""
    if not svg:
        return None
    m = re.search(r'<g fill="gray">(.*?)</g>', svg, re.S)
    if not m:
        return None
    znaci = []
    for d in re.findall(r'd="([^"]*)"', m.group(1)):
        potpis, tacke, poligoni = _putanja(d)
        znaci.append({"potpis": potpis, "tacke": tacke, "poligoni": poligoni})
    sum_ = []
    ms = re.search(r'<g stroke="silver"[^>]*>(.*?)</g>', svg, re.S)
    if ms:
        for d in re.findall(r'd="([^"]*)"', ms.group(1)):
            sum_.extend(_putanja(d)[2])
    return {"sum": sum_, "znaci": znaci}


def _unutra(t, poly):
    x, y = t
    ok = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            ok = not ok
    return ok


def rupe(poligoni):
    """Indeksi podputanja koje su rupe (leze unutar druge podputanje, npr. unutrasnjost slova o)."""
    r = set()
    for i, p in enumerate(poligoni):
        cx = sum(t[0] for t in p) / len(p)
        cy = sum(t[1] for t in p) / len(p)
        if any(j != i and _unutra((cx, cy), q) and _unutra(p[0], q) for j, q in enumerate(poligoni)):
            r.add(i)
    return r


def _norm_tacke(tacke):
    """Poravnanje po srednjem x (slova su na razlicitim mestima); y ostaje (razlika malo/veliko slovo)."""
    sx = sum(t[0] for t in tacke) / len(tacke)
    return [(x - sx, y) for x, y in tacke]


def _razlika(a, b):
    return max(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 for p, q in zip(a, b))


class CitacCaptche:
    """Svaki znak je zaseban vektorski oblik; isti znak uvek ima isti niz komandi (M, L, C, z),
    a tacke se pomeraju najvise par piksela. Znak se prepoznaje poredjenjem sa naucenim uzorcima."""
    PRAG = 4.5          # najveca razlika tacaka (px) da bi znak vazio kao isti
    RAZMAK = 2.5        # koliko drugi najblizi znak mora da bude dalje
    PO_ZNAKU = 12       # koliko uzoraka se cuva po znaku

    def __init__(self, putanja=UZORCI_PATH):
        self.putanja = putanja
        self.uzorci = {}        # potpis -> [(znak, norm_tacke)]
        self._lock = threading.Lock()
        for z, potpis, tacke in SEME_CAPTCHE:
            self._dodaj(z, potpis, [tuple(t) for t in tacke], cuvaj=False)
        try:
            with open(putanja, encoding="utf-8") as f:
                for u in json.load(f):
                    self._dodaj(u["z"], u["s"], [tuple(t) for t in u["p"]], cuvaj=False)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _dodaj(self, znak, potpis, tacke, cuvaj=True):
        lista = self.uzorci.setdefault(potpis, [])
        n = _norm_tacke(tacke)
        if sum(1 for z, _ in lista if z == znak) >= self.PO_ZNAKU:
            return False
        lista.append((znak, n))
        return True

    def poznati_znaci(self):
        return sorted({z for lista in self.uzorci.values() for z, _ in lista})

    def procitaj_znak(self, g):
        kandidati = self.uzorci.get(g["potpis"])
        if not kandidati:
            return None, None
        n = _norm_tacke(g["tacke"])
        najbolji = {}
        for z, t in kandidati:
            if len(t) != len(n):
                continue
            d = _razlika(n, t)
            if d < najbolji.get(z, 1e9):
                najbolji[z] = d
        if not najbolji:
            return None, None
        red = sorted(najbolji.items(), key=lambda x: x[1])
        z, d = red[0]
        drugi = red[1][1] if len(red) > 1 else 1e9
        if d <= self.PRAG and drugi - d >= self.RAZMAK:
            return z, d
        return None, d

    def procitaj(self, svg):
        """(tekst, siguran). tekst ima '?' na mestu znaka koji nije prepoznat."""
        p = parsiraj_svg(svg)
        if not p or not p["znaci"]:
            return None, False
        with self._lock:
            znaci = [self.procitaj_znak(g)[0] for g in p["znaci"]]
        tekst = "".join(z or "?" for z in znaci)
        return tekst, all(znaci) and len(znaci) >= 4

    def nauci(self, svg, tekst):
        """Uci iz captche koju je sajt prihvatio. Vraca broj novih uzoraka."""
        p = parsiraj_svg(svg)
        if not p or len(p["znaci"]) != len(tekst):
            return 0
        novih = 0
        with self._lock:
            for g, z in zip(p["znaci"], tekst):
                postoji = self.procitaj_znak(g)[0]
                if postoji == z:
                    continue                 # vec ga zna
                if self._dodaj(z, g["potpis"], g["tacke"]):
                    novih += 1
            if novih:
                self._sacuvaj()
        return novih

    def _sacuvaj(self):
        """Cuvaju se samo nauceni uzorci (seme je ugradjeno u program)."""
        ugradjeni = Counter((z, s) for z, s, _ in SEME_CAPTCHE)
        vidjeno, izlaz = Counter(), []
        for s, lista in self.uzorci.items():
            for z, t in lista:
                vidjeno[(z, s)] += 1
                if vidjeno[(z, s)] <= ugradjeni.get((z, s), 0):
                    continue
                izlaz.append({"z": z, "s": s, "p": [[round(x, 2), round(y, 2)] for x, y in t]})
        try:
            tmp = self.putanja + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(izlaz, f, separators=(",", ":"))
            os.replace(tmp, self.putanja)
        except OSError:
            upisi_dnevnik("Uzorci captche nisu sacuvani: " + traceback.format_exc())


# ----------------------------------------------------------------------
# Sajt (ASP.NET WebForms + UpdatePanel)
# ----------------------------------------------------------------------
class SajtGreska(Exception):
    pass


class SajtOgranicenje(SajtGreska):
    """HTTP 429/503 - sajt trazi pauzu."""


def skrivena_polja(t):
    polja = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', t or ""):
        tag = m.group(0)
        n = re.search(r'name="([^"]*)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            polja[htmlmod.unescape(n.group(1))] = htmlmod.unescape(v.group(1)) if v else ""
    return polja


def parsiraj_delta(t):
    """Odgovor UpdatePanel-a: 'duzina|tip|id|sadrzaj|' ponovljeno. Vraca listu (tip, id, sadrzaj)."""
    delovi, i, n = [], 0, len(t or "")
    while i < n:
        j = t.find("|", i)
        if j < 0:
            break
        try:
            duz = int(t[i:j])
        except ValueError:
            raise SajtGreska("neocekivan odgovor sajta: %r" % t[i:i + 80])
        k = t.find("|", j + 1)
        m = t.find("|", k + 1)
        if k < 0 or m < 0:
            break
        delovi.append((t[j + 1:k], t[k + 1:m], t[m + 1:m + 1 + duz]))
        i = m + 1 + duz + 1
    return delovi


def nadji_svg(t):
    m = re.search(r"<svg.*?</svg>", t or "", re.S)
    return m.group(0) if m else None


def poruke_stranice(t):
    poruke = [cist(x) for x in re.findall(r"<li>(.*?)</li>", t or "", re.S)]
    for x in re.findall(r'<p class="err-warning">(.*?)</p>', t or "", re.S):
        if cist(x):
            poruke.append(cist(x))
    return [p for p in poruke if p]


def tabela(t, gid):
    """GridView -> lista redova; red = {'celije': [...], 'dugme': ime image-dugmeta, 'nep': nepID, 'izabran': bool}."""
    m = re.search(r'<table[^>]*id="ContentPlaceHolder1_%s".*?</table>' % gid, t or "", re.S)
    if not m:
        return None
    redovi = []
    for tr in re.finditer(r"<tr([^>]*)>(.*?)</tr>", m.group(0), re.S):
        atr, sadrzaj = tr.group(1), tr.group(2)
        if 'class="header"' in atr or "<th" in sadrzaj:
            continue
        celije_html = re.findall(r"<td[^>]*>(.*?)</td>", sadrzaj, re.S)
        celije = []
        for c in celije_html:
            tx = cist(c)
            if not tx:
                ti = re.search(r'<img[^>]*title="([^"]*)"', c)
                if ti and "Селекција" not in ti.group(1) and "Подаци о" not in ti.group(1):
                    tx = htmlmod.unescape(ti.group(1))
            celije.append(tx)
        dugme = re.search(r'<input type="image" name="([^"]*)"', sadrzaj)
        nep = re.search(r"nepID=([^'\"]*)", sadrzaj)
        redovi.append({"celije": celije, "dugme": dugme.group(1) if dugme else None,
                       "nep": htmlmod.unescape(nep.group(1)) if nep else None,
                       "izabran": 'class="selected"' in atr})
    return redovi


def parsiraj_rezultat(t):
    """FindParcelaResult.aspx -> recnik sa parcelom, objektima i posebnim delovima (izabranog dela/objekta)."""
    def lbl(ime):
        m = re.search(r'id="ContentPlaceHolder1_ucOpstinaKoInfo_%s">(.*?)</span>' % ime, t or "", re.S)
        return cist(m.group(1)) if m else ""

    g1 = tabela(t, "GridView1")
    if g1 is None:
        return None
    delovi, ukupno = [], ""
    for r in g1:
        c = r["celije"]
        if any("∑" in x for x in c):
            ukupno = next((x.replace("∑:", "").strip() for x in c if "∑" in x), "")
            continue
        if len(c) < 8:
            continue
        delovi.append({"broj": c[2], "deo": c[3], "povrsina": c[4], "ulica": c[5], "nacin": c[6], "vrsta": c[7],
                       "evidencija": c[1], "dugme": r["dugme"], "nep": r["nep"], "izabran": r["izabran"]})
    objekti = []
    for r in tabela(t, "GridView2") or []:
        c = r["celije"]
        if len(c) < 7:
            continue
        objekti.append({"ulica": c[1], "kbr": c[2], "kpbr": c[3], "povrsina": c[4], "nacin": c[5], "status": c[6],
                        "dugme": r["dugme"], "nep": r["nep"], "izabran": r["izabran"]})
    posebni = []
    for r in tabela(t, "GridView3") or []:
        c = r["celije"]
        if len(c) < 6:
            continue
        posebni.append({"evid": c[0], "ulaz": c[1], "stan": c[2], "podbr": c[3], "nacin": c[4], "povrsina": c[5],
                        "nep": r["nep"]})
    return {"opstina": lbl("lblOpstinaNaziv"), "ko": lbl("lblKoNaziv"), "delovi": delovi, "ukupno": ukupno,
            "objekti": objekti, "posebni": posebni, "poruke": poruke_stranice(t)}


def parsiraj_adresu(t):
    """FindAdresaResult.aspx (tabela 'Parcele') -> [{'kbr','ko','broj','deo','povrsina','vrsta','nacin'}]:
    delovi parcela na toj adresi. None ako stranica nije rezultat pretrage po adresi."""
    redovi = tabela(t, "Parcele")
    if redovi is None:
        return None
    out = []
    for r in redovi:
        c = r["celije"]
        if len(c) < 8 or not c[3]:
            continue
        out.append({"kbr": c[1], "ko": c[2], "broj": c[3], "deo": c[4], "povrsina": c[5], "vrsta": c[6],
                    "nacin": c[7]})
    return out


# Polja koja se menjaju bez promene na nepokretnosti (azurnost baze, sifre) - ne prate se.
NEP_IZOSTAVI = ("Датум ажурности", "Матични број општине", "Матични број катастарске општине", "Служба")
_NEP_TOK = re.compile(
    r'<td class="print_form_item_h2?"[^>]*>(?P<h>.*?)</td>'
    r'|<tbody class="print_group">'
    r'|<tr>\s*<td class="print_form_item_v"[^>]*>(?P<k>.*?)</td>\s*<td class="print_form_item_v"[^>]*>(?P<v>.*?)</td>\s*</tr>'
    r'|\*\*\*(?P<n>[^*<]+)\*\*\*', re.S)


def parsiraj_nepokretnost(t, sve=False):
    """Stranica 'Podaci o nepokretnosti' (izvod iz baze katastra) ->
    [{'naslov': 'Имаоци права на парцели - Б лист', 'zapisi': [[(polje, vrednost), ...], ...], 'tekst': [...]}]
    ili None ako stranica nije u poznatom obliku."""
    m = re.search(r'<p class="big_head">.*', t or "", re.S)
    if not m:
        return None
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", m.group(0), flags=re.S | re.I)
    b = re.sub(r"<!--.*?-->", "", b, flags=re.S)
    sekcije, sek, novi_zapis = [], None, True
    for x in _NEP_TOK.finditer(b):
        if x.group("h") is not None:
            if "lblNepRefBr" in x.group("h"):
                continue
            naslov = cist(x.group("h"))
            if naslov:
                sek = {"naslov": naslov, "zapisi": [], "tekst": []}
                sekcije.append(sek)
                novi_zapis = True
        elif sek is None:
            continue
        elif x.group("n") is not None:
            sek["tekst"].append(" ".join(x.group("n").split()))
        elif x.group("k") is None:
            novi_zapis = True                      # <tbody class="print_group"> - novi zapis
        else:
            polje = cist(x.group("k")).rstrip(":").strip()
            vrednost = re.sub(r"\(\s*више информација\s*\)", "", cist(x.group("v"))).strip()
            if not polje or (polje in NEP_IZOSTAVI and not sve):
                continue
            if novi_zapis or not sek["zapisi"]:
                sek["zapisi"].append([])
                novi_zapis = False
            sek["zapisi"][-1].append((polje, vrednost))
    return sekcije or None


def redovi_nepokretnosti(sekcije):
    """Sekcije -> redovi teksta za snimak i poredjenje: '[sekcija] polje: vrednost; polje: vrednost'.
    Od stranice zgrade ili posebnog dela uzima se samo njen deo (2. ili 3. list), jer se podaci o parceli
    ponavljaju na svakoj stranici."""
    if not sekcije:
        return []
    pocetak = 0
    for i, s in enumerate(sekcije):
        if re.match(r"^\d+\.\s", s["naslov"]):
            pocetak = i
    redovi = []
    for s in sekcije[pocetak:]:
        if s["naslov"] == "Подаци о непокретности":
            continue
        for z in s["zapisi"]:
            polja = "; ".join("%s: %s" % (k, v) for k, v in z if v)
            if polja:
                redovi.append("[%s] %s" % (s["naslov"], polja))
        for tx in s["tekst"]:
            redovi.append("[%s] %s" % (s["naslov"], tx))
    return redovi


def iz_nepokretnosti(redovi, sekcija_pocinje, polja=("Назив", "Удео")):
    """Kratak izvod iz redova jedne sekcije, npr. vlasnici: 'ПЕТРОВИЋ ПЕТАР 1/2; ...'."""
    out = []
    for r in redovi or []:
        m = re.match(r"^\[([^\]]*)\]\s*(.*)$", r)
        if not m or not m.group(1).startswith(sekcija_pocinje):
            continue
        d = dict(p.split(": ", 1) for p in m.group(2).split("; ") if ": " in p)
        if d:
            out.append(" ".join(d[p] for p in polja if d.get(p)) or m.group(2))
        else:
            out.append(m.group(2))
    return "; ".join(out)


def vlasnici_tereti(snimak):
    """(vlasnici, tereti) parcele iz snimka; prazno ako podaci o nepokretnosti nisu ucitani."""
    redovi = ((snimak or {}).get("nepokretnost") or {}).get("parcela")
    if not redovi:
        return "", ""
    return (iz_nepokretnosti(redovi, "Имаоци права на парцели"),
            iz_nepokretnosti(redovi, "Терети на парцели", ("Опис",)))


def kratko_ime_nep(kljuc):
    """'poseban deo CARA DUSANA 200, ulaz 1, stan 5, evid. 7, СТАН' -> 'СТАН 5 (ЦАРА ДУШАНА 200)'."""
    m = re.match(r"^poseban deo (.*?), ulaz ([^,]*), stan ([^,]*), evid\. ([^,]*), (.*)$", kljuc)
    if m:
        obj, ulaz, stan, evid, nacin = (x.strip() for x in m.groups())
        return ("%s %s" % (nacin or "poseban deo", stan or evid)).strip() + ((" (%s)" % obj) if obj else "")
    return kljuc


def vlasnici_objekata(snimak):
    """Vlasnici zgrada i posebnih delova (stanova, garaza...) iz snimka, za tabelu pretrage i CSV."""
    out = []
    for kljuc, redovi in ((snimak or {}).get("nepokretnost") or {}).items():
        if kljuc == "parcela":
            continue
        v = iz_nepokretnosti(redovi, "Имаоци права на")
        if v:
            out.append("%s: %s" % (kratko_ime_nep(kljuc), v.replace("; ", ", ")))
    return "; ".join(out)


def grupisi_redove(redovi):
    """Redovi '[sekcija] polje: v; polje: v' -> [(sekcija, [zapis, ...])]; zapis je lista (polje, vrednost) ili tekst."""
    out = []
    for r in redovi or []:
        m = re.match(r"^\[([^\]]*)\]\s*(.*)$", r)
        sek, tx = (m.group(1), m.group(2)) if m else ("", r)
        if not out or out[-1][0] != sek:
            out.append((sek, []))
        delovi = tx.split("; ")
        if ": " not in delovi[0]:
            out[-1][1].append(tx)
            continue
        polja = []
        for d in delovi:
            if ": " in d:
                polja.append(d.split(": ", 1))
            else:
                polja[-1][1] += "; " + d          # vrednost koja i sama ima "; " (npr. naziv ulice)
        out[-1][1].append([(k, v) for k, v in polja])
    return out


def upisi_nepokretnost(t, naziv, redovi):
    """U tk.Text upisuje podatke jedne stavke (parcela, zgrada, poseban deo) pregledno, po sekcijama kao na sajtu."""
    t.tag_configure("naslov", font=("Segoe UI", 13, "bold"), spacing3=6)
    t.tag_configure("sekcija", font=("Segoe UI", 11, "bold"), foreground="#1f4e79", spacing1=10, spacing3=3)
    t.tag_configure("vlasnik", font=("Segoe UI", 10, "bold"))
    t.tag_configure("siv", foreground="#666")
    t.configure(state="normal")
    t.delete("1.0", "end")
    t.insert("end", naziv + "\n", "naslov")
    if not redovi:
        t.insert("end", "Podaci sa sajta za ovu stavku nisu učitani (uključi u meniju Alati učitavanje "
                        "vlasnika i ponovi pretragu).\n", "siv")
    for sek, zapisi in grupisi_redove(redovi):
        t.insert("end", sek + "\n", "sekcija")
        for z in zapisi:
            if isinstance(z, str):
                t.insert("end", "    " + z + "\n", "siv")
            elif "Имаоци права" in sek:
                d = dict(z)
                t.insert("end", "    • " + d.get("Назив", ""), "vlasnik")
                ost = [d.get(k) for k in ("Удео", "Врста права", "Облик својине") if d.get(k)]
                t.insert("end", ("   —   " + ", ".join(ost) if ost else "") + "\n")
            else:
                for k, v in z:
                    t.insert("end", "    %s: " % k, "siv")
                    t.insert("end", v + "\n")
                t.insert("end", "\n")
    t.configure(state="disabled")


def stablo_nepokretnosti(sn):
    """[(iid, roditelj, naziv, redovi, kljuc)] za prozor Detalji: parcela, pa zgrade, pa posebni delovi ispod svoje
    zgrade; kljuc = naziv podataka o nepokretnosti u snimku."""
    nep = dict((sn or {}).get("nepokretnost") or {})
    stavke = [("parcela", "", "Parcela (zemljište i vlasnici parcele)", nep.pop("parcela", []), "parcela")]
    objekti = {}
    for i, o in enumerate(sn.get("objekti", [])):
        kljuc = " ".join(("objekat %s %s %s" % (o[1], o[2], o[3])).split())
        k, n = kljuc, 2
        while k in objekti.values():
            k = "%s (%d)" % (kljuc, n)
            n += 1
        objekti["o%d" % i] = k
        naziv = "Zgrada %d: %s%s, %s m²" % (i + 1, ("%s %s" % (o[1], o[2])).strip(), (" / " + o[3]) if o[3] else "",
                                             o[4]) + ((" (%s)" % o[5].lower()) if o[5] else "")
        stavke.append(("o%d" % i, "", naziv, nep.pop(k, []), k))
    imena_obj = {iid: " ".join(("%s %s" % (o[1], o[2])).split()) for iid, o in
                 zip(("o%d" % i for i in range(len(sn.get("objekti", [])))), sn.get("objekti", []))}
    vidjeni = set()
    for j, x in enumerate(sn.get("posebni", [])):
        kljuc = " ".join(("poseban deo %s, ulaz %s, stan %s, evid. %s, %s" % (x[0], x[2], x[3], x[1], x[5])).split())
        k, n = kljuc, 2
        while k in vidjeni:
            k = "%s (%d)" % (kljuc, n)
            n += 1
        vidjeni.add(k)
        roditelj = next((iid for iid, ime in imena_obj.items() if ime == " ".join(x[0].split())), "")
        naziv = "%s %s%s, %s m²" % ((x[5] or "poseban deo").capitalize(), x[3] or x[1],
                                    (", ulaz %s" % x[2]) if x[2] else "", x[6])
        stavke.append(("p%d" % j, roditelj, naziv, nep.pop(k, []), k))
    for i, (k, redovi) in enumerate(nep.items()):          # sto se nije uparilo, ne sme da se izgubi
        stavke.append(("x%d" % i, "", k, redovi, k))
    return stavke


def prikaz_nepokretnosti(nep):
    """Za prozor Detalji: redovi grupisani po sekcijama."""
    delovi = []
    for kljuc, redovi in nep.items():
        delovi.append("=== %s ===" % kljuc)
        prethodna = None
        for r in redovi:
            m = re.match(r"^\[([^\]]*)\]\s*(.*)$", r)
            sek, tx = (m.group(1), m.group(2)) if m else ("", r)
            if sek != prethodna:
                delovi.append("\n%s" % sek)
                prethodna = sek
            delovi.append("    " + tx.replace("; ", "  |  "))
        delovi.append("")
    return "\n".join(delovi)


def tekst_nepokretnosti(t):
    """Stranica 'Podaci o nepokretnosti' -> redovi teksta. Poznat oblik stranice se cita po poljima;
    ako se oblik promeni, uzima se sav vidljiv tekst iz tabela (bez datuma izvoda)."""
    redovi = redovi_nepokretnosti(parsiraj_nepokretnost(t))
    if redovi:
        return redovi
    t = re.sub(r"<(script|style|head)[^>]*>.*?</\1>", " ", t or "", flags=re.S | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<input[^>]*>", " ", t, flags=re.I)
    t = re.sub(r"</t[dh]>", " | ", t, flags=re.I)
    t = re.sub(r"</(tr|p|div|h\d|li|caption|table)>|<br\s*/?>", "\n", t, flags=re.I)
    redovi = []
    d = dt.date.today()
    danas = ("%02d.%02d.%d" % (d.day, d.month, d.year), "%d.%d.%d." % (d.day, d.month, d.year))
    for red in cist_redove(t):
        if any(x in red for x in danas) or "Датум ажурности" in red:   # datum izvoda / azurnosti
            continue
        redovi.append(red)
    return redovi


def cist_redove(t):
    out = []
    for red in t.split("\n"):
        r = htmlmod.unescape(re.sub(r"<[^>]+>", " ", red)).replace("\xa0", " ")
        r = " ".join(r.split()).strip(" |")
        r = re.sub(r"(\s*\|\s*)+", " | ", r)
        if r and r != "|":
            out.append(r)
    return out


class Obrazac:
    def __init__(self, url, polja, svg):
        self.url, self.polja, self.svg = url, polja, svg


class Sajt:
    def __init__(self, base=BASE):
        self.base = base
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8"})
        self._pa = None          # skrivena polja stranice PublicAccess.aspx
        self.origin = base[:base.index("/", 8)] if base.count("/") > 2 else base

    def _odgovor(self, r):
        if r.status_code in (429, 503):
            raise SajtOgranicenje("sajt trazi pauzu (HTTP %d)" % r.status_code)
        if r.status_code >= 400:
            raise SajtGreska("HTTP %d" % r.status_code)
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "utf-8"
        return r.text

    def get(self, putanja, referer=None):
        h = {"Referer": referer} if referer else {}
        return self._odgovor(self.s.get(urllib.parse.urljoin(self.base, putanja), headers=h, timeout=45))

    def post(self, putanja, podaci, ajax=False, referer=None):
        url = urllib.parse.urljoin(self.base, putanja)
        h = {"Origin": self.origin, "Referer": referer or url,
             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        if ajax:
            h.update({"X-MicrosoftAjax": "Delta=true", "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"})
        return self._odgovor(self.s.post(url, data=urllib.parse.urlencode(podaci, encoding="utf-8"),
                                         headers=h, timeout=45))

    # --- opstine i katastarske opstine -----------------------------------
    def opstine(self):
        t = self.get("PublicAccess.aspx")
        self._pa = skrivena_polja(t)
        m = re.search(r"<select[^>]*dropOpstina.*?</select>", t, re.S)
        if not m:
            raise SajtGreska("na stranici nema spiska opstina")
        return [[int(v), cist(n)] for v, n in re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)', m.group(0))]

    def ko(self, opstina_id):
        if self._pa is None:
            self.opstine()
        p = "ctl00$ContentPlaceHolder1$getOpstinaKO$"
        podaci = dict(self._pa)
        podaci.update({p + "ToolkitScriptManager": p + "UpdatePanelKO|" + p + "dropOpstina",
                       "__EVENTTARGET": p + "dropOpstina", "__EVENTARGUMENT": "", "__LASTFOCUS": "",
                       p + "dropOpstina": str(opstina_id), "__ASYNCPOST": "true"})
        t = self.post("PublicAccess.aspx", podaci, ajax=True)
        sadrzaj = ""
        for tip, idd, s in parsiraj_delta(t):
            if tip == "hiddenField":
                self._pa[idd] = s
            elif tip == "updatePanel":
                sadrzaj += s
        ko = [[int(k), cist(n)] for k, n in re.findall(r'hLinkKo_\d+"[^>]*KoID=(\d+)">([^<]*)</a>', sadrzaj)]
        if not ko:
            raise SajtGreska("sajt nije vratio katastarske opstine")
        return ko

    # --- pretraga parcele -------------------------------------------------
    def otvori(self, ko_id):
        put = "FindParcela.aspx?KoID=%s" % ko_id
        t = self.get(put, referer=urllib.parse.urljoin(self.base, "PublicAccess.aspx"))
        svg = nadji_svg(t)
        if not svg:
            raise SajtGreska("stranica pretrage nema captchu (KoID %s)" % ko_id)
        return Obrazac(urllib.parse.urljoin(self.base, put), skrivena_polja(t), svg)

    def posalji(self, obr, broj, tekst):
        """('ok', html rezultata) | ('captcha', None) - obrazac dobija novu captchu | ('nema', poruka)."""
        p = "ctl00$ContentPlaceHolder1$"
        podaci = {p + "ctl00": p + "UpdatePanel1|" + p + "btnSubmit"}
        podaci.update(obr.polja)
        podaci.update({"__EVENTTARGET": "", "__EVENTARGUMENT": "", p + "txtBrParcele": broj,
                       p + "SVGCaptchaControl$CaptchaText": tekst, "__ASYNCPOST": "true", p + "btnSubmit": "Прикажи"})
        t = self.post(obr.url, podaci, ajax=True, referer=obr.url)
        return self._odgovor_obrasca(obr, t, "sajt nije vratio parcelu")

    def _odgovor_obrasca(self, obr, t, nema):
        """Odgovor na 'Прикажи' (parcela ili adresa): preusmerenje na rezultat, losa captcha ili poruka sajta."""
        delovi = parsiraj_delta(t)
        for tip, idd, s in delovi:
            if tip == "pageRedirect":
                cilj = urllib.parse.unquote(s)
                return "ok", self.get(cilj, referer=obr.url)
        sadrzaj = ""
        for tip, idd, s in delovi:
            if tip == "hiddenField":
                obr.polja[idd] = s
            elif tip == "updatePanel":
                sadrzaj += s
        svg = nadji_svg(sadrzaj)
        poruke = poruke_stranice(sadrzaj)
        if any("Неисправна комбинација" in x for x in poruke):
            if svg:
                obr.svg = svg
            return "captcha", None
        if svg:
            obr.svg = svg
        return "nema", "; ".join(x for x in poruke if "код са слике" not in x) or nema

    # --- pretraga po adresi (kao na eKatastru: opstina, ulica sa spiska sajta, kucni broj) ---------------
    def ulice(self, opstina_id, tekst, koliko=10):
        """Predlozi ulica sa sajta za upisan pocetak naziva (sajt trazi bar 2 slova, prima i latinicu):
        [(naziv, ID ulice)], npr. ('БЕОГРАД (ЧУКАРИЦА), ГРУЈЕ МИШКОВИЋА', '791113003725')."""
        put = urllib.parse.urljoin(self.base, "FindAdresa.aspx?OpstinaID=%s" % opstina_id)
        if getattr(self, "_ulice_za", None) != str(opstina_id):
            self.get(put, referer=urllib.parse.urljoin(self.base, "PublicAccess.aspx"))
            self._ulice_za = str(opstina_id)
        telo = json.dumps({"prefixText": tekst, "count": koliko, "contextKey": str(opstina_id)}, ensure_ascii=False)
        h = {"Origin": self.origin, "Referer": put, "Content-Type": "application/json; charset=UTF-8",
             "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"}
        t = self._odgovor(self.s.post(urllib.parse.urljoin(self.base, "FindAdresa.aspx/PretragaUlica"),
                                      data=telo.encode("utf-8"), headers=h, timeout=30))
        try:
            stavke = json.loads(t).get("d") or []
        except (ValueError, AttributeError):
            raise SajtGreska("spisak ulica nije u poznatom obliku")
        out = []
        for x in stavke:
            try:
                u = json.loads(x) if isinstance(x, str) else x
            except ValueError:
                continue
            naziv, uid = norm(u.get("First")), str(u.get("Second") or "").strip()
            if naziv and uid and uid != "-1":
                out.append((naziv, uid))
        return out

    def otvori_adresu(self, opstina_id):
        put = "FindAdresa.aspx?OpstinaID=%s" % opstina_id
        t = self.get(put, referer=urllib.parse.urljoin(self.base, "PublicAccess.aspx"))
        svg = nadji_svg(t)
        if not svg:
            raise SajtGreska("stranica pretrage po adresi nema captchu (opstina %s)" % opstina_id)
        self._ulice_za = str(opstina_id)
        return Obrazac(urllib.parse.urljoin(self.base, put), skrivena_polja(t), svg)

    def posalji_adresu(self, obr, ulica, ulica_id, kbr, tekst):
        """('ok', html FindAdresaResult) | ('captcha', None) | ('nema', poruka) - kao posalji()."""
        p = "ctl00$ContentPlaceHolder1$"
        a = p + "ucAdresa$"
        podaci = {p + "ToolkitScriptManager": p + "UpdatePanel1|" + p + "btnSubmit"}
        podaci.update(obr.polja)
        podaci.update({"__EVENTTARGET": "", "__EVENTARGUMENT": "", a + "txtUlica": ulica, a + "hdnUlicaID": ulica_id,
                       a + "txtKucniBroj": kbr, p + "SVGCaptchaControl$CaptchaText": tekst,
                       "hiddenInputToUpdateATBuffer_CommonToolkitScripts": "0", "__ASYNCPOST": "true",
                       p + "btnSubmit": "Прикажи"})
        t = self.post(obr.url, podaci, ajax=True, referer=obr.url)
        return self._odgovor_obrasca(obr, t, "sajt nije vratio parcelu za tu adresu")

    def izaberi(self, html_stranice, dugme):
        """Klik na 'Selekcija reda' u rezultatu (drugi deo parcele ili drugi objekat). Vraca novi HTML."""
        p = "ctl00$ContentPlaceHolder1$"
        podaci = {p + "ToolkitScriptManager1": p + "UpdatePanel1|" + dugme}
        podaci.update(skrivena_polja(html_stranice))
        podaci.update({"__EVENTTARGET": "", "__EVENTARGUMENT": "", dugme + ".x": "8", dugme + ".y": "7",
                       "__ASYNCPOST": "true"})
        url = urllib.parse.urljoin(self.base, "FindParcelaResult.aspx")
        t = self.post(url, podaci, ajax=True, referer=url)
        delovi = parsiraj_delta(t)
        for tip, idd, s in delovi:
            if tip == "pageRedirect":
                return self.get(urllib.parse.unquote(s), referer=url)
        sadrzaj, skrivena = "", {}
        for tip, idd, s in delovi:
            if tip == "updatePanel":
                sadrzaj += s
            elif tip == "hiddenField":
                skrivena[idd] = s
        if not sadrzaj:
            raise SajtGreska("izbor reda nije vratio podatke")
        # skrivena polja idu uz HTML, da sledeci klik na istom stanju ima vazeci ViewState
        return sadrzaj + "".join('<input type="hidden" name="%s" value="%s" />'
                                 % (htmlmod.escape(k), htmlmod.escape(v)) for k, v in skrivena.items())

    def nepokretnost(self, nep_id):
        t = self.get("NepokretnostProperties.aspx?nepID=" + nep_id,
                     referer=urllib.parse.urljoin(self.base, "FindParcelaResult.aspx"))
        if "SVGCaptchaControl" in t or "<svg" in t:
            raise SajtGreska("podaci o nepokretnosti traze captchu")
        self.poslednja_strana = t
        return tekst_nepokretnosti(t)


def spoji_objekte(objekti, posebni):
    """Isti objekat se na sajtu prikazuje uz svaki deo parcele na kome stoji (npr. deo pod objektom i deo
    pod ostalim delom objekta) - ovde postaje jedan red sa spiskom delova. Isto vazi i za posebne delove."""
    obj, redosled = {}, []
    for o in objekti:
        k = tuple(o.get(x, "") for x in KOLONE_OBJEKATA)
        if k not in obj:
            obj[k] = dict(o, deo_parcele=[])
            redosled.append(k)
        if o.get("deo_parcele") not in obj[k]["deo_parcele"]:
            obj[k]["deo_parcele"].append(o.get("deo_parcele"))
    objekti_out = []
    for k in redosled:
        o = obj[k]
        objekti_out.append(dict(o, deo_parcele=", ".join(str(d) for d in o["deo_parcele"])))
    indeks = {k: i for i, k in enumerate(redosled)}
    pos, vidjeno = [], set()
    for x in posebni:
        k = (x.get("objekat", ""),) + tuple(x.get(c, "") for c in KOLONE_POSEBNIH)   # kao do v16: snimci se ne menjaju
        if k not in vidjeno:
            vidjeno.add(k)
            pos.append(dict(x, obj_idx=indeks.get(x.get("obj_kljuc"))))
    return objekti_out, pos


def objekti_dela(sn, deo):
    """Indeksi objekata koji stoje na delu parcele `deo` (kao na sajtu: klik na deo parcele)."""
    rez = []
    for i, o in enumerate(sn.get("objekti", [])):
        delovi = [s.strip() for s in str(o[0]).split(",") if s.strip()]
        if not delovi or str(deo).strip() in delovi:
            rez.append(i)
    return rez


def posebni_objekta(sn, i):
    """Indeksi posebnih delova objekta i (kao na sajtu: 'Посебни делови изабраног објекта'). Snimci od v17 pamte
    tacan objekat; stariji se uparuju po ulici i kucnom broju. Poseban deo koji ne moze da se upari ide uz svaki."""
    objekti, posebni = sn.get("objekti", []), sn.get("posebni", [])
    veze = sn.get("posebni_obj")
    if isinstance(veze, list) and len(veze) == len(posebni):
        return [j for j, v in enumerate(veze) if v == i or v is None]
    oznake = [" ".join(" ".join(str(x) for x in o[1:3]).split()) for o in objekti]
    return [j for j, x in enumerate(posebni)
            if " ".join(str(x[0]).split()) == oznake[i] or " ".join(str(x[0]).split()) not in oznake]


# ----------------------------------------------------------------------
# Snimak parcele i poredjenje
# ----------------------------------------------------------------------
KOLONE_DELOVA = ("deo", "povrsina", "ulica", "nacin", "vrsta", "evidencija")
KOLONE_OBJEKATA = ("ulica", "kbr", "kpbr", "povrsina", "nacin", "status")
KOLONE_POSEBNIH = ("evid", "ulaz", "stan", "podbr", "nacin", "povrsina")


def napravi_snimak(rez):
    """Iz prikupljenih podataka pravi snimak bez ID-jeva sajta (oni mogu da se menjaju od sesije do sesije)."""
    return {
        "opstina": rez["opstina"], "ko": rez["ko"], "ukupno": rez.get("ukupno", ""),
        "delovi": [[d.get(k, "") for k in KOLONE_DELOVA] for d in rez["delovi"]],
        "objekti": [[o.get("deo_parcele", "")] + [o.get(k, "") for k in KOLONE_OBJEKATA] for o in rez["objekti"]],
        "posebni": [[o.get("objekat", "")] + [o.get(k, "") for k in KOLONE_POSEBNIH] for o in rez["posebni"]],
        "posebni_obj": [o.get("obj_idx") for o in rez["posebni"]],     # ne poredi se (poredi() ga ne gleda)
        "nepokretnost": rez.get("nepokretnost", {}), "nep_v": NEP_VERZIJA,
        "napomene": rez.get("napomene", []),
    }


def sumnjiv_snimak(stari, novi, sveze_nep=()):
    """v37: odgovor sajta koji izgleda nepotpuno (sajt pod opterećenjem vrati okrnjenu stranicu) - takva provera ne
    sme da postane "promena" koja ode klijentu. Vraća razlog ili None. sveze_nep = podaci o nepokretnosti koji su
    stvarno skinuti u ovoj proveri (stari se inače prepisuju u novi snimak)."""
    if not stari or not novi:
        return None
    if stari.get("delovi") and not novi.get("delovi"):
        return "sajt nije vratio delove parcele (ranije %d)" % len(stari["delovi"])
    if len(stari.get("posebni") or []) >= 3 and not novi.get("posebni") and novi.get("objekti"):
        return "zgrade su tu, a nema nijednog posebnog dela (ranije %d)" % len(stari["posebni"])
    if "parcela" in sveze_nep and ista_nep_verzija(stari, novi) and vlasnici_tereti(stari)[0] and \
            not vlasnici_tereti(novi)[0]:
        return "nema vlasnika parcele (ranije: %s)" % vlasnici_tereti(stari)[0][:80]
    return None


def otisak_snimka(sn):
    return hashlib.sha1(json.dumps(sn, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def ista_nep_verzija(stari, novi):
    """Podaci o nepokretnosti iz starije verzije programa zapisani su drugacije - ne porede se."""
    return (stari or {}).get("nep_v") == (novi or {}).get("nep_v")


def _opis_reda(sekcija, red):
    if sekcija == "delovi":
        return "deo %s: %s m², %s, %s" % (red[0], red[1], red[3], red[2])
    if sekcija == "objekti":
        return "objekat (deo parcele %s): %s %s %s, %s m², %s, %s" % tuple(red)
    return "poseban deo (%s): evid. %s, stan %s, %s, %s m²" % (red[0], red[1], red[3], red[5], red[6])


NAZIV_SEKCIJE = {"delovi": "Delovi parcele", "objekti": "Objekti", "posebni": "Posebni delovi"}


def poredi(stari, novi):
    """Lista promena (tekst) izmedju dva snimka."""
    promene = []
    for sek in ("delovi", "objekti", "posebni"):
        a = Counter(tuple(r) for r in stari.get(sek, []))
        b = Counter(tuple(r) for r in novi.get(sek, []))
        for r in (a - b).elements():
            promene.append("uklonjeno - " + _opis_reda(sek, r))
        for r in (b - a).elements():
            promene.append("novo - " + _opis_reda(sek, r))
    sn, nn = stari.get("nepokretnost", {}), novi.get("nepokretnost", {})
    if not ista_nep_verzija(stari, novi):
        sn = {}
    for kljuc in sorted(set(sn) & set(nn)):
        a, b = Counter(sn[kljuc]), Counter(nn[kljuc])
        for r in (a - b).elements():
            promene.append("%s: uklonjeno - %s" % (kljuc, r))
        for r in (b - a).elements():
            promene.append("%s: novo - %s" % (kljuc, r))
    return promene


# --- praćenje pojedinačnih stavki (Dejan, v22: npr. samo stan 56, ne cela parcela ni ostali stanovi) ---
def _delovi_kljuca(k):
    """'poseban deo <objekat>, ulaz U, stan S, evid. E, <način>' -> (objekat, ulaz, stan, evid, način); None za
    parcelu i zgradu."""
    if not k or not k.startswith("poseban deo "):
        return None
    s = re.sub(r" \(\d+\)$", "", k[len("poseban deo "):])
    try:
        s, ostatak = s.rsplit(", evid.", 1)
        s, stan = s.rsplit(", stan", 1)
        objekat, ulaz = s.rsplit(", ulaz", 1)
    except ValueError:
        return None
    evid, _, nacin = ostatak.partition(",")
    return objekat.strip(), ulaz.strip(), stan.strip(), evid.strip(), nacin.strip()


_KLJUC_STANA = re.compile(r"stan (\S+?)(?:, ulaz (\S+))?")


def kljuc_stana(stan, ulaz=""):
    """Stan iz zadatka, dok se ne nađe na sajtu: 'stan 56' ili 'stan 56, ulaz 2'."""
    return "stan %s%s" % (stan, (", ulaz %s" % ulaz) if ulaz else "")


def nadji_kljuc(k, kljucevi):
    """Praćena stavka (ključ iz ranijeg snimka) među stavkama na sajtu sada: isti ključ, a za poseban deo i isti
    objekat i evid. broj (ili ulaz i stan) - ključ se promeni kad se promeni npr. način korišćenja. None = nema je."""
    kljucevi = list(kljucevi)
    if k in kljucevi:
        return k
    m = _KLJUC_STANA.fullmatch(k or "")
    if m:            # v32: stan iz ugovora („stan 56“) - na sajtu jedini poseban deo sa tim brojem stana (i ulazom)
        nadjeni = list(dict.fromkeys(x for x, e in ((x, _delovi_kljuca(x)) for x in kljucevi)
                                     if e and e[2] == m.group(1) and (not m.group(2) or e[1] == m.group(2))))
        if len(nadjeni) > 1:
            nadjeni = [x for x in nadjeni if lat(_delovi_kljuca(x)[4]) == "stan"]
        return nadjeni[0] if len(nadjeni) == 1 else None
    d = _delovi_kljuca(k)
    if not d:
        return None
    isti_objekat = [(x, e) for x, e in ((x, _delovi_kljuca(x)) for x in kljucevi) if e and e[0] == d[0]]
    for uslov in ((lambda e: bool(d[3]) and e[3] == d[3]), (lambda e: bool(d[2]) and e[1:3] == d[1:3])):
        nadjeni = list(dict.fromkeys(x for x, e in isti_objekat if uslov(e)))
        if len(nadjeni) == 1:
            return nadjeni[0]
    return None


def opis_stavke(k):
    """Kratak naziv praćene stavke: 'parcela', 'zgrada <ulica kbr>', 'stan 56', 'garažni prostor 3'..."""
    if k == "parcela":
        return "parcela"
    if k.startswith("objekat "):
        return "zgrada " + k[len("objekat "):]
    d = _delovi_kljuca(k)
    if not d:
        return k
    objekat, ulaz, stan, evid, nacin = d
    vrsta = "stan" if "стан" == nacin.lower() or lat(nacin) == "stan" else (nacin.lower() or "poseban deo")
    return "%s %s%s" % (vrsta, stan or ("evid. " + evid), (", ulaz %s" % ulaz) if ulaz not in ("", "1") else "")


def pracene_stavke(p):
    """Ključevi stavki koje se prate na parceli (red iz baze); [] = prati se cela parcela."""
    try:
        lista = json.loads((p or {}).get("stavke") or "[]")
    except ValueError:
        return []
    return [k for k in lista if isinstance(k, str) and k] if isinstance(lista, list) else []


def redovi_stavki(sn):
    """Ključ stavke -> (sekcija, redovi tabele) iz snimka: parcela = delovi parcele, zgrada i poseban deo = svoj red."""
    out = {"parcela": ("delovi", [tuple(r) for r in (sn or {}).get("delovi", [])])}
    for iid, _, _, _, k in stablo_nepokretnosti(sn or {}):
        if iid[:1] in ("o", "p") and iid[1:].isdigit():
            sek = "objekti" if iid[0] == "o" else "posebni"
            out[k] = (sek, [tuple(sn[sek][int(iid[1:])])])
    return out


def poredi_stavke(stari, novi, mapa):
    """Promene samo za praćene stavke. mapa: {ključ u starom snimku: ključ sada na sajtu ili None}."""
    promene = []
    rs, rn = redovi_stavki(stari), redovi_stavki(novi)
    sn, nn = stari.get("nepokretnost", {}), novi.get("nepokretnost", {})
    if not ista_nep_verzija(stari, novi):
        sn = {}
    for k, k2 in mapa.items():
        if not k2:
            if k in rs and k != "parcela":         # javlja se jednom: u novom snimku je više nema
                promene.append("%s: više nije na sajtu (prati se) - bilo je: %s" % (
                    opis_stavke(k), "; ".join(_opis_reda(rs[k][0], r) for r in rs[k][1])))
            continue
        if k in rs and k2 in rn:
            sek = rs[k][0]
            a, b = Counter(rs[k][1]), Counter(rn[k2][1])
            for r in (a - b).elements():
                promene.append("uklonjeno - " + _opis_reda(sek, r))
            for r in (b - a).elements():
                promene.append("novo - " + _opis_reda(sek, r))
        if k in sn and k2 in nn:
            a, b = Counter(sn[k]), Counter(nn[k2])
            for r in (a - b).elements():
                promene.append("%s: uklonjeno - %s" % (k2, r))
            for r in (b - a).elements():
                promene.append("%s: novo - %s" % (k2, r))
    return promene


# --- v29 (Dejan: "Prenatrpano podacima koji nisu jasni"): promena za prikaz - samo šta je bilo -> šta je sada ---
_RED_NEP = re.compile(r"^(?P<k>.+?): (?P<v>uklonjeno|novo) - (?P<r>\[.*)$", re.S)
_RED_TAB = re.compile(r"^(?P<v>uklonjeno|novo) - (?P<r>.*)$", re.S)
_GLAVNA_POLJA = ("Назив", "Опис")          # po njima se zapis prepoznaje (vlasnik, teret, napomena)
_DODATNA_POLJA = ("Удео", "Датум")         # uz glavno polje kad je zapis nov ili uklonjen


def _zapis(r):
    """'[sekcija] polje: vrednost; polje: vrednost' -> (sekcija, [(polje, vrednost)]); tekst bez polja -> ('', tekst).
    Vrednost može da sadrži '; ' (npr. 'Назив улице: ЦАРА ДУШАНА; ЦАРА ДУШАНА 200')."""
    m = re.match(r"\[([^\]]*)\]\s?(.*)$", r, re.S)
    if not m:
        return "", [("", r)]
    sek, polja = m.group(1), []
    for deo in m.group(2).split("; "):
        k, sep, v = deo.partition(": ")
        if sep and k.strip() and len(k) <= 60:
            polja.append((k.strip(), v.strip()))
        elif polja:
            polja[-1] = (polja[-1][0], polja[-1][1] + "; " + deo)
        else:
            polja.append(("", deo))
    return sek, polja


def _kratka_sekcija(s):
    """'Имаоци права на посебном делу' -> 'Имаоци права'; '3. Подаци о посебном делу објекта - В2 лист' -> bez broja i lista."""
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"\s+-\s+\S+\s+лист$", "", s)
    return re.sub(r"\s+на\s+(парцели|објекту|посебном делу(\s+објекта)?)$", "", s) or s


def _glavno_polje(polja):
    for ime in _GLAVNA_POLJA:
        for k, _ in polja:
            if k == ime:
                return k
    return polja[0][0] if polja else ""


def _uparuj(uklonjeni, novi, slicnost, prag):
    """Parovi (staro, novo) istog zapisa, najsličniji prvi, i ostaci (samo uklonjeni, samo novi)."""
    kandidati = sorted(((slicnost(a, b), i, j) for i, a in enumerate(uklonjeni) for j, b in enumerate(novi)),
                       key=lambda x: (-x[0], x[1], x[2]))
    ui, nj, parovi = set(), set(), []
    for s, i, j in kandidati:
        if i not in ui and j not in nj and s >= prag(uklonjeni[i]):
            ui.add(i)
            nj.add(j)
            parovi.append((i, j))
    parovi.sort()
    return ([(uklonjeni[i], novi[j]) for i, j in parovi], [a for i, a in enumerate(uklonjeni) if i not in ui],
            [b for j, b in enumerate(novi) if j not in nj])


def _slicnost_zapisa(a, b):
    """Broj istih polja; isti vlasnik (Назив) ili isti opis je uvek isti zapis."""
    g = _glavno_polje(a)
    isto = g in _GLAVNA_POLJA and dict(a).get(g) == dict(b).get(g)
    return len(set(a) & set(b)) + (len(a) if isto else 0)


def _red_tabele(r):
    """'poseban deo (ulica): evid. 56, stan 56, СТАН, 46 m²' -> (ključ za uparivanje, naziv, vrednosti)."""
    glava, _, telo = r.partition(": ")
    m = re.match(r"^evid\. (.*?), stan (.*?), (.*), (.*? m²)$", telo, re.S) if glava.startswith("poseban deo") else None
    if m:
        evid, stan, nacin, pov = m.groups()
        vrsta = "stan" if lat(nacin) == "stan" else (nacin.lower() or "poseban deo")
        naziv = "%s %s" % (vrsta, stan) if stan.strip() else "%s evid. %s" % (vrsta, evid)
        return (glava, stan.strip() or evid), naziv, ["evid. " + evid, "stan " + stan, nacin, pov]
    vrednosti = telo.split(", ")
    if glava.startswith("objekat"):
        return (glava, vrednosti[0]), "zgrada " + " ".join(vrednosti[0].split()), vrednosti
    return (glava,), glava, vrednosti


def _grupisane_promene(redovi):
    """Promene iz baze (kako ih pravi poredi/poredi_stavke), grupisane po stavki i sekciji i uparene staro - novo."""
    grupe, redosled = {}, []

    def grupa(kljuc):
        if kljuc not in grupe:
            grupe[kljuc] = {"uklonjeno": [], "novo": []}
            redosled.append(kljuc)
        return grupe[kljuc]

    for red in redovi or []:
        red = (red or "").strip()
        if not red:
            continue
        m = _RED_NEP.match(red)
        if m:
            sek, polja = _zapis(m.group("r"))
            grupa(("nep", opis_stavke(m.group("k")), sek))[m.group("v")].append(polja)
            continue
        m = _RED_TAB.match(red)
        if m:
            kljuc, naziv, vrednosti = _red_tabele(m.group("r"))
            grupa(("tab",) + kljuc)[m.group("v")].append((naziv, vrednosti))
            continue
        grupa(("tekst", red))

    for kljuc in redosled:
        g = grupe[kljuc]
        if kljuc[0] == "tekst":
            yield ("tekst", kljuc[1])
        elif kljuc[0] == "tab":
            parovi, ukl, nov = _uparuj(g["uklonjeno"], g["novo"], lambda a, b: 1, lambda a: 1)
            for (naziv, a), (_, b) in parovi:
                yield ("tab", naziv, a, b)
            for naziv, v in ukl:
                yield ("tab", naziv, v, None)
            for naziv, v in nov:
                yield ("tab", naziv, None, v)
        else:
            _, stavka, sek = kljuc
            glavna = bool(re.match(r"^\d+\.\s", sek))
            ukl, nov = g["uklonjeno"], g["novo"]
            prazno = lambda polja: len(polja) == 1 and not polja[0][0] and polja[0][1].startswith("Нема ")
            if any(not prazno(x) for x in ukl + nov):          # „Нема терета“ i sl. samo kad nema ničeg drugog
                ukl, nov = [x for x in ukl if not prazno(x)], [x for x in nov if not prazno(x)]
            parovi, ukl, nov = _uparuj(ukl, nov, _slicnost_zapisa, lambda a: max(1, (len(a) + 1) // 2))
            gde = "%s · %s" % (stavka, _kratka_sekcija(sek) or "podaci")
            for a, b in parovi:
                yield ("nep", gde, a, b, glavna)
            for a in ukl:
                yield ("nep", gde, a, None, glavna)
            for b in nov:
                yield ("nep", gde, None, b, glavna)


# --- v31 (Dejan: "hocu da se jasno vidi staro stanje i novo stanje, i da se tacno oznaci izmena") ---
# Delovi prikaza: (tekst, vrsta); vrsta "" obično, "polje" naziv polja, "izmena" tačno ono što se promenilo.
_RECI = re.compile(r"\s+|[^\s,;()]+|[,;()]")


def _oznaci_razliku(a, b):
    """Dve vrednosti istog polja -> delovi starog i novog, promenjene reči označene kao „izmena“."""
    import difflib
    ta, tb = _RECI.findall(a), _RECI.findall(b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    if sm.ratio() < 0.34:                          # potpuno drugačije - označava se cela vrednost
        return [(a, "izmena")], [(b, "izmena")]
    da, db = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        vrsta = "" if op == "equal" else "izmena"
        da += [(x, vrsta) for x in ta[i1:i2]]
        db += [(x, vrsta) for x in tb[j1:j2]]
    return _spoji_delove(da), _spoji_delove(db)


def _spoji_delove(delovi):
    """Susedni delovi iste vrste u jedan; razmaci na ivici izmene ostaju neoznačeni."""
    out = []
    for t, v in delovi:
        if v == "izmena" and not t.strip():
            v = ""
        if out and out[-1][1] == v:
            out[-1] = (out[-1][0] + t, v)
        else:
            out.append((t, v))
    rez = []
    for i, (t, v) in enumerate(out):              # razmak između dve izmene pripada izmeni
        if not v and not t.strip() and 0 < i < len(out) - 1 and out[i - 1][1] == out[i + 1][1] == "izmena":
            v = "izmena"
        if rez and rez[-1][1] == v:
            rez[-1] = (rez[-1][0] + t, v)
        else:
            rez.append((t, v))
    return rez


def _polje(k, delovi):
    return ([("%s: " % k, "polje")] if k else []) + delovi


def _redovi_delova(redovi):
    """Lista redova (svaki je lista delova) -> delovi sa prelomom reda između."""
    out = []
    for i, r in enumerate(redovi):
        if i:
            out.append(("\n", ""))
        out += r
    return out


def _ceo_zapis(polja):
    """Nov ili uklonjen zapis (vlasnik, teret, napomena...): glavna vrednost i udeo/datum, sve označeno."""
    g = _glavno_polje(polja)
    if g in _GLAVNA_POLJA:
        d = dict(polja)
        redovi = [[(d[g], "izmena")]] + [_polje(k, [(d[k], "izmena")]) for k in _DODATNA_POLJA if k in d and k != g]
    else:
        redovi = [_polje(k, [(v, "izmena")]) for k, v in polja]
    return _redovi_delova(redovi)


def _razlika_delova(a, b, glavna_sekcija):
    """Isti zapis pre i posle: polja koja su se promenila (uz glavnu vrednost kao oznaku čiji je zapis)."""
    da, db = dict(a), dict(b)
    g = _glavno_polje(a)
    ra, rb = [], []
    if da.get(g) == db.get(g) and not glavna_sekcija and g and g in da:
        ra.append([(da[g], "")])
        rb.append([(db[g], "")])
    for k in dict.fromkeys([k for k, _ in a] + [k for k, _ in b]):
        sa, sb = da.get(k), db.get(k)
        if sa == sb:
            continue
        x, y = _oznaci_razliku(sa or "", sb or "")
        ra.append(_polje("" if k == g else k, x if sa is not None else [("-", "")]))
        rb.append(_polje("" if k == g else k, y if sb is not None else [("-", "")]))
    return _redovi_delova(ra), _redovi_delova(rb)


def promene_staro_novo(redovi):
    """v31: promene za prikaz u dve kolone. Svaka: {"gde": 'stan 56 · Имаоци права', "staro": delovi,
    "novo": delovi}; prazna lista = nije postojalo / više ne postoji."""
    out = []
    for x in _grupisane_promene(redovi):
        if x[0] == "tekst":
            m = re.match(r"^(?P<k>.+?): više nije na sajtu \(prati se\) - bilo je: (?P<b>.*)$", x[1], re.S)
            if m:
                out.append({"gde": m.group("k"), "staro": _redovi_delova([[(d, "")] for d in m.group("b").split("; ")]),
                            "novo": [("više nije na sajtu", "izmena")]})
            else:
                out.append({"gde": "", "staro": [], "novo": [(x[1], "")]})
        elif x[0] == "tab":
            _, naziv, a, b = x
            if a is None or b is None:
                out.append({"gde": naziv, "staro": [(", ".join(a), "izmena")] if a else [],
                            "novo": [(", ".join(b), "izmena")] if b else []})
                continue
            if len(a) == len(b):
                parovi = [("Површина" if p.endswith(" m²") and q.endswith(" m²") else "",) + _oznaci_razliku(p, q)
                          for p, q in zip(a, b) if p != q]
            else:
                parovi = [("",) + _oznaci_razliku(", ".join(a), ", ".join(b))]
            out.append({"gde": naziv, "staro": _redovi_delova([_polje(k, p) for k, p, _ in parovi]),
                        "novo": _redovi_delova([_polje(k, q) for k, _, q in parovi])})
        else:
            _, gde, a, b, glavna = x
            if a is None or b is None:
                out.append({"gde": gde, "staro": _ceo_zapis(a) if a else [], "novo": _ceo_zapis(b) if b else []})
            else:
                sa, sb = _razlika_delova(a, b, glavna)
                out.append({"gde": gde, "staro": sa, "novo": sb})
    return out


def tekst_delova(delovi):
    return "".join(t for t, _ in delovi).replace("\n", ", ") if delovi else "-"


def red_promene(pr):
    """Jedna promena u jednom redu (lista, poruke, dnevnik): 'stan 56 · Имаоци права | staro: X | novo: Y'."""
    if not pr["gde"] and not pr["staro"]:
        return tekst_delova(pr["novo"])
    return "%s%sstaro: %s | novo: %s" % (pr["gde"], " | " if pr["gde"] else "", tekst_delova(pr["staro"]),
                                         tekst_delova(pr["novo"]))


def jasne_promene(redovi):
    """Promene iz baze -> kratki redovi za prikaz (v31: staro i novo stanje). U bazi ostaje pun zapis."""
    return [red_promene(pr) for pr in promene_staro_novo(redovi)]


def kratak_opis(snimak):
    if not snimak:
        return "", "", ""
    delovi = snimak.get("delovi", [])
    pov = snimak.get("ukupno") or (delovi[0][1] if len(delovi) == 1 else "")
    nacini = list(dict.fromkeys(d[3] for d in delovi if d[3]))
    obj = snimak.get("objekti", [])
    opis_obj = ("%d objek%s" % (len(obj), "at" if len(obj) == 1 else "ta")) if obj else "bez objekata"
    pos = snimak.get("posebni", [])
    if pos:
        opis_obj += ", %d posebn%s del%s" % (len(pos), "i" if len(pos) == 1 else "ih", "" if len(pos) == 1 else "ova")
    return pov, "%d deo/delova: %s" % (len(delovi), "; ".join(nacini)[:120]) if len(delovi) != 1 else (nacini[0] if nacini else ""), opis_obj


def kratak_opis_stavki(snimak, kljucevi):
    """v26 (Dejan: "neka se prikaze samo ono sto pratim, ne sve na toj parceli"): površina, način korišćenja i
    zgrada samo praćenih stavki (stan, zgrada, parcela); bez praćenih stavki - cela parcela."""
    if not snimak or not kljucevi:
        return kratak_opis(snimak)
    rs = redovi_stavki(snimak)
    pov, nacini, gde = [], [], []
    for k in kljucevi:
        sek, redovi = rs.get(k, (None, []))
        if k == "parcela":
            a, b, _ = kratak_opis(snimak)
            pov.append(a)
            nacini.append(b)
            gde.append("parcela")
        elif sek == "objekti" and redovi:
            o = redovi[0]            # deo, ulica, kućni broj, podbroj, površina, način, status
            pov.append(o[4])
            nacini.append(o[5])
            gde.append(" ".join(("zgrada %s %s%s" % (o[1], o[2], (" / " + o[3]) if o[3] else "")).split()))
        elif sek == "posebni" and redovi:
            x = redovi[0]            # objekat, evid. broj, ulaz, stan, podbroj, način, površina
            pov.append(x[6])
            nacini.append(x[5])
            gde.append(" ".join(("zgrada " + x[0]).split()))
        else:
            nacini.append("%s: nema na sajtu" % opis_stavke(k))
    pov = [str(x) for x in pov if x]
    return " + ".join(pov), "; ".join(dict.fromkeys(n for n in nacini if n)), ", ".join(dict.fromkeys(gde))


# ----------------------------------------------------------------------
# Sifarnik opstina i KO
# ----------------------------------------------------------------------
class Sifarnik:
    def __init__(self, putanja=SIFARNIK_PATH):
        self.putanja = putanja
        self.opstine = [list(o) for o in OPSTINE_UGRADJENE]
        self.ko = {k: [list(x) for x in v] for k, v in KO_UGRADJENE.items()}
        try:
            with open(putanja, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("opstine"):
                self.opstine = d["opstine"]
            self.ko.update(d.get("ko") or {})
        except (OSError, ValueError):
            pass
        self.opstine.sort(key=lambda o: srpski_kljuc(o[1]))

    def sacuvaj(self):
        try:
            with open(self.putanja, "w", encoding="utf-8") as f:
                json.dump({"opstine": self.opstine, "ko": self.ko, "osvezeno": sada()}, f, ensure_ascii=False)
        except OSError:
            pass

    def postavi_opstine(self, lista):
        if lista:
            self.opstine = sorted(lista, key=lambda o: srpski_kljuc(o[1]))
            self.sacuvaj()

    def postavi_ko(self, opstina_id, lista):
        self.ko[str(opstina_id)] = sorted(lista, key=lambda o: srpski_kljuc(o[1]))
        self.sacuvaj()

    def ko_za(self, opstina_id):
        return self.ko.get(str(opstina_id))

    def naziv_opstine(self, opstina_id):
        return next((o[1] for o in self.opstine if str(o[0]) == str(opstina_id)), "")


# ----------------------------------------------------------------------
# Baza
# ----------------------------------------------------------------------
def napravi_rezervu_baze():
    """Pri svakom pokretanju (jednom dnevno) kopija katastar.db u folder 'rezerve'; cuva se poslednjih 15."""
    if not os.path.exists(DB_PATH):
        return
    try:
        os.makedirs(REZERVE_DIR, exist_ok=True)
        cilj = os.path.join(REZERVE_DIR, "katastar_%s.db" % dt.date.today().strftime("%Y%m%d"))
        if not os.path.exists(cilj):
            izvor, c = sqlite3.connect(DB_PATH), sqlite3.connect(cilj)
            with c:
                izvor.backup(c)
            izvor.close()
            c.close()
        stare = sorted(f for f in os.listdir(REZERVE_DIR) if f.startswith("katastar_") and f.endswith(".db"))
        for f in stare[:-15]:
            os.remove(os.path.join(REZERVE_DIR, f))
    except Exception:
        upisi_dnevnik("Rezervna kopija baze nije napravljena: " + traceback.format_exc())


def _mig_rok_grupe(c):
    """v36: rok provere po grupi (dana) i brže čitanje istorije promena."""
    c.execute("CREATE TABLE IF NOT EXISTS rok_grupe (naziv TEXT PRIMARY KEY, dana INTEGER)")
    c.execute("CREATE INDEX IF NOT EXISTS istorija_parcela ON istorija(parcela_id)")


# v36: promene šeme baze, redom; broj se pamti u PRAGMA user_version. Pre prve nove promene program pravi rezervu
# rezerve/katastar_pre_vN.db (N = verzija programa koja menja šemu). Nova promena = nova stavka na kraju spiska.
# Samo NOVE tabele i indeksi (ili kolona u parcele): ako se program vrati na stariju verziju (v34), ona mora da radi
# sa novom bazom - zato se postojeće tabele ne menjaju (npr. INSERT INTO grupe VALUES (?) u starijim verzijama).
def _mig_sumnjivo(c):
    """v37: sumnjiv odgovor sajta (otisak) - isti odgovor u dve uzastopne provere se prihvata kao pravo stanje."""
    c.execute("CREATE TABLE IF NOT EXISTS sumnjivo (parcela_id INTEGER PRIMARY KEY, otisak TEXT, vreme TEXT)")


MIGRACIJE = [(1, "v36", _mig_rok_grupe), (2, "v37", _mig_sumnjivo)]


class Baza:
    def __init__(self, path=DB_PATH):
        self.path = path
        with self._con() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS parcele (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opstina_id INTEGER, opstina TEXT, ko_id INTEGER NOT NULL, ko TEXT, broj TEXT NOT NULL,
                klijent TEXT DEFAULT '', grupa TEXT DEFAULT '', napomena TEXT DEFAULT '',
                dodat TEXT, provereno TEXT, snimak TEXT, pokusaj TEXT, greska TEXT,
                promene TEXT, promena_vreme TEXT,
                UNIQUE(ko_id, broj));
            CREATE TABLE IF NOT EXISTS istorija (
                id INTEGER PRIMARY KEY AUTOINCREMENT, parcela_id INTEGER, vreme TEXT, tekst TEXT);
            CREATE TABLE IF NOT EXISTS grupe (naziv TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS podesavanja (kljuc TEXT PRIMARY KEY, vrednost TEXT);
            """)
            # v8: arhiva (datum arhiviranja) i odlaganje provere (do datuma); takve ne idu u "Proveri sve"
            kolone = [r[1] for r in c.execute("PRAGMA table_info(parcele)")]
            # v22: stavke = JSON lista ključeva stavki koje se prate (npr. samo jedan stan); prazno = cela parcela
            for k in ("arhivirano", "odlozeno_do", "stavke"):
                if k not in kolone:
                    c.execute("ALTER TABLE parcele ADD COLUMN %s TEXT" % k)
            c.execute("UPDATE parcele SET odlozeno_do=NULL WHERE odlozeno_do IS NOT NULL AND odlozeno_do<=?",
                      (dt.date.today().isoformat(),))
        self._migriraj()

    def _migriraj(self):
        """v36: promene šeme koje baza još nema, svaka u svojoj transakciji; pre prve rezerva cele baze."""
        with self._con() as c:
            stara = c.execute("PRAGMA user_version").fetchone()[0]
            ima_podataka = c.execute("SELECT EXISTS(SELECT 1 FROM parcele)").fetchone()[0]
        nove = [m for m in MIGRACIJE if m[0] > stara]
        if not nove:
            return
        if ima_podataka:
            folder = os.path.join(os.path.dirname(os.path.abspath(self.path)), "rezerve")
            os.makedirs(folder, exist_ok=True)
            cilj = os.path.join(folder, "katastar_pre_%s.db" % nove[0][1])
            if not os.path.exists(cilj):
                izvor, kopija = sqlite3.connect(self.path), sqlite3.connect(cilj)
                with kopija:
                    izvor.backup(kopija)
                izvor.close()
                kopija.close()
                upisi_dnevnik("Baza: rezerva pre promene šeme (%s): %s" % (nove[0][1], cilj))
        for broj, verzija, fn in nove:
            with self._con() as c:
                fn(c)
                c.execute("PRAGMA user_version=%d" % broj)
            upisi_dnevnik("Baza: šema %d (%s)" % (broj, verzija))

    @contextlib.contextmanager
    def _con(self):
        """v36: veza se posle upotrebe i zatvara (ranije je samo potvrđivana transakcija, a veza ostajala otvorena)."""
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def podesavanje(self, kljuc, podrazumevano=""):
        with self._con() as c:
            r = c.execute("SELECT vrednost FROM podesavanja WHERE kljuc=?", (kljuc,)).fetchone()
        return r["vrednost"] if r else podrazumevano

    def postavi_podesavanje(self, kljuc, vrednost):
        with self._con() as c:
            c.execute("INSERT OR REPLACE INTO podesavanja VALUES (?,?)", (kljuc, vrednost))

    def dodaj(self, opstina_id, opstina, ko_id, ko, broj, klijent="", grupa="", napomena="", snimak=None):
        grupa = (self.dodaj_grupu(grupa) or "") if grupa else ""
        with self._con() as c:
            cur = c.execute("INSERT OR IGNORE INTO parcele (opstina_id, opstina, ko_id, ko, broj, klijent, grupa, "
                            "napomena, dodat, snimak, provereno) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (opstina_id, opstina, ko_id, ko, broj, klijent, grupa, napomena, sada(),
                             json.dumps(snimak, ensure_ascii=False) if snimak else None, sada() if snimak else None))
            if grupa:
                c.execute("INSERT OR IGNORE INTO grupe (naziv) VALUES (?)", (grupa,))
            return cur.rowcount > 0

    def parcela_po_mestu(self, ko_id, broj):
        with self._con() as c:
            r = c.execute("SELECT * FROM parcele WHERE ko_id=? AND broj=?", (ko_id, broj)).fetchone()
            return dict(r) if r else None

    def izmeni(self, pid, klijent, grupa, napomena):
        grupa = (self.dodaj_grupu(grupa) or "") if grupa else ""
        with self._con() as c:
            c.execute("UPDATE parcele SET klijent=?, grupa=?, napomena=? WHERE id=?", (klijent, grupa, napomena, pid))
            if grupa:
                c.execute("INSERT OR IGNORE INTO grupe (naziv) VALUES (?)", (grupa,))

    def parcele(self, ids=None):
        with self._con() as c:
            if ids:
                q = "SELECT * FROM parcele WHERE id IN (%s)" % ",".join("?" * len(ids))
                rows = c.execute(q, list(ids)).fetchall()
            else:
                rows = c.execute("SELECT * FROM parcele").fetchall()
        lista = [dict(r) for r in rows]
        lista.sort(key=lambda p: (srpski_kljuc(p["grupa"] or "~"), srpski_kljuc(p["ko"] or ""), broj_kljuc(p["broj"])))
        return lista

    def istorija(self, pid):
        with self._con() as c:
            return [dict(r) for r in c.execute("SELECT * FROM istorija WHERE parcela_id=? ORDER BY id DESC", (pid,))]

    def ukloni(self, ids):
        with self._con() as c:
            for pid in ids:
                c.execute("DELETE FROM parcele WHERE id=?", (pid,))
                c.execute("DELETE FROM istorija WHERE parcela_id=?", (pid,))

    def oznaci_pregledano(self, ids):
        with self._con() as c:
            for pid in ids:
                c.execute("UPDATE parcele SET promene=NULL WHERE id=?", (pid,))

    def zabelezi_neuspeh(self, pid, razlog):
        with self._con() as c:
            c.execute("UPDATE parcele SET pokusaj=?, greska=? WHERE id=?", (sada(), razlog, pid))

    def arhiviraj(self, ids):
        with self._con() as c:
            c.executemany("UPDATE parcele SET arhivirano=?, odlozeno_do=NULL WHERE id=?",
                          [(dt.date.today().isoformat(), i) for i in ids])

    def odlozi(self, ids, do):
        with self._con() as c:
            c.executemany("UPDATE parcele SET odlozeno_do=?, arhivirano=NULL WHERE id=?",
                          [(do.isoformat(), i) for i in ids])

    def vrati_u_proveru(self, ids):
        with self._con() as c:
            c.executemany("UPDATE parcele SET odlozeno_do=NULL, arhivirano=NULL WHERE id=?", [(i,) for i in ids])

    def grupe(self):
        with self._con() as c:
            g = {r[0] for r in c.execute("SELECT naziv FROM grupe")}
            g |= {r[0] for r in c.execute("SELECT DISTINCT grupa FROM parcele WHERE grupa<>''")}
        return sorted(g, key=srpski_kljuc)

    def _postojeca(self, naziv):
        """Postojeci naziv grupe bez obzira na velika/mala slova, ili None."""
        k = norm(naziv).casefold()
        return next((g for g in self.grupe() if g.casefold() == k), None)

    def dodaj_grupu(self, naziv):
        """Vraca naziv grupe (postojece, ako vec ima ista bez obzira na velika/mala slova)."""
        naziv = norm(naziv)
        if not naziv or naziv == BEZ_GRUPE:
            return None
        postojeca = self._postojeca(naziv)
        if postojeca:
            return postojeca
        with self._con() as c:
            c.execute("INSERT OR IGNORE INTO grupe (naziv) VALUES (?)", (naziv,))
        return naziv

    def grupisi_po_klijentu(self, klijent=None):
        """Parcele istog klijenta (isto ime bez obzira na pismo, velika slova i kvacice) idu u istu grupu,
        kao u Asistent PRO. Dira samo parcele BEZ grupe:
          - klijent vec ima parcele u tacno jednoj grupi -> i ove idu u nju;
          - nijedna nije u grupi, a postoji grupa sa imenom klijenta -> idu u nju;
          - nijedna nije u grupi, a ima ih bar dve -> nova grupa sa imenom klijenta (kako je upisan u prvoj).
        Klijent cije su parcele u dve ili vise grupa se ne dira. klijent=None: svi klijenti.
        Vraca [(grupa, broj premestenih parcela, nova_grupa)]."""
        with self._con() as c:
            redovi = [dict(r) for r in c.execute("SELECT id, klijent, grupa FROM parcele ORDER BY id")]
        postojece = {lat(g): g for g in self.grupe()}
        po_klijentu = {}
        for r in redovi:
            k = lat(norm(r["klijent"]))
            if k:
                po_klijentu.setdefault(k, []).append(r)
        if klijent is not None:
            k = lat(norm(klijent))
            po_klijentu = {k: po_klijentu[k]} if k in po_klijentu else {}
        rez = []
        for k, lst in po_klijentu.items():
            bez = [r["id"] for r in lst if not r["grupa"]]
            u_grupama = {r["grupa"] for r in lst if r["grupa"]}
            if not bez:
                continue
            if len(u_grupama) == 1:
                g = u_grupama.pop()
            elif not u_grupama and k in postojece:
                g = postojece[k]
            elif not u_grupama and len(bez) >= 2:
                g = norm(lst[0]["klijent"])
            else:
                continue
            nova = lat(g) not in postojece
            g = self.dodaj_grupu(g)
            if not g:
                continue
            postojece[lat(g)] = g
            self.promeni_grupu(bez, g)
            rez.append((g, len(bez), nova))
        rez.sort(key=lambda x: srpski_kljuc(x[0]))
        return rez

    def preimenuj_grupu(self, stara, nova):
        nova = norm(nova)
        postojeca = self._postojeca(nova)
        if postojeca and postojeca.casefold() != stara.casefold():
            nova = postojeca                  # spajanje u postojecu grupu
        with self._con() as c:
            c.execute("UPDATE parcele SET grupa=? WHERE grupa=?", (nova, stara))
            c.execute("DELETE FROM grupe WHERE naziv=?", (stara,))
            c.execute("INSERT OR IGNORE INTO grupe (naziv) VALUES (?)", (nova,))

    def obrisi_grupu(self, naziv):
        with self._con() as c:
            c.execute("UPDATE parcele SET grupa='' WHERE grupa=?", (naziv,))
            c.execute("DELETE FROM grupe WHERE naziv=?", (naziv,))

    def promeni_grupu(self, ids, grupa):
        grupa = (self.dodaj_grupu(grupa) or "") if grupa else ""
        with self._con() as c:
            for pid in ids:
                c.execute("UPDATE parcele SET grupa=? WHERE id=?", (grupa, pid))

    def postavi_stavke(self, pid, kljucevi):
        """Šta se prati na parceli: lista ključeva stavki ili [] (cela parcela)."""
        with self._con() as c:
            c.execute("UPDATE parcele SET stavke=? WHERE id=?",
                      (json.dumps(list(kljucevi), ensure_ascii=False) if kljucevi else None, pid))

    def dopuni_nep(self, pid, dopuna):
        """Podaci o nepokretnosti skinuti van provere ulaze u snimak praćene parcele ako ih tamo nema (to je stanje sa
        kojim se poredi pri sledećoj proveri). Postojeći se ne menjaju: promena se vidi samo kroz proveru."""
        with self._con() as c:
            r = c.execute("SELECT snimak FROM parcele WHERE id=?", (pid,)).fetchone()
            try:
                sn = json.loads(r["snimak"]) if r and r["snimak"] else None
            except ValueError:
                sn = None
            if not sn or sn.get("nep_v") != NEP_VERZIJA:
                return 0
            nep = sn.setdefault("nepokretnost", {})
            novo = {k: v for k, v in dopuna.items() if v and k not in nep}
            if novo:
                nep.update(novo)
                c.execute("UPDATE parcele SET snimak=? WHERE id=?", (json.dumps(sn, ensure_ascii=False), pid))
            return len(novo)

    def sumnjivo_ponovljeno(self, pid, otisak):
        """v37: True ako je isti sumnjiv odgovor stigao i u prethodnoj proveri (onda je to stvarno stanje na sajtu);
        inače se pamti i vraća False."""
        with self._con() as c:
            r = c.execute("SELECT otisak FROM sumnjivo WHERE parcela_id=?", (pid,)).fetchone()
            if r and r["otisak"] == otisak:
                c.execute("DELETE FROM sumnjivo WHERE parcela_id=?", (pid,))
                return True
            c.execute("INSERT OR REPLACE INTO sumnjivo VALUES (?,?,?)", (pid, otisak, sada()))
            return False

    def obradi(self, p, snimak, mapa=None):
        """Upisuje novu proveru. Vraca (prva, promene). mapa (v22): prate se samo te stavke
        ({ključ u starom snimku: ključ sada}) - samo one se porede, a ključevi se pamte kako se sada zovu."""
        stari = None
        if p.get("snimak"):
            try:
                stari = json.loads(p["snimak"])
            except ValueError:
                stari = None
        promene = (poredi_stavke(stari, snimak, mapa) if mapa else poredi(stari, snimak)) if stari else []
        with self._con() as c:
            c.execute("DELETE FROM sumnjivo WHERE parcela_id=?", (p["id"],))     # v37
            if promene:
                tekst = "\n".join(promene)
                pre = c.execute("SELECT promene FROM parcele WHERE id=?", (p["id"],)).fetchone()
                ukupno = ((pre["promene"] + "\n") if pre and pre["promene"] else "") + tekst
                c.execute("UPDATE parcele SET promene=?, promena_vreme=? WHERE id=?", (ukupno, sada(), p["id"]))
                c.execute("INSERT INTO istorija (parcela_id, vreme, tekst) VALUES (?,?,?)", (p["id"], sada(), tekst))
            c.execute("UPDATE parcele SET snimak=?, provereno=?, pokusaj=NULL, greska=NULL, opstina=COALESCE(NULLIF(?,''), opstina), "
                      "ko=COALESCE(NULLIF(?,''), ko) WHERE id=?",
                      (json.dumps(snimak, ensure_ascii=False), sada(), snimak.get("opstina", ""), snimak.get("ko", ""),
                       p["id"]))
            if mapa and any(v and v != k for k, v in mapa.items()):
                # stavka se na sajtu sada drugačije zove: pamti se novi naziv (spisak se čita ponovo - mogao je da se
                # promeni dok je provera trajala)
                r = c.execute("SELECT stavke FROM parcele WHERE id=?", (p["id"],)).fetchone()
                tren = pracene_stavke(dict(r)) if r else []
                c.execute("UPDATE parcele SET stavke=? WHERE id=?", (json.dumps(
                    list(dict.fromkeys(mapa.get(k) or k for k in tren)), ensure_ascii=False) if tren else None, p["id"]))
        return stari is None, promene

    def pretrazi(self, upit, sve=None):
        """v36: tekst za pretragu (bez obzira na pismo i kvačice) se računa jednom po parceli i pamti dok se parcela
        ne promeni - ranije se za svako slovo u polju za pretragu ponovo prolazilo kroz sve snimke (0,7 s na 1000
        parcela, sada 0,01 s). sve = već učitan spisak parcela (da se baza ne čita dvaput)."""
        u = lat(upit)
        ids = set()
        indeks = self.__dict__.setdefault("_indeks", {})
        for p in (self.parcele() if sve is None else sve):
            polja = (p["broj"], p["ko"], p["opstina"], p["klijent"], p["grupa"], p["napomena"], p["promene"] or "")
            kljuc = polja + (hash(p["snimak"] or ""),)      # otisak celog snimka (promena iste dužine)
            pre = indeks.get(p["id"])
            if pre is None or pre[0] != kljuc:
                pre = indeks[p["id"]] = (kljuc, "\n".join(lat(x or "") for x in polja + (p["snimak"] or "",)))
            if u in pre[1]:
                ids.add(p["id"])
        return ids


# ----------------------------------------------------------------------
# Pozadinski posao: pretraga parcela (i za spisak i za pracenje)
# ----------------------------------------------------------------------
class Posao:
    def __init__(self, trazi_odgovor, log, gotovo, prikazi=None, stanje=None):
        self.trazi_odgovor = trazi_odgovor   # f(svg, opis) -> tekst | None (preskoci) | False (prekini)
        self.log, self.gotovo = log, gotovo
        self.prikazi = prikazi or (lambda opis: None)
        self.stanje = stanje or (lambda tekst: None)
        self.stop = False

    def pokreni(self, *args):
        threading.Thread(target=self._radi, args=args, daemon=True).start()

    def _cekaj(self, sekundi, poruka=None):
        kraj = time.time() + sekundi
        while time.time() < kraj and not self.stop:
            if poruka:
                self.stanje("%s (%d s)" % (poruka, kraj - time.time()))
            time.sleep(0.25 if TEST_REZIM else 0.5)
        if poruka:
            self.stanje("")


class Pretraga(Posao):
    """zadaci: [{'ko_id','ko','opstina_id','opstina','broj', 'pid' (samo za pracenje)}]
    ili po adresi: [{'opstina_id','opstina','ulica','ulica_id','kbr','adresa'}] - adresa se prvo trazi na sajtu,
    pa se svaka parcela na njoj trazi kao i inace (isti rezultat kao pretraga po broju parcele).
    Za svaku parcelu poziva self.rezultat(zadatak, podaci | None, razlog)."""

    def __init__(self, citac, detaljno, nepokretnost, *a, **k):
        super().__init__(*a, **k)
        self.citac, self.detaljno, self.sa_nep = citac, detaljno, nepokretnost
        self.rezultat = lambda z, podaci, razlog: None
        self.sajt = None
        self.ok = 0
        self.neuspeli = []
        self.auto_ok = self.auto_odbijeno = self.rucno = 0
        self._nep_nedostupno = False
        self._nadjene = {}           # (ko_id, broj) -> podaci: susedni kucni brojevi cesto su na istoj parceli
        self.prednost = None         # kljuc stavke koju je korisnik trazio ("Ucitaj sa sajta") - ucitava se prva
        self.strana = None           # f(kljuc, html) posle svake ucitane stranice "Podaci o nepokretnosti"
        self.samo = None             # skup kljuceva stavki koje se skidaju (izabrane u prozoru parcele); None = po sa_nep
        self.direktno = None         # {"sajt", "nid", "naslov"}: sesija ranije pretrage - izabrane stavke se skidaju
        #                              bez nove pretrage i captche; ako sesija vise ne vazi, parcela se trazi ponovo
        self.ko_za = None            # f(opstina_id) -> [[ko_id, naziv]] iz sifarnika (za pretragu po adresi)
        self.sacuvaj_ko = None       # f(opstina_id, lista) - KO ucitane sa sajta idu u sifarnik

    def _skini_direktno(self):
        """Izabrane stavke preko nepID iz ranije pretrage (ista sesija, bez captche). Vraca kljuceve koje treba
        skinuti novom pretragom ([] = gotovo ili prekinuto)."""
        sajt, nid, naslov = self.direktno["sajt"], self.direktno["nid"], self.direktno["naslov"]
        red = [k for k in nid if k in self.samo]
        if self.prednost in red:
            red.remove(self.prednost)
            red.insert(0, self.prednost)
        ostalo = [k for k in self.samo if k not in nid]
        for i, k in enumerate(red):
            if self.stop:
                return []
            self.stanje("%s: skidam sa sajta %d od %d" % (naslov, i + 1, len(red)))
            try:
                if i:
                    self.pauza(PAUZA_ZAHTEVA)
                self._zahtev(sajt.nepokretnost, naslov, nid[k])
                html = sajt.poslednja_strana
                if not parsiraj_nepokretnost(html):
                    raise SajtGreska("stranica bez podataka o nepokretnosti")
            except InterruptedError:
                return []
            except SajtOgranicenje as e:
                self.stop = True
                self.log("%s: sajt je trazio pauzu (%s) - skinuto %d od %d, ostalo kasnije." % (naslov, e, i, len(red)),
                         "info")
                return []
            except (SajtGreska, requests.RequestException) as e:
                upisi_dnevnik("SKIDANJE %s (%s): %r" % (naslov, k, e))
                return ostalo + red[i:]
            if self.strana:
                try:
                    self.strana(k, html)
                except Exception:
                    upisi_dnevnik(traceback.format_exc())
        return ostalo

    def pauza(self, raspon):
        if not TEST_REZIM:
            self._cekaj(random.uniform(*raspon))
        else:
            self._cekaj(0.05)

    def _radi(self, zadaci):
        try:
            if self.direktno:
                ostalo = self._skini_direktno()
                if not ostalo:                       # sve skinuto (ili prekinuto)
                    return
                self.samo = set(ostalo)
                self.log("%s: sesija sa sajta vise ne vazi - parcela se trazi ponovo (captcha), pa se skida samo "
                         "izabrano (%d)." % (self.direktno["naslov"], len(ostalo)), "info")
            self.sajt = Sajt()
            for i, z in enumerate(zadaci):
                if self.stop:
                    break
                if z.get("ulica_id"):
                    if not self._adresa(z, i + 1, len(zadaci)):
                        break
                elif not self._obradi(z, i + 1, len(zadaci)):
                    break
                if i < len(zadaci) - 1 and not self.stop:
                    if TEST_REZIM:
                        self._cekaj(0.05)
                    else:
                        self._cekaj(random.uniform(*PAUZA_IZMEDJU_PARCELA), "kratka pauza pre sledece parcele")
        except Exception as e:
            self.log("Neocekivana greska: %r" % (e,), "neuspeh")
            upisi_dnevnik(traceback.format_exc())
        finally:
            if self.auto_ok or self.auto_odbijeno:
                self.log("Captcha: automatski procitano %d, rucno %d%s" % (
                    self.auto_ok, self.rucno, (", sajt odbio automatsko citanje %d put(a)" % self.auto_odbijeno)
                    if self.auto_odbijeno else ""), "tiho")
            self.gotovo(self)

    def _javi(self, z, podaci, razlog):
        try:
            self.rezultat(z, podaci, razlog)
        except Exception:
            upisi_dnevnik(traceback.format_exc())

    def _obradi(self, z, rb, ukupno):
        """Jedna parcela: pretraga, rezultat. False ako je prekinuto."""
        naslov = "%s %s" % (z["ko"], z["broj"])
        try:
            podaci, razlog = self._jedna(z, naslov, rb, ukupno)
        except Exception as e:
            upisi_dnevnik(traceback.format_exc())
            podaci, razlog = None, "neocekivana greska (%r)" % (e,)
        if podaci is None and razlog is None:      # prekinuto
            return False
        if podaci is None:
            self.neuspeli.append((naslov, razlog))
        else:
            self.ok += 1
            self._nadjene[(z.get("ko_id"), z["broj"])] = podaci
        self._javi(z, podaci, razlog)
        return True

    def _adresa(self, z, rb, ukupno):
        """Pretraga po adresi: sajt vrati parcele (i delove) na toj adresi, pa se svaka parcela trazi kao i inace.
        False ako je prekinuto."""
        naslov = z["adresa"]
        nije = dict(z, ko=z["opstina"], ko_id=None, broj=z["adresa"])     # red za adresu koja nije nadjena
        try:
            html, razlog = self._upit(
                naslov, "[%d/%d] %s" % (rb, ukupno, naslov), lambda: self.sajt.otvori_adresu(z["opstina_id"]),
                lambda obr, tekst: self.sajt.posalji_adresu(obr, z["ulica"], z["ulica_id"], z["kbr"], tekst),
                "adresa nije pronadjena (%s)")
            if html is not None:
                parcele = parsiraj_adresu(html)
                if not parcele:
                    poruke = poruke_stranice(html)
                    html, razlog = None, "adresa nije pronadjena (%s)" % ("; ".join(poruke) or "sajt nije vratio parcelu")
        except Exception as e:
            upisi_dnevnik(traceback.format_exc())
            html, razlog = None, "neocekivana greska (%r)" % (e,)
        if html is None:
            if razlog is None:
                return False
            self.neuspeli.append((naslov, razlog))
            self._javi(nije, None, razlog)
            return True
        mesta = list(dict.fromkeys((p["ko"], p["broj"]) for p in parcele))     # deo parcele -> parcela
        self.log("%s: na adresi %d parcel%s (%s)" % (naslov, len(mesta), "a" if len(mesta) == 1 else "e",
                                                    ", ".join("%s %s" % m for m in mesta)), "tiho")
        for j, (ko, broj) in enumerate(mesta):
            if self.stop:
                return False
            z2 = {"opstina_id": z["opstina_id"], "opstina": z["opstina"], "ko_id": None, "ko": ko, "broj": broj,
                  "adresa": z["adresa"]}
            try:
                k = self._ko(z["opstina_id"], ko, naslov)
            except InterruptedError:
                return False
            except (SajtGreska, requests.RequestException) as e:
                k, razlog = None, "katastarske opstine nisu ucitane: %s" % e
            else:
                razlog = "KO %s nije u spisku opstine %s" % (ko, z["opstina"])
            if k is None:
                self.neuspeli.append(("%s %s" % (ko, broj), razlog))
                self._javi(z2, None, razlog)
                continue
            z2["ko_id"], z2["ko"] = k
            if (z2["ko_id"], broj) in self._nadjene:          # vec ucitana za drugi kucni broj - bez nove captche
                self.ok += 1
                self._javi(z2, self._nadjene[(z2["ko_id"], broj)], None)
                continue
            self.pauza(PAUZA_ZAHTEVA)
            if not self._obradi(z2, rb, ukupno):
                return False
        return True

    def _ko(self, opstina_id, naziv, naslov):
        """KO iz rezultata po adresi (naziv) -> [ko_id, naziv], iz sifarnika ili sa sajta; None ako je nema."""
        def nadji(lista):
            k = lat(norm(naziv))
            return next((list(x) for x in lista or [] if lat(norm(x[1])) == k), None)
        x = nadji(self.ko_za(opstina_id) if self.ko_za else None)
        if x is None:
            lista = self._zahtev(self.sajt.ko, naslov, opstina_id)
            if self.sacuvaj_ko:
                self.sacuvaj_ko(opstina_id, lista)
            x = nadji(lista)
        return x

    def _zahtev(self, f, naslov, *args):
        """Poziv sajta sa ponavljanjem: greska veze 2 puta posle 10 s, ograničenje jednom posle 60 s."""
        veza, ogr = 0, 0
        while True:
            if self.stop:
                raise InterruptedError()
            try:
                return f(*args)
            except SajtOgranicenje as e:
                if ogr >= 1:
                    raise
                ogr += 1
                self.log("%s: %s - cekam %d s pa nastavljam" % (naslov, e, CEKANJE_429), "info")
                self._cekaj(5 if TEST_REZIM else CEKANJE_429, "sajt je trazio pauzu, nastavljam za")
            except (requests.ConnectionError, requests.Timeout) as e:
                if veza >= 2:
                    raise
                veza += 1
                self.log("%s: greska veze (%s) - pokusavam ponovo za 10 s" % (naslov, e.__class__.__name__), "info")
                self._cekaj(1 if TEST_REZIM else 10, "greska veze, pokusavam ponovo za")

    def _jedna(self, z, naslov, rb, ukupno):
        """(podaci, None) | (None, razlog) | (None, None) ako je prekinuto."""
        html, razlog = self._upit(naslov, "[%d/%d] %s" % (rb, ukupno, naslov), lambda: self.sajt.otvori(z["ko_id"]),
                                  lambda obr, tekst: self.sajt.posalji(obr, z["broj"], tekst),
                                  "parcela nije pronadjena (%s)")
        if html is None:
            return None, razlog
        try:
            self.stanje("citam rezultat...")
            return self._prikupi(html, naslov, z.get("stavke")), None
        except InterruptedError:
            return None, None
        except SajtOgranicenje as e:
            self.stop = True
            return None, "%s - provera prekinuta, pokusaj kasnije" % e
        except (SajtGreska, requests.RequestException) as e:
            return None, "greska sajta: %s" % e

    def _upit(self, naslov, opis, otvori, posalji, nema):
        """Obrazac sa captchom (parcela ili adresa) do rezultata: (html rezultata, None) | (None, razlog) |
        (None, None) ako je prekinuto."""
        try:
            self.stanje("otvaram pretragu...")
            obr = self._zahtev(otvori, naslov)
            pokusaj = auto_pokusaj = odbijeno_ovde = 0
            while True:
                if self.stop:
                    return None, None
                auto = False
                tekst, siguran = None, False
                # svaka nova slika se prvo da citacu; kad prepozna svih 5 znakova, salje se sama
                if self.citac is not None and odbijeno_ovde < AUTO_POKUSAJA:
                    tekst, siguran = self.citac.procitaj(obr.svg)
                if siguran:
                    auto = True
                    self.prikazi(opis)
                    self.stanje("captcha procitana automatski: %s" % tekst)
                elif self.citac is not None and auto_pokusaj < AUTO_POKUSAJA:
                    auto_pokusaj += 1
                    self.stanje("citac nije siguran (%s) - nova slika..." % (tekst or "?"))
                    self.pauza((0.8, 1.5))
                    obr = self._zahtev(otvori, naslov)
                    continue
                else:
                    if pokusaj >= MAX_POKUSAJA:
                        return None, "captcha nije prihvacena ni posle %d pokusaja" % MAX_POKUSAJA
                    pokusaj += 1
                    tekst = self.trazi_odgovor(obr.svg, "%s  -  pokusaj %d" % (opis, pokusaj))
                    if tekst is False:
                        self.stop = True
                        return None, None
                    if tekst is None:
                        return None, "preskoceno na tvoj zahtev"
                svg = obr.svg
                self.stanje("saljem upit...")
                vrsta, odg = self._zahtev(posalji, naslov, obr, tekst)
                if vrsta == "captcha":
                    if auto:
                        self.auto_odbijeno += 1
                        odbijeno_ovde += 1
                        self.log("%s: sajt nije prihvatio automatsko citanje (%s), nova slika..." % (naslov, tekst), "tiho")
                    else:
                        self.log("%s: kod nije prihvacen (pazi na velika i mala slova), nova slika..." % naslov, "info")
                    continue
                if auto:
                    self.auto_ok += 1
                else:
                    self.rucno += 1
                if self._citac_za_ucenje is not None:
                    try:
                        n = self._citac_za_ucenje.nauci(svg, tekst)
                        if n:
                            self.log("Citac captche je naucio %d nov%s znak%s." % (
                                n, "" if n == 1 else "a", "" if n == 1 else "a"), "tiho")
                    except Exception:
                        upisi_dnevnik(traceback.format_exc())
                if vrsta == "nema":
                    return None, nema % odg
                return odg, None
        except InterruptedError:
            return None, None
        except SajtOgranicenje as e:
            self.stop = True
            return None, "%s - provera prekinuta, pokusaj kasnije" % e
        except (SajtGreska, requests.RequestException) as e:
            return None, "greska sajta: %s" % e

    _citac_za_ucenje = None

    def _prikupi(self, html_rez, naslov, stavke=None):
        """stavke (v22): praćenje samo tih stavki parcele - skidaju se samo njihovi podaci o nepokretnosti (a objekti i
        posebni delovi svih delova parcele, da bi se stavka našla gde god da je)."""
        detaljno = self.detaljno or any(k != "parcela" for k in stavke or ())
        rez = parsiraj_rezultat(html_rez)
        if rez is None or not rez["delovi"]:
            poruke = poruke_stranice(html_rez)
            raise SajtGreska("rezultat bez podataka o parceli%s" % ((" (%s)" % "; ".join(poruke)) if poruke else ""))
        napomene = []
        objekti, posebni = [], []
        izabran_deo = next((d["deo"] for d in rez["delovi"] if d["izabran"]), rez["delovi"][0]["deo"])

        def ubaci(r, deo):
            izabran_obj = next((i for i, o in enumerate(r["objekti"]) if o["izabran"]), 0)
            for i, o in enumerate(r["objekti"]):
                o = dict(o, deo_parcele=deo)
                objekti.append(o)
            return izabran_obj

        def ubaci_posebne(r, deo, o_idx, objekat, o=None):
            kljuc = tuple(o.get(k, "") for k in KOLONE_OBJEKATA) if o else None   # kom objektu pripada
            for x in r["posebni"]:
                posebni.append(dict(x, objekat=objekat, obj_kljuc=kljuc))

        def obradi_deo(html_d, r, deo):
            iz = ubaci(r, deo)
            if r["objekti"] and r["posebni"]:
                o = r["objekti"][iz]
                ubaci_posebne(r, deo, iz, ("%s %s" % (o["ulica"], o["kbr"])).strip() or "objekat %d" % (iz + 1), o)
            elif r["objekti"]:
                iz = None        # posebni delovi se na sajtu vide tek kad se klikne objekat - klikni svaki
            if detaljno and (len(r["objekti"]) > 1 or iz is None):
                for j, o in enumerate(r["objekti"]):
                    if j == iz or not o["dugme"] or self.stop:
                        continue
                    try:
                        self.pauza(PAUZA_ZAHTEVA)
                        h2 = self._zahtev(self.sajt.izaberi, naslov, html_d, o["dugme"])
                        r2 = parsiraj_rezultat(h2)
                        if r2:
                            ubaci_posebne(r2, deo, j, ("%s %s" % (o["ulica"], o["kbr"])).strip() or "objekat %d" % (j + 1),
                                          o)
                    except (SajtGreska, requests.RequestException) as e:
                        napomene.append("posebni delovi objekta %d (deo %s) nisu ucitani: %s" % (j + 1, deo, e))
                        upisi_dnevnik("IZBOR OBJEKTA: %r" % (e,))

        obradi_deo(html_rez, rez, izabran_deo)
        if detaljno:
            for d in rez["delovi"]:
                if d["deo"] == izabran_deo or not d["dugme"] or self.stop:
                    continue
                try:
                    self.pauza(PAUZA_ZAHTEVA)
                    h = self._zahtev(self.sajt.izaberi, naslov, html_rez, d["dugme"])
                    r = parsiraj_rezultat(h)
                    if r is None:
                        raise SajtGreska("nepoznat oblik odgovora")
                    obradi_deo(h, r, d["deo"])
                except (SajtGreska, requests.RequestException) as e:
                    napomene.append("objekti na delu %s nisu ucitani: %s" % (d["deo"], e))
                    upisi_dnevnik("IZBOR DELA: %r" % (e,))
        rez["objekti"], rez["posebni"] = spoji_objekte(objekti, posebni)
        nep, nep_html = {}, {}
        # "Podaci o nepokretnosti" ne traze captchu: parcela (A, B, G list i napomene), svaki objekat (V1 list) i
        # svaki poseban deo (V2 list). Spisak svih stavki (sa nepID ove sesije) ide uvek u rezultat, da se iz
        # prozora parcele skine samo ono sto je izabrano (Dejan, v21); sta se skida odmah: self.samo (izabrane
        # stavke), inace "sve" ili nista.
        spisak, vidjeni, imena = [], set(), set()
        kandidati = [("parcela", rez["delovi"][0].get("nep"))]
        for o in rez["objekti"]:
            kandidati.append(("objekat %s %s %s" % (o["ulica"], o["kbr"], o["kpbr"]), o.get("nep")))
        for x in rez["posebni"]:
            kandidati.append(("poseban deo %s, ulaz %s, stan %s, evid. %s, %s" % (
                x.get("objekat", ""), x.get("ulaz", ""), x.get("stan", ""), x.get("evid", ""),
                x.get("nacin", "")), x.get("nep")))
        for ime, nid in kandidati:
            if nid and nid not in vidjeni:
                vidjeni.add(nid)
                ime = " ".join(ime.split())
                n = 2
                while ime in imena:                          # dva reda istog opisa - kljuc mora biti jedinstven
                    ime = "%s (%d)" % (ime.rsplit(" (", 1)[0] if n > 2 else ime, n)
                    n += 1
                imena.add(ime)
                spisak.append((ime, nid))
        redosled = [ime for ime, _ in spisak]                          # redom kao na sajtu
        rez["nep_id"], rez["nep_redosled"], rez["nep_potpuno"] = dict(spisak), redosled, False
        if self.samo is not None:
            spisak = [x for x in spisak if x[0] in self.samo]
        elif stavke:                                   # praćene stavke (v22), i kad su se na sajtu preimenovale
            trazi = {nadji_kljuc(k, redosled) for k in stavke} - {None}
            spisak = [x for x in spisak if x[0] in trazi]
        elif self.sa_nep != "sve":
            spisak = [x for x in spisak if x[0] == "parcela"] if self.sa_nep else []
        if spisak and not self._nep_nedostupno:
            if self.prednost:
                spisak.sort(key=lambda x: x[0] != self.prednost)      # trazena stavka prva, ostale istim redom
            if len(spisak) > MAX_NEPOKRETNOSTI:
                napomene.append("podaci o nepokretnosti ucitani za prvih %d od %d (parcela, objekti, posebni delovi)"
                                % (MAX_NEPOKRETNOSTI, len(spisak)))
                spisak = spisak[:MAX_NEPOKRETNOSTI]
            for i, (ime, nid) in enumerate(spisak):
                if self.stop:
                    napomene.append("podaci o nepokretnosti ucitani za %d od %d (prekinuto)" % (i, len(spisak)))
                    break
                if len(spisak) > 1:
                    self.stanje("%s: podaci o nepokretnosti %d od %d" % (naslov, i + 1, len(spisak)))
                try:
                    self.pauza(PAUZA_ZAHTEVA)
                    nep[ime] = self._zahtev(self.sajt.nepokretnost, naslov, nid)
                    nep_html[ime] = getattr(self.sajt, "poslednja_strana", "")
                    if self.strana:
                        try:
                            self.strana(ime, nep_html[ime])
                        except Exception:
                            upisi_dnevnik(traceback.format_exc())
                except InterruptedError:                 # Prekini: ono sto je ucitano ostaje
                    napomene.append("podaci o nepokretnosti ucitani za %d od %d (prekinuto)" % (i, len(spisak)))
                    break
                except SajtOgranicenje as e:
                    self.stop = True
                    napomene.append("podaci o nepokretnosti ucitani za %d od %d - sajt je trazio pauzu (%s), "
                                    "pokusaj kasnije" % (i, len(spisak), e))
                    self.log("%s: sajt je trazio pauzu - ucitano %d od %d, ostalo kasnije." % (naslov, i, len(spisak)),
                             "info")
                    break
                except (SajtGreska, requests.RequestException) as e:
                    napomene.append("podaci o nepokretnosti (%s) nisu ucitani: %s" % (ime, e))
                    if "captch" in str(e):
                        self._nep_nedostupno = True
                        self.log("Podaci o nepokretnosti traze captchu - u ovoj proveri se preskacu.", "info")
                        break
            nep = {k: nep[k] for k in redosled if k in nep}
            nep_html = {k: nep_html[k] for k in redosled if k in nep_html}
            rez["nep_potpuno"] = self.sa_nep == "sve" and self.samo is None and not stavke and len(nep) == len(redosled)
        rez["nepokretnost"] = nep
        rez["nep_html"] = nep_html
        rez["napomene"] = napomene
        return rez


# ----------------------------------------------------------------------
# Prozor
# ----------------------------------------------------------------------
# Izgled (ista tema kao Asistent PRO) i prikaz "Podaci o nepokretnosti" kao na eKatastru
# ----------------------------------------------------------------------
SKALA = 1.0                 # uvecanje po kome program crta (1.25 = 125%); postavlja se pri pokretanju
SKALA_WINDOWS = 1.0         # uvecanje podeseno u Windowsu
MIN_VISINA = 864            # najmanja visina ekrana (u tackama pri 100%) da tabela i panel budu pregledni


def px(n):
    """Velicina u pikselima prilagodjena uvecanju ekrana (fontovi u tackama se prilagode sami)."""
    return int(round(n * SKALA))


def ukljuci_ostar_prikaz():
    """Program koji Windowsu ne kaze da sam crta u punoj rezoluciji Windows pri uvecanju 125% ili 150% razvlaci
    kao sliku, pa su slova i linije mutni. Zove se pre otvaranja prozora (kao u Asistent PRO)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def postavi_skalu(root, velicina="auto"):
    """SKALA = uvecanje iz Windowsa. Na laptopu 1920x1080 sa 150% to je kao ekran 1280x720, pa za tabelu
    rezultata ne ostane mesta; tada program crta kao pri 125% (i dalje ostro, slova malo sitnija).
    Prikaz -> Velicina prikaza -> kao u Windows-u vraca puno uvecanje."""
    global SKALA, SKALA_WINDOWS
    try:
        win = max(1.0, round(float(root.winfo_fpixels("1i")) / 96.0, 2))
        s = win
        if velicina != "windows":
            s = round(min(win, max(1.0, root.winfo_screenheight() / float(MIN_VISINA))), 2)
        if abs(s - win) > 0.005:
            root.tk.call("tk", "scaling", s * 96.0 / 72.0)
    except (tk.TclError, ValueError):
        win = s = 1.0
    SKALA, SKALA_WINDOWS = s, win
    return SKALA


def primeni_temu(root):
    """Svetla, ravna tema: bele kartice na sivoplavoj pozadini, plavo dugme za glavnu radnju (kao Asistent PRO)."""
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except tk.TclError:
        return s
    root.configure(bg=T_POZADINA)
    for k, v in (("*Toplevel.background", T_POZADINA), ("*Font", "{Segoe UI} 10"),
                 ("*Text.background", T_POVRSINA), ("*Text.foreground", T_TEKST), ("*Text.relief", "flat"),
                 ("*Text.borderWidth", 0), ("*Text.highlightThickness", 1),
                 ("*Text.highlightBackground", T_IVICA), ("*Text.highlightColor", T_AKCENT),
                 ("*Text.selectBackground", T_IZBOR), ("*Text.selectForeground", T_TEKST),
                 ("*TCombobox*Listbox.background", T_POVRSINA), ("*TCombobox*Listbox.foreground", T_TEKST),
                 ("*TCombobox*Listbox.selectBackground", T_IZBOR), ("*TCombobox*Listbox.selectForeground", T_TEKST),
                 ("*TCombobox*Listbox.font", "{Segoe UI} 10"), ("*Menu.font", "{Segoe UI} 10")):
        root.option_add(k, v)
    s.configure(".", background=T_POZADINA, foreground=T_TEKST, font=FONT, bordercolor=T_IVICA,
                lightcolor=T_POZADINA, darkcolor=T_POZADINA, troughcolor=T_POZADINA,
                focuscolor=T_AKCENT, selectbackground=T_IZBOR, selectforeground=T_TEKST, insertcolor=T_TEKST)
    s.configure("TFrame", background=T_POZADINA)
    s.configure("Kartica.TFrame", background=T_POVRSINA)
    s.configure("TLabel", background=T_POZADINA, foreground=T_TEKST)
    s.configure("Sivo.TLabel", foreground=T_SIVO)
    s.configure("Kartica.TLabel", background=T_POVRSINA)
    s.configure("KarticaSivo.TLabel", background=T_POVRSINA, foreground=T_SIVO)
    s.configure("Naslov.TLabel", background=T_POVRSINA, font=("Segoe UI", 11, "bold"))
    s.configure("TButton", background=T_POVRSINA, foreground=T_TEKST, bordercolor=T_IVICA,
                lightcolor=T_POVRSINA, darkcolor=T_POVRSINA, padding=(px(12), px(5)), relief="flat", focusthickness=1,
                focuscolor=T_POVRSINA)
    s.map("TButton", background=[("disabled", "#f3f4f6"), ("pressed", "#e3e9f3"), ("active", "#f0f4fb")],
          foreground=[("disabled", "#a3aab6")], bordercolor=[("active", "#b9c4d6")],
          lightcolor=[("pressed", "#e3e9f3"), ("active", "#f0f4fb")], darkcolor=[("pressed", "#e3e9f3"), ("active", "#f0f4fb")])
    s.configure("Glavno.TButton", background=T_AKCENT, foreground="#ffffff", bordercolor=T_AKCENT,
                lightcolor=T_AKCENT, darkcolor=T_AKCENT, font=FONT_B, focuscolor=T_AKCENT)
    s.map("Glavno.TButton", background=[("disabled", "#a9bbe3"), ("pressed", T_AKCENT_TAMNO), ("active", "#2d63d6")],
          foreground=[("disabled", "#eef2fb")], bordercolor=[("disabled", "#a9bbe3"), ("active", "#2d63d6")],
          lightcolor=[("disabled", "#a9bbe3"), ("pressed", T_AKCENT_TAMNO), ("active", "#2d63d6")],
          darkcolor=[("disabled", "#a9bbe3"), ("pressed", T_AKCENT_TAMNO), ("active", "#2d63d6")])
    s.configure("Prekid.TButton", foreground=BOJA_NEUSPEH)
    s.configure("Mali.TButton", padding=(px(8), px(3)))
    for w in ("TEntry", "TCombobox"):
        s.configure(w, fieldbackground=T_POVRSINA, background=T_POVRSINA, bordercolor=T_IVICA,
                    lightcolor=T_POVRSINA, darkcolor=T_POVRSINA, padding=px(4), arrowcolor=T_SIVO)
        s.map(w, bordercolor=[("focus", T_AKCENT)], lightcolor=[("focus", T_AKCENT)],
              fieldbackground=[("readonly", T_POVRSINA), ("disabled", "#f3f4f6")],
              selectbackground=[("readonly", T_POVRSINA)], selectforeground=[("readonly", T_TEKST)])
    s.configure("TCheckbutton", background=T_POZADINA)
    s.configure("Kartica.TRadiobutton", background=T_POVRSINA, foreground=T_SIVO, indicatorsize=px(12),
                indicatormargin=(0, 0, px(5), 0), indicatorbackground=T_POVRSINA)
    s.map("Kartica.TRadiobutton", background=[("active", T_POVRSINA)], foreground=[("selected", T_TEKST)])
    s.configure("Treeview", background=T_POVRSINA, fieldbackground=T_POVRSINA, foreground=T_TEKST,
                bordercolor=T_POVRSINA, lightcolor=T_POVRSINA, darkcolor=T_POVRSINA, rowheight=px(30), font=FONT,
                borderwidth=0)
    s.map("Treeview", background=[("selected", T_IZBOR)], foreground=[("selected", T_TEKST)])
    s.configure("Treeview.Heading", background="#f3f5f9", foreground=T_SIVO, font=("Segoe UI", 9, "bold"),
                bordercolor=T_IVICA, lightcolor="#f3f5f9", darkcolor="#f3f5f9", relief="flat", padding=(px(8), px(7)))
    s.map("Treeview.Heading", background=[("active", "#e9edf4")], lightcolor=[("active", "#e9edf4")])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    for o in ("Vertical", "Horizontal"):
        s.configure("%s.TScrollbar" % o, background="#c9d1dd", troughcolor=T_POVRSINA, bordercolor=T_POVRSINA,
                    lightcolor="#c9d1dd", darkcolor="#c9d1dd", arrowcolor=T_SIVO, gripcount=0, relief="flat",
                    arrowsize=px(13))
        s.map("%s.TScrollbar" % o, background=[("active", "#aeb8c8")])
    s.configure("Horizontal.TProgressbar", background=T_AKCENT, troughcolor="#dde3ec", bordercolor="#dde3ec",
                lightcolor=T_AKCENT, darkcolor=T_AKCENT, thickness=px(8))
    s.configure("Sash", sashthickness=px(8), gripcount=0, background=T_POZADINA)
    s.configure("TPanedwindow", background=T_POZADINA)
    s.configure("TNotebook", background=T_POZADINA, bordercolor=T_IVICA, tabmargins=(0, 4, 0, 0))
    s.configure("TNotebook.Tab", background="#e3e8f0", foreground=T_SIVO, padding=(px(16), px(7)), bordercolor=T_IVICA,
                lightcolor="#e3e8f0", font=("Segoe UI", 10, "bold"))
    s.map("TNotebook.Tab", background=[("selected", T_POVRSINA)], foreground=[("selected", T_ZAGLAVLJE)],
          lightcolor=[("selected", T_POVRSINA)])
    s.configure("TLabelframe", background=T_POZADINA, bordercolor=T_IVICA, lightcolor=T_POZADINA,
                darkcolor=T_POZADINA, relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=T_POZADINA, foreground=T_ZAGLAVLJE, font=FONT_B)
    s.configure("TSeparator", background=T_IVICA)
    return s


def kartica(roditelj, **kw):
    """Bela kartica sa tankim okvirom (kao u Asistent PRO)."""
    return tk.Frame(roditelj, bg=T_POVRSINA, highlightthickness=1, highlightbackground=T_IVICA,
                    highlightcolor=T_IVICA, **kw)


def tackasta(roditelj, bg=T_POVRSINA):
    """Tackasta linija kao na stranici izvoda sa eKatastra."""
    c = tk.Canvas(roditelj, height=3, bg=bg, highlightthickness=0, borderwidth=0)
    c.bind("<Configure>", lambda e: (c.delete("all"), c.create_line(0, 1, e.width, 1, fill=EK_TACKE, dash=(1, 3))))
    return c


def _ima_svoj_klizac(w):
    """Tabela, tekst ili lista čiji sadržaj ne stane ceo: točkić iznad nje pomera samo nju (ona to radi sama)."""
    if not isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox)):
        return False
    try:
        a, b = (float(x) for x in w.yview())
    except (tk.TclError, TypeError, ValueError):
        return False
    return a > 0.0 or b < 1.0


def _tocak_misa(e):
    """Tockic misa pomera okvir sa klizacem (skrol_okvir) ispod kursora; ostalo se ne dira. Iznad tabele koja ima
    svoj klizač (npr. 193 stana) pomera se samo ta tabela, ne i cela stranica (Dejan, v23)."""
    try:
        w = e.widget.winfo_containing(e.x_root, e.y_root) if not isinstance(e.widget, str) else None
        while w is not None and not isinstance(w, str):
            if _ima_svoj_klizac(w):
                return
            if getattr(w, "skrol", False):
                if e.delta:
                    w.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
                else:
                    w.yview_scroll(1 if e.num == 5 else -1, "units")
                return
            w = w.master
    except tk.TclError:
        pass


def skrol_okvir(roditelj, bg=T_POVRSINA):
    """Okvir sa klizacem (Canvas + Frame); tockic misa radi dok je kursor iznad njega."""
    cv = tk.Canvas(roditelj, bg=bg, highlightthickness=0, borderwidth=0)
    sb = ttk.Scrollbar(roditelj, orient="vertical", command=cv.yview)
    cv.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    cv.pack(side="left", fill="both", expand=True)
    f = tk.Frame(cv, bg=bg)
    prozor = cv.create_window(0, 0, window=f, anchor="nw")
    f.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
    cv.bind("<Configure>", lambda e: cv.itemconfigure(prozor, width=e.width))

    cv.skrol = True
    roditelj.bind_all("<MouseWheel>", _tocak_misa)
    roditelj.bind_all("<Button-4>", _tocak_misa)
    roditelj.bind_all("<Button-5>", _tocak_misa)
    f.platno = cv
    return f


BG_STARO, FG_STARO = "#fde2e2", "#b42318"      # v31: šta je bilo (promenjeni deo)
BG_NOVO_IZM, FG_NOVO_IZM = "#d3f2dd", "#0f6b35"  # v31: šta je sada (promenjeni deo)


def _visina_po_sadrzaju(t):
    """Visina ćelije (Text) tačno koliko redova zauzima njen tekst na trenutnoj širini."""
    try:
        r = t.count("1.0", "end", "update", "displaylines")
    except tk.TclError:
        return
    n = r if isinstance(r, int) else (r[0] if r else 1)
    n = max(1, int(n or 1))
    if int(t.cget("height")) != n:
        t.configure(height=n)


def tabela_promena(roditelj, promene, bg=T_POVRSINA):
    """v31: promene u tri kolone - stavka | staro stanje | novo stanje; promenjeni deo crveno (bilo) i zeleno (sada)."""
    f = tk.Frame(roditelj, bg=T_IVICA)
    f.columnconfigure(0, weight=0)
    f.columnconfigure(1, weight=1, uniform="sn")
    f.columnconfigure(2, weight=1, uniform="sn")
    f.celije, tekst = [], []

    def celija(red, kol, delovi, zaglavlje=False, sirina=10):
        t = tk.Text(f, wrap="word", font=FONT_B if zaglavlje else FONT, height=1, width=sirina, padx=8, pady=3,
                    borderwidth=0, highlightthickness=0, cursor="arrow", takefocus=0,
                    bg=T_GRUPA if zaglavlje else T_POVRSINA, fg=T_ZAGLAVLJE if zaglavlje else T_TEKST)
        t.tag_configure("polje", foreground=T_SIVO)
        t.tag_configure("gde", font=FONT_B)
        t.tag_configure("nema", foreground=T_SIVO)
        t.tag_configure("izmena_staro", background=BG_STARO, foreground=FG_STARO, font=FONT_B)
        t.tag_configure("izmena_novo", background=BG_NOVO_IZM, foreground=FG_NOVO_IZM, font=FONT_B)
        for deo, vrsta in delovi:
            t.insert("end", deo, ("izmena_staro" if kol == 1 else "izmena_novo") if vrsta == "izmena" else vrsta)
        t.configure(state="disabled")
        t.grid(row=red, column=kol, sticky="nsew", padx=(0 if kol else 1, 1), pady=(0 if red else 1, 1))
        t.bind("<Configure>", lambda e, t=t: _visina_po_sadrzaju(t))
        f.celije.append(t)
        return t

    celija(0, 0, [("", "")], True, 24)
    celija(0, 1, [("Staro stanje", "")], True)
    celija(0, 2, [("Novo stanje", "")], True)
    for i, pr in enumerate(promene, 1):
        celija(i, 0, [(pr["gde"] or "-", "gde")], sirina=24)
        celija(i, 1, pr["staro"] or [("nije postojalo", "nema")])
        celija(i, 2, pr["novo"] or [("više ne postoji", "nema")])
        tekst.append(red_promene(pr))
    f.tekst = "\n".join(tekst)
    return f


def nacrtaj_izvod(f, sekcije, vreme=None, prazno=None):
    """Sadrzaj prozora 'Подаци о непокретности' kao na sajtu: zaglavlje RGZ, naslov izvoda i sekcije sa
    parovima polje / vrednost (40% / 60%). Vraca prikazani tekst (za proveru)."""
    bg = f.cget("bg")
    f.columnconfigure(0, weight=2, uniform="kv")
    f.columnconfigure(1, weight=3, uniform="kv")
    tekst, parovi = [], []
    red = [0]

    def dodaj(w, **kw):
        w.grid(row=red[0], column=0, columnspan=2, sticky="we", **kw)
        red[0] += 1

    zag = tk.Frame(f, bg=bg)
    for s in ("Република Србија", "Републички геодетски завод", "Геодетско-катастарски информациони систем"):
        tk.Label(zag, text=s, bg=bg, fg=EK_NASLOV, font=("Trebuchet MS", 12, "bold"), anchor="w").pack(anchor="w")
    dodaj(zag, padx=14, pady=(12, 8))
    dodaj(tackasta(f, bg), padx=8)
    dodaj(tk.Label(f, text="katastar.rgz.gov.rs/eKatastarPublic  |  %s" % (vreme or "podaci iz poslednje provere"),
                   bg=bg, fg=T_SIVO, font=("Segoe UI", 9), anchor="w"), padx=14, pady=5)
    dodaj(tackasta(f, bg), padx=8)
    dodaj(tk.Label(f, text="Извод из базе података катастра непокретности", bg=bg, fg=EK_NASLOV,
                   font=("Trebuchet MS", 14, "bold")), pady=(14, 8))
    tekst.append("Извод из базе података катастра непокретности")
    if not sekcije:
        dodaj(tk.Label(f, text=prazno or "Podaci sa sajta za ovu stavku nisu učitani (Alati -> učitavanje vlasnika, "
                               "pa ponovi pretragu ili proveru).", bg=bg, fg=T_SIVO, font=FONT, wraplength=px(760),
                       justify="center"), padx=14, pady=10)
        if prazno:
            tekst.append(prazno)
    for s in sekcije or []:
        glavna = bool(re.match(r"^\d+\.", s["naslov"])) or s["naslov"] == "Подаци о непокретности"
        dodaj(tk.Label(f, text=s["naslov"], bg=EK_SEKCIJA if glavna else EK_PODSEKCIJA, fg=EK_NASLOV,
                       font=("Segoe UI", 11 if glavna else 10, "bold"), anchor="w", padx=8, pady=5),
              padx=8, pady=((16 if glavna else 10), 2))
        tekst.append(s["naslov"])
        for zi, z in enumerate(s["zapisi"]):
            if zi:
                dodaj(tk.Frame(f, bg="#b9c4d6", height=1), padx=8, pady=(6, 6))
            for k, v in z:
                kl = tk.Label(f, text=k + ":", bg=bg, fg=T_TEKST, font=FONT_B, anchor="nw", justify="left",
                              wraplength=px(300))
                kl.grid(row=red[0], column=0, sticky="nwe", padx=(16, 6), pady=(3, 1))
                boja, font = T_TEKST, FONT
                if k.startswith("Лице уписано"):
                    boja, font = ("#000080" if v.startswith("ДА") else "#b22222"), FONT_B
                vl = tk.Label(f, text=v, bg=bg, fg=boja, font=font, anchor="nw", justify="left", wraplength=px(460))
                vl.grid(row=red[0], column=1, sticky="nwe", padx=(6, 12), pady=(3, 1))
                parovi.append((kl, vl))
                red[0] += 1
                dodaj(tackasta(f, bg), padx=12)
                tekst.append("%s: %s" % (k, v))
        for t in s["tekst"]:
            dodaj(tk.Label(f, text="*** %s ***" % t, bg=bg, fg=T_SIVO, font=FONT, anchor="w"), padx=16, pady=4)
            tekst.append(t)
    dodaj(tk.Frame(f, bg=bg, height=16))

    def prelom(e):
        for kl, vl in parovi:
            kl.configure(wraplength=max(px(120), int(e.width * 0.4) - px(30)))
            vl.configure(wraplength=max(px(160), int(e.width * 0.6) - px(30)))
    f.bind("<Configure>", prelom, add="+")
    return "\n".join(tekst)


def sekcije_iz_redova(redovi):
    """Kad originalna stranica nije sacuvana: redovi iz snimka -> sekcije za prikaz kao na sajtu."""
    out = []
    for sek, zapisi in grupisi_redove(redovi):
        s = {"naslov": sek, "zapisi": [], "tekst": []}
        for z in zapisi:
            (s["tekst"] if isinstance(z, str) else s["zapisi"]).append(z)
        out.append(s)
    return out


def dir_izvoda(ko_id, ko, broj):
    ime = re.sub(r"[^\w\-]+", "_", "%s_%s_%s" % (ko_id, ko, broj), flags=re.U).strip("_")
    return os.path.join(IZVODI_DIR, ime)


def sa_osnovom(t):
    """Stranica sa sajta dobija <base>, da se u pregledacu otvori sa slikama i stilom sa eKatastra."""
    osnova = '<base href="%s">' % htmlmod.escape(BASE)
    m = re.search(r"<head[^>]*>", t or "", re.I)
    return (t[:m.end()] + osnova + t[m.end():]) if m else osnova + (t or "")


def ime_izvoda(kljuc):
    """Ime fajla stranice u izvodi/: uvek isto za istu stavku (prozor otvoren dok se ucitava ostaje ispravan)."""
    return "parcela.html" if kljuc == "parcela" else "d%s.html" % hashlib.md5(kljuc.encode("utf-8")).hexdigest()[:10]


def _indeks_izvoda(d):
    try:
        with open(os.path.join(d, "indeks.json"), encoding="utf-8") as f:
            indeks = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(indeks, dict):
        return {}
    return {k: v for k, v in indeks.items() if isinstance(v, dict) and v.get("fajl")}


def _upisi_indeks(d, indeks):
    with open(os.path.join(d, "indeks.json"), "w", encoding="utf-8") as f:
        json.dump(indeks, f, ensure_ascii=False, indent=1)


def sacuvaj_izvode(ko_id, ko, broj, stranice, potpuno=True, redosled=None):
    """Originalne stranice 'Podaci o nepokretnosti' (poslednje preuzete) idu u izvodi/<KO>_<broj>/, da se u
    programu prikazu cele i da se otvore u pregledacu isto kao na sajtu. Vraca folder ili None.
    potpuno=False (ucitavanje prekinuto, sajt trazio pauzu, neka stranica nije stigla): ranije sacuvane stranice
    stavki koje sada nisu ucitane ostaju."""
    stranice = {k: v for k, v in (stranice or {}).items() if v}
    if not stranice:
        return None
    d = dir_izvoda(ko_id, ko, broj)
    os.makedirs(d, exist_ok=True)
    vreme = dt.datetime.now().strftime("%d.%m.%Y. %H:%M:%S")
    novi = {}
    for kljuc, t in stranice.items():
        fajl = ime_izvoda(kljuc)
        with open(os.path.join(d, fajl), "w", encoding="utf-8") as f:
            f.write(sa_osnovom(t))
        novi[kljuc] = {"fajl": fajl, "vreme": vreme}
    ostaju = {}
    if not potpuno:
        zauzeti = {v["fajl"] for v in novi.values()}
        for kljuc, x in _indeks_izvoda(d).items():
            if kljuc not in novi and x["fajl"] not in zauzeti and os.path.isfile(os.path.join(d, x["fajl"])):
                ostaju[kljuc] = x
    sve = {**novi, **ostaju}
    red = [k for k in (redosled or []) if k in sve] + list(novi) + list(ostaju)     # redom kao na sajtu
    indeks = {k: sve[k] for k in dict.fromkeys(red)}
    for ime in os.listdir(d):
        if ime.endswith(".html") and ime not in {v["fajl"] for v in indeks.values()}:
            try:
                os.remove(os.path.join(d, ime))
            except OSError:
                pass
    _upisi_indeks(d, indeks)
    return d


def dodaj_izvod(ko_id, ko, broj, kljuc, t, redosled=None):
    """Jedna stranica 'Podaci o nepokretnosti' dodaje se u izvodi/ parcele, a ostale ostaju (stavka skinuta iz
    prozora parcele; redosled = stavke redom kao na sajtu, da i PDF bude tim redom)."""
    if not t:
        return None
    d = dir_izvoda(ko_id, ko, broj)
    os.makedirs(d, exist_ok=True)
    indeks = _indeks_izvoda(d)
    fajl = ime_izvoda(kljuc)
    with open(os.path.join(d, fajl), "w", encoding="utf-8") as f:
        f.write(sa_osnovom(t))
    indeks[kljuc] = {"fajl": fajl, "vreme": dt.datetime.now().strftime("%d.%m.%Y. %H:%M:%S")}
    if redosled:
        indeks = {k: indeks[k] for k in dict.fromkeys([k for k in redosled if k in indeks] + list(indeks))}
    _upisi_indeks(d, indeks)
    return d


def ucitaj_izvod(ko_id, ko, broj, kljuc):
    """(html, vreme izvoda, putanja) za sacuvanu stranicu ili (None, None, None)."""
    try:
        d = dir_izvoda(ko_id, ko, broj)
        with open(os.path.join(d, "indeks.json"), encoding="utf-8") as f:
            x = json.load(f)[kljuc]
        put = os.path.join(d, x["fajl"])
        with open(put, encoding="utf-8") as f:
            t = f.read()
    except (OSError, ValueError, KeyError, TypeError):
        return None, None, None
    m = re.search(r"eKatastarPublic(?:&nbsp;|\s)*\|(?:&nbsp;|\s)*([^<]+)<", t)
    return t, (m.group(1).strip() if m else x.get("vreme")), put


def izvodi_za_pdf(ko_id, ko, broj):
    """[(opis, putanja)] sacuvanih originala 'Подаци о непокретности' parcele, redom kao na sajtu
    (parcela, pa objekti, pa posebni delovi)."""
    d = dir_izvoda(ko_id, ko, broj)
    try:
        with open(os.path.join(d, "indeks.json"), encoding="utf-8") as f:
            indeks = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for kljuc, x in indeks.items():
        put = os.path.join(d, str(x.get("fajl", "")))
        if os.path.isfile(put):
            out.append((kljuc, put))
    return out


def poslovi_pdf(mesta):
    """[(ko_id, ko, broj)] -> ([(html, ime.pdf)], [parcele bez sačuvanih originala])."""
    poslovi, bez = [], []
    for ko_id, ko, broj in mesta:
        izv = izvodi_za_pdf(ko_id, ko, broj)
        if not izv:
            bez.append("%s %s" % (ko, broj))
        for n, (opis, put) in enumerate(izv, 1):
            poslovi.append((put, ime_fajla("%s %s - %d %s" % (ko, broj, n, opis)) + ".pdf"))
    return poslovi, bez


# --- v32 (Dejan: "kada ti ubacim ugovor i kazem izvuci sve parcele"): zadatak koji Claude ostavi u folderu zadaci ---
# {"naziv", "klijent", "grupa" (podrazumevano klijent), "pdf": true, "folder" (gde PDF; inače stalni ili PDF),
#  "postojece": "preskoci" | "premesti" | "proveri" (v35, parcela koja je već u praćenju; podrazumevano preskoci),
#  "parcele": [{"opstina" ili "opstina_id", "ko" ili "ko_id", "broj", "stan", "ulaz", "napomena"}]}
# v35: zadatak može da stigne i preko Drive-a (folder ASISTENT KATASTAR/zadaci), izveštaj se vraća u izvestaji/ tamo
POSTOJECE = ("preskoci", "premesti", "proveri")
DRIVE_FOLDER = "ASISTENT KATASTAR"


def nadji_drive_folder():
    """v35: folder ASISTENT KATASTAR na Google Drive-u (Drive za računare: G:\\My Drive\\...), ili None."""
    zadat = os.environ.get("KATASTAR_DRIVE")
    if zadat is not None or TEST_REZIM:
        return zadat if zadat and os.path.isdir(zadat) else None
    kandidati = []
    if os.name == "nt":
        for slovo in "GHIJKLMNOPQRSTUVWXYZDEF":
            if not os.path.isdir(slovo + ":\\"):
                continue
            for koren in ("My Drive", "Moj disk", "Мој диск", "Moja disk"):
                kandidati.append(os.path.join(slovo + ":\\", koren, DRIVE_FOLDER))
    kucni = os.path.expanduser("~")
    kandidati += [os.path.join(kucni, "Google Drive", "My Drive", DRIVE_FOLDER),
                  os.path.join(kucni, "My Drive", DRIVE_FOLDER)]
    return next((k for k in kandidati if os.path.isdir(k)), None)


def ucitaj_zadatak(put):
    """JSON zadatak -> dict; ValueError sa razlogom ako nije ispravan."""
    with open(put, encoding="utf-8-sig") as f:
        d = json.load(f)
    if not isinstance(d, dict) or not isinstance(d.get("parcele"), list) or not d["parcele"]:
        raise ValueError("nema spiska parcela")
    parcele = []
    for i, x in enumerate(d["parcele"], 1):
        if not isinstance(x, dict):
            raise ValueError("parcela %d nije ispravno zapisana" % i)
        broj = "".join(str(x.get("broj") or "").split())
        if not re.fullmatch(r"[0-9]{1,6}(/[0-9]{1,3})?", broj):
            raise ValueError("parcela %d: neispravan broj parcele (%s)" % (i, broj or "prazno"))
        p = {k: norm(str(x.get(k) or "")) for k in ("opstina", "ko", "stan", "ulaz", "napomena")}
        for k in ("opstina_id", "ko_id"):
            try:
                p[k] = int(x[k]) if x.get(k) not in (None, "") else None
            except (TypeError, ValueError):
                raise ValueError("parcela %s: %s nije broj" % (broj, k))
        if not (p["ko_id"] or p["ko"]):
            raise ValueError("parcela %s: nije navedena katastarska opština" % broj)
        p["broj"] = broj
        parcele.append(p)
    klijent = norm(str(d.get("klijent") or ""))
    postojece = norm(str(d.get("postojece") or "preskoci")).lower()
    if postojece not in POSTOJECE:
        raise ValueError("postojece mora biti %s (a ne %s)" % (", ".join(POSTOJECE), postojece))
    return {"naziv": norm(str(d.get("naziv") or "")) or klijent or os.path.splitext(os.path.basename(put))[0],
            "klijent": klijent, "grupa": norm(str(d.get("grupa") or "")) or klijent,
            "sacuvaj_pdf": d.get("pdf", True) is not False, "folder": str(d.get("folder") or "").strip(),
            "postojece": postojece, "parcele": parcele}


def izvestaj_zadatka_tekst(z):
    """Izveštaj zadatka za čitanje (Claude ga prenosi Dejanu)."""
    red = ["Zadatak: %s" % z.get("naziv", z.get("fajl", "")), "Završeno: %s" % sada()]
    if z.get("greska"):
        red.append("NIJE ZAVRŠEN: %s" % z["greska"])
    for r in z.get("rezultat", []):
        red.append("- %s %s%s: %s%s%s" % (r["ko"], r["broj"], (" stan " + r["stan"]) if r.get("stan") else "",
                                         r["stanje"] + (" (nije ponovo proverena)" if r.get("preskocena") else ""),
                                         ("; provera: %s" % r["provera"]) if r.get("provera") else "",
                                         ("; " + r["napomena"]) if r.get("napomena") else ""))
    pdf = z.get("pdf_rez")
    if pdf:
        red.append("PDF: sačuvano %d u %s" % (pdf["sacuvano"], pdf["folder"]))
        red += ["  nije napravljen: %s" % x for x in pdf["nije"]]
        if pdf["bez_originala"]:
            red.append("  bez listova sa sajta: %s" % ", ".join(pdf["bez_originala"]))
    return "\n".join(red) + "\n"


def ime_fajla(t, duzina=150):
    """Naziv fajla bez znakova koje Windows ne dozvoljava (/ u broju parcele postaje -)."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", str(t))
    t = " ".join(t.split()).strip(" .")
    return t[:duzina].rstrip(" .") or "izvod"


def nadji_pregledac():
    """Microsoft Edge ili Google Chrome: PDF prave isto kao "Штампај" na sajtu > Sacuvaj kao PDF."""
    zadat = os.environ.get("KATASTAR_PREGLEDAC")
    if zadat:
        return zadat if os.path.isfile(zadat) else None
    kandidati = []
    if os.name == "nt":
        try:
            import winreg
            for exe in ("msedge.exe", "chrome.exe"):
                for koren in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        with winreg.OpenKey(koren, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + exe) as k:
                            kandidati.append(winreg.QueryValue(k, None))
                    except OSError:
                        pass
        except ImportError:
            pass
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            b = os.environ.get(env)
            if b:
                kandidati += [os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe"),
                              os.path.join(b, "Google", "Chrome", "Application", "chrome.exe")]
    else:
        kandidati += [shutil.which(x) or "" for x in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]
    for k in kandidati:
        k = (k or "").strip().strip('"')
        if k and os.path.isfile(k):
            return k
    return None


def html_u_pdf(pregledac, html, pdf, profil, cekaj=120):
    """Originalna stranica (sa stilom za stampu sa eKatastra) u PDF, bez zaglavlja i podnozja pregledaca
    (na stranici vec pise katastar.rgz.gov.rs i vreme izvoda). Pregledac radi nevidljivo, u svom profilu.
    Papir A4 kao kad se stampa iz pregledaca u Srbiji (pregledac bez prozora inace uzima americki Letter)."""
    with open(html, encoding="utf-8") as f:
        t = f.read()
    a4 = '<style media="print">@page { size: A4; }</style>'
    m = re.search(r"</head\s*>", t, re.I)
    t = (t[:m.start()] + a4 + t[m.start():]) if m else a4 + t
    kopija = os.path.join(profil, "stranica.html")
    with open(kopija, "w", encoding="utf-8") as f:
        f.write(t)
    komanda = [pregledac, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--disable-extensions", "--user-data-dir=" + profil, "--no-pdf-header-footer",
               "--print-to-pdf-no-header", "--print-to-pdf=" + pdf, pathlib.Path(kopija).as_uri()]
    if os.name != "nt":
        komanda.insert(1, "--no-sandbox")
    subprocess.run(komanda, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=cekaj,
                   creationflags=0x08000000 if os.name == "nt" else 0)      # bez crnog prozora
    return os.path.isfile(pdf) and os.path.getsize(pdf) > 0


KOLONE_PRETRAGE = [("ko", "KO", 130, "w"), ("parcela", "Parcela", 80, "w"), ("deo", "Delova", 65, "center"),
                   ("povrsina", "Površina m²", 100, "e"), ("ulica", "Ulica / potes", 160, "w"),
                   ("nacin", "Način korišćenja", 250, "w"), ("objekti", "Objekata", 80, "center"),
                   ("posebni", "Posebnih delova", 115, "center"), ("vlasnici", "Vlasnici parcele (udeo)", 320, "w"),
                   ("tereti", "Tereti", 150, "w"), ("status", "Status", 170, "w")]


class PredloziListe:
    """Padajuca lista u koju moze i da se kuca: upises deo naziva (cirilicom ili latinicom, sa ili bez
    kvacica, npr. 'vozd' ili 'зем') i ispod polja iskacu odgovarajuce stavke. Strelica na polju i dalje
    otvara ceo spisak. Enter, Tab ili klik bira stavku; strelice gore/dole se krecu kroz predloge."""
    REDOVA = 8
    _PRESKOCI = ("Up", "Down", "Return", "KP_Enter", "Tab", "ISO_Left_Tab", "Escape", "Prior", "Next")

    def __init__(self, cb, izabrano=None, kucanje=None, dalje=None):
        self.cb = cb
        self.izabrano = izabrano        # posle izbora stavke (kucanjem ili iz spiska)
        self.kucanje = kucanje          # tekst u polju se promenio
        self.dalje = dalje              # polje koje dobija fokus kad se stavka izabere Enterom
        self.prazno = "nema takvog naziva"     # tekst u listi kad nista ne odgovara
        self.lb = None
        self.pogoci = []
        self._tekst = cb.get()
        cb.bind("<KeyRelease>", self._pusten, add="+")
        cb.bind("<Down>", lambda e: self._pomeri(1))
        cb.bind("<Up>", lambda e: self._pomeri(-1))
        cb.bind("<Return>", self._enter)
        cb.bind("<KP_Enter>", self._enter)
        cb.bind("<Tab>", self._tab, add="+")
        cb.bind("<Escape>", self._esc)
        cb.bind("<FocusOut>", lambda e: cb.after(150, self._posle_fokusa), add="+")
        cb.bind("<FocusIn>", lambda e: cb.after_idle(self._oznaci_sve), add="+")
        cb.bind("<<ComboboxSelected>>", self._iz_spiska, add="+")
        top = cb.winfo_toplevel()
        top.bind("<Button-1>", self._klik_negde, add="+")
        top.bind("<Configure>", lambda e: self.sakrij() if e.widget is top else None, add="+")

    # --- pomocno ---
    def vrednosti(self):
        v = self.cb.cget("values")
        return list(v) if v else []

    def nadji(self, tekst):
        """Stavke koje odgovaraju upisanom tekstu: prvo one koje tako pocinju, pa one u kojima neka rec tako
        pocinje, pa ostale koje sadrze tekst."""
        t = lat(tekst).strip()
        if not t:
            return []
        vr = self.vrednosti()
        lv = {v: lat(v) for v in vr}
        pocetak = [v for v in vr if lv[v].startswith(t)]
        rec = [v for v in vr if v not in pocetak and any(r.startswith(t) for r in re.split(r"[\s\-(),.]+", lv[v]))]
        deo = [v for v in vr if v not in pocetak and v not in rec and t in lv[v]]
        return pocetak + rec + deo

    def razresi(self):
        """Stavka na koju se odnosi upisani tekst (ista bez obzira na pismo, ili jedina koja odgovara) ili None."""
        tekst = self.cb.get()
        t = lat(tekst).strip()
        if not t:
            return None
        tacno = [v for v in self.vrednosti() if lat(v).strip() == t]
        if tacno:
            return tacno[0]
        pog = self.nadji(tekst)
        return pog[0] if len(pog) == 1 else None

    def vidljiv(self):
        try:
            return self.lb is not None and bool(self.lb.winfo_ismapped())
        except tk.TclError:
            return False

    def sakrij(self):
        if self.lb is not None:
            try:
                self.lb.place_forget()
            except tk.TclError:
                self.lb = None

    def _oznaci_sve(self):
        try:
            if str(self.cb.cget("state")) != "disabled" and self.cb.focus_get() is self.cb:
                self.cb.selection_range(0, "end")
        except (KeyError, tk.TclError):
            pass

    # --- predlozi ---
    def osvezi(self):
        tekst = self.cb.get()
        self.pogoci = self.nadji(tekst)
        if not tekst.strip() or (len(self.pogoci) == 1 and self.pogoci[0] == tekst):
            self.sakrij()
            return
        self.prikazi()

    def prikazi(self):
        top = self.cb.winfo_toplevel()
        if self.lb is None or not self.lb.winfo_exists():
            self.lb = tk.Listbox(top, activestyle="none", exportselection=False, takefocus=0, font=FONT,
                                 bg=T_POVRSINA, fg=T_TEKST, selectbackground=T_IZBOR, selectforeground=T_TEKST,
                                 relief="flat", bd=0, highlightthickness=1, highlightbackground=T_AKCENT,
                                 highlightcolor=T_AKCENT)
            self.lb.bind("<Button-1>", self._klik_na_predlog)
            self.lb.bind("<Motion>", self._ispod_misa)
            self.lb.bind("<MouseWheel>", lambda e: (self.lb.yview_scroll(-1 if e.delta > 0 else 1, "units"),
                                                    "break")[1])
        lb = self.lb
        lb.delete(0, "end")
        if self.pogoci:
            for v in self.pogoci:
                lb.insert("end", v)
            lb.selection_set(0)
            lb.activate(0)
        else:
            lb.insert("end", self.prazno)
            lb.itemconfigure(0, foreground=T_SIVO, selectforeground=T_SIVO, selectbackground=T_POVRSINA)
        top.update_idletasks()
        x = self.cb.winfo_rootx() - top.winfo_rootx()
        y = self.cb.winfo_rooty() - top.winfo_rooty() + self.cb.winfo_height()
        lb.configure(height=max(1, min(self.REDOVA, lb.size())))
        lb.place(x=x, y=y, width=max(self.cb.winfo_width(), px(260)))
        lb.lift()

    def izaberi(self, v):
        self.sakrij()
        vr = self.vrednosti()
        if v in vr:
            self.cb.current(vr.index(v))
        else:
            self.cb.set(v)
        self._tekst = self.cb.get()
        try:
            self.cb.selection_clear()
            self.cb.icursor("end")
        except tk.TclError:
            pass
        if self.izabrano:
            self.izabrano()

    def _kandidat(self):
        if self.vidljiv() and self.pogoci:
            sel = self.lb.curselection()
            return self.pogoci[sel[0] if sel else 0]
        return self.razresi()

    # --- dogadjaji ---
    def _pusten(self, e):
        if e.keysym in self._PRESKOCI or e.keysym.startswith(("Shift", "Control", "Alt", "Caps", "Super", "Win")):
            return
        tekst = self.cb.get()
        if tekst != self._tekst:
            self._tekst = tekst
            if self.kucanje:
                self.kucanje()
        self.osvezi()

    def _pomeri(self, d):
        if not self.vidljiv() or not self.pogoci:
            return None                      # bez predloga strelica otvara ceo spisak (kao i ranije)
        sel = self.lb.curselection()
        i = max(0, min(len(self.pogoci) - 1, (sel[0] if sel else -1) + d))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.activate(i)
        self.lb.see(i)
        return "break"

    def _enter(self, e=None):
        v = self._kandidat()
        if v:
            self.izaberi(v)
            if self.dalje is not None:
                try:
                    self.dalje.focus_set()
                except tk.TclError:
                    pass
        return "break"

    def _tab(self, e=None):
        if self.vidljiv():
            v = self._kandidat()
            if v:
                self.izaberi(v)
        return None

    def _esc(self, e=None):
        if self.vidljiv():
            self.sakrij()
            return "break"
        return None

    def _posle_fokusa(self):
        try:
            f = self.cb.focus_get()
        except (KeyError, tk.TclError):
            f = None
        if f is self.cb:
            return
        if f is not None and str(f).startswith(str(self.cb) + "."):
            self.sakrij()                    # otvoren je ceo spisak (strelica na polju)
            return
        self.sakrij()
        try:
            if self.cb.winfo_exists() and self.cb.current() < 0 and self.cb.get().strip():
                v = self.razresi()
                if v:
                    self.izaberi(v)
        except tk.TclError:
            pass

    def _iz_spiska(self, e=None):
        self.sakrij()
        self._tekst = self.cb.get()
        if self.izabrano:
            self.izabrano()

    def _klik_na_predlog(self, e):
        if self.pogoci:
            i = self.lb.nearest(e.y)
            if 0 <= i < len(self.pogoci):
                self.izaberi(self.pogoci[i])
                self.cb.focus_set()
        return "break"

    def _ispod_misa(self, e):
        if self.pogoci:
            i = self.lb.nearest(e.y)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.lb.activate(i)

    def _klik_negde(self, e):
        if self.vidljiv() and e.widget is not self.lb and e.widget is not self.cb:
            self.sakrij()


def slika_izbora(vrsta, vel):
    """Kvadratic na pocetku reda u prozoru parcele: 'ne' = nije skinuto (prazan), 'da' = oznaceno za skidanje
    (plavo, kvacica), 'ima' = skinuto sa sajta (zeleno, kvacica)."""
    ivica, pozadina = {"ne": ("#8a97a8", "#ffffff"), "da": ("#1f5fbf", "#2f6fd6"), "ima": ("#2a7d4f", "#3a9d5d")}[vrsta]
    deb = max(2.0, vel / 7.0)
    tacke = [(0.22, 0.52), (0.42, 0.72), (0.78, 0.30)]

    def do_duzi(x, y, a, b):
        (x1, y1), (x2, y2) = a, b
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        return ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** 0.5

    redovi = []
    for j in range(vel):
        red = []
        for i in range(vel):
            if i in (0, vel - 1) or j in (0, vel - 1):
                c = ivica
            elif vrsta != "ne" and min(do_duzi(i + 0.5, j + 0.5, (a[0] * vel, a[1] * vel), (b[0] * vel, b[1] * vel))
                                       for a, b in zip(tacke, tacke[1:])) <= deb / 2:
                c = "#ffffff"
            else:
                c = pozadina
            red.append(c)
        redovi.append("{" + " ".join(red) + "}")
    img = tk.PhotoImage(width=vel, height=vel)
    img.put(" ".join(redovi))
    return img


class KopiranjeCelija:
    """Kao u Asistent PRO: pritisak na celiju izabere red (poplavi) i preko celije stavi nevidljivo polje sa istim
    tekstom, pa prevlacenje misem odmah oznacava deo teksta (npr. samo broj predmeta), kao u Wordu; Ctrl+C ga
    kopira. Polje se ne vidi: celija izgleda isto, vidi se samo oznaceni deo. Ctrl+C u listi kopira izabrane
    redove (kolone razdvojene tabom, lepi se pravo u Excel ili Word). Dvoklik i Enter rade isto sto i ranije."""
    POMAK_TEKSTA = 4            # gde pocinje tekst u celiji u odnosu na levu ivicu celije (clam tema)
    POMAK_STABLA = 18           # isto za prvu kolonu stabla: bbox uracunava uvlaku, ostaje mesto strelice
    UVLAKA_POLJA = 1            # tk.Entry crta tekst 1 piksel od svoje leve ivice (bez okvira)

    def __init__(self, app, tree, otvori=None, preskoci=None, meni=None, kolona_broja=None, bez_stabla=False):
        self.app, self.tree = app, tree
        self.bez_stabla = bez_stabla                    # prva kolona (#0) je samo kvadratic izbora - ne kopira se
        self.otvori = otvori                            # sta radi dvoklik / Enter
        self.preskoci = preskoci or (lambda iid: False)  # redovi bez polja (grupe, "nema")
        self.meni = meni                                # fn(menu, iid): dodatne stavke desnog klika na polje
        self.kolona_broja = kolona_broja                # (kolona, opis) za "Kopiraj broj parcele"
        self.e = None
        self.info = None
        self.sidro = None                               # granica u tekstu od koje je pocelo prevlacenje
        tree.bind("<Button-1>", self._pritisak, add="+")
        tree.bind("<B1-Motion>", self._vuci, add="+")
        tree.bind("<ButtonRelease-1>", self._otpustanje, add="+")
        tree.bind("<<TreeviewSelect>>", self._izbor_promenjen, add="+")
        for t in ("<Control-c>", "<Control-C>"):
            tree.bind(t, lambda ev: (self.kopiraj_redove(), "break")[1])
        app._kopiranja.append(self)

    # --- tekst ---
    def kolona_na(self, x, iid=None):
        """Kolona pod misem. identify_column prva 4 piksela kolone racuna u prethodnu (mesto za razvlacenje
        kolone), pa se za red gleda okvir svake celije."""
        if iid and self.tree.exists(iid):
            for k in self.kolone():
                try:
                    bb = self.tree.bbox(iid, k)
                except tk.TclError:
                    bb = ""
                if bb and bb[0] <= x < bb[0] + bb[2]:
                    return k
        c = self.tree.identify_column(x)
        if c == "#0":
            return None if self.bez_stabla else "#0"
        if not c.startswith("#"):
            return None
        prikazane = self.tree["displaycolumns"]
        if prikazane in ("#all", ("#all",)):
            prikazane = self.tree["columns"]
        i = int(c[1:]) - 1
        return prikazane[i] if 0 <= i < len(prikazane) else None

    def kolone(self):
        prikazane = self.tree["displaycolumns"]
        if prikazane in ("#all", ("#all",)):
            prikazane = self.tree["columns"]
        sa_stablom = "tree" in str(self.tree.cget("show")) and not self.bez_stabla
        return (["#0"] if sa_stablom else []) + list(prikazane)

    def tekst_celije(self, iid, kol):
        if kol == "#0":
            return str(self.tree.item(iid, "text"))
        return str(self.tree.set(iid, kol))

    def tekst_reda(self, iid):
        return "\t".join(self.tekst_celije(iid, k) for k in self.kolone())

    def redovi_za_kopiranje(self, iids=None):
        """Izabrani redovi; izabran red koji ima podredjene (grupa) znaci sve njene redove."""
        if iids is None:
            iids = []
            for iid in self.tree.selection():
                deca = self.tree.get_children(iid)
                iids += list(deca) if deca and self.preskoci(iid) else [iid]
        return [i for i in iids if self.tree.exists(i) and not self.preskoci(i)]

    def kopiraj_redove(self, iids=None):
        redovi = self.redovi_za_kopiranje(iids)
        if redovi:
            self.app._kopiraj("\n".join(self.tekst_reda(i) for i in redovi),
                              "Kopiran ceo red" if len(redovi) == 1 else "Kopirano redova: %d" % len(redovi))

    def kopiraj_brojeve(self, iids=None):
        redovi = self.redovi_za_kopiranje(iids)
        if redovi and self.kolona_broja:
            k, opis = self.kolona_broja
            self.app._kopiraj("\n".join(self.tekst_celije(i, k) for i in redovi),
                              opis if len(redovi) == 1 else "%s: %d" % (opis, len(redovi)))

    # --- polje preko celije ---
    def _pritisak(self, e):
        """Pritisak na celiju: red se izabere i odmah moze da se prevlaci preko teksta. Shift/Ctrl = biranje vise
        redova (bez polja); strelica grupe i naslovi kolona rade kao i ranije."""
        self.zatvori()
        self.sidro = None
        if e.state & 0x0005 or self.tree.identify_region(e.x, e.y) not in ("tree", "cell"):
            return None
        iid = self.tree.identify_row(e.y)
        kol = self.kolona_na(e.x, iid)
        if not iid or not kol or self.preskoci(iid):
            return None
        if kol == "#0" and "indicator" in str(self.tree.identify_element(e.x, e.y)):
            return None
        self.pritisni(iid, kol, e.x_root)
        return "break"

    def pritisni(self, iid, kol, x_root):
        """Izabere red, otvori nevidljivo polje preko celije i zapamti gde je pocelo prevlacenje."""
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.otvori_oznaku(iid, kol)
        if self.e is not None:
            try:
                self.e.update_idletasks()       # polje dobije pravu sirinu pre racunanja polozaja u tekstu
                self.e.xview_moveto(0)
            except tk.TclError:
                pass
            self.sidro = self._granica(x_root)
            self.e.selection_clear()
            self.e.icursor(self.sidro)

    def _granica(self, x_root):
        """Granica izmedju dva znaka najbliza misu (kao u obicnom polju za tekst). Van celije tekst klizi."""
        e, info = self.e, self.info
        x = x_root - self.tree.winfo_rootx() - info.get("x", 0)
        sirina = info.get("w", 0)
        try:
            if sirina and x > sirina - 2:
                e.xview_scroll(1, "units")
            elif x < 0:
                e.xview_scroll(-1, "units")
            i = e.index("@%d" % x)
            # tkinter Entry nema svoj bbox (e.bbox je bbox mreze), pa se pita Tk direktno
            bb = e.tk.splitlist(e.tk.call(e._w, "bbox", i)) if i < len(e.get()) else None
            bb = [int(v) for v in bb] if bb else None
            if bb and x - bb[0] >= bb[2] / 2:
                i += 1
            return i
        except tk.TclError:
            return 0

    def vuci_do(self, x_root):
        if self.e is None or self.sidro is None:
            return
        i = self._granica(x_root)
        a, b = sorted((self.sidro, i))
        if a == b:
            self.e.selection_clear()
        else:
            self.e.selection_range(a, b)
        self.e.icursor(i)

    def _vuci(self, ev):
        if self.e is None or self.sidro is None:
            return None
        self.vuci_do(ev.x_root)
        return "break"

    def _otpustanje(self, ev=None):
        if self.sidro is None:
            return None
        self.sidro = None
        return "break"

    def _zelena(self, iid, kol):
        if self.tree is getattr(self.app, "tree", None) and kol == "provereno":
            return self.app._zelene.get(iid)
        return None

    def tekst_polja(self, iid, kol):
        """Tekst kakav se vidi u celiji (preko celije Provera moze biti zelena oznaka sa kvacicom)."""
        z = self._zelena(iid, kol)
        return str(z.cget("text")) if z is not None else self.tekst_celije(iid, kol)

    def otvori_oznaku(self, iid, kol, izbor=None, novo=True):
        self.zatvori()
        if not iid or self.preskoci(iid) or not self.tree.exists(iid) or not kol:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        tekst = self.tekst_polja(iid, kol)
        zelena = self._zelena(iid, kol)
        tag = (self.tree.item(iid, "tags") or ("",))[0]
        font = (str(self.tree.tag_configure(tag, "font")) if tag else "") or FONT
        if zelena is not None:                  # isto kao zelena oznaka preko celije
            bg, fg, font = BG_ZELENO, BOJA_OK, FONT
            pocetak = int(zelena.cget("bd")) + int(zelena.cget("highlightthickness")) + int(zelena.cget("padx"))
            kraj = pocetak
        else:                                   # red je izabran: boje izabranog reda
            bg, fg = T_IZBOR, T_TEKST
            pocetak = self.POMAK_STABLA if kol == "#0" else self.POMAK_TEKSTA
            kraj = self.POMAK_TEKSTA
        poravnanje = {"center": "center", "e": "right"}.get(str(self.tree.column(kol, "anchor")), "left")
        e = tk.Entry(self.tree, readonlybackground=bg, bg=bg, fg=fg, font=font, relief="flat", bd=0,
                     highlightthickness=0, selectbackground=T_AKCENT, selectforeground="#ffffff",
                     selectborderwidth=0, justify=poravnanje, insertbackground=bg, insertwidth=1,
                     exportselection=False, cursor="xterm", takefocus=0)
        e.insert(0, tekst)
        e.configure(state="readonly")
        e.bind("<Escape>", lambda ev: (self.zatvori(True), "break")[1])
        e.bind("<Return>", self._otvori_red)
        e.bind("<Button-1>", self._klik)
        e.bind("<Button-3>", self._meni)
        e.bind("<<Copy>>", self.kopiraj)
        e.bind("<Control-a>", lambda ev: (e.select_range(0, "end"), "break")[1])
        e.bind("<Control-A>", lambda ev: (e.select_range(0, "end"), "break")[1])
        for taster in ("<Up>", "<Down>", "<Prior>", "<Next>"):
            e.bind(taster, lambda ev, t=taster: self._taster(t))
        e.bind("<FocusOut>", lambda ev: self.tree.after(80, self._fokus))
        e.bind("<MouseWheel>", lambda ev: self.tree.yview_scroll(-1 if ev.delta > 0 else 1, "units"))
        self.e = e
        self.info = {"iid": iid, "kol": kol, "vreme": time.time() if novo else 0.0,
                     "dx": max(0, pocetak - self.UVLAKA_POLJA), "desno": max(0, kraj - self.UVLAKA_POLJA)}
        self.pozicioniraj()
        self.tree.after_idle(self.pozicioniraj)
        e.focus_set()
        if izbor:
            e.select_range(*izbor)
            e.icursor(izbor[1])

    def pozicioniraj(self):
        e, info = self.e, self.info
        if e is None:
            return
        try:
            bb = self.tree.bbox(info["iid"], info["kol"]) if self.tree.exists(info["iid"]) else ""
            if not bb:
                e.place_forget()
                return
            x, y, w, h = bb
            dx = max(0, min(info["dx"], w - 10))
            sir = max(10, w - dx - info["desno"])  # tekst se sece i poravnava kao u celiji
            info["x"], info["w"] = x + dx, sir
            e.place(x=x + dx, y=y, width=sir, height=h)
            e.lift()
        except tk.TclError:
            pass

    def zatvori(self, fokus_na_listu=False):
        e, self.e, self.info, self.sidro = self.e, None, None, None
        if e is not None:
            try:
                e.destroy()
            except tk.TclError:
                pass
        if fokus_na_listu:
            try:
                self.tree.focus_set()
            except tk.TclError:
                pass

    def stanje(self):
        """Sta je otvoreno (da se vrati posle osvezavanja liste) ili None."""
        e, info = self.e, self.info
        if e is None:
            return None
        try:
            izbor = (e.index("sel.first"), e.index("sel.last")) if e.selection_present() else None
            return dict(info, tekst=e.get(), izbor=izbor)
        except tk.TclError:
            return None

    def vrati(self, st):
        if not st or not self.tree.exists(st["iid"]):
            return
        rod = self.tree.parent(st["iid"])
        if rod and not self.tree.item(rod, "open"):
            return
        if st["kol"] not in self.kolone():
            return
        isti = self.tekst_polja(st["iid"], st["kol"]) == st["tekst"]
        self.otvori_oznaku(st["iid"], st["kol"], izbor=st["izbor"] if isti else None, novo=False)

    def _fokus(self):
        """Fokus je otisao u drugo polje programa: polje za kopiranje vise ne treba (van programa ostaje)."""
        e = self.e
        if e is None:
            return
        try:
            if not e.winfo_ismapped():
                return
            w = self.tree.focus_get()
        except (KeyError, tk.TclError):
            w = None
        if w is not None and w is not e and w is not e.winfo_toplevel():
            self.zatvori()

    def _taster(self, taster):
        self.zatvori(True)
        self.tree.event_generate(taster)
        return "break"

    def _izbor_promenjen(self, ev=None):
        """Desni klik ili strelice izaberu drugi red: polje (plava celija) ne sme da ostane na starom redu."""
        if self.info and self.info["iid"] not in self.tree.selection():
            self.zatvori()

    def _klik(self, ev):
        """Drugi klik odmah posle otvaranja = dvoklik na red. Kasniji klik samo pomera kursor.
        Shift/Ctrl+klik na polje bira vise redova, isto kao na listi."""
        if ev.state & 0x0005:
            x, y = ev.x_root - self.tree.winfo_rootx(), ev.y_root - self.tree.winfo_rooty()
            self.zatvori(True)
            self.tree.event_generate("<Control-Button-1>" if ev.state & 0x0004 else "<Shift-Button-1>",
                                     x=x, y=y, rootx=ev.x_root, rooty=ev.y_root)
            return "break"
        info = self.info
        if info and time.time() - info["vreme"] < 0.5:
            return self._otvori_red(ev)
        return None

    def _otvori_red(self, ev=None):
        self.zatvori(True)
        if self.otvori:
            self.otvori()
        return "break"

    def tekst_izbora(self):
        e = self.e
        if e is None:
            return ""
        try:
            if e.selection_present():
                return e.get()[e.index("sel.first"):e.index("sel.last")]
        except tk.TclError:
            pass
        return ""

    def kopiraj(self, ev=None):
        """Ctrl+C u polju: kopira oznaceno; ako nista nije oznaceno, celu celiju."""
        e = self.e
        if e is None:
            return None
        izbor = self.tekst_izbora()
        self.app._kopiraj(izbor or e.get(), "Kopirano" if izbor else "Kopirana cela ćelija")
        return "break"

    def _meni(self, ev):
        e, info = self.e, self.info
        if e is None:
            return "break"
        iid = info["iid"]
        izbor = self.tekst_izbora()
        m = tk.Menu(self.tree, tearoff=0)
        m.add_command(label="Kopiraj označeno (Ctrl+C)", state="normal" if izbor else "disabled",
                      command=lambda: self.app._kopiraj(izbor, "Kopirano"))
        m.add_command(label="Kopiraj celu ćeliju", command=lambda: self.app._kopiraj(e.get(), "Kopirana cela ćelija"))
        if self.kolona_broja:
            m.add_command(label="Kopiraj broj parcele", command=lambda: self.kopiraj_brojeve([iid]))
        m.add_command(label="Kopiraj ceo red", command=lambda: self.kopiraj_redove([iid]))
        m.add_separator()
        m.add_command(label="Označi sve (Ctrl+A)", command=lambda: e.select_range(0, "end"))
        if self.otvori:
            m.add_command(label="Otvori (Enter)", command=self._otvori_red)
        if self.meni:
            self.meni(m, iid)
        m.add_command(label="Zatvori polje (Esc)", command=lambda: self.zatvori(True))
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            m.grab_release()
        return "break"


def meni_kopiranja(m, kop, iid):
    """Stavke za kopiranje u desnom kliku na red liste."""
    redovi = kop.redovi_za_kopiranje()
    n = len(redovi)
    kol = kop.kolona_na_misu if getattr(kop, "kolona_na_misu", None) else None
    if kol and iid and not kop.preskoci(iid):
        naslov = kop.tree.heading(kol, "text") if kol != "#0" else kop.tree.heading("#0", "text")
        m.add_command(label="Kopiraj ćeliju „%s“" % naslov,
                      command=lambda: kop.app._kopiraj(kop.tekst_celije(iid, kol), "Kopirana ćelija"))
    if kop.kolona_broja and n:
        m.add_command(label="Kopiraj broj parcele" if n == 1 else "Kopiraj brojeve parcela (%d)" % n,
                      command=kop.kopiraj_brojeve)
    if n:
        m.add_command(label="Kopiraj ceo red (Ctrl+C)" if n == 1 else "Kopiraj izabrane redove (%d)" % n,
                      command=kop.kopiraj_redove)


# --- arhiva i odlaganje provere (kao Asistent PRO v17) ---
def arhiviran(p):
    return bool(p.get("arhivirano"))


def odlozen(p, danas=None):
    """Provera odlozena: parcela ne ide u "Proveri sve" do tog datuma (na sam taj dan ponovo ide)."""
    d = p.get("odlozeno_do")
    return bool(d) and d > (danas or dt.date.today()).isoformat()


def aktivan(p, danas=None):
    """Parcela ide u "Proveri sve": nije u arhivi i provera joj nije odlozena."""
    return not arhiviran(p) and not odlozen(p, danas)


def dodaj_mesece(d, n):
    m = d.month - 1 + n
    g, m = d.year + m // 12, m % 12 + 1
    dana = (31, 29 if g % 4 == 0 and (g % 100 or g % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return dt.date(g, m, min(d.day, dana[m - 1]))


def citaj_datum(t):
    """'7.1.2027', '07.01.2027.', '7.1.27', '7/1/2027' ili '2027-01-07' -> date; inace None."""
    t = (t or "").strip().rstrip(".").replace("/", ".").replace("-", ".").replace(" ", "")
    delovi = [x for x in t.split(".") if x]
    try:
        if len(delovi) != 3:
            return None
        if len(delovi[0]) == 4:
            g, m, d = map(int, delovi)
        else:
            d, m, g = map(int, delovi)
            if g < 100:
                g += 2000
        return dt.date(g, m, d)
    except ValueError:
        return None


def srp_datum(iso):
    """'2027-01-07' -> '07.01.2027'"""
    try:
        return dt.date.fromisoformat((iso or "")[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return iso or ""


def br_parcela(n):
    if n % 10 == 1 and n % 100 != 11:
        return "%d parcela" % n
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "%d parcele" % n
    return "%d parcela" % n


def norm(t):
    return " ".join((t or "").split())


# --- precica na radnoj povrsini i u Start meniju (kao Asistent PRO) ---
PRECICA_PS1 = r"""# Pravi precicu "Asistent KATASTAR" na radnoj povrsini i u Start meniju (pokrece program bez crnog prozora).
# Precica dobija isti Windows ID aplikacije kao program, pa taskbar koristi ostru ikonicu sa precice
# i zakacena ikonica se ne duplira kad se program otvori.
$appId = "advokatcolja.asistentkatastar"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = $null
try {
    $py = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
    if ($py) { $pyw = Join-Path (Split-Path $py) "pythonw.exe" }
} catch { }
if (-not $pyw -or -not (Test-Path $pyw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $pyw = $cmd.Source }
}
if ($env:AK_PYTHONW -and (Test-Path $env:AK_PYTHONW)) { $pyw = $env:AK_PYTHONW }
if (-not $pyw -or -not (Test-Path $pyw)) {
    Write-Host "Nije pronadjen pythonw.exe. Instaliraj Python (python.org) sa opcijom 'py launcher'." -ForegroundColor Red
    exit 1
}
$ikona = Join-Path $dir "asistent_katastar.ico"
if (-not (Test-Path $ikona)) { $ikona = Join-Path $dir "katastar.ico" }

$kod = @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
namespace AsistentKatastar {
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore {
        [PreserveSig] int GetCount(out uint c);
        [PreserveSig] int GetAt(uint i, out PropertyKey k);
        [PreserveSig] int GetValue(ref PropertyKey k, IntPtr v);
        [PreserveSig] int SetValue(ref PropertyKey k, IntPtr v);
        [PreserveSig] int Commit();
    }
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct PropertyKey { public Guid fmtid; public uint pid; }
    public static class Precica {
        public static void PostaviId(string putanja, string id) {
            Type t = Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"));
            object link = Activator.CreateInstance(t);
            try {
                IPersistFile pf = (IPersistFile)link;
                pf.Load(putanja, 2);
                IPropertyStore ps = (IPropertyStore)link;
                PropertyKey k = new PropertyKey();
                k.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
                k.pid = 5;
                // PROPVARIANT VT_LPWSTR (31): 8 bajtova zaglavlja + pokazivac na tekst
                IntPtr pv = Marshal.AllocCoTaskMem(24);
                IntPtr tekst = Marshal.StringToCoTaskMemUni(id);
                try {
                    for (int i = 0; i < 24; i++) Marshal.WriteByte(pv, i, 0);
                    Marshal.WriteInt16(pv, 0, 31);
                    Marshal.WriteIntPtr(pv, 8, tekst);
                    int hr = ps.SetValue(ref k, pv);
                    if (hr != 0) Marshal.ThrowExceptionForHR(hr);
                    hr = ps.Commit();
                    if (hr != 0) Marshal.ThrowExceptionForHR(hr);
                } finally {
                    Marshal.FreeCoTaskMem(tekst);
                    Marshal.FreeCoTaskMem(pv);
                }
                pf.Save(putanja, true);
            } finally {
                Marshal.ReleaseComObject(link);
            }
        }
    }
}
'@
$imaId = $true
try { Add-Type -TypeDefinition $kod -ErrorAction Stop } catch { $imaId = $false }

$ws = New-Object -ComObject WScript.Shell
foreach ($mapa in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $putanja = Join-Path $mapa "Asistent KATASTAR.lnk"
    $lnk = $ws.CreateShortcut($putanja)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + (Join-Path $dir "asistent_katastar.py") + '"'
    $lnk.WorkingDirectory = $dir
    $lnk.IconLocation = $ikona + ",0"
    $lnk.Description = "Asistent KATASTAR - pretraga i pracenje parcela"
    $lnk.Save()
    if ($imaId) {
        try { [AsistentKatastar.Precica]::PostaviId($putanja, $appId) }
        catch { $imaId = $false; Write-Host "Napomena: ID aplikacije nije upisan u precicu ($($_.Exception.Message))." -ForegroundColor Yellow }
    }
    Write-Host "Napravljena precica: $putanja"
}
if (-not $imaId) {
    Write-Host "Precica radi, ali taskbar mozda nece spojiti zakacenu ikonicu i otvoren program." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Gotovo. Desni klik na precicu Asistent KATASTAR > Zakaci na traku zadataka (Windows 11: Prikazi vise opcija)."
"""


def putanja_ikone(png=False):
    """Nova ikonica (v8, u stilu Asistent PRO); ako je nema, stara."""
    for ime in (("asistent_katastar_ikona.png", "katastar_ikona.png") if png
                else ("asistent_katastar.ico", "katastar.ico")):
        p = os.path.join(DIR, ime)
        if os.path.exists(p):
            return p
    return None


def radna_povrsina():
    """Folder radne povrsine (i kad je preusmeren na OneDrive)."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def napravi_precicu(gotovo=None):
    """Upisuje napravi_precicu.ps1 pored programa i pokrece ga bez prozora (PowerShell pravi precicu na radnoj
    povrsini i u Start meniju sa ikonicom i Windows ID-jem programa). gotovo(ok, poruka) se zove iz niti."""
    import subprocess
    ps1 = os.path.join(DIR, "napravi_precicu.ps1")
    try:
        staro = ""
        if os.path.exists(ps1):
            with open(ps1, encoding="utf-8", errors="replace") as f:
                staro = f.read()
        novo = PRECICA_PS1.replace("\r\n", "\n")
        if staro.replace("\r\n", "\n") != novo:
            with open(ps1, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
                f.write(novo)
    except OSError as e:
        if gotovo:
            gotovo(False, "napravi_precicu.ps1 nije upisan: %s" % e)
        return
    if os.name != "nt":
        if gotovo:
            gotovo(False, "prečica se pravi samo na Windowsu")
        return
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    env = dict(os.environ, AK_PYTHONW=pyw if os.path.exists(pyw) else "")
    psh = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                       "powershell.exe")

    def radi():
        try:
            r = subprocess.run([psh if os.path.exists(psh) else "powershell.exe", "-NoProfile", "-NonInteractive",
                                "-ExecutionPolicy", "Bypass", "-File", ps1], env=env, capture_output=True,
                               timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            izlaz = (r.stdout + r.stderr).decode("utf-8", "replace")
            ok = r.returncode == 0 and ("Napravljena precica" in izlaz or
                                        os.path.exists(os.path.join(radna_povrsina(), "Asistent KATASTAR.lnk")))
            if not ok:
                upisi_dnevnik("Precica nije napravljena:\n" + izlaz[-1500:])
            if gotovo:
                gotovo(ok, "" if ok else (izlaz.strip().splitlines() or ["nepoznata greška"])[-1])
        except Exception as e:
            upisi_dnevnik("Precica nije napravljena: %r" % (e,))
            if gotovo:
                gotovo(False, str(e))
    threading.Thread(target=radi, daemon=True).start()


class App:
    def __init__(self, root):
        self.root = root
        napravi_rezervu_baze()
        self.baza = Baza()
        postavi_skalu(root, self.baza.podesavanje("velicina", "auto"))  # 125%, 150%...: pikseli rastu sa slovima
        self.sif = Sifarnik()
        self.citac = CitacCaptche()
        self.posao = None
        self.rezim = None
        self._zadatak = None         # v32: zadatak iz foldera zadaci koji je u toku
        self._odgovor = None
        self._dogadjaj = threading.Event()
        self._svg_crtez = None
        self._tagovi = set()
        self._otvorene = set()
        self.sesija_ok = set()
        self.sesija_novo = {}        # pid -> [promene] nadjene u ovoj sesiji (ostaje dok je program otvoren)
        self._auto_otvorene = set()  # grupe koje su se same otvorile zbog promene (jednom po sesiji)
        self.rezultati = {}          # iid parcele u tabeli pretrage -> (zadatak, podaci, razlog)
        self._ceka_stavku = None     # skidanje izabranih stavki: šta se traži, šta je stiglo, prozori koji čekaju
        self._otvori_posle = None    # v28: parcela čiji se prozor osvežava kad stigne trenutno stanje sa sajta
        self._sesije = {}            # (ko_id, broj) -> sesija poslednje pretrage parcele (nepID stavki)
        self._paneli = []            # otvoreni prozori parcela (osvežavaju se kad stavka stigne)
        self._slike_izbora = {v: slika_izbora(v, max(12, px(14))) for v in ("ne", "da", "ima")}
        self.upit_var = tk.StringVar()
        self.prikaz_var = tk.StringVar(value=PRIKAZI[0])
        self._kopiranja = []         # liste u kojima klik na celiju daje polje za kopiranje (kao Asistent PRO)
        self._zelene = {}            # iid -> zelena oznaka preko celije "Provera"
        self._sirine = {}            # automatske i rucne sirine kolona po listi
        self.root.report_callback_exception = self._izuzetak

        root.title("Asistent KATASTAR %s - pretraga i praćenje parcela (eKatastar)" % VERZIJA)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry("%dx%d+0+0" % (min(px(1500), sw - 16), min(px(900), sh - 90)))
        root.minsize(min(px(1000), sw - 40), min(px(600), sh - 80))
        try:
            root.state("zoomed")
        except tk.TclError:
            pass
        primeni_temu(root)
        self._font_mera = tkfont.Font(root=root, family="Segoe UI", size=10, weight="bold")
        self._font_naslov = tkfont.Font(root=root, family="Segoe UI", size=9, weight="bold")

        self.auto_var = tk.BooleanVar(value=True)
        self.detaljno_var = tk.BooleanVar(value=self.baza.podesavanje("detaljno", "1") == "1")
        self.nep_var = tk.BooleanVar(value=self.baza.podesavanje("nepokretnost", "1") == "1")
        # Dejan (v21): pretraga prvo samo prikaze sve stavke (parcela, zgrade, stanovi), a on bira sta se skida
        self.nep_pretraga_var = tk.StringVar(value=self.baza.podesavanje("nep_pretraga", "spisak"))
        self.nep_pretraga_var.trace_add("write", lambda *a: self.baza.postavi_podesavanje(
            "nep_pretraga", self.nep_pretraga_var.get()))
        self.obavestenje_var = tk.BooleanVar(value=self.baza.podesavanje("obavestenje", "1") == "1")
        self.obavestenje_cap_var = tk.BooleanVar(value=self.baza.podesavanje("obavestenje_captcha", "1") == "1")
        self.auto_grupe_var = tk.BooleanVar(value=self.baza.podesavanje("auto_grupe", "1") == "1")
        for var, k in ((self.detaljno_var, "detaljno"), (self.nep_var, "nepokretnost"),
                       (self.obavestenje_var, "obavestenje"),
                       (self.obavestenje_cap_var, "obavestenje_captcha"),
                       (self.auto_grupe_var, "auto_grupe")):
            var.trace_add("write", lambda *a, v=var, kl=k: self.baza.postavi_podesavanje(kl, "1" if v.get() else "0"))
        self._korisnik_prekinuo = False

        self._napravi_meni()
        self._napravi_zaglavlje()
        self._napravi_statusnu_traku()
        self._napravi_captcha()
        self.paned = ttk.PanedWindow(self.root, orient="vertical")
        self.paned.pack(fill="both", expand=True, padx=px(16), pady=(px(8), px(4)))
        self.nb = ttk.Notebook(self.paned)
        self.paned.add(self.nb, weight=1)
        self._napravi_pretragu()
        self._napravi_pracenje()
        self._napravi_log()
        grupisano = self._grupisi_pri_pokretanju()
        self.osvezi_listu()
        self._osvezi_desno()
        self.log("Spremno. Pretraga više parcela: upiši ili izaberi opštinu i KO, upiši brojeve parcela i klikni "
                 "\"Pretraži\".", "info")
        self._javi_grupisanje(grupisano)
        if SKALA < SKALA_WINDOWS - 0.005:
            self.log("Prikaz je prilagođen ekranu (%d%% umesto %d%% iz Windows-a) da tabela rezultata ima mesta; "
                     "Prikaz > Veličina prikaza vraća veća slova." % (round(SKALA * 100), round(SKALA_WINDOWS * 100)),
                     "tiho")
        self.root.after(250, self._ticker)
        self.root.after(2500, self._proveri_precicu)
        self.root.after(4000, lambda: self.baza.pretrazi("\x00"))   # v36: tekst za pretragu se pripremi unapred
        self._pokreni_zadatke()               # v32: zadaci od Claude-a (folder zadaci)

    # --- meni i trake ----------------------------------------------------
    def _napravi_meni(self):
        m = tk.Menu(self.root)
        mp = tk.Menu(m, tearoff=0)
        mp.add_command(label="Proveri sve praćene parcele", command=lambda: self.proveri(False))
        mp.add_command(label="Proveri izabrane", command=lambda: self.proveri(True))
        mp.add_command(label="Proveri odložene i arhivirane", command=lambda: self.proveri(False, neaktivni=True))
        mp.add_separator()
        mp.add_command(label="Prekini", command=self._prekini)
        m.add_cascade(label="Provera", menu=mp)
        mr = tk.Menu(m, tearoff=0)
        mr.add_command(label="Dodaj parcele u praćenje...", command=self.dodaj_dijalog)
        mr.add_separator()
        mr.add_command(label="Detalji", command=self.detalji)
        mr.add_command(label="Kopiraj broj parcele (KO i broj)", command=lambda: self._kop_pracenja.kopiraj_brojeve())
        mr.add_command(label="Kopiraj izabrane redove (Ctrl+C)", command=lambda: self._kop_pracenja.kopiraj_redove())
        mr.add_command(label="Izmeni (klijent, grupa, napomena)...", command=self.izmeni)
        mr.add_command(label="Označi kao pregledano", command=self.oznaci_pregledano)
        mr.add_command(label="Označi SVE kao pregledano", command=self.oznaci_sve_pregledano)
        mr.add_separator()
        mo = tk.Menu(mr, tearoff=0)
        for n, txt in ((1, "1 mesec"), (3, "3 meseca"), (6, "6 meseci"), (12, "1 godinu")):
            mo.add_command(label=txt, command=lambda n=n: self.odlozi(meseci=n))
        mo.add_separator()
        mo.add_command(label="Do datuma...", command=self.odlozi)
        mr.add_cascade(label="Odloži proveru", menu=mo)
        mr.add_command(label="Arhiviraj", command=self.arhiviraj)
        mr.add_command(label="Vrati u redovnu proveru", command=self.vrati_u_proveru)
        mr.add_separator()
        mr.add_command(label="Sačuvaj kao PDF (izabrane parcele ili grupa)", command=lambda: self.pdf_pracenja())
        mr.add_command(label="Folder za PDF izvode...", command=self.izaberi_pdf_folder)
        mr.add_separator()
        mr.add_command(label="Ukloni izabrane iz praćenja (u Arhivu; iz Arhive trajno)", command=self.ukloni)
        m.add_cascade(label="Parcela", menu=mr)
        mg = tk.Menu(m, tearoff=0)
        mg.add_command(label="Nova grupa...", command=self.nova_grupa)
        mg.add_command(label="Premesti izabrane u grupu...", command=self.promeni_grupu)
        mg.add_command(label="Preimenuj grupu...", command=self.preimenuj_grupu)
        mg.add_command(label="Obriši grupu", command=self.obrisi_grupu)
        mg.add_separator()
        mg.add_command(label="Grupiši parcele istog klijenta (sada)", command=self.grupisi_sada)
        mg.add_checkbutton(label="Automatski grupiši parcele istog klijenta", variable=self.auto_grupe_var)
        m.add_cascade(label="Grupa", menu=mg)
        mv = tk.Menu(m, tearoff=0)
        for pr in PRIKAZI:
            mv.add_radiobutton(label=pr, variable=self.prikaz_var, value=pr, command=self.osvezi_listu)
        mv.add_separator()
        mv.add_command(label="Pretraga u listi praćenja (Ctrl+F)", command=self._fokus_pretrage)
        mv.add_command(label="Proširi sve grupe", command=lambda: self._grupe_otvori(True))
        mv.add_command(label="Skupi sve grupe", command=lambda: self._grupe_otvori(False))
        mv.add_command(label="Širine kolona po sadržaju",
                       command=lambda: [self._prilagodi_kolone(t, sve=True) for t in (self.tree, self.tree_p)])
        mv.add_separator()
        self.velicina_var = tk.StringVar(value=self.baza.podesavanje("velicina", "auto"))
        mv.add_radiobutton(label="Veličina prikaza: prilagođena ekranu (više mesta za tabelu)",
                           variable=self.velicina_var, value="auto", command=self._promeni_velicinu)
        mv.add_radiobutton(label="Veličina prikaza: kao u Windows-u (%d%%, veća slova)" % round(SKALA_WINDOWS * 100),
                           variable=self.velicina_var, value="windows", command=self._promeni_velicinu)
        m.add_cascade(label="Prikaz", menu=mv)
        ma = tk.Menu(m, tearoff=0)
        ma.add_checkbutton(label="Automatski čitaj captchu", variable=self.auto_var)
        ma.add_checkbutton(label="Učitaj objekte i posebne delove za sve delove parcele", variable=self.detaljno_var)
        ma.add_radiobutton(label="Pretraga: samo prikaži sve stavke, ja biram šta se skida sa sajta",
                           variable=self.nep_pretraga_var, value="spisak")
        ma.add_radiobutton(label="Pretraga: odmah skini sve (vlasnici i tereti za parcelu, zgrade i stanove)",
                           variable=self.nep_pretraga_var, value="sve")
        ma.add_checkbutton(label="Praćenje: učitaj vlasnike, terete i napomene za parcelu, objekte i posebne delove",
                           variable=self.nep_var)
        ma.add_checkbutton(label="Windows obaveštenje kad se provera završi", variable=self.obavestenje_var)
        ma.add_checkbutton(label="Obaveštenje i zvuk kad treba da upišeš captchu", variable=self.obavestenje_cap_var)
        ma.add_checkbutton(label="Automatski grupiši parcele istog klijenta", variable=self.auto_grupe_var)
        ma.add_separator()
        ma.add_command(label="Napravi prečicu na radnoj površini i u Start meniju (za taskbar)",
                       command=self.napravi_precicu_sada)
        ma.add_command(label="Osveži spisak opština sa sajta", command=self.osvezi_opstine)
        ma.add_command(label="Kopiraj sve poruke", command=self._kopiraj_log)
        ma.add_command(label="Obriši prikaz poruka", command=self._obrisi_log)
        ma.add_command(label="Otvori dnevnik.txt", command=lambda: self._otvori(DNEVNIK_PATH))
        ma.add_command(label="Prikaži sve poruke (dnevnik rada)", command=self.prikazi_dnevnik)
        ma.add_separator()
        ma.add_command(label="Folder za PDF izvode...", command=self.izaberi_pdf_folder)
        ma.add_command(label="Folder na Drive-u (zadaci, rezerve)...", command=self.izaberi_drive_folder)  # v35
        m.add_cascade(label="Alati", menu=ma)
        self.root.config(menu=m)

    # --- PDF izvoda -------------------------------------------------------
    def pdf_pretrage(self):
        """Jednim klikom: sve sacuvane originalne stranice 'Подаци о непокретности' pronadjenih parcela kao PDF
        (isto kao "Штампај" na sajtu > Sacuvaj kao PDF), u jedan nov folder. Vise izabranih redova = samo oni."""
        sel = [i for i in self.tree_p.selection() if i in self.rezultati]
        iids = sel if len(sel) > 1 else list(self.tree_p.get_children(""))
        mesta = []
        for iid in iids:
            z, podaci, _ = self.rezultati.get(iid, (None, None, None))
            if z and podaci is not None:
                mesta.append((z.get("ko_id"), z["ko"], z["broj"]))
        self.sacuvaj_pdf(mesta)

    def pdf_pracenja(self, ids=None, naziv=None):
        """Lista praćenja: PDF svih sačuvanih originala izabranih parcela ili cele grupe (v30, Dejan: "da celu
        grupu, npr za klijenta, SVE skinem kao pdf"); naziv = ime grupe za naziv podfoldera."""
        ids = self.izabrani_ids() if ids is None else ids
        if not ids:
            messagebox.showinfo("PDF izvoda", "Izaberi parcele ili grupu (klijenta) u listi praćenja, pa „Sačuvaj kao PDF“.")
            return
        self.sacuvaj_pdf([(p["ko_id"], p["ko"], p["broj"]) for p in self.baza.parcele(ids)], naziv)

    def pdf_folder(self):
        """Stalni folder za PDF (Folder za PDF... > Uvek u isti folder), ili None: program pita pri svakom cuvanju
        (Dejan: svaka parcela ima svoj folder, drugi klijent)."""
        if self.baza.podesavanje("pdf_nacin", "pitaj") == "stalni":
            return self.baza.podesavanje("pdf_folder", "") or PDF_DIR
        return None

    def izaberi_drive_folder(self):
        """v35: folder ASISTENT KATASTAR na Drive-u: odatle program uzima zadatke od Claude-a (zadaci) i tamo vraća
        izveštaj; tamo čuva i drugu kopiju rezervi baze. Podrazumevano ga nalazi sam (G:\\My Drive\\ASISTENT KATASTAR)."""
        d = tk.Toplevel(self.root)
        d.title("Folder na Drive-u")
        d.transient(self.root)
        d.resizable(False, False)
        f = ttk.Frame(d, padding=px(14))
        f.pack(fill="both", expand=True)
        sad = self.baza.podesavanje("drive_folder", "")
        nacin = tk.StringVar(value="iskljuceno" if sad == "-" else ("izabran" if sad else "auto"))
        nadjen = nadji_drive_folder()
        put = tk.StringVar(value=sad if sad not in ("", "-") else (nadjen or ""))
        ttk.Label(f, text="Folder %s na Google Drive-u (zadaci od Claude-a, rezerve baze)" % DRIVE_FOLDER,
                  font=FONT_B).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(f, text="Pronađi sam: %s" % (nadjen or "nije pronađen"), variable=nacin,
                        value="auto").grid(row=1, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        ttk.Radiobutton(f, text="Ovaj folder:", variable=nacin, value="izabran").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(px(6), px(2)))
        ttk.Entry(f, textvariable=put, width=58, state="readonly").grid(row=3, column=0, sticky="we",
                                                                        padx=(px(22), px(6)))

        def izaberi():
            izbor = filedialog.askdirectory(parent=d, mustexist=True, title="Folder %s na Drive-u" % DRIVE_FOLDER,
                                            initialdir=put.get() if os.path.isdir(put.get()) else DIR)
            if izbor:
                put.set(os.path.normpath(izbor))
                nacin.set("izabran")
        ttk.Button(f, text="Izaberi...", command=izaberi).grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(f, text="Ne koristi Drive", variable=nacin, value="iskljuceno").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(px(6), 0))

        def ok(_=None):
            n = nacin.get()
            self.baza.postavi_podesavanje("drive_folder", "-" if n == "iskljuceno" else (
                put.get() if n == "izabran" and put.get() else ""))
            if hasattr(self, "_drive_nadjen"):
                del self._drive_nadjen
            d.destroy()
            dd = self.drive_folder()
            self.log("Folder na Drive-u: %s" % (dd or "ne koristi se"), "info")
        dugmad = ttk.Frame(f)
        dugmad.grid(row=5, column=0, columnspan=2, sticky="e", pady=(px(12), 0))
        ttk.Button(dugmad, text="U redu", command=ok).pack(side="left", padx=px(4))
        ttk.Button(dugmad, text="Otkaži", command=d.destroy).pack(side="left")
        d.bind("<Return>", ok)
        d.bind("<Escape>", lambda e: d.destroy())
        d.grab_set()

    def izaberi_pdf_folder(self):
        """Folder za PDF...: pitaj pri svakom cuvanju (podrazumevano) ili uvek isti folder."""
        d = tk.Toplevel(self.root)
        d.title("Folder za PDF izvode")
        d.transient(self.root)
        d.resizable(False, False)
        f = ttk.Frame(d, padding=px(14))
        f.pack(fill="both", expand=True)
        nacin = tk.StringVar(value=self.baza.podesavanje("pdf_nacin", "pitaj"))
        put = tk.StringVar(value=self.baza.podesavanje("pdf_folder", "") or PDF_DIR)
        ttk.Label(f, text="Gde da se čuvaju PDF izvodi?", font=FONT_B).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Pitaj pri svakom čuvanju (npr. izaberem folder klijenta)", variable=nacin,
                        value="pitaj").grid(row=1, column=0, columnspan=3, sticky="w", pady=(px(8), 0))
        ttk.Radiobutton(f, text="Uvek u isti folder (za svako čuvanje nov podfolder sa datumom i KO):",
                        variable=nacin, value="stalni").grid(row=2, column=0, columnspan=3, sticky="w",
                                                              pady=(px(6), px(2)))
        ttk.Entry(f, textvariable=put, width=58, state="readonly").grid(row=3, column=0, columnspan=2, sticky="we",
                                                                        padx=(px(22), px(6)))

        def izaberi():
            sad = put.get()
            izbor = filedialog.askdirectory(parent=d, mustexist=False, title="Stalni folder za PDF izvode",
                                            initialdir=sad if os.path.isdir(sad) else DIR)
            if izbor:
                put.set(os.path.normpath(izbor))
                nacin.set("stalni")

        def ok(_=None):
            self.baza.postavi_podesavanje("pdf_nacin", nacin.get())
            if nacin.get() == "stalni":
                self.baza.postavi_podesavanje("pdf_folder", put.get())
                self._javi("PDF izvodi se uvek čuvaju u: %s  (za svako čuvanje nov podfolder)" % put.get())
            else:
                self._javi("Pri svakom čuvanju PDF izvoda program pita za folder.")
            d.destroy()
        ttk.Button(f, text="Izaberi...", command=izaberi).grid(row=3, column=2, sticky="w")
        b = ttk.Frame(f)
        b.grid(row=4, column=0, columnspan=3, sticky="we", pady=(px(14), 0))
        ttk.Button(b, text="U redu", style="Glavno.TButton", command=ok).pack(side="left")
        ttk.Button(b, text="Odustani", command=d.destroy).pack(side="right")
        d.bind("<Return>", ok)
        d.bind("<Escape>", lambda e: d.destroy())
        self._pdf_dijalog = {"prozor": d, "nacin": nacin, "put": put, "izaberi": izaberi, "ok": ok}
        d.grab_set()

    def sacuvaj_pdf(self, mesta, naziv=None):
        if getattr(self, "_pdf_radi", False):
            messagebox.showinfo("PDF izvoda", "PDF se već pravi, sačekaj da se završi.")
            return
        mesta = list(dict.fromkeys(mesta))
        if not mesta:
            messagebox.showinfo("PDF izvoda", "Nema pronađenih parcela za PDF.")
            return
        poslovi, bez = poslovi_pdf(mesta)
        if not poslovi:
            messagebox.showinfo("PDF izvoda", "Za ove parcele nema sačuvanih originala „Подаци о непокретности“.\n\n"
                                "Uključi Alati > Pretraga: učitaj vlasnike i terete, pa ponovi pretragu.")
            return
        kos = list(dict.fromkeys(m[1] for m in mesta))
        n = len(mesta)
        parcela = "%d parcel%s" % (n, "a" if n == 1 else "e" if n < 5 else "a")
        naziv = "%s %s (%s)" % (dt.datetime.now().strftime("%Y-%m-%d %H.%M"),
                                naziv or (kos[0] if len(kos) == 1 else "više KO"), parcela)
        self._napravi_pdf(poslovi, bez, "%s, %d PDF" % (parcela, len(poslovi)), naziv,
                          "Pravim PDF: %d stranic%s za %d parcel%s..." % (
                              len(poslovi), "a" if len(poslovi) == 1 else "e", n, "u" if n == 1 else "e"))

    def sacuvaj_jedan_pdf(self, html, ime, parent=None):
        """Jedna stranica 'Подаци о непокретности' (parcela, zgrada ili poseban deo) kao PDF, u izgledu sa
        eKatastra; pita za folder kao i "Sačuvaj sve kao PDF" (ili ide u stalni folder, bez podfoldera)."""
        if getattr(self, "_pdf_radi", False):
            messagebox.showinfo("PDF izvoda", "PDF se već pravi, sačekaj da se završi.", parent=parent)
            return
        if not html or not os.path.isfile(html):
            messagebox.showinfo("PDF izvoda", "Za ovaj red nije sačuvana originalna stranica „Подаци о "
                                "непокретности“.\n\nUključi Alati > Pretraga: učitaj vlasnike i terete (ili proveri "
                                "parcelu u praćenju), pa pokušaj ponovo.", parent=parent)
            return
        ime = ime_fajla(ime) + ".pdf"
        self._napravi_pdf([(html, ime)], [], ime, None, "Pravim PDF: %s..." % ime, parent=parent)

    def _napravi_pdf(self, poslovi, bez, opis, podfolder, poruka, parent=None, osnova=None):
        """Zajednicko za sve PDF-ove: pregledac, folder (pita, ili stalni folder), imena bez presnimavanja, nit.
        osnova (v32, zadatak): folder bez pitanja, u njemu nov podfolder. Vraća False ako PDF nije pokrenut."""
        pregledac = nadji_pregledac()
        if not pregledac:
            if osnova:
                return False
            messagebox.showwarning("PDF izvoda", "Nije pronađen Microsoft Edge ni Google Chrome. PDF se pravi preko "
                                   "njih, isto kao Štampaj > Sačuvaj kao PDF na sajtu.", parent=parent)
            return False
        stalni = osnova or self.pdf_folder()
        if stalni and podfolder:
            osnova = os.path.join(stalni, ime_fajla(podfolder))
            folder, k = osnova, 2
            while os.path.exists(folder):          # dva klika u istom minutu: nov folder, nista se ne presnimava
                folder, k = "%s (%d)" % (osnova, k), k + 1
        elif stalni:
            folder = stalni
        else:
            poslednji = self.baza.podesavanje("pdf_poslednji", "")
            izbor = filedialog.askdirectory(
                parent=parent or self.root, mustexist=False,
                title="Gde da sačuvam PDF? (%s)" % opis,
                initialdir=poslednji if os.path.isdir(poslednji) else os.path.expanduser("~"))
            if not izbor:
                self._javi("PDF nije sačuvan (folder nije izabran).")
                return False
            folder = os.path.normpath(izbor)
            self.baza.postavi_podesavanje("pdf_poslednji", folder)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            if osnova:
                upisi_dnevnik("PDF folder %s: %r" % (folder, e))
                return False
            messagebox.showwarning("PDF izvoda", "Folder nije napravljen:\n%s\n\n%s" % (folder, e), parent=parent)
            return False
        zauzeto = set()
        for i, (html, ime) in enumerate(poslovi):  # postojeci PDF u folderu klijenta se ne presnimava: "ime (2).pdf"
            osn, k = ime[:-4], 2
            while ime.casefold() in zauzeto or os.path.exists(os.path.join(folder, ime)):
                ime, k = "%s (%d).pdf" % (osn, k), k + 1
            zauzeto.add(ime.casefold())
            poslovi[i] = (html, ime)
        self._pdf_radi = True
        self._javi(poruka)
        threading.Thread(target=self._pdf_nit, args=(pregledac, poslovi, folder, bez), daemon=True).start()
        return True

    def _pdf_nit(self, pregledac, poslovi, folder, bez):
        profil = tempfile.mkdtemp(prefix="katastar_pdf_")
        uspelo, lose = 0, []
        try:
            for i, (html, ime) in enumerate(poslovi, 1):
                self.root.after(0, lambda t="PDF %d od %d: %s" % (i, len(poslovi), ime): self.lbl_stanje.configure(text=t))
                try:
                    if html_u_pdf(pregledac, html, os.path.join(folder, ime), profil):
                        uspelo += 1
                    else:
                        lose.append(ime)
                except (OSError, subprocess.SubprocessError) as e:
                    lose.append(ime)
                    upisi_dnevnik("PDF %s: %r" % (ime, e))
        finally:
            shutil.rmtree(profil, ignore_errors=True)
        self.root.after(0, self._pdf_gotovo, folder, uspelo, lose, bez)

    def _pdf_gotovo(self, folder, uspelo, lose, bez):
        self._pdf_radi = False
        self.lbl_stanje.configure(text="")
        poruka = "PDF izvoda sačuvano: %d%s, u %s" % (uspelo, (", nije uspelo: %d" % len(lose)) if lose else "",
                                                       folder)
        self.log(poruka + "  (%s)" % folder, "uspeh" if uspelo and not lose else "neuspeh_naslov")
        for x in lose:
            self.log("    PDF nije napravljen: %s" % x, "neuspeh")
        if bez:
            self.log("    bez sačuvanih originala: %s" % ", ".join(bez), "neuspeh")
        if self.posao is None:
            self.lbl_opis.configure(text=poruka + (("; bez originala: %s" % ", ".join(bez)) if bez else ""))
        if self._zadatak is not None and self._zadatak.get("faza") == "pdf":     # v32: tiho, bez otvaranja foldera
            self._zadatak["pdf_rez"] = {"folder": folder, "sacuvano": uspelo, "nije": lose, "bez_originala": bez}
            self._zavrsi_zadatak(self._zadatak)
            return
        if uspelo:
            try:
                os.startfile(folder)
            except (AttributeError, OSError):
                pass

    # --- v32: zadaci od Claude-a (folder zadaci) ----------------------------
    def _pokreni_zadatke(self):
        """Pri pokretanju: folder zadaci postoji; zadatak prekinut zatvaranjem programa vraća se u red."""
        try:
            os.makedirs(ZADACI_DIR, exist_ok=True)
            u_radu = os.path.join(ZADACI_DIR, "u radu")
            if os.path.isdir(u_radu):
                for ime in os.listdir(u_radu):
                    if ime.lower().endswith(".json") and not os.path.exists(os.path.join(ZADACI_DIR, ime)):
                        os.replace(os.path.join(u_radu, ime), os.path.join(ZADACI_DIR, ime))
        except OSError as e:
            upisi_dnevnik("ZADACI: %r" % (e,))
        self.root.after(ZADACI_TIK_MS, self._tik_zadataka)

    def _tik_zadataka(self):
        try:
            self._proveri_zadatke()
        except Exception:
            upisi_dnevnik(traceback.format_exc())
        self.root.after(ZADACI_TIK_MS, self._tik_zadataka)

    # v35: folder na Drive-u (ASISTENT KATASTAR) - zadaci od Claude-a stižu tamo, a tamo se vraća i izveštaj
    def drive_folder(self):
        """Folder ASISTENT KATASTAR na Drive-u: izabran u Alati > Folder na Drive-u, ili pronađen sam; None = nema."""
        izbor = self.baza.podesavanje("drive_folder", "")
        if izbor == "-":
            return None
        if izbor:
            return izbor if os.path.isdir(izbor) else None
        if not hasattr(self, "_drive_nadjen"):
            self._drive_nadjen = nadji_drive_folder()
        return self._drive_nadjen

    def drive_zadaci(self):
        d = self.drive_folder()
        if not d:
            return None
        z = os.path.join(d, "zadaci")
        try:
            os.makedirs(z, exist_ok=True)
        except OSError:
            return None
        return z

    def _uzmi_sa_drive(self):
        """Prvi zadatak iz Drive foldera ide u lokalni zadaci/u radu (ime počinje sa drive__: izveštaj ide i na Drive).
        Vraća ime fajla u 'u radu' ili None."""
        self._drive_tik = getattr(self, "_drive_tik", 0) + 1
        if self._drive_tik % 3 != 1:          # Drive se gleda na svakih 15 s (lokalni folder na 5 s)
            return None
        dz = self.drive_zadaci()
        if not dz:
            return None
        try:
            imena = sorted(f for f in os.listdir(dz) if f.lower().endswith(".json") and not f.startswith("."))
        except OSError:
            return None
        if not imena:
            return None
        u_radu = os.path.join(ZADACI_DIR, "u radu")
        os.makedirs(u_radu, exist_ok=True)
        ime = "drive__" + imena[0]
        try:
            shutil.copy2(os.path.join(dz, imena[0]), os.path.join(u_radu, ime))
            os.remove(os.path.join(dz, imena[0]))
        except OSError as e:
            upisi_dnevnik("ZADACI (Drive): %r" % (e,))
            return None
        return ime

    def _proveri_zadatke(self):
        """Na svakih nekoliko sekundi: ako program ne radi ništa drugo, uzima prvi zadatak iz foldera zadaci
        (v35: ili iz foldera zadaci na Drive-u)."""
        if self._zadatak is not None or self.posao is not None or getattr(self, "_pdf_radi", False):
            return
        try:
            imena = sorted(f for f in os.listdir(ZADACI_DIR) if f.lower().endswith(".json"))
        except OSError:
            return
        u_radu = os.path.join(ZADACI_DIR, "u radu")
        if imena:
            os.makedirs(u_radu, exist_ok=True)
            ime = imena[0]
            os.replace(os.path.join(ZADACI_DIR, ime), os.path.join(u_radu, ime))
        else:
            ime = self._uzmi_sa_drive()
            if not ime:
                return
        put = os.path.join(u_radu, ime)
        sa_drive = ime.startswith("drive__")
        ime = ime[len("drive__"):] if sa_drive else ime
        z = {"fajl": ime, "put": put, "naziv": os.path.splitext(ime)[0], "rezultat": [], "provera": {},
             "sa_drive": sa_drive, "postojece": "preskoci"}
        try:
            z.update(ucitaj_zadatak(put))
        except (OSError, ValueError) as e:
            z["greska"] = "neispravan zadatak: %s" % e
            self._zavrsi_zadatak(z)
            return
        self._zadatak = z
        self.log("--- Zadatak: %s (%s) ---" % (z["naziv"], br_parcela(len(z["parcele"]))), "novo_naslov")
        self.lbl_opis.configure(text="Zadatak %s: pripremam parcele..." % z["naziv"])
        nedostaju = sorted({x["opstina_id"] or self._opstina_id(x["opstina"]) for x in z["parcele"]
                            if not x["ko_id"]} - {None})
        nedostaju = [oid for oid in nedostaju if self.sif.ko_za(oid) is None]
        if not nedostaju:
            self._dodaj_parcele_zadatka(z)
            return

        def nit():                            # KO opštine koja još nije otvarana: spisak sa sajta (bez captche)
            ucitane, greska = {}, None
            try:
                s = Sajt()
                for oid in nedostaju:
                    ucitane[oid] = s.ko(oid)
            except Exception as e:
                greska = e
                upisi_dnevnik("ZADATAK KO: %r" % (e,))
            self.root.after(0, self._ko_za_zadatak, z, ucitane, greska)
        self.lbl_opis.configure(text="Zadatak %s: učitavam katastarske opštine sa sajta..." % z["naziv"])
        threading.Thread(target=nit, daemon=True).start()

    def _ko_za_zadatak(self, z, ucitane, greska):
        for oid, lista in ucitane.items():
            if lista:
                self.sif.postavi_ko(oid, [list(x) for x in lista])
        z["greska_ko"] = ("katastarske opštine nisu učitane sa sajta (%s)" % greska) if greska else ""
        self._dodaj_parcele_zadatka(z)

    def _opstina_id(self, naziv):
        k = lat(norm(naziv))
        nadjene = [o[0] for o in self.sif.opstine if k and lat(norm(o[1])) == k]
        return nadjene[0] if len(nadjene) == 1 else None

    def _mesto_zadatka(self, x, greska_ko=""):
        """Parcela iz zadatka -> (opstina_id, opstina, ko_id, ko) ili razlog (tekst)."""
        oid = x["opstina_id"] or (self._opstina_id(x["opstina"]) if x["opstina"] else None)
        if x["opstina"] and not oid:
            return "nepoznata opština %s" % x["opstina"]
        k = lat(norm(x["ko"]))
        if oid:
            lista = [(oid, y) for y in self.sif.ko_za(oid) or []]
        else:                                 # samo KO: traži se u svim poznatim opštinama
            lista = [(int(o), y) for o, kos in self.sif.ko.items() for y in kos]
        nadjene = [(o, y) for o, y in lista if (x["ko_id"] and str(y[0]) == str(x["ko_id"])) or
                   (not x["ko_id"] and lat(norm(y[1])) == k)]
        nadjene = list({(o, y[0]): (o, y) for o, y in nadjene}.values())
        if len(nadjene) > 1:
            return "KO %s postoji u više opština - treba navesti opštinu" % x["ko"]
        if not nadjene:
            if x["ko_id"] and x["ko"] and oid:
                return oid, self.sif.naziv_opstine(oid) or x["opstina"], x["ko_id"], x["ko"]
            return greska_ko or "KO %s nije pronađena%s" % (x["ko"] or x["ko_id"], (" u opštini %s" % (
                self.sif.naziv_opstine(oid) or x["opstina"])) if oid else "")
        o, y = nadjene[0]
        return o, self.sif.naziv_opstine(o) or x["opstina"], y[0], y[1]

    def _dodaj_parcele_zadatka(self, z):
        """Parcele iz zadatka u praćenje (grupa klijenta; stan iz ugovora = prati se samo on), pa provera."""
        if self._zadatak is not z:
            return
        pids, novi, vidjene = [], set(), []
        z["preskoceno"] = 0
        for x in z["parcele"]:
            r = {"ko": x["ko"] or str(x["ko_id"]), "broj": x["broj"], "stan": x["stan"], "ulaz": x["ulaz"]}
            z["rezultat"].append(r)
            m = self._mesto_zadatka(x, z.get("greska_ko", ""))
            if isinstance(m, str):
                r["stanje"] = "nije dodata - " + m
                continue
            oid, opstina, ko_id, ko = m
            r["ko"] = ko
            novo = self.baza.dodaj(oid, opstina, ko_id, ko, x["broj"], klijent=z["klijent"], grupa=z["grupa"],
                                   napomena=x["napomena"])
            p = self.baza.parcela_po_mestu(ko_id, x["broj"])
            if p is None:
                r["stanje"] = "nije dodata - greška baze"
                continue
            r["pid"] = p["id"]
            if novo:
                r["stanje"] = "dodata u praćenje" + ((", grupa %s" % p["grupa"]) if p["grupa"] else "")
                novi.add(p["id"])
                if x["stan"]:
                    self.baza.postavi_stavke(p["id"], [kljuc_stana(x["stan"], x["ulaz"])])
            elif p["id"] in vidjene:         # ista parcela još jednom (npr. dva stana u istoj zgradi)
                r["stanje"] = "ista parcela kao gore"
                prate = pracene_stavke(p)
                if p["id"] in novi and prate:
                    self.baza.postavi_stavke(p["id"], (prate + [kljuc_stana(x["stan"], x["ulaz"])]) if x["stan"]
                                             else [])
                continue
            else:
                # v35 (Dejan: "neke su već u aplikaciji, neću duplikate"): parcela koja je već u praćenju se ne
                # dodaje ponovo i podrazumevano se ne proverava; "premesti" je prebacuje u grupu zadatka
                r["stanje"] = "već je bila u praćenju" + ((", grupa %s" % p["grupa"]) if p["grupa"] else "")
                if z["postojece"] == "premesti" and z["grupa"] and lat(p["grupa"]) != lat(z["grupa"]):
                    self.baza.promeni_grupu([p["id"]], z["grupa"])
                    r["stanje"] += " - premeštena u grupu %s" % (self.baza.parcela_po_mestu(ko_id, x["broj"])["grupa"])
                if z["postojece"] != "proveri":
                    r["preskocena"] = True
                    z["preskoceno"] += 1
                    vidjene.append(p["id"])
                    continue
            vidjene.append(p["id"])
            pids.append(p["id"])
        z["pids"] = pids
        self.osvezi_listu()
        if not pids:
            if not z["preskoceno"]:
                z["greska"] = "nijedna parcela nije dodata"
            self._zavrsi_zadatak(z)
            return
        po_id = {p["id"]: p for p in self.baza.parcele(pids)}
        zadaci = [{"pid": p["id"], "opstina_id": p["opstina_id"], "opstina": p["opstina"], "ko_id": p["ko_id"],
                   "ko": p["ko"], "broj": p["broj"], "p": p, "stavke": pracene_stavke(p), "zadatak": True}
                  for p in (po_id[i] for i in pids if i in po_id)]
        z["mesta"] = {x["pid"]: (x["ko_id"], x["ko"], x["broj"]) for x in zadaci}    # pod tim imenom se čuvaju listovi
        z["faza"] = "provera"
        self.log("Zadatak %s: u praćenju %s, skidam listove sa sajta..." % (z["naziv"], br_parcela(len(zadaci))),
                 "info")
        self.nb.select(1)
        self._pokreni(zadaci, "provera", nep="sve")

    def _posle_provere_zadatka(self, posao):
        """Provera zadatka je gotova: ishod po parceli, pa PDF svih listova (bez pitanja za folder)."""
        z = self._zadatak
        po_id = {p["id"]: p for p in self.baza.parcele(z["pids"])}
        mesta = []
        for r in z["rezultat"]:
            if "pid" not in r or r["pid"] not in po_id:
                continue
            p = po_id[r["pid"]]
            ishod = z["provera"].get(r["pid"])
            r["provera"] = "skinuto sa sajta" if ishod == "ok" else (ishod or "nije stigla na red")
            if ishod == "ok":
                mesta.append(z["mesta"].get(r["pid"]) or (p["ko_id"], p["ko"], p["broj"]))
                if r.get("stan") and kljuc_stana(r["stan"], r.get("ulaz", "")) in pracene_stavke(p):
                    r["napomena"] = "stan %s nije pronađen jednoznačno na parceli" % r["stan"]
        if self._korisnik_prekinuo:
            z["greska"] = "prekinuto (Prekini)"
            self._zavrsi_zadatak(z)
            return
        if posao.stop:
            z["greska"] = "sajt je tražio pauzu - deo parcela nije skinut, pokreni zadatak ponovo kasnije"
        mesta = list(dict.fromkeys(mesta))
        if not z["sacuvaj_pdf"] or not mesta:
            self._zavrsi_zadatak(z)
            return
        poslovi, bez = poslovi_pdf(mesta)
        if not poslovi:
            z["pdf_rez"] = {"folder": "", "sacuvano": 0, "nije": [], "bez_originala": bez}
            self._zavrsi_zadatak(z)
            return
        z["faza"] = "pdf"
        podfolder = "%s %s (%s)" % (dt.datetime.now().strftime("%Y-%m-%d %H.%M"), z["grupa"] or z["naziv"],
                                    br_parcela(len(mesta)))
        osnova = z["folder"] or self.pdf_folder() or PDF_DIR
        if not self._napravi_pdf(poslovi, bez, "", podfolder, "Zadatak %s: pravim PDF (%d)..." % (
                z["naziv"], len(poslovi)), osnova=osnova):
            z["greska"] = "PDF nije napravljen (nema Edge/Chrome ili folder %s nije dostupan)" % osnova
            self._zavrsi_zadatak(z)

    def _zavrsi_zadatak(self, z):
        """Izveštaj (tekst i JSON) u zadaci/izvestaji, zadatak u zadaci/obradjeni, poruka i obaveštenje."""
        self._zadatak = None
        tekst = izvestaj_zadatka_tekst(z)
        osnova = os.path.splitext(z["fajl"])[0]
        try:
            for pod in ("izvestaji", "obradjeni"):
                os.makedirs(os.path.join(ZADACI_DIR, pod), exist_ok=True)
            with open(os.path.join(ZADACI_DIR, "izvestaji", osnova + ".txt"), "w", encoding="utf-8") as f:
                f.write(tekst)
            with open(os.path.join(ZADACI_DIR, "izvestaji", osnova + ".json"), "w", encoding="utf-8") as f:
                json.dump({k: z.get(k) for k in ("naziv", "klijent", "grupa", "greska", "rezultat", "pdf_rez",
                                                 "preskoceno")},
                          f, ensure_ascii=False, indent=1)
            cilj, k = os.path.join(ZADACI_DIR, "obradjeni", z["fajl"]), 2
            while os.path.exists(cilj):
                cilj, k = os.path.join(ZADACI_DIR, "obradjeni", "%s (%d).json" % (osnova, k)), k + 1
            if os.path.exists(z["put"]):
                os.replace(z["put"], cilj)
        except OSError as e:
            upisi_dnevnik("ZADATAK IZVESTAJ: %r" % (e,))
        if z.get("sa_drive"):                 # v35: izveštaj i u folder na Drive-u (tamo ga čita Claude)
            dz = self.drive_zadaci()
            try:
                if dz:
                    os.makedirs(os.path.join(dz, "izvestaji"), exist_ok=True)
                    for ext in (".txt", ".json"):
                        shutil.copy(os.path.join(ZADACI_DIR, "izvestaji", osnova + ext),
                                    os.path.join(dz, "izvestaji", osnova + ext))
            except OSError as e:
                upisi_dnevnik("ZADATAK IZVESTAJ (Drive): %r" % (e,))
        rez = [r for r in z.get("rezultat", []) if not r.get("preskocena")]
        ok = sum(r.get("provera") == "skinuto sa sajta" for r in rez)
        pdf = z.get("pdf_rez") or {}
        sazetak = "skinuto %d od %d%s%s%s" % (ok, len(rez), (", PDF %d" % pdf["sacuvano"]) if pdf else "",
                                              (", već u praćenju %d" % z["preskoceno"]) if z.get("preskoceno") else "",
                                              (" - " + z["greska"]) if z.get("greska") else "")
        self.log("--- Zadatak %s: %s ---" % (z["naziv"], sazetak),
                 "neuspeh_naslov" if z.get("greska") or ok < len(rez) else "uspeh")
        self.lbl_opis.configure(text="Zadatak %s: %s" % (z["naziv"], sazetak))
        if os.name == "nt" and self.obavestenje_var.get():
            try:
                posalji_obavestenje("Asistent KATASTAR: zadatak završen", [z["naziv"], sazetak])
            except Exception:
                upisi_dnevnik(traceback.format_exc())

    def _promeni_velicinu(self):
        self.baza.postavi_podesavanje("velicina", self.velicina_var.get())
        messagebox.showinfo("Veličina prikaza", "Nova veličina prikaza važi kad zatvoriš i ponovo pokreneš program.")

    def _otvori(self, putanja):
        try:
            os.startfile(putanja)
        except Exception as e:
            messagebox.showinfo("Fajl", "Fajl je ovde:\n%s\n(%s)" % (putanja, e))

    def _napravi_zaglavlje(self):
        """Tamnoplava traka sa ikonicom i nazivom programa (kao u Asistent PRO)."""
        z = tk.Frame(self.root, bg=T_ZAGLAVLJE, height=px(54))
        z.pack(fill="x")
        z.pack_propagate(False)
        self._ikona_mala = None
        png = putanja_ikone(png=True)
        if png:
            try:
                img = tk.PhotoImage(file=png)
                k = max(1, img.width() // px(34))
                self._ikona_mala = img.subsample(k, k)
                tk.Label(z, image=self._ikona_mala, bg=T_ZAGLAVLJE).pack(side="left", padx=(16, 10))
            except tk.TclError:
                self._ikona_mala = None
        tk.Label(z, text="Asistent KATASTAR", bg=T_ZAGLAVLJE, fg="#ffffff", font=("Segoe UI", 15, "bold")).pack(
            side="left", padx=(0 if self._ikona_mala else 16, 12))
        tk.Label(z, text="pretraga i praćenje parcela  ·  eKatastar, Republički geodetski zavod",
                 bg=T_ZAGLAVLJE, fg="#b9c8e6", font=("Segoe UI", 10)).pack(side="left", pady=(4, 0))
        dani = ("ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota", "nedelja")
        d = dt.date.today()
        tk.Label(z, text="%s, %s" % (dani[d.weekday()], d.strftime("%d.%m.%Y.")), bg=T_ZAGLAVLJE, fg="#dfe7f6",
                 font=("Segoe UI", 10)).pack(side="right", padx=16)

    def _napravi_statusnu_traku(self):
        s = ttk.Frame(self.root, padding=(16, 4, 16, 6))
        s.pack(side="bottom", fill="x")
        s.columnconfigure(1, weight=1)
        self.napredak = ttk.Progressbar(s, length=170, mode="determinate")
        self.napredak.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="w")
        self.lbl_opis = ttk.Label(s, text="Spremno.", font=FONT_B)
        self.lbl_opis.grid(row=0, column=1, sticky="w")
        self.lbl_stanje = ttk.Label(s, text="", foreground=T_AKCENT)
        self.lbl_stanje.grid(row=1, column=1, sticky="w")
        self.lbl_desno = ttk.Label(s, text="", style="Sivo.TLabel")
        self.lbl_desno.grid(row=0, column=2, rowspan=2, sticky="e", padx=(10, 0))

    def _osvezi_desno(self):
        n = len(self.citac.poznati_znaci())
        self.lbl_desno.configure(text="čitač captche zna %d znakova%s" % (
            n, "" if n >= 50 else " (uči iz svakog prihvaćenog koda)"))

    def _kombinacije_opstina(self, f, red, kol, na_ko=None):
        """Opština + KO: naziv može da se upiše (ćirilicom ili latinicom, npr. 'vozd') pa se izabere iz predloga,
        a strelica na polju i dalje otvara ceo spisak. Vraća (cb_opstina, cb_ko, lbl)."""
        cb_o = ttk.Combobox(f, width=26, values=[o[1] for o in self.sif.opstine])
        cb_o.grid(row=red, column=kol, padx=(0, 8), sticky="w")
        cb_k = ttk.Combobox(f, width=26)
        cb_k.grid(row=red, column=kol + 1, padx=(0, 8), sticky="w")
        lbl = ttk.Label(f, text="", foreground="#555")
        cb_o._ko = []
        cb_o._za = None              # opština čije su KO trenutno u listi
        cb_o._predlozi = PredloziListe(cb_o, izabrano=lambda: self._opstina_izabrana(cb_o, cb_k, lbl),
                                       kucanje=lambda: self._opstina_kuca(cb_o, cb_k), dalje=cb_k)
        cb_k._predlozi = PredloziListe(cb_k)
        return cb_o, cb_k, lbl

    def _izabrana_opstina(self, cb_o):
        i = cb_o.current()
        return self.sif.opstine[i] if 0 <= i < len(self.sif.opstine) else None

    def _izabrana_ko(self, cb_o, cb_k):
        if cb_o._za is None or cb_o._za != self._izabrana_opstina(cb_o):
            return None
        i = cb_k.current()
        return cb_o._ko[i] if 0 <= i < len(cb_o._ko) else None

    def _opstina_kuca(self, cb_o, cb_k):
        """Upisan tekst više nije izabrana opština: lista KO se prazni dok se opština ponovo ne izabere."""
        if cb_o._za is not None and self._izabrana_opstina(cb_o) == cb_o._za:
            return
        cb_o._za = None
        cb_o._ko = []
        if cb_k.get() or cb_k.cget("values"):
            cb_k.set("")
            cb_k.configure(values=[])

    def _opstina_izabrana(self, cb_o, cb_k, lbl):
        o = self._izabrana_opstina(cb_o)
        if o is not None and o == cb_o._za and cb_o._ko:
            return                   # ista opština, KO su već u listi
        cb_k.set("")
        cb_k.configure(values=[])
        cb_o._ko = []
        cb_o._za = None
        if not o:
            return
        ko = self.sif.ko_za(o[0])
        if ko:
            cb_o._ko = ko
            cb_o._za = o
            cb_k.configure(values=[k[1] for k in ko])
            if len(ko) == 1:
                cb_k.current(0)
            lbl.configure(text="")
            return
        lbl.configure(text="učitavam katastarske opštine sa sajta...")
        cb_k.configure(state="disabled")

        def radi():
            try:
                lista = Sajt().ko(o[0])
                self.sif.postavi_ko(o[0], lista)
                poruka = ""
            except Exception as e:
                upisi_dnevnik("KO za %s: %s" % (o[1], traceback.format_exc()))
                poruka = "KO nisu učitane: %s" % e

            def gotovo():
                cb_k.configure(state="normal")
                lbl.configure(text=poruka)
                if poruka:
                    self.log("%s - %s" % (o[1], poruka), "greska")
                if self._izabrana_opstina(cb_o) == o:
                    self._opstina_izabrana(cb_o, cb_k, lbl) if not poruka else None
            self.root.after(0, gotovo)
        threading.Thread(target=radi, daemon=True).start()

    def osvezi_opstine(self):
        def radi():
            try:
                lista = Sajt().opstine()
                self.sif.postavi_opstine(lista)
                self.root.after(0, lambda: (self._postavi_opstine_u_liste(),
                                            self.log("Spisak opština osvežen (%d)." % len(lista), "info")))
            except Exception as e:
                poruka = "Spisak opština nije osvežen: %s" % e
                self.root.after(0, lambda: self.log(poruka, "greska"))
        threading.Thread(target=radi, daemon=True).start()

    def _postavi_opstine_u_liste(self):
        for cb in (self.cb_opstina,):
            cb.configure(values=[o[1] for o in self.sif.opstine])

    # --- kartica: pretraga vise parcela ------------------------------------
    def _napravi_pretragu(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text="  Pretraga više parcela  ")
        forma = kartica(tab)
        forma.pack(fill="x")
        f = ttk.Frame(forma, style="Kartica.TFrame", padding=(14, 10, 14, 10))
        f.pack(fill="x")
        self._naslovi_pretrage = []
        for kol in range(3):
            lbl = ttk.Label(f, text="", style="KarticaSivo.TLabel")
            lbl.grid(row=0, column=kol, sticky="w", pady=(0, 3))
            self._naslovi_pretrage.append(lbl)
        self.cb_opstina, self.cb_ko, self.lbl_ko = self._kombinacije_opstina(f, 1, 0)
        self.lbl_ko.configure(style="KarticaSivo.TLabel", wraplength=px(230))
        self.lbl_ko.grid(row=2, column=1, sticky="w", pady=(4, 0))
        # Dejan (v26): "nema potrebe ovoliko polje", Enter pokreće pretragu; nalepljen spisak (više redova) ide u red
        self.txt_brojevi = self._polje_u_redu(f, 60)
        self.txt_brojevi.grid(row=1, column=2, sticky="we", padx=(0, 12))
        self.cb_ko._predlozi.dalje = self.txt_brojevi
        f.columnconfigure(2, weight=1)
        # Dejan: pretraga i po adresi, kao na eKatastru - opština, ulica sa spiska sajta, kućni broj; posle toga
        # svaka parcela na adresi se traži kao i po broju, pa su rezultati isti (tabela, prozor parcele, PDF, praćenje)
        nac = ttk.Frame(f, style="Kartica.TFrame")
        nac.grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(nac, text="Traži po:", style="KarticaSivo.TLabel").pack(side="left")
        self.nacin_var = tk.StringVar(value="adresa" if self.baza.podesavanje("nacin_pretrage") == "adresa"
                                      else "parcela")
        self._radio_nacina = {}
        for vr, tx in (("parcela", "parceli"), ("adresa", "adresi")):
            rb = ttk.Radiobutton(nac, text=tx, value=vr, variable=self.nacin_var, style="Kartica.TRadiobutton",
                                 command=self._nacin_pretrage)
            rb.pack(side="left", padx=(px(6), 0))
            self._radio_nacina[vr] = rb
        self.cb_ulica = ttk.Combobox(f, width=42)
        self.cb_ulica.grid(row=1, column=1, padx=(0, 8), sticky="w")
        self.txt_kbr = self._polje_u_redu(f, 34)
        self.txt_kbr.grid(row=1, column=2, sticky="we", padx=(0, 12))
        self.cb_ulica._predlozi = PredloziListe(self.cb_ulica, kucanje=self._ulica_kuca, dalje=self.txt_kbr)
        self._ulice_po_nazivu = {}   # naziv ulice sa sajta -> ID ulice (za opštinu self._ulice_za)
        self._ulice_za = None
        self._ulice_kes = {}         # (opština, upisan tekst) -> [(naziv, ID)]
        self._ulice_upit = None      # poslednji upit; stariji odgovori se ne prikazuju
        self._ulica_posle = None
        self._sajt_ulica = None
        self._ulice_brava = threading.Lock()
        pr = self.cb_opstina._predlozi
        izabrana = pr.izabrano
        pr.izabrano = lambda: (izabrana(), self._opstina_za_ulicu())
        self._nacin_pretrage(sacuvaj=False)
        dug = ttk.Frame(f, style="Kartica.TFrame")
        dug.grid(row=1, column=3, rowspan=2, sticky="n")
        self.btn_pretrazi = ttk.Button(dug, text="Pretraži", style="Glavno.TButton", width=14, command=self.pretrazi)
        self.btn_pretrazi.pack(fill="x")
        self.btn_prekini1 = ttk.Button(dug, text="Prekini", style="Prekid.TButton", command=self._prekini,
                                       state="disabled")
        self.btn_prekini1.pack(fill="x", pady=(6, 0))

        # Dejan: bez panela "Rezultat pretrazivanja parcela" ispod tabele; sve se vidi u rezultatima, a dvoklik
        # na parcelu otvara delove, zgrade i stanove u posebnom prozoru
        rez = kartica(tab)
        rez.pack(fill="both", expand=True, pady=(px(10), 0))
        zag = ttk.Frame(rez, style="Kartica.TFrame", padding=(12, 8, 12, 6))
        zag.pack(fill="x")
        ttk.Label(zag, text="Rezultati pretrage", style="Naslov.TLabel").pack(side="left")
        self.lbl_rez = ttk.Label(zag, text="", style="KarticaSivo.TLabel")
        self.lbl_rez.pack(side="left", padx=(12, 0))
        for tx, cmd in (("Očisti", self.ocisti_rezultate), ("Izvezi u Excel (CSV)...", self.izvezi),
                        ("Dodaj izabrane u praćenje...", self.dodaj_iz_pretrage),
                        ("Otvori u posebnom prozoru", self.detalji_pretrage),
                        ("Folder za PDF...", self.izaberi_pdf_folder),
                        ("Sačuvaj sve kao PDF", self.pdf_pretrage)):
            ttk.Button(zag, text=tx, style="Mali.TButton", command=cmd).pack(side="right", padx=(6, 0))
        tk.Frame(rez, bg=T_IVICA, height=1).pack(fill="x")
        fr = ttk.Frame(rez, style="Kartica.TFrame")
        fr.pack(fill="both", expand=True)
        kol = [k[0] for k in KOLONE_PRETRAGE]
        self.tree_p = ttk.Treeview(fr, columns=kol[1:], show="tree headings", selectmode="extended", height=4)
        self.tree_p.heading("#0", text="KO", anchor="w")
        self.tree_p.column("#0", width=px(130), minwidth=px(80), stretch=False)
        for k, naslov, w, an in KOLONE_PRETRAGE[1:]:
            self.tree_p.heading(k, text=naslov, anchor=an if an != "e" else "e")
            self.tree_p.column(k, width=px(w), minwidth=px(40), anchor=an, stretch=False)
        self.tree_p.tag_configure("nema", foreground=BOJA_NEUSPEH)
        self.tree_p.tag_configure("par", background="#f7f9fc")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tree_p.yview)
        sbx = ttk.Scrollbar(fr, orient="horizontal", command=self.tree_p.xview)
        self.tree_p.configure(yscrollcommand=sb.set, xscrollcommand=sbx.set)
        sb.pack(side="right", fill="y")
        sbx.pack(side="bottom", fill="x")
        self.tree_p.pack(side="left", fill="both", expand=True)
        self.tree_p.bind("<Double-1>", lambda e: self.detalji_pretrage())
        self.tree_p.bind("<Return>", lambda e: self.detalji_pretrage())
        self.tree_p.bind("<Button-3>", self._meni_pretrage)
        self._kop_pretrage = KopiranjeCelija(self, self.tree_p, otvori=self.detalji_pretrage,
                                             kolona_broja=("parcela", "Kopiran broj parcele"))

    NASLOVI_PRETRAGE = {
        "parcela": ("Opština", "Katastarska opština",
                    "Brojevi parcela  (zarez ili razmak;  podbroj 10383/1;  opseg 100-110;  Enter = Pretraži)"),
        "adresa": ("Opština", "Ulica  (upiši bar 2 slova, pa izaberi sa spiska)",
                   "Kućni brojevi  (zarez ili razmak;  npr. 5, 7, 12a;  Enter = Pretraži)")}

    def _polje_u_redu(self, roditelj, sirina):
        """Polje za brojeve u jednom redu: Enter = Pretraži; nalepljen spisak iz više redova se spoji zarezima."""
        t = tk.Text(roditelj, height=1, width=sirina, font=("Segoe UI", 11), wrap="none", undo=True, padx=px(4),
                    pady=px(3))
        for dog in ("<Return>", "<KP_Enter>", "<Control-Return>"):
            t.bind(dog, lambda e: (self.pretrazi(), "break")[1])
        t.bind("<<Paste>>", self._nalepi_u_red)
        return t

    @staticmethod
    def _nalepi_u_red(e):
        w = e.widget
        try:
            tekst = w.clipboard_get()
        except tk.TclError:
            return "break"
        tekst = ", ".join(x for x in (r.strip(" ,;\t") for r in tekst.splitlines()) if x)
        try:
            w.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        w.insert("insert", tekst)
        w.see("insert")
        return "break"

    def _nacin_pretrage(self, sacuvaj=True):
        """Pretraga po broju parcele (opština, KO, brojevi) ili po adresi (opština, ulica, kućni brojevi)."""
        nacin = "adresa" if self.nacin_var.get() == "adresa" else "parcela"
        adresa = nacin == "adresa"
        for w, vidljiv in ((self.cb_ko, not adresa), (self.txt_brojevi, not adresa), (self.cb_ulica, adresa),
                           (self.txt_kbr, adresa)):
            if vidljiv:
                w.grid()
            else:
                w.grid_remove()
        for lbl, tx in zip(self._naslovi_pretrage, self.NASLOVI_PRETRAGE[nacin]):
            lbl.configure(text=tx)
        self.cb_ko._predlozi.sakrij()
        self.cb_ulica._predlozi.sakrij()
        self.cb_opstina._predlozi.dalje = self.cb_ulica if adresa else self.cb_ko
        if sacuvaj:
            self.baza.postavi_podesavanje("nacin_pretrage", nacin)

    def _opstina_za_ulicu(self):
        """Druga opština: ulica izabrana za prethodnu više ne važi."""
        o = self._izabrana_opstina(self.cb_opstina)
        if o and self._ulice_za is not None and o[0] != self._ulice_za:
            self.cb_ulica.set("")
            self.cb_ulica.configure(values=[])
            self._ulice_po_nazivu = {}
            self._ulice_za = None

    def _ulica_kuca(self):
        """Kucanje u polju ulice: posle kratke pauze ulice se traže na sajtu (kao na eKatastru, od 2 slova)."""
        if self._ulica_posle is not None:
            self.root.after_cancel(self._ulica_posle)
            self._ulica_posle = None
        pr = self.cb_ulica._predlozi
        o = self._izabrana_opstina(self.cb_opstina)
        tekst = self.cb_ulica.get().strip()
        if not o:
            pr.prazno = "prvo izaberi opštinu"
        elif len(tekst) < 2:
            pr.prazno = "upiši bar 2 slova naziva ulice"
        else:
            pr.prazno = "tražim ulice na sajtu..."
            self._ulica_posle = self.root.after(300, self._trazi_ulice)

    def _trazi_ulice(self):
        self._ulica_posle = None
        o = self._izabrana_opstina(self.cb_opstina)
        tekst = self.cb_ulica.get().strip()
        if not o or len(tekst) < 2:
            return
        kljuc = (o[0], tekst.casefold())
        self._ulice_upit = kljuc
        if kljuc in self._ulice_kes:
            self._ulice_stigle(o, tekst, kljuc, self._ulice_kes[kljuc], "")
            return

        def radi():
            try:
                with self._ulice_brava:
                    if self._sajt_ulica is None:
                        self._sajt_ulica = Sajt()
                    lista, greska = self._sajt_ulica.ulice(o[0], tekst), ""
            except Exception as e:
                upisi_dnevnik("ULICE %s %r: %s" % (o[1], tekst, traceback.format_exc()))
                lista, greska = None, str(e)
            self.root.after(0, lambda: self._ulice_stigle(o, tekst, kljuc, lista, greska))
        threading.Thread(target=radi, daemon=True).start()

    def _ulice_stigle(self, o, tekst, kljuc, lista, greska):
        if lista is not None:
            self._ulice_kes[kljuc] = lista
        if kljuc != self._ulice_upit or self._izabrana_opstina(self.cb_opstina) != o:
            return                   # u međuvremenu je upisano nešto drugo
        self._ulice_upit = None
        pr = self.cb_ulica._predlozi
        if lista is None:
            pr.prazno = "ulice nisu učitane sa sajta (%s)" % greska[:80]
            lista = []
        else:
            pr.prazno = "nema takve ulice u opštini %s" % o[1]
        if self._ulice_za != o[0]:
            self._ulice_po_nazivu = {}
            self._ulice_za = o[0]
        self._ulice_po_nazivu.update(dict(lista))
        self.cb_ulica.configure(values=[n for n, _ in lista])
        try:
            if self.cb_ulica.focus_get() is self.cb_ulica and self.cb_ulica.get().strip() == tekst:
                pr.osvezi()
                if lista and not pr.pogoci:          # sajt je našao ulicu po nečemu što ovde ne piše - pokaži je
                    pr.pogoci = [n for n, _ in lista]
                    pr.prikazi()
        except (KeyError, tk.TclError):
            pass

    def _razresi_unos(self, cb_o, cb_k):
        """Upisan, a još neizabran naziv (npr. 'vozdovac' pa odmah klik na Pretraži): bira se kao Enterom."""
        tekst_ko = cb_k.get()
        for cb in (cb_o, cb_k):
            try:
                if cb.current() < 0 and cb.get().strip():
                    v = cb._predlozi.razresi()
                    if v:
                        cb._predlozi.izaberi(v)
                cb._predlozi.sakrij()
            except tk.TclError:
                pass
            if cb is cb_o and tekst_ko and not cb_k.get():
                cb_k.set(tekst_ko)          # izbor opštine je ispraznio KO koja je već bila upisana

    def _meni_pretrage(self, e):
        iid = self.tree_p.identify_row(e.y)
        if iid and iid not in self.tree_p.selection():
            self.tree_p.selection_set(iid)
        kop = self._kop_pretrage
        kop.kolona_na_misu = kop.kolona_na(e.x, iid)
        m = tk.Menu(self.root, tearoff=0)
        if iid:
            m.add_command(label="Otvori u posebnom prozoru", command=self.detalji_pretrage)
            meni_kopiranja(m, kop, iid)
            m.add_separator()
            m.add_command(label="Dodaj izabrane u praćenje...", command=self.dodaj_iz_pretrage)
            m.add_separator()
        m.add_command(label="Sačuvaj PDF izvoda (izabrane, ili sve ako je izabran jedan red)",
                      command=self.pdf_pretrage)
        m.add_command(label="Folder za PDF izvode...", command=self.izaberi_pdf_folder)
        m.add_command(label="Izvezi u Excel (CSV)...", command=self.izvezi)
        m.add_command(label="Očisti rezultate", command=self.ocisti_rezultate)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def pretrazi(self):
        if self.posao:
            return
        if self.nacin_var.get() == "adresa":
            self._pretrazi_adresu()
            return
        self._razresi_unos(self.cb_opstina, self.cb_ko)
        o = self._izabrana_opstina(self.cb_opstina)
        k = self._izabrana_ko(self.cb_opstina, self.cb_ko)
        brojevi, lose = raspakuj_brojeve(self.txt_brojevi.get("1.0", "end"))
        if not o or not k:
            messagebox.showwarning("Pretraga", "Izaberi opštinu i katastarsku opštinu.")
            return
        if lose:
            messagebox.showwarning("Pretraga", "Neispravni brojevi parcela: %s\n\nFormat: 10383 ili 10383/1, opseg 100-110."
                                   % ", ".join(lose[:10]))
            return
        if not brojevi:
            messagebox.showwarning("Pretraga", "Upiši bar jedan broj parcele.")
            return
        zadaci = [{"opstina_id": o[0], "opstina": o[1], "ko_id": k[0], "ko": k[1], "broj": b} for b in brojevi]
        self.log("--- Pretraga %d parcel%s, KO %s, %s ---" % (len(zadaci), "e" if len(zadaci) == 1 else "a", k[1], sada()), "info")
        self._pokreni(zadaci, "pretraga")

    def _pretrazi_adresu(self):
        cb = self.cb_opstina
        try:
            if cb.current() < 0 and cb.get().strip():
                v = cb._predlozi.razresi()
                if v:
                    cb._predlozi.izaberi(v)
            cb._predlozi.sakrij()
        except tk.TclError:
            pass
        o = self._izabrana_opstina(cb)
        if not o:
            messagebox.showwarning("Pretraga po adresi", "Izaberi opštinu.")
            return
        ulica = norm(self.cb_ulica.get())
        uid = self._ulice_po_nazivu.get(ulica) if self._ulice_za == o[0] else None
        if uid is None and self._ulice_za == o[0]:
            v = self.cb_ulica._predlozi.razresi()            # upisano, a nije izabrano sa spiska
            if v in self._ulice_po_nazivu:
                self.cb_ulica._predlozi.izaberi(v)
                ulica, uid = v, self._ulice_po_nazivu[v]
        self.cb_ulica._predlozi.sakrij()
        if uid is None:
            messagebox.showwarning("Pretraga po adresi", "Upiši bar 2 slova naziva ulice i izaberi ulicu sa spiska "
                                   "(kao na eKatastru, spisak dolazi sa sajta za opštinu %s)." % o[1])
            return
        brojevi, lose = raspakuj_kucne(self.txt_kbr.get("1.0", "end"))
        if lose:
            messagebox.showwarning("Pretraga po adresi", "Neispravni kućni brojevi: %s\n\nKućni broj ima najviše 5 "
                                   "znakova (npr. 5, 12a), brojevi se odvajaju zarezom ili razmakom." % ", ".join(lose[:10]))
            return
        if not brojevi:
            messagebox.showwarning("Pretraga po adresi", "Upiši bar jedan kućni broj.")
            return
        kratko = kratka_ulica(ulica)
        zadaci = [{"opstina_id": o[0], "opstina": o[1], "ulica": ulica, "ulica_id": uid, "kbr": b,
                   "adresa": "%s %s" % (kratko, b)} for b in brojevi]
        self.log("--- Pretraga po adresi: %s, kućni broj%s %s, opština %s, %s ---" % (
            kratko, "" if len(brojevi) == 1 else "evi", ", ".join(brojevi), o[1], sada()), "info")
        self._pokreni(zadaci, "pretraga")

    @staticmethod
    def _vrednosti_reda(z, podaci):
        sn = napravi_snimak(podaci)
        delovi = sn["delovi"]
        pov = sn.get("ukupno") or (delovi[0][1] if delovi else "")
        ulice = "; ".join(dict.fromkeys(d[2] for d in delovi if d[2]))
        nacini = "; ".join(dict.fromkeys(d[3] for d in delovi if d[3]))
        status = ("pronađeno" + ((" po adresi %s" % z["adresa"]) if z.get("adresa") else "") +
                  ((" (napomena: %s)" % podaci["napomene"][0]) if podaci.get("napomene") else ""))
        vlasnici, tereti = vlasnici_tereti(sn)
        return (z["broj"], len(delovi), pov, ulice, nacini, len(sn["objekti"]) or "",
                len(sn["posebni"]) or "", vlasnici, tereti, status)

    def _dodaj_red_pretrage(self, z, podaci, razlog):
        iid = z.get("zameni")
        if iid in self.rezultati and self.tree_p.exists(iid):
            # "Učitaj sa sajta": isti red parcele dobija nove podatke (ako nije uspelo, stari ostaju)
            if podaci is not None:
                stari = self.rezultati[iid][1]
                if stari and not podaci.get("nep_potpuno"):        # prekinuto: ranije učitane stavke ostaju
                    nep = dict(podaci.get("nepokretnost") or {})
                    for k, v in (stari.get("nepokretnost") or {}).items():
                        nep.setdefault(k, v)
                    podaci = dict(podaci, nepokretnost=nep)
                self.rezultati[iid] = (z, podaci, razlog)
                self.tree_p.item(iid, values=self._vrednosti_reda(z, podaci))
                self._prilagodi_kolone(self.tree_p)
            return
        iid = "r%d" % (len(self.rezultati) + 1)
        self.rezultati[iid] = (z, podaci, razlog)
        par = ("par",) if len(self.rezultati) % 2 == 0 else ()
        if podaci is None:
            self.tree_p.insert("", "end", iid=iid, text=z["ko"], values=(z["broj"],) + ("",) * 8 +
                               ("nije pronađeno: " + razlog,), tags=("nema",) + par)
        else:
            self.tree_p.insert("", "end", iid=iid, text=z["ko"], tags=par, values=self._vrednosti_reda(z, podaci))
            if not self.tree_p.selection():
                self.tree_p.selection_set(iid)
                self.tree_p.focus(iid)
        self.tree_p.see(iid)
        self._prilagodi_kolone(self.tree_p)
        n_ok = sum(1 for _, p, _ in self.rezultati.values() if p)
        self.lbl_rez.configure(text="%d parcel%s, pronađeno %d" % (len(self.rezultati),
                                                                  "a" if len(self.rezultati) == 1 else "e", n_ok))

    def ocisti_rezultate(self):
        if self.posao and self.rezim == "pretraga":
            return
        self._kop_pretrage.zatvori()
        self.tree_p.delete(*self.tree_p.get_children(""))
        self.rezultati.clear()
        self.lbl_rez.configure(text="")

    def _izabrani_rezultati(self):
        iids = []
        for iid in self.tree_p.selection():
            koren = iid.split("_")[0]
            if koren not in iids:
                iids.append(koren)
        return [self.rezultati[i] for i in iids if i in self.rezultati]

    def detalji_pretrage(self):
        rez = self._izabrani_rezultati()
        if not rez:
            return
        z, podaci, razlog = rez[0]
        if podaci is None:
            messagebox.showinfo("Detalji", "%s %s: %s" % (z["ko"], z["broj"], razlog))
            return
        self._prozor_detalja("%s, KO %s, parcela %s" % (podaci.get("opstina") or z["opstina"], z["ko"], z["broj"]),
                             napravi_snimak(podaci), [], mesto=(z.get("ko_id"), z["ko"], z["broj"]))

    def izvezi(self):
        if not self.rezultati:
            messagebox.showinfo("Izvoz", "Nema rezultata za izvoz.")
            return
        put = filedialog.asksaveasfilename(
            parent=self.root, title="Sačuvaj rezultate", defaultextension=".csv",
            initialdir=DIR, initialfile="parcele_%s.csv" % dt.datetime.now().strftime("%Y%m%d_%H%M"),
            filetypes=[("CSV (Excel)", "*.csv")])
        if not put:
            return
        try:
            n = izvezi_csv(put, list(self.rezultati.values()))
        except OSError as e:
            messagebox.showerror("Izvoz", "Fajl nije sačuvan: %s\n(ako je otvoren u Excelu, zatvori ga)" % e)
            return
        self.log("Izvezeno %d redova u %s" % (n, put), "uspeh")
        if messagebox.askyesno("Izvoz", "Sačuvano (%d redova). Otvoriti fajl?" % n):
            self._otvori(put)

    def dodaj_iz_pretrage(self):
        rez = [r for r in self._izabrani_rezultati() if r[1] is not None]
        if not rez:
            messagebox.showinfo("Praćenje", "Izaberi pronađene parcele u rezultatima.")
            return
        podaci = self._dijalog_podataka("Dodaj u praćenje (%d parcel%s)" % (len(rez), "a" if len(rez) == 1 else "e"))
        if podaci is None:
            return
        klijent, grupa, napomena = podaci
        novih = 0
        for z, p, _ in rez:
            if self.baza.dodaj(z["opstina_id"], p.get("opstina") or z["opstina"], z["ko_id"], p.get("ko") or z["ko"],
                               z["broj"], klijent, grupa, napomena, snimak=napravi_snimak(p)):
                novih += 1
        self.log("Dodato u praćenje: %d (već praćeno: %d)." % (novih, len(rez) - novih), "info")
        if not self._grupisi_klijenta(klijent, grupa):      # kao u Asistent PRO: 2+ parcele klijenta -> grupa
            self.osvezi_listu()
        self.nb.select(1)

    # --- kartica: pracenje -------------------------------------------------
    def _napravi_pracenje(self):
        tab = ttk.Frame(self.nb, padding=(0, 10, 0, 0))
        self.nb.add(tab, text="  Praćenje parcela  ")
        t = ttk.Frame(tab)
        t.pack(fill="x")
        self.btn_sve = ttk.Button(t, text="Proveri sve", style="Glavno.TButton", command=lambda: self.proveri(False))
        self.btn_izabrane = ttk.Button(t, text="Proveri izabrane", command=lambda: self.proveri(True))
        self.btn_prekini2 = ttk.Button(t, text="Prekini", style="Prekid.TButton", command=self._prekini,
                                       state="disabled")
        # v30 (Dejan: "ne vidim opciju sacuvaj sve kao PDF"): vidljivo i u listi praćenja (izabrane parcele ili grupa)
        self.btn_pdf_pracenja = ttk.Button(t, text="Sačuvaj kao PDF", command=lambda: self.pdf_pracenja())
        for w in (self.btn_sve, self.btn_izabrane, self.btn_pdf_pracenja, self.btn_prekini2):
            w.pack(side="left", padx=(0, 6))
        ttk.Separator(t, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        ttk.Button(t, text="+ Dodaj parcele", command=self.dodaj_dijalog).pack(side="left")
        ttk.Label(t, text="Prikaz", style="Sivo.TLabel").pack(side="left", padx=(18, 6))
        cb = ttk.Combobox(t, textvariable=self.prikaz_var, values=PRIKAZI, state="readonly", width=30)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.osvezi_listu())
        ttk.Button(t, text="X", width=3, style="Mali.TButton", command=lambda: self.upit_var.set("")).pack(
            side="right", padx=(4, 0))
        e = ttk.Entry(t, width=32, textvariable=self.upit_var)
        e.pack(side="right", ipady=1)
        self.e_upit = e
        ttk.Label(t, text="Pretraga (broj, KO, klijent, vlasnik, tekst)", style="Sivo.TLabel").pack(side="right",
                                                                                                 padx=(0, 6))
        self.upit_var.trace_add("write", lambda *a: self.osvezi_listu())
        self.root.bind("<Control-f>", lambda ev: self._fokus_pretrage())
        self._napravi_kartice(tab)

        lista = kartica(tab)
        lista.pack(fill="both", expand=True, pady=(10, 0))
        leg = ttk.Frame(lista, style="Kartica.TFrame", padding=(12, 8, 12, 6))
        leg.pack(fill="x")
        self.lbl_broj = ttk.Label(leg, text="", style="Naslov.TLabel")
        self.lbl_broj.pack(side="left")
        # legenda boja u redovima (kao Asistent PRO), sleva nadesno: zuto, podebljano, zeleno, crveno, sivo
        for txt, kw in reversed(((" promena u ovoj sesiji ", dict(bg=BG_PROMENA, font=("Segoe UI", 9, "bold"))),
                                 (" nepregledana promena od ranije ", dict(bg=T_POVRSINA, font=("Segoe UI", 9, "bold"))),
                                 (" provereno, bez promene ", dict(bg=BG_ZELENO, fg=BOJA_OK, font=("Segoe UI", 9))),
                                 (" provera nije uspela ", dict(bg=T_POVRSINA, fg=BOJA_NEUSPEH,
                                                                font=("Segoe UI", 9))),
                                 (" odloženo / u arhivi ", dict(bg=T_POVRSINA, fg=T_SIVO, font=("Segoe UI", 9))))):
            tk.Label(leg, text=txt, padx=4, pady=1, **kw).pack(side="right", padx=(6, 0))
        ttk.Label(leg, text="Boje redova:", style="KarticaSivo.TLabel", font=("Segoe UI", 9)).pack(side="right")
        tk.Frame(lista, bg=T_IVICA, height=1).pack(fill="x")
        fr = ttk.Frame(lista, style="Kartica.TFrame")
        fr.pack(fill="both", expand=True)
        kol = ("parcela", "opstina", "povrsina", "nacin", "objekti", "promena", "provereno")
        self.tree = ttk.Treeview(fr, columns=kol, show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Klijent / grupa", anchor="w")
        self.tree.column("#0", width=px(250), minwidth=px(120), stretch=False)
        for k, naslov, w, an in (("parcela", "KO / parcela", 190, "w"), ("opstina", "Opština", 120, "w"),
                                 ("povrsina", "Površina m²", 95, "e"), ("nacin", "Način korišćenja", 220, "w"),
                                 ("objekti", "Objekti", 170, "w"), ("promena", "Promena", 280, "w"),
                                 ("provereno", "Provera", 280, "w")):
            self.tree.heading(k, text=naslov, anchor=an)
            self.tree.column(k, width=px(w), minwidth=px(40), anchor=an, stretch=False)
        # Provera i Promena odmah posle parcele, da se vide bez pomeranja udesno; dugi opisi idu na kraj
        self.tree.configure(displaycolumns=("parcela", "opstina", "povrsina", "provereno", "promena", "nacin", "objekti"))
        self.tree.tag_configure("grupa", font=FONT_B, background=T_GRUPA, foreground=T_ZAGLAVLJE)
        self.tree.tag_configure("grupa_novo", font=FONT_B, background=BG_PROMENA, foreground=T_TEKST)
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(fr, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=lambda a, b: (sb.set(a, b), self.root.after_idle(self._pozicioniraj_zelene)),
                            xscrollcommand=lambda a, b: (xsb.set(a, b), self.root.after_idle(self._pozicioniraj_zelene)))
        xsb.pack(side="bottom", fill="x")
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self._kop_pracenja = KopiranjeCelija(self, self.tree, otvori=self.detalji,
                                             preskoci=lambda iid: iid.startswith("g:"),
                                             kolona_broja=("parcela", "Kopiran broj parcele"))
        self.tree.bind("<Double-1>", self._dvoklik)
        self.tree.bind("<Return>", lambda e: self.detalji())
        self.tree.bind("<Button-3>", self._meni_desni)
        self.tree.bind("<<TreeviewOpen>>", lambda e: self._otvorene.add(self.tree.focus()))
        self.tree.bind("<<TreeviewClose>>", lambda e: self._otvorene.discard(self.tree.focus()))

    def _fokus_pretrage(self):
        self.nb.select(1)
        self.e_upit.focus_set()
        self.e_upit.select_range(0, "end")

    def _dvoklik(self, e):
        iid = self.tree.identify_row(e.y)
        if iid and not iid.startswith("g:"):
            self.detalji()

    def _grupe_otvori(self, otvori):
        for iid in self.tree.get_children(""):
            if iid.startswith("g:"):
                self.tree.item(iid, open=otvori)
                (self._otvorene.add if otvori else self._otvorene.discard)(iid)
        self._prilagodi_kolone(self.tree)

    def _napravi_kartice(self, roditelj):
        """Red kartica sa brojevima (kao u Asistent PRO); klik na karticu prikazuje te parcele, drugi klik sve.
        Boja trake na kartici = boja u listi."""
        f = ttk.Frame(roditelj)
        f.pack(fill="x", pady=(10, 0))
        self.kartice = {}
        for kljuc, naslov, traka, prikaz in (
                ("svi", "Praćene parcele", T_AKCENT, PRIKAZI[0]),
                ("sesija", "Promena u ovoj sesiji", "#e0a800", PRIKAZI[1]),
                ("nepregledano", "Nepregledana promena", "#4b5563", PRIKAZI[2]),
                ("provereno", "Provereno u ovoj sesiji", BOJA_OK, PRIKAZI[4]),
                ("neuspelo", "Nije provereno / nije uspelo", BOJA_NEUSPEH, PRIKAZI[3])):
            k = tk.Frame(f, bg=T_POVRSINA, highlightthickness=1, highlightbackground=T_IVICA,
                         highlightcolor=T_IVICA, cursor="hand2")
            k.pack(side="left", fill="x", expand=True, padx=(0, 10 if kljuc != "neuspelo" else 0))
            tr = tk.Frame(k, bg=traka, width=5)
            tr.pack(side="left", fill="y")
            unutra = tk.Frame(k, bg=T_POVRSINA)
            unutra.pack(side="left", fill="both", expand=True, padx=(12, 8), pady=(5, 6))
            broj = tk.Label(unutra, text="0", bg=T_POVRSINA, fg=T_TEKST, font=("Segoe UI", 16, "bold"), anchor="w")
            broj.pack(fill="x")
            opis = tk.Label(unutra, text=naslov, bg=T_POVRSINA, fg=T_SIVO, font=("Segoe UI", 9), anchor="w")
            opis.pack(fill="x")
            dod = tk.Label(unutra, text="", bg=T_POVRSINA, fg=T_SIVO, font=("Segoe UI", 8), anchor="w")
            dod.pack(fill="x")
            self.kartice[kljuc] = {"okvir": k, "delovi": (k, unutra, broj, opis, dod), "broj": broj, "dod": dod,
                                   "prikaz": prikaz}
            for w in (k, tr, unutra, broj, opis, dod):
                w.bind("<Button-1>", lambda e, p=prikaz: self._kartica_klik(p))

    def _kartica_klik(self, prikaz):
        self.prikaz_var.set(PRIKAZI[0] if self.prikaz_var.get() == prikaz else prikaz)
        self.osvezi_listu()

    def _osvezi_kartice(self, vrednosti):
        """vrednosti: kljuc -> (broj, dodatni tekst, istaknuto)"""
        prikaz = self.prikaz_var.get()
        for kljuc, (broj, dod, istaknuto) in vrednosti.items():
            k = self.kartice[kljuc]
            pozadina = BG_PROMENA if istaknuto else T_POVRSINA
            for w in k["delovi"]:
                w.configure(bg=pozadina)
            k["broj"].configure(text=str(broj), fg=BOJA_NEUSPEH if kljuc == "neuspelo" and broj else T_TEKST)
            k["dod"].configure(text=dod)
            aktivna = k["prikaz"] == prikaz and prikaz != PRIKAZI[0]
            k["okvir"].configure(highlightthickness=2 if aktivna else 1,
                                 highlightbackground=T_AKCENT if aktivna else T_IVICA)

    def _tag(self, bg, fg, bold):
        ime = "t_%s_%s_%d" % ((bg or "-").strip("#"), (fg or "-").strip("#"), bold)
        if ime not in self._tagovi:
            self.tree.tag_configure(ime, background=bg or T_POVRSINA, foreground=fg or T_TEKST,
                                    font=FONT_B if bold else FONT)
            self._tagovi.add(ime)
        return ime

    def osvezi_listu(self):
        izabrano = set(self.tree.selection())
        oznaka = self._kop_pracenja.stanje()        # otvoreno polje za kopiranje se vraca posle osvezavanja
        self._kop_pracenja.zatvori()
        gore = self.tree.yview()[0]                 # polozaj klizaca se cita PRE brisanja (inace lista skace na vrh)
        self.tree.delete(*self.tree.get_children(""))
        sve = self.baza.parcele()
        upit = self.upit_var.get().strip()
        pogoci = self.baza.pretrazi(upit, sve) if upit else None
        prikaz = self.prikaz_var.get()
        if prikaz not in PRIKAZI:
            prikaz = PRIKAZI[0]
        filtrirano = pogoci is not None or prikaz != PRIKAZI[0]
        zelene = {}

        def ok_sesija(p):
            return p["id"] in self.sesija_ok and not p["greska"]

        def prolazi(p):
            if pogoci is not None and p["id"] not in pogoci:
                return False
            if prikaz == PRIKAZI[6]:
                return arhiviran(p)
            if prikaz == PRIKAZI[5]:
                return odlozen(p)
            if prikaz == PRIKAZI[1]:
                return p["id"] in self.sesija_novo
            if prikaz == PRIKAZI[2]:             # i iz arhive: promena ne sme da promakne
                return bool(p["promene"])
            if arhiviran(p) and pogoci is None:  # arhiva se vidi u Prikaz -> Arhiva i u pretrazi
                return False
            if prikaz == PRIKAZI[3]:
                return aktivan(p) and (not p["provereno"] or bool(p["greska"]))
            if prikaz == PRIKAZI[4]:
                return ok_sesija(p)
            return True

        po_grupi = {}
        if not filtrirano:
            for g in self.baza.grupe():
                po_grupi[g] = []
        prikazano = 0
        for p in sve:
            if prolazi(p):
                po_grupi.setdefault(p["grupa"] or BEZ_GRUPE, []).append(p)
                prikazano += 1
        if not filtrirano:               # grupa ciji su sve parcele u arhivi se ne prikazuje (prazna grupa da)
            imaju = {p["grupa"] for p in sve if p["grupa"]}
            for g in [g for g, lst in po_grupi.items() if not lst and g in imaju]:
                del po_grupi[g]

        def tekst_provere(p):
            if p["greska"]:
                t = "NIJE USPELO (%s): %s" % ((p["pokusaj"] or "")[:16], p["greska"])
                return t + ("  |  poslednja uspešna: %s" % p["provereno"] if p["provereno"] else "")
            return p["provereno"] or "nije provereno"

        def red_parcele(roditelj, p):
            sn = None
            try:
                sn = json.loads(p["snimak"]) if p["snimak"] else None
            except ValueError:
                pass
            prate = pracene_stavke(p)
            pov, nacin, obj = kratak_opis_stavki(sn, prate)
            prom = jasne_promene((p["promene"] or "").split("\n")) or [""]
            prom_txt = ("%s: %s%s" % (p["promena_vreme"] or "", prom[0], (" (+%d)" % (len(prom) - 1)) if len(prom) > 1 else "")
                        if p["promene"] else "")
            novo_sesija = p["id"] in self.sesija_novo
            fg = T_SIVO if not aktivan(p) and not novo_sesija else BOJA_NEUSPEH if p["greska"] else None
            provera = tekst_provere(p)
            if arhiviran(p):
                provera = "U ARHIVI od %s  |  %s" % (srp_datum(p["arhivirano"]), provera)
            elif odlozen(p):
                provera = "ODLOŽENO do %s  |  %s" % (srp_datum(p["odlozeno_do"]), provera)
            if novo_sesija:              # ceo red zut (i celija Provera), bez zelene oznake
                n = len(jasne_promene(self.sesija_novo[p["id"]]))
                provera = "PROMENA u ovoj sesiji%s  |  %s" % ((" (%d)" % n) if n > 1 else "", provera)
            elif ok_sesija(p):
                zelene[str(p["id"])] = "✓ " + provera
            ime = (p["klijent"] or "") + (("  - " + p["napomena"]) if p["napomena"] else "")
            if prate:
                ime += ("  " if ime else "") + "[prati se samo: %s]" % ", ".join(opis_stavke(k) for k in prate)
            self.tree.insert(roditelj, "end", iid=str(p["id"]), text=ime,
                             values=("%s  %s" % (p["ko"], p["broj"]), p["opstina"] or "", pov, nacin, obj,
                                     prom_txt, provera),
                             tags=(self._tag(BG_PROMENA if novo_sesija else None, fg,
                                             novo_sesija or bool(p["promene"])),))

        for g in sorted((x for x in po_grupi if x != BEZ_GRUPE), key=srpski_kljuc):
            lst = po_grupi[g]
            giid = "g:" + g
            aktivni = [p for p in lst if aktivan(p)]
            danas_ok = sum(ok_sesija(p) for p in aktivni)
            u_sesiji = sum(p["id"] in self.sesija_novo for p in lst)
            nepregl = sum(bool(p["promene"]) for p in lst)
            n_odl, n_arh = sum(odlozen(p) for p in lst), sum(arhiviran(p) for p in lst)
            opis = "  ·  ".join(
                (["provereno u ovoj sesiji: %d/%d" % (danas_ok, len(aktivni))] if aktivni or not lst else []) +
                (["odloženo: %d" % n_odl] if n_odl else []) + (["u arhivi: %d" % n_arh] if n_arh else []))
            promena = ("PROMENA: %s" % br_parcela(u_sesiji)) if u_sesiji else \
                ("nepregledano: %s" % br_parcela(nepregl)) if nepregl else ""
            self.tree.insert("", "end", iid=giid, text="%s  (%d)" % (g, len(lst)),
                             open=(giid in self._otvorene) or pogoci is not None or prikaz != PRIKAZI[0],
                             values=("", "", "", "", "", promena, opis),
                             tags=("grupa_novo",) if u_sesiji else ("grupa",))
            if aktivni and danas_ok == len(aktivni) and not u_sesiji:
                zelene[giid] = opis
            for p in lst:
                red_parcele(giid, p)
        for p in po_grupi.get(BEZ_GRUPE, []):
            red_parcele("", p)
        ostalo = [i for i in izabrano if self.tree.exists(i)]
        if ostalo:
            self.tree.selection_set(ostalo)
        self._prilagodi_kolone(self.tree)
        self._postavi_zelene(zelene)
        self.tree.yview_moveto(gore)
        self._kop_pracenja.vrati(oznaka)
        self.lbl_broj.configure(text=("%s  ·  %d od %d" % ("Pretraga" if pogoci is not None else prikaz, prikazano,
                                                             len(sve))) if filtrirano else "Praćene parcele")
        postoje = {p["id"] for p in sve}
        u_sesiji = [pid for pid in self.sesija_novo if pid in postoje]
        n_prom = sum(len(jasne_promene(self.sesija_novo[pid])) for pid in u_sesiji)
        nepregl = [p for p in sve if p["promene"]]
        van_arhive = [p for p in sve if not arhiviran(p)]
        aktivni = [p for p in sve if aktivan(p)]
        n_odl = sum(odlozen(p) for p in sve)
        n_arh = len(sve) - len(van_arhive)
        neuspelo = [p for p in aktivni if not p["provereno"] or p["greska"]]
        provereno = sum(ok_sesija(p) for p in aktivni)
        n_grupa = len(self.baza.grupe())
        self._osvezi_kartice({
            "svi": (len(van_arhive), ("%d grup%s" % (n_grupa, "a" if n_grupa % 10 == 1 and n_grupa % 100 != 11 else
                                                     "e" if 2 <= n_grupa % 10 <= 4 and not 12 <= n_grupa % 100 <= 14
                                                     else "a")) +
                    ("  ·  %d odloženo" % n_odl if n_odl else "") + ("  ·  %d u arhivi" % n_arh if n_arh else ""),
                    False),
            "sesija": (len(u_sesiji), ("%d promen%s  ·  klik za prikaz" % (n_prom, "a" if n_prom % 10 == 1 and
                                                                           n_prom % 100 != 11 else "e" if
                                                                           2 <= n_prom % 10 <= 4 and
                                                                           not 12 <= n_prom % 100 <= 14 else "a"))
                       if u_sesiji else "ništa novo do sada", bool(u_sesiji)),
            "nepregledano": (len(nepregl), "" if nepregl else "sve pregledano", False),
            "provereno": ("%d / %d" % (provereno, len(aktivni)), "", False),
            "neuspelo": (len(neuspelo), "", False)})

    # --- zelena celija "Provera" (kao Asistent PRO) ---
    def _postavi_zelene(self, zelene):
        """Treeview ne moze da oboji jednu celiju, pa se preko celije 'Provera' stavlja zelena oznaka."""
        for iid in list(self._zelene):
            if iid not in zelene or not self.tree.exists(iid):
                self._zelene.pop(iid).destroy()
        for iid, tekst in zelene.items():
            lbl = self._zelene.get(iid)
            if lbl is None:
                lbl = tk.Label(self.tree, anchor="w", bg=BG_ZELENO, fg=BOJA_OK, padx=8, font=FONT)
                lbl.bind("<Button-1>", lambda e, i=iid: self.tree.selection_set(i) if i.startswith("g:") else
                         self._kop_pracenja.pritisni(i, "provereno", e.x_root))
                lbl.bind("<B1-Motion>", self._kop_pracenja._vuci)
                lbl.bind("<ButtonRelease-1>", self._kop_pracenja._otpustanje)
                lbl.bind("<Double-1>", lambda e, i=iid: (self.tree.selection_set(i),
                                                         None if i.startswith("g:") else self.detalji()))
                lbl.bind("<Button-3>", lambda e, i=iid: self._meni_desni(e, i))
                lbl.bind("<MouseWheel>", lambda e: self.tree.yview_scroll(-1 if e.delta > 0 else 1, "units"))
                self._zelene[iid] = lbl
            lbl.configure(text=tekst)
        self.root.after_idle(self._pozicioniraj_zelene)

    def _pozicioniraj_zelene(self):
        try:
            for iid, lbl in list(self._zelene.items()):
                bb = self.tree.bbox(iid, "provereno") if self.tree.exists(iid) else ""
                if bb:
                    lbl.place(x=bb[0], y=bb[1], width=bb[2], height=bb[3])
                    lbl.lift()
                else:
                    lbl.place_forget()
        except tk.TclError:
            pass

    def _ticker(self):
        """Zelene oznake i polja za kopiranje prate klizace i otvaranje grupa."""
        self._pozicioniraj_zelene()
        for k in list(self._kopiranja):
            try:
                if not k.tree.winfo_exists():
                    self._kopiranja.remove(k)
                    continue
            except tk.TclError:
                self._kopiranja.remove(k)
                continue
            k.pozicioniraj()
        self.root.after(250, self._ticker)

    # --- sirine kolona po sadrzaju (kao Asistent PRO) ---
    def _prilagodi_kolone(self, tree, sve=False):
        """Sirina svake kolone = najduzi tekst u njoj (i u zatvorenim grupama) ili naslov. Kolona koju si sam
        razvukao ili suzio ostaje takva do zatvaranja programa (ili Prikaz -> Sirine kolona po sadrzaju)."""
        st = self._sirine.setdefault(str(tree), {"auto": {}, "rucne": set()})
        sa_stablom = "tree" in str(tree.cget("show"))
        kolone = (("#0",) if sa_stablom else ()) + tuple(tree["columns"])
        if sve:
            st["rucne"].clear()
        for k in kolone:
            if not sve and k in st["auto"] and int(tree.column(k, "width")) != st["auto"][k]:
                st["rucne"].add(k)
        meri, naslov = self._font_mera.measure, self._font_naslov.measure
        naj = {k: naslov(tree.heading(k, "text")) + 28 for k in kolone}
        kol = tree["columns"]

        def obidji(roditelj, nivo):
            for iid in tree.get_children(roditelj):
                t = tree.item(iid, "text")
                if t and sa_stablom:
                    naj["#0"] = max(naj["#0"], meri(t) + 22 * (nivo + 1) + 16)
                for k, v in zip(kol, tree.item(iid, "values")):
                    if v != "":
                        naj[k] = max(naj[k], meri(str(v)) + 24)
                obidji(iid, nivo + 1)
        obidji("", 0)
        for k in kolone:
            if k in st["rucne"]:
                continue
            w = min(naj[k], px(MAX_KOLONE.get(k, MAX_SIRINA_KOLONE)))
            tree.column(k, width=w)
            st["auto"][k] = w
        self.root.after_idle(self._pozicioniraj_zelene)

    def izabrani_ids(self):
        ids = []
        for iid in self.tree.selection():
            if iid.startswith("g:"):
                ids.extend(int(c) for c in self.tree.get_children(iid))
            else:
                ids.append(int(iid))
        return list(dict.fromkeys(ids))

    def _meni_desni(self, e, iid=None):
        iid = iid or self.tree.identify_row(e.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
        kop = self._kop_pracenja
        kop.kolona_na_misu = kop.kolona_na(e.x, iid) if e.widget is self.tree else "provereno"
        m = tk.Menu(self.root, tearoff=0)
        if not iid:
            m.add_command(label="Dodaj parcele u praćenje...", command=self.dodaj_dijalog)
            m.add_command(label="Nova grupa...", command=self.nova_grupa)
        elif iid.startswith("g:"):
            # v25 (Dejan: "previse ima stvari"): kopiranje i "Nova grupa" su u meniju Grupa
            g = iid[2:]
            ids_g = [int(c) for c in self.tree.get_children(iid)]
            sel = self.baza.parcele(ids_g) if ids_g else []
            m.add_command(label="Proveri ovu grupu", command=lambda: self.proveri(True))
            if ids_g:            # v30 (Dejan): cela grupa (klijent) kao PDF, jednim klikom
                m.add_command(label="Sačuvaj sve kao PDF (%s)" % br_parcela(len(ids_g)),
                              command=lambda: self.pdf_pracenja(ids_g, None if g == BEZ_GRUPE else g))
            if any(p.get("promene") for p in sel):
                m.add_command(label="Označi grupu kao pregledanu", command=self.oznaci_pregledano)
            if ids_g:
                m.add_separator()
                m.add_cascade(label="Odloži proveru grupe", menu=self._meni_odlaganja(m, ids_g))
                if any(not arhiviran(p) for p in sel):
                    m.add_command(label="Arhiviraj grupu (%s)" % br_parcela(len(ids_g)),
                                  command=lambda: self.arhiviraj(ids_g))
                if any(not aktivan(p) for p in sel):
                    m.add_command(label="Vrati grupu u redovnu proveru", command=lambda: self.vrati_u_proveru(ids_g))
            if g != BEZ_GRUPE:
                m.add_separator()
                m.add_command(label="Preimenuj grupu...", command=self.preimenuj_grupu)
                m.add_command(label="Obriši grupu (parcele ostaju)", command=self.obrisi_grupu)
        else:
            # v25: Detalji = dupli klik / Enter, ceo red = Ctrl+C, celija = klik na nju; sve je i u meniju Parcela
            ids = self.izabrani_ids()
            sel = self.baza.parcele(ids)
            vise = (" (%d)" % len(ids)) if len(ids) > 1 else ""
            m.add_command(label="Proveri ovu parcelu" if len(ids) == 1 else "Proveri izabrane" + vise,
                          command=lambda: self.proveri(True))
            m.add_command(label="Sačuvaj kao PDF" + vise, command=lambda: self.pdf_pracenja(ids))
            n = len(kop.redovi_za_kopiranje())
            if kop.kolona_broja and n:
                m.add_command(label="Kopiraj broj parcele" if n == 1 else "Kopiraj brojeve parcela (%d)" % n,
                              command=kop.kopiraj_brojeve)
            if len(ids) == 1:
                m.add_command(label="Izmeni (klijent, grupa, napomena)...", command=self.izmeni)
            else:
                m.add_command(label="Premesti u grupu" + vise + "...", command=self.promeni_grupu)
            if any(p.get("promene") for p in sel):
                m.add_command(label="Označi kao pregledano" + vise, command=self.oznaci_pregledano)
            if len(sel) == 1 and pracene_stavke(sel[0]):
                m.add_command(label="Prati celu parcelu (sada samo: %s)" % ", ".join(
                    opis_stavke(k) for k in pracene_stavke(sel[0])), command=lambda: self._prati_celu(pid=sel[0]["id"]))
            m.add_separator()
            m.add_cascade(label="Odloži proveru" + vise, menu=self._meni_odlaganja(m, ids))
            if any(not arhiviran(p) for p in sel):
                m.add_command(label="Arhiviraj" + vise, command=lambda: self.arhiviraj(ids))
            if any(not aktivan(p) for p in sel):
                m.add_command(label="Vrati u redovnu proveru" + vise, command=lambda: self.vrati_u_proveru(ids))
            m.add_separator()
            m.add_command(label=("Obriši trajno" if all(arhiviran(p) for p in sel) else "Ukloni iz praćenja") + vise,
                          command=self.ukloni)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # --- odlaganje provere i arhiva (kao Asistent PRO) ---
    def _meni_odlaganja(self, roditelj, ids, sa_datumom=True):
        """Podmeni "Odlozi proveru": 1, 3, 6 meseci, godinu dana ili do datuma koji upises."""
        pod = tk.Menu(roditelj, tearoff=0)
        danas = dt.date.today()
        for n, txt in ((1, "1 mesec"), (3, "3 meseca"), (6, "6 meseci"), (12, "1 godinu")):
            oznaka = ("%s  (do %s)" % (txt, dodaj_mesece(danas, n).strftime("%d.%m.%Y"))) if sa_datumom else txt
            pod.add_command(label=oznaka, command=lambda n=n: self.odlozi(ids, meseci=n))
        pod.add_separator()
        pod.add_command(label="Do datuma...", command=lambda: self.odlozi(ids))
        return pod

    def _javi(self, tekst):
        """Poruka o radnji: u statusnu traku (ako provera ne radi) i u rezultate."""
        if self.posao is None:
            self.lbl_opis.configure(text=tekst)
        self.log(tekst, "tiho")

    def _pitaj_datum(self, broj):
        predlog = dodaj_mesece(dt.date.today(), 3).strftime("%d.%m.%Y")
        while True:
            t = simpledialog.askstring(
                "Odloži proveru", "Do kog datuma se %s ne proverava%s u \"Proveri sve\"?\n"
                "Od tog dana ponovo ide u proveru. (npr. %s)" % (br_parcela(broj), "ju" if broj > 1 else "", predlog),
                parent=self.root, initialvalue=predlog)
            if t is None:
                return None
            d = citaj_datum(t)
            if d is None:
                messagebox.showwarning("Odloži proveru", "Datum nije prepoznat. Upiši ga kao %s." % predlog,
                                       parent=self.root)
            elif d <= dt.date.today():
                messagebox.showwarning("Odloži proveru", "Datum mora biti posle današnjeg.", parent=self.root)
            else:
                return d

    def odlozi(self, ids=None, meseci=None):
        ids = ids or self.izabrani_ids()
        if not ids:
            messagebox.showinfo("Odloži proveru", "Izaberi parcelu ili grupu u listi praćenja.")
            return
        do = dodaj_mesece(dt.date.today(), meseci) if meseci else self._pitaj_datum(len(ids))
        if not do:
            return
        self.baza.odlozi(ids, do)
        self.osvezi_listu()
        vise = len(ids) > 1
        self._javi("Provera odložena do %s: %s. Do tada ne ide%s u \"Proveri sve\" (u listi %s siv%s)." % (
            do.strftime("%d.%m.%Y"), br_parcela(len(ids)), "u" if vise else "", "su" if vise else "je",
            "e" if vise else "a"))

    def arhiviraj(self, ids=None):
        ids = ids or self.izabrani_ids()
        if not ids:
            messagebox.showinfo("Arhiviraj", "Izaberi parcelu ili grupu u listi praćenja.")
            return
        self.baza.arhiviraj(ids)
        self.osvezi_listu()
        vise = len(ids) > 1
        self._javi("U arhivu: %s. Ne ide%s u \"Proveri sve\"; vid%s se u Prikaz -> Arhiva i u pretrazi." % (
            br_parcela(len(ids)), "u" if vise else "", "e" if vise else "i"))

    def vrati_u_proveru(self, ids=None):
        ids = ids or self.izabrani_ids()
        if not ids:
            messagebox.showinfo("Vrati u redovnu proveru", "Izaberi parcelu ili grupu u listi praćenja.")
            return
        self.baza.vrati_u_proveru(ids)
        self.osvezi_listu()
        self._javi("Vraćeno u redovnu proveru: %s." % br_parcela(len(ids)))

    # --- grupe po klijentu (kao Asistent PRO v18) ---
    def _posle_grupisanja(self, rez, pid=None):
        """Osvezi listu; grupa u koju je parcela upravo usla se otvori, a parcela izabere."""
        for g, _, _ in rez:
            self._otvorene.add("g:" + g)
        self.osvezi_listu()
        if rez and pid is not None and self.tree.exists(str(pid)):
            self.tree.selection_set(str(pid))
            self.tree.see(str(pid))
        self._javi_grupisanje(rez)

    def _javi_grupisanje(self, rez):
        if not rez:
            return
        delovi = [("nova grupa %s (%s)" if nova else "u grupu %s: %s") % (g, br_parcela(n)) for g, n, nova in rez]
        self._javi("Parcele istog klijenta grupisane: " + ", ".join(delovi) + ".")

    def _grupisi_pri_pokretanju(self):
        """Jednom (prvo pokretanje v8, pa opet v15, jer do v15 parcele dodate iz Pretrage nisu isle u grupu):
        postojece parcele bez grupe istog klijenta idu u grupu."""
        if self.baza.podesavanje("auto_grupe_sredjeno") == "v15":
            return []
        self.baza.postavi_podesavanje("auto_grupe_sredjeno", "v15")
        rez = self.baza.grupisi_po_klijentu() if self.auto_grupe_var.get() else []
        for g, _, _ in rez:
            self._otvorene.add("g:" + g)
        return rez

    def grupisi_sada(self):
        rez = self.baza.grupisi_po_klijentu()
        if not rez:
            messagebox.showinfo("Grupiši po klijentu", "Nema parcela bez grupe koje treba grupisati.\n"
                                "(Grupa se pravi kad klijent ima bar dve parcele bez grupe.)")
            return
        self._posle_grupisanja(rez)

    def _grupisi_klijenta(self, klijent, grupa, pid=None):
        """Posle dodavanja ili izmene: parcela bez grupe ide u grupu svog klijenta (ako je ukljuceno)."""
        if grupa or not klijent or not self.auto_grupe_var.get():
            return False
        rez = self.baza.grupisi_po_klijentu(klijent)
        if rez:
            self._posle_grupisanja(rez, pid)
        return bool(rez)

    # --- kopiranje ---
    def _kopiraj(self, tekst, opis="Kopirano"):
        tekst = tekst if isinstance(tekst, str) else ""
        self.root.clipboard_clear()
        self.root.clipboard_append(tekst)
        if self.posao is None:
            kratko = " | ".join(" ".join(red.split()) for red in tekst.splitlines() if red.strip())
            if len(kratko) > 90:
                kratko = kratko[:87] + "..."
            self.lbl_opis.configure(text=("%s: %s" % (opis, kratko)) if kratko else "%s (prazno)" % opis)

    # --- precica i taskbar (kao Asistent PRO) ---
    def _proveri_precicu(self):
        """Kad precice nema (ili je sa starom ikonicom): napravi je na radnoj povrsini i u Start meniju, da program
        moze da se zakaci na taskbar kao Asistent PRO."""
        if os.name != "nt" or TEST_REZIM:
            return
        ikona = os.path.basename(putanja_ikone() or "")
        lnk = os.path.join(radna_povrsina(), "Asistent KATASTAR.lnk")
        if os.path.exists(lnk) and self.baza.podesavanje("precica_ikona") == ikona:
            return
        self.napravi_precicu_sada(tiho=True)

    def napravi_precicu_sada(self, tiho=False):
        ikona = os.path.basename(putanja_ikone() or "")
        savet = ("Da bi bio u taskbaru: desni klik na prečicu \"Asistent KATASTAR\" na radnoj površini > "
                 "Zakači na traku zadataka (Windows 11: prvo Prikaži više opcija).")

        def gotovo(ok, poruka):
            def u_prozoru():
                if ok:
                    self.baza.postavi_podesavanje("precica_ikona", ikona)
                    self.log("Prečica \"Asistent KATASTAR\" (nova ikonica) je na radnoj površini i u Start meniju. "
                             + savet, "uspeh")
                    if not tiho:
                        messagebox.showinfo("Prečica", "Prečica je napravljena na radnoj površini i u Start meniju.\n\n"
                                            + savet)
                else:
                    self.log("Prečica nije napravljena: %s. Može i ručno: dvoklik na napravi_precicu.bat u folderu "
                             "programa." % poruka, "greska")
                    if not tiho:
                        messagebox.showwarning("Prečica", "Prečica nije napravljena: %s\n\nMože i ručno: dvoklik na "
                                               "napravi_precicu.bat u folderu programa." % poruka)
            self.root.after(0, u_prozoru)
        napravi_precicu(gotovo)

    def _dijalog_podataka(self, naslov, klijent="", grupa="", napomena=""):
        d = tk.Toplevel(self.root)
        d.title(naslov)
        d.transient(self.root)
        d.grab_set()
        f = ttk.Frame(d, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Klijent / naziv").grid(row=0, column=0, sticky="w")
        e_k = ttk.Entry(f, width=36)
        e_k.insert(0, klijent)
        e_k.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 6))
        ttk.Label(f, text="Grupa (izaberi ili upiši novu)").grid(row=2, column=0, sticky="w")
        cb = ttk.Combobox(f, width=34, values=self.baza.grupe())
        cb.set(grupa)
        cb.grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 6))
        ttk.Label(f, text="Napomena").grid(row=4, column=0, sticky="w")
        e_n = ttk.Entry(f, width=36)
        e_n.insert(0, napomena)
        e_n.grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 10))
        rez = {}

        def ok(_=None):
            rez["v"] = (e_k.get().strip(), cb.get().strip(), e_n.get().strip())
            d.destroy()
        ttk.Button(f, text="U redu", command=ok).grid(row=6, column=0, sticky="w")
        ttk.Button(f, text="Odustani", command=d.destroy).grid(row=6, column=1, sticky="e")
        d.bind("<Return>", ok)
        d.bind("<Escape>", lambda e: d.destroy())
        e_k.focus_set()
        self.root.wait_window(d)
        return rez.get("v")

    def dodaj_dijalog(self):
        d = tk.Toplevel(self.root)
        d.title("Dodaj parcele u praćenje")
        d.transient(self.root)
        d.grab_set()
        f = ttk.Frame(d, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Opština").grid(row=0, column=0, sticky="w")
        ttk.Label(f, text="Katastarska opština").grid(row=0, column=1, sticky="w")
        cb_o, cb_k, lbl = self._kombinacije_opstina(f, 1, 0)
        o0 = self._izabrana_opstina(self.cb_opstina)
        if o0:
            cb_o.current(self.sif.opstine.index(o0))
            self._opstina_izabrana(cb_o, cb_k, lbl)
            k0 = self._izabrana_ko(self.cb_opstina, self.cb_ko)
            if k0 and k0 in cb_o._ko:
                cb_k.current(cb_o._ko.index(k0))
        lbl.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="Brojevi parcela (zarez, razmak ili novi red; 10383/1; 100-110)").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        t = tk.Text(f, height=3, width=56, font=("Segoe UI", 10))
        t.grid(row=4, column=0, columnspan=2, sticky="we")
        cb_k._predlozi.dalje = t
        ttk.Label(f, text="Klijent / naziv").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(f, text="Grupa").grid(row=5, column=1, sticky="w", pady=(8, 0))
        e_k = ttk.Entry(f, width=28)
        e_k.grid(row=6, column=0, sticky="we", padx=(0, 8))
        cb_g = ttk.Combobox(f, width=26, values=self.baza.grupe())
        cb_g.grid(row=6, column=1, sticky="we")
        ttk.Label(f, text="Napomena").grid(row=7, column=0, sticky="w", pady=(8, 0))
        e_n = ttk.Entry(f, width=56)
        e_n.grid(row=8, column=0, columnspan=2, sticky="we")
        ttk.Label(f, text="Parcele se dodaju bez provere; klikni \"Proveri izabrane\" da se prvi put učitaju.",
                  foreground="#555").grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def ok():
            self._razresi_unos(cb_o, cb_k)
            o = self._izabrana_opstina(cb_o)
            k = self._izabrana_ko(cb_o, cb_k)
            brojevi, lose = raspakuj_brojeve(t.get("1.0", "end"))
            if not o or not k:
                messagebox.showwarning("Dodaj", "Izaberi opštinu i katastarsku opštinu.", parent=d)
                return
            if lose or not brojevi:
                messagebox.showwarning("Dodaj", "Proveri brojeve parcela%s." % ((": " + ", ".join(lose[:10])) if lose else ""),
                                       parent=d)
                return
            klijent, grupa = e_k.get().strip(), cb_g.get().strip()
            novih = sum(1 for b in brojevi if self.baza.dodaj(o[0], o[1], k[0], k[1], b, klijent,
                                                              grupa, e_n.get().strip()))
            self.log("Dodato u praćenje: %d (već praćeno: %d)." % (novih, len(brojevi) - novih), "info")
            d.destroy()
            if not self._grupisi_klijenta(klijent, grupa):
                self.osvezi_listu()
            self.nb.select(1)
        b = ttk.Frame(f)
        b.grid(row=10, column=0, columnspan=2, sticky="we", pady=(10, 0))
        ttk.Button(b, text="Dodaj", command=ok).pack(side="left")
        ttk.Button(b, text="Odustani", command=d.destroy).pack(side="right")
        d.bind("<Escape>", lambda e: d.destroy())

    def izmeni(self):
        ids = self.izabrani_ids()
        if not ids:
            return
        stare = self.baza.parcele(ids)
        p = stare[0]
        podaci = self._dijalog_podataka("Izmeni %s" % ("parcelu %s %s" % (p["ko"], p["broj"]) if len(ids) == 1
                                                         else "%d parcela" % len(ids)),
                                        p["klijent"], p["grupa"], p["napomena"])
        if podaci is None:
            return
        for pid in ids:
            self.baza.izmeni(pid, *podaci)
        klijent, grupa, _ = podaci
        # grupise se kad je klijent promenjen bar jednoj od izabranih (rucno "bez grupe" za istog klijenta se postuje)
        promenjen = any(lat(norm(klijent)) != lat(norm(x["klijent"])) for x in stare)
        if not promenjen or not self._grupisi_klijenta(klijent, grupa, ids[0]):
            self.osvezi_listu()

    def oznaci_pregledano(self):
        ids = self.izabrani_ids()
        if ids:
            self.baza.oznaci_pregledano(ids)
            self.osvezi_listu()

    def oznaci_sve_pregledano(self):
        ids = [p["id"] for p in self.baza.parcele()]
        if ids and messagebox.askyesno("Pregledano", "Označiti SVE parcele kao pregledane?"):
            self.baza.oznaci_pregledano(ids)
            self.osvezi_listu()

    def ukloni(self):
        """v36: "Ukloni iz praćenja" premešta u Arhivu (ništa se ne gubi); parcele koje su već u Arhivi se odatle
        brišu trajno, zajedno sa istorijom promena (uz potvrdu)."""
        ids = self.izabrani_ids()
        if not ids:
            return
        sel = self.baza.parcele(ids)
        aktivne = [p["id"] for p in sel if not arhiviran(p)]
        if aktivne:
            self.baza.arhiviraj(aktivne)
            self.osvezi_listu()
            self._javi("Uklonjeno iz praćenja: %s - u Arhivi su (Prikaz -> Arhiva); trajno brisanje je odatle." %
                       br_parcela(len(aktivne)))
            return
        if messagebox.askyesno("Obriši trajno", "Trajno obrisati %s iz Arhive, zajedno sa istorijom promena?\n"
                               "Ovo se ne može vratiti." % br_parcela(len(ids))):
            self.baza.ukloni(ids)
            self.osvezi_listu()

    def _izaberi_grupu(self, naslov):
        sel = self.tree.selection()
        if sel and sel[0].startswith("g:") and sel[0][2:] != BEZ_GRUPE:
            return sel[0][2:]
        g = self.baza.grupe()
        if not g:
            messagebox.showinfo(naslov, "Nema grupa.")
            return None
        return simpledialog.askstring(naslov, "Naziv grupe:\n" + ", ".join(g), parent=self.root)

    def nova_grupa(self):
        n = simpledialog.askstring("Nova grupa", "Naziv grupe:", parent=self.root)
        if n and n.strip():
            self.baza.dodaj_grupu(n.strip())
            self.osvezi_listu()

    def promeni_grupu(self):
        ids = self.izabrani_ids()
        if not ids:
            return
        g = simpledialog.askstring("Premesti u grupu", "Grupa (postojeće: %s)\nprazno = bez grupe:"
                                   % ", ".join(self.baza.grupe()), parent=self.root)
        if g is None:
            return
        self.baza.promeni_grupu(ids, g.strip())
        self.osvezi_listu()

    def preimenuj_grupu(self):
        stara = self._izaberi_grupu("Preimenuj grupu")
        if not stara:
            return
        nova = simpledialog.askstring("Preimenuj grupu", "Novi naziv za \"%s\":" % stara, parent=self.root)
        if nova and nova.strip():
            self.baza.preimenuj_grupu(stara, nova.strip())
            self.osvezi_listu()

    def obrisi_grupu(self):
        g = self._izaberi_grupu("Obriši grupu")
        if g and messagebox.askyesno("Obriši grupu", "Obrisati grupu \"%s\"? Parcele ostaju (bez grupe)." % g):
            self.baza.obrisi_grupu(g)
            self.osvezi_listu()

    # --- v28 (Dejan: "kada kliknem dva puta... samo otvori, a neka bude tu dugme osveži, da povuce nove podatke") ---
    def _osvezi_prozor(self, w):
        """Dugme „Osveži sa sajta“ u prozoru parcele: proverava tu parcelu na sajtu (samo praćene stavke, ako se
        prate) i prikazuje trenutno stanje u istom prozoru. Dupli klik u listi samo otvara sačuvano stanje."""
        c = self._otvori_posle
        if c is not None and c["pid"] == w.pid:
            return                                    # već se osvežava
        if self.posao:
            self._poruka_prozora(w, ("nije", "Provera ili pretraga je u toku. Osveži kad se završi."))
            return
        lst = self.baza.parcele([w.pid])
        if not lst:
            self._poruka_prozora(w, ("nije", "Parcela više nije u praćenju."))
            return
        p = lst[0]
        prate = pracene_stavke(p)
        opis = "%s %s%s" % (p["ko"], p["broj"], (" (samo %s)" % ", ".join(opis_stavke(k) for k in prate))
                            if prate else "")
        self._otvori_posle = {"pid": p["id"], "rez": None}
        self.log("--- Osveži sa sajta: %s ---" % opis, "info")
        self._pokreni([{"pid": p["id"], "opstina_id": p["opstina_id"], "opstina": p["opstina"], "ko_id": p["ko_id"],
                        "ko": p["ko"], "broj": p["broj"], "p": p, "stavke": prate}], "provera")
        self.lbl_opis.configure(text="Preuzimam trenutno stanje sa sajta: %s ..." % opis)
        for x in self._prozori_parcele(p["id"]):
            x.btn_osvezi.configure(state="disabled", text="Osvežavam...")
            self._poruka_prozora(x, ("ceka", "Preuzimam trenutno stanje sa sajta: %s ..." % opis))

    def _prozori_parcele(self, pid):
        return [x for x in self.root.winfo_children() if isinstance(x, tk.Toplevel) and getattr(x, "pid", None) == pid
                and x.winfo_exists()]

    @staticmethod
    def _poruka_prozora(w, poruka):
        """Traka ispod naslova: sačuvano / u toku / trenutno stanje / promena / nije preuzeto."""
        bg, fg = {"ok": (BG_ZELENO, BOJA_OK), "promena": (BG_PROMENA, T_TEKST), "nije": ("#fde2e2", BOJA_NEUSPEH)
                  }.get(poruka[0], (T_POVRSINA, T_SIVO))
        w.traka.configure(bg=bg)
        w.okvir_poruke.configure(bg=bg)
        naslov, telo = "", poruka[1]
        if getattr(w, "tabela_promena", None) is not None:
            w.tabela_promena.destroy()
            w.tabela_promena = None
        if poruka[0] == "promena":            # v31: naslov, pa tabela staro stanje / novo stanje
            naslov, promene = poruka[1], poruka[2]
            w.tabela_promena = tabela_promena(w.okvir_poruke, promene[:MAX_PROMENA_TRAKA])
            telo = ("... i još %d (kartica Istorija promena)" % (len(promene) - MAX_PROMENA_TRAKA)
                    if len(promene) > MAX_PROMENA_TRAKA else "")
        w.poruka_naslov.configure(text=naslov, bg=bg, fg=fg)
        w.poruka.configure(text=telo, bg=bg, fg=fg, font=FONT if poruka[0] in ("sacuvano", "ceka", "promena") else FONT_B)
        w.poruka_naslov.pack_forget()
        w.poruka.pack_forget()
        if naslov:
            w.poruka_naslov.pack(fill="x")
        if w.tabela_promena is not None:
            w.tabela_promena.pack(fill="x", padx=12, pady=(2, 2))
        if telo:
            w.poruka.pack(fill="x")

    def _osvezen(self, c, prekinuto):
        """Provera iz „Osveži sa sajta“ je gotova: novi podaci u svim otvorenim prozorima te parcele."""
        rez = c.get("rez")
        if prekinuto:
            poruka = ("nije", "Osvežavanje je prekinuto. Prikazano je poslednje sačuvano stanje.")
        elif rez is None or rez[0] == "nije":
            poruka = ("nije", "Sa sajta nije preuzeto%s. Prikazano je poslednje sačuvano stanje." % (
                (" (%s)" % rez[1]) if rez else ""))
        elif rez[0] == "promena":
            poruka = ("promena", "PROMENA - upravo preuzeto sa sajta", promene_staro_novo(rez[1]))
        else:
            poruka = ("ok", "Trenutno stanje, upravo preuzeto sa sajta%s." % (
                "" if rez[0] == "prva" else " - bez promena od prethodne provere"))
        prozori = self._prozori_parcele(c["pid"])
        lst = self.baza.parcele([c["pid"]])
        for w in prozori:
            w.btn_osvezi.configure(state="normal", text="Osveži sa sajta")
            if lst and not prekinuto and rez and rez[0] != "nije":
                self._popuni_prozor(w, lst[0])
            elif lst:                         # neuspeh se vidi i u naslovu (poslednji pokušaj nije uspeo)
                w.lbl_provera.configure(text=self._tekst_provere_prozora(lst[0]))
            self._poruka_prozora(w, poruka)
        if prozori and lst and lst[0]["promene"] and not prekinuto:     # promena se vidi u prozoru
            self.baza.oznaci_pregledano([c["pid"]])
            self.osvezi_listu()

    def _popuni_prozor(self, w, p):
        """Podaci, natpis poslednje provere i istorija u otvorenom prozoru parcele (posle osvežavanja)."""
        try:
            sn = json.loads(p["snimak"]) if p["snimak"] else None
        except ValueError:
            sn = None
        if sn:
            self._prikazi_u_panelu(w.panel, sn, (p["ko_id"], p["ko"], p["broj"]), p["opstina"] or sn.get("opstina", ""))
        w.lbl_provera.configure(text=self._tekst_provere_prozora(p))
        istorija = self.baza.istorija(p["id"])
        w.nb.tab(w.f2, text="  Istorija promena (%d)  " % len(istorija))
        self._popuni_istoriju(w.istorija, istorija)

    @staticmethod
    def _tekst_provere_prozora(p):
        stanje = ("U ARHIVI od %s   |   " % srp_datum(p.get("arhivirano")) if arhiviran(p) else
                  "Provera odložena do %s   |   " % srp_datum(p.get("odlozeno_do")) if odlozen(p) else "")
        return "%sPoslednja provera: %s%s" % (stanje, p["provereno"] or "-", ("   |   poslednji pokušaj nije uspeo: %s"
                                                                             % p["greska"]) if p["greska"] else "")

    @staticmethod
    def _popuni_istoriju(f, istorija):
        """v31: svaka provera sa promenom - vreme, pa tabela staro stanje / novo stanje."""
        for x in f.winfo_children():
            x.destroy()
        tekst = []
        for h in istorija:
            tk.Label(f, text=h["vreme"], bg=T_POVRSINA, fg=T_ZAGLAVLJE, font=FONT_B, anchor="w").pack(
                fill="x", padx=12, pady=(10, 3))
            tab = tabela_promena(f, promene_staro_novo(h["tekst"].split("\n")))
            tab.pack(fill="x", padx=12)
            tekst += [h["vreme"], tab.tekst]
        if not istorija:
            tk.Label(f, text="Nema zabeleženih promena od dodavanja u praćenje.", bg=T_POVRSINA, fg=T_SIVO, font=FONT,
                     anchor="w").pack(fill="x", padx=12, pady=10)
        f.tekst = "\n".join(tekst)
        try:
            f.platno.yview_moveto(0)
        except (AttributeError, tk.TclError):
            pass

    def detalji(self, pid=None, poruka=None):
        """Prozor parcele iz poslednjeg sačuvanog stanja; poruka = (vrsta, tekst) iznad podataka (v26)."""
        if pid is None:
            ids = self.izabrani_ids()
            if not ids:
                return
            pid = ids[0]
        lst = self.baza.parcele([pid])
        if not lst:
            return
        p = lst[0]
        sn = json.loads(p["snimak"]) if p["snimak"] else None
        if not sn:
            messagebox.showinfo("Detalji", "Parcela još nije proverena." + (("\n\n" + poruka[1]) if poruka else ""))
            return
        self._prozor_detalja("%s, KO %s, parcela %s%s" % (p["opstina"], p["ko"], p["broj"],
                                                          ("  -  " + p["klijent"]) if p["klijent"] else ""),
                             sn, self.baza.istorija(p["id"]), p, mesto=(p["ko_id"], p["ko"], p["broj"]),
                             samo_praceno=bool(pracene_stavke(p)), poruka=poruka)
        if p["promene"]:
            self.baza.oznaci_pregledano([p["id"]])
            self.osvezi_listu()

    def _prozor_detalja(self, naslov, sn, istorija, p=None, mesto=None, samo_praceno=False, poruka=None):
        w = tk.Toplevel(self.root)
        w.title(naslov)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w.geometry("%dx%d" % (min(px(1320), sw - 60), min(px(820), sh - 120)))
        zag = tk.Frame(w, bg=T_ZAGLAVLJE)
        zag.pack(fill="x")
        tk.Label(zag, text=naslov, bg=T_ZAGLAVLJE, fg="#ffffff", font=("Segoe UI", 13, "bold"), padx=16,
                 pady=10).pack(side="left")
        if p:
            w.pid = p["id"]
            w.lbl_provera = tk.Label(zag, text=self._tekst_provere_prozora(p), bg=T_ZAGLAVLJE, fg="#dfe7f6", font=FONT)
            w.lbl_provera.pack(side="right", padx=16)
            # v28: otvara se sačuvano stanje; „Osveži sa sajta“ preuzima trenutno (u istom prozoru)
            w.traka = tk.Frame(w, bg=T_POVRSINA)
            w.traka.pack(fill="x")
            w.btn_osvezi = ttk.Button(w.traka, text="Osveži sa sajta", style="Glavno.TButton",
                                      command=lambda: self._osvezi_prozor(w))
            w.btn_osvezi.pack(side="left", anchor="n", padx=(12, 0), pady=6)
            w.okvir_poruke = tk.Frame(w.traka, bg=T_POVRSINA)
            w.okvir_poruke.pack(side="left", fill="x", expand=True, pady=6)
            w.poruka_naslov = tk.Label(w.okvir_poruke, text="", anchor="w", justify="left", padx=12, font=FONT_B)
            w.poruka = tk.Label(w.okvir_poruke, text="", anchor="w", justify="left", padx=12, wraplength=px(1050))
            w.poruka.pack(fill="x")
            w.tabela_promena = None
            self._poruka_prozora(w, poruka or ("sacuvano", "Sačuvano stanje sa poslednje provere."))
        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=12, pady=(8, 12))
        f1 = ttk.Frame(nb, padding=(0, 8, 0, 0))
        nb.add(f1, text="  Podaci o parceli (kao na eKatastru)  ")
        k = kartica(f1)
        k.pack(fill="both", expand=True)
        panel = self._napravi_panel_parcele(k)
        panel["filter"] = samo_praceno
        w.panel = panel
        self._prikazi_u_panelu(panel, sn, mesto or ("", sn.get("ko", ""), ""), sn.get("opstina", ""))
        if p is not None:
            f2 = ttk.Frame(nb, padding=(0, 8, 0, 0))
            nb.add(f2, text="  Istorija promena (%d)  " % len(istorija))
            k2 = kartica(f2)
            k2.pack(fill="both", expand=True)
            t = skrol_okvir(k2)
            self._popuni_istoriju(t, istorija)
            w.nb, w.f2, w.istorija = nb, f2, t
        w.bind("<Escape>", lambda e: w.destroy())
        return w

    def _napravi_panel_parcele(self, okvir):
        """Parcela prikazana kao rezultat pretrage na eKatastru: zemljiste, objekti i posebni delovi.
        Dvoklik (ili Enter) na red otvara 'Подаци о непокретности' kao kucica na sajtu."""
        p = {"stavke": {}, "mesto": ("", "", "")}
        zag = ttk.Frame(okvir, style="Kartica.TFrame", padding=(12, 8, 12, 2))
        zag.pack(fill="x")
        tk.Label(zag, text="Резултат претраживања парцела", bg=T_POVRSINA, fg=EK_NASLOV,
                 font=("Trebuchet MS", 12, "bold"), anchor="w").pack(side="left")
        p["info"] = tk.Label(zag, text="", bg=T_POVRSINA, fg=T_TEKST, font=FONT, anchor="w")
        p["info"].pack(side="left", padx=(18, 0))
        p["lbl_prati"] = tk.Label(zag, text="", bg=T_POVRSINA, fg=T_AKCENT, font=FONT_B, anchor="e")
        p["lbl_prati"].pack(side="right")
        p["prate"] = set()
        # v26 (Dejan: "ako je stan, samo stan"): prikaz samo praćenih stavki ili cele parcele
        p["filter"], p["filter_prikazan"], p["sekcije"], p["vidljive"] = False, False, [], {}
        p["btn_filter"] = ttk.Button(zag, text="", style="Mali.TButton", command=lambda: self._prebaci_filter(p))
        # v29 (Dejan: "Nepotreban i presiroko uputstvo"): bez uputstva u prozoru
        # Dejan (v21): sa sajta se skida samo ono što označiš (ili sve)
        alat = tk.Frame(okvir, bg=T_POVRSINA)
        alat.pack(fill="x", padx=12, pady=(2, 4))
        for vrsta, opis in (("ne", "nije skinuto"), ("da", "označeno za skidanje"), ("ima", "skinuto sa sajta")):
            tk.Label(alat, image=self._slike_izbora[vrsta], text=" " + opis, compound="left", bg=T_POVRSINA,
                     fg=T_TEKST, font=("Segoe UI", 9)).pack(side="left", padx=(0, 14))
        p["stanje"] = tk.Label(alat, text="", bg=T_POVRSINA, fg=T_AKCENT, font=("Segoe UI", 9, "bold"), anchor="w")
        p["stanje"].pack(side="left", padx=(6, 0))
        p["btn_sve"] = ttk.Button(alat, text="Skini sve", command=lambda: self._skini_iz_panela(p, None))
        p["btn_sve"].pack(side="right")
        p["btn_oznacene"] = ttk.Button(alat, text="Skini označene (0)", style="Glavno.TButton",
                                       command=lambda: self._skini_iz_panela(p, sorted(p["oznaceno"])))
        p["btn_oznacene"].pack(side="right", padx=(0, 6))
        # Dejan (v27): "ili sve, ili samo određeno kad kliknem, ali da ima dugme za sve"
        p["btn_prati_celu"] = ttk.Button(alat, text="Prati celu parcelu", style="Glavno.TButton",
                                         command=lambda: self._prati_celu_iz_panela(p))
        p["oznaceno"], p["ucitano"] = set(), set()
        telo = skrol_okvir(okvir)
        p["telo"] = telo
        p["tabele"] = {}
        for oznaka, natpis, kolone in (
                ("parcela", "Подаци о земљишту (парцела и делови парцела)",
                 (("Број парцеле", 95), ("Број дела", 75), ("Површина (m²)", 100), ("Улица/Потес", 170),
                  ("Начин коришћења земљишта", 270), ("Врста земљишта", 210), ("Имаоци права на парцели (удео)", 380))),
                ("o", "Подаци о зградама и другим грађевинским објектима",
                 (("Део парцеле", 85), ("Улица", 200), ("Кућни број", 85), ("Подброј", 70), ("Површина (m²)", 100),
                  ("Начин коришћења објекта", 230), ("Статус објекта", 250), ("Имаоци права на објекту (удео)", 380))),
                ("p", "Посебни делови изабраног објекта (станови, пословни простори, гараже)",
                 (("Објекат", 190), ("Евид. број", 80), ("Бр. улаза", 80), ("Бр. стана", 80), ("Подбр.", 65),
                  ("Начин коришћења посебног дела", 230), ("Корисна пов. (m²)", 120),
                  ("Имаоци права на посебном делу (удео)", 380)))):
            lbl = tk.Label(telo, text=natpis, bg=EK_SEKCIJA, fg=EK_NASLOV, font=FONT_B, anchor="w", padx=8, pady=5)
            lbl.pack(fill="x", padx=12, pady=(10, 0))
            fr = tk.Frame(telo, bg=T_POVRSINA, highlightthickness=1, highlightbackground=T_IVICA)
            fr.pack(fill="x", padx=12)
            p["sekcije"].append((oznaka, lbl, natpis, fr))
            tr = ttk.Treeview(fr, columns=[str(i) for i in range(len(kolone))], show="tree headings", height=1,
                              selectmode="browse")
            tr.heading("#0", text="", anchor="w")
            tr.column("#0", width=px(34), minwidth=px(34), stretch=False, anchor="w")
            for i, (n, wd) in enumerate(kolone):
                tr.heading(str(i), text=n, anchor="w")
                tr.column(str(i), width=px(wd), minwidth=px(50), anchor="w", stretch=(i == len(kolone) - 1))
            tr.tag_configure("prazno", foreground=T_SIVO)
            tr.tag_configure("par", background="#f7f9fc")
            tr.tag_configure("prati", font=FONT_B)          # stavka koja se prati (v22)
            tr.pack(fill="x")
            tr.bind("<Double-1>", lambda e, o=oznaka: self._otvori_iz_panela(p, o, e))
            tr.bind("<Return>", lambda e, o=oznaka: self._otvori_iz_panela(p, o))
            tr.bind("<Button-1>", lambda e, o=oznaka: self._klik_izbora(p, o, e))      # pre kopiranja ćelija
            tr.bind("<space>", lambda e, o=oznaka: self._oznaci_red(p, o))
            kop = KopiranjeCelija(self, tr, otvori=lambda o=oznaka: self._otvori_iz_panela(p, o),
                                  preskoci=lambda iid: iid == "prazno", bez_stabla=True)
            tr.bind("<Button-3>", lambda e, o=oznaka, k=kop: self._meni_panela(e, p, o, k))
            p["tabele"][oznaka] = tr
        # kao na sajtu: deo parcele -> objekti na tom delu -> posebni delovi izabranog objekta
        p["tabele"]["parcela"].bind("<<TreeviewSelect>>", lambda e: self._panel_deo(p), add="+")
        p["tabele"]["o"].bind("<<TreeviewSelect>>", lambda e: self._panel_objekat(p), add="+")
        p["napomena"] = tk.Label(telo, text="", bg=T_POVRSINA, fg=BOJA_NEUSPEH, font=("Segoe UI", 9), anchor="w",
                                 justify="left", wraplength=px(1100))
        p["napomena"].pack(fill="x", padx=12, pady=(8, 10))
        self._panel = p
        self._paneli = [x for x in self._paneli if self._panel_ziv(x)] + [p]
        self._osvezi_izbor(p)
        return p

    def _prikazi_u_panelu(self, p, sn, mesto=("", "", ""), opstina=""):
        p["mesto"] = mesto
        ko_id, ko, broj = mesto
        if not sn:
            p["stavke"] = {}
            p["sn"] = None
            for tr in p["tabele"].values():
                tr.delete(*tr.get_children(""))
                tr.configure(height=1)
            p["info"].configure(text="izaberi pronađenu parcelu u rezultatima")
            p["napomena"].configure(text="")
            p["oznaceno"], p["ucitano"] = set(), set()
            p["stanje"].configure(text="")
            self._osvezi_pracenje_panela(p)
            return
        p["info"].configure(text="Општина: %s      Катастарска општина: %s      Парцела: %s" % (
            opstina or sn.get("opstina", ""), ko or sn.get("ko", ""), broj))
        stavke = {x[0]: x for x in stablo_nepokretnosti(sn)}
        # stavke skinute posle snimka (izabrane u ovom prozoru, ili iz drugog prozora) - podaci iz izvodi/
        indeks = _indeks_izvoda(dir_izvoda(ko_id, ko, broj)) if ko_id and broj else {}
        for iid, x in list(stavke.items()):
            if not x[3] and x[4] in indeks:
                t = ucitaj_izvod(ko_id, ko, broj, x[4])[0]
                if t:
                    stavke[iid] = x[:3] + (tekst_nepokretnosti(t),) + x[4:]
        p["stavke"] = stavke
        p["ucitano"] = {x[4] for x in stavke.values() if x[3]} | set(indeks)
        p["oznaceno"] = set()
        p["na_sajtu"] = self._na_sajtu(mesto)

        def vl(iid):
            x = stavke.get(iid)
            return iz_nepokretnosti(x[3], "Имаоци права на").replace("; ", ",   ") if x else ""
        p["sn"], p["vl"], p["deo"], p["objekat"] = sn, vl, None, None
        tp = p["tabele"]["parcela"]
        self._popuni_tabelu(tp, [("parcela_%d" % i, (broj, d[0], d[1], d[2], d[3], d[4], vl("parcela")))
                                 for i, d in enumerate(sn.get("delovi", []))], lambda iid: self._slika_reda(p, iid))
        if sn.get("delovi"):
            tp.selection_set("parcela_0")       # kao na sajtu: izabran je prvi deo parcele
            tp.focus("parcela_0")
        self._panel_deo(p)
        nap = sn.get("napomene") or []
        p["napomena"].configure(text=("Napomena: " + "; ".join(nap)) if nap else "")
        p["stanje"].configure(text="")
        self._osvezi_pracenje_panela(p)

    @staticmethod
    def _popuni_tabelu(tr, lista, slika=None):
        tr.delete(*tr.get_children(""))
        for n, (iid, vals) in enumerate(lista):
            tr.insert("", "end", iid=iid, values=vals, tags=("par",) if n % 2 else (),
                      **({"image": slika(iid)} if slika else {}))
        if not lista:
            tr.insert("", "end", iid="prazno", values=("", "— нема —"), tags=("prazno",))
        tr.configure(height=max(1, min(8, len(lista))))

    def _panel_deo(self, p):
        """Izabran deo parcele: samo objekti na tom delu, prvi od njih izabran, pa njegovi posebni delovi."""
        if p.get("filter_prikazan"):          # samo praćene stavke: ne zavisi od izabranog dela
            return
        sn, tp = p.get("sn"), p["tabele"]["parcela"]
        sel = [i for i in tp.selection() if i != "prazno"]
        deo = tp.item(sel[0], "values")[1] if sel else None
        if sn is None or (deo == p.get("deo") and p.get("objekat") is not None):
            return
        p["deo"], p["objekat"] = deo, None
        ids = objekti_dela(sn, deo) if deo is not None else []
        to = p["tabele"]["o"]
        self._popuni_tabelu(to, [("o%d" % i, tuple(sn["objekti"][i]) + (p["vl"]("o%d" % i),)) for i in ids],
                            lambda iid: self._slika_reda(p, iid))
        if ids:
            to.selection_set("o%d" % ids[0])
            to.focus("o%d" % ids[0])
        self._panel_objekat(p)

    def _panel_objekat(self, p):
        if p.get("filter_prikazan"):
            return
        sn, to = p.get("sn"), p["tabele"]["o"]
        sel = [i for i in to.selection() if i != "prazno"]
        i = int(sel[0][1:]) if sel else -1
        if sn is None or i == p.get("objekat"):
            return
        p["objekat"] = i
        ids = posebni_objekta(sn, i) if i >= 0 else []
        self._popuni_tabelu(p["tabele"]["p"], [("p%d" % j, tuple(sn["posebni"][j]) + (p["vl"]("p%d" % j),))
                                               for j in ids], lambda iid: self._slika_reda(p, iid))

    def _meni_panela(self, e, p, oznaka, kop):
        tr = p["tabele"][oznaka]
        iid = tr.identify_row(e.y)
        if not iid or iid == "prazno":
            return
        tr.selection_set(iid)
        tr.focus(iid)
        kop.kolona_na_misu = kop.kolona_na(e.x, iid)
        # Dejan (v24): "previše ima stvari" - samo ono što ima smisla za taj red; otvaranje je dvoklik, ceo red Ctrl+C,
        # cela parcela se vraća u listi praćenja
        m = tk.Menu(self.root, tearoff=0)
        kljuc = self._kljuc_reda(p, iid)
        ko_id, ko, broj = p["mesto"]
        if kljuc and ucitaj_izvod(ko_id, ko, broj, kljuc)[2]:
            m.add_command(label="Sačuvaj kao PDF...", command=lambda: self._pdf_iz_panela(p, oznaka))
        elif kljuc and self._moze_skinuti(p, kljuc):
            m.add_command(label="Skini sa sajta", command=lambda: self._skini_iz_panela(p, [kljuc]))
        if kljuc and ko_id and broj and p.get("sn"):       # praćenje samo izabranih stavki (v22)
            if kljuc in p["prate"]:
                m.add_command(label="Ne prati više ovu stavku", command=lambda: self._ne_prati(p, kljuc))
            else:
                m.add_command(label="Prati samo ovu stavku (%s)" % opis_stavke(kljuc),
                              command=lambda: self._prati(p, [kljuc]))
            ozn = [k for k in self._kljucevi_panela(p) if k in p["oznaceno"]]
            if len(ozn) > 1:
                m.add_command(label="Prati samo označene (%d)" % len(ozn), command=lambda: self._prati(p, ozn))
        kol = kop.kolona_na_misu
        if kol:
            if m.index("end") is not None:
                m.add_separator()
            m.add_command(label="Kopiraj „%s“" % tr.heading(kol, "text"),
                          command=lambda: self._kopiraj(kop.tekst_celije(iid, kol), "Kopirana ćelija"))
        if m.index("end") is None:
            return
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _pdf_iz_panela(self, p, oznaka):
        """Desni klik na red parcele, zgrade ili posebnog dela > Sačuvaj kao PDF (original sa eKatastra)."""
        tr = p["tabele"][oznaka]
        sel = tr.focus() or (tr.selection() or [""])[0]
        if not sel or sel == "prazno":
            return
        x = p["stavke"].get("parcela" if oznaka == "parcela" else sel)
        ko_id, ko, broj = p["mesto"]
        html = ucitaj_izvod(ko_id, ko, broj, x[4])[2] if x and x[4] else None
        self.sacuvaj_jedan_pdf(html, "%s %s - %s" % (ko, broj, x[4] if x else sel), parent=tr.winfo_toplevel())

    # --- izbor stavki za skidanje (v21) -------------------------------------
    @staticmethod
    def _panel_ziv(p):
        try:
            return bool(p["tabele"]["parcela"].winfo_exists())
        except (KeyError, tk.TclError):
            return False

    @staticmethod
    def _kljuc_reda(p, iid):
        if not iid or iid == "prazno":
            return None
        if iid.startswith("parcela"):
            return "parcela"
        x = p["stavke"].get(iid)
        return x[4] if x else None

    def _na_sajtu(self, mesto):
        """Stavke parcele koje na sajtu imaju 'Podatke o nepokretnosti' (iz poslednje pretrage u ovom pokretanju
        programa) ili None ako se ne zna."""
        ko_id, ko, broj = mesto
        ses = self._sesije.get((str(ko_id), broj))
        if ses:
            return set(ses["nid"])
        for z, podaci, _ in self.rezultati.values():
            if podaci and podaci.get("nep_id") and str(z.get("ko_id")) == str(ko_id) and z.get("broj") == broj:
                return set(podaci["nep_id"])
        return None

    def _moze_skinuti(self, p, k):
        return bool(k) and (p.get("na_sajtu") is None or k in p["na_sajtu"])

    def _slika_reda(self, p, iid):
        k = self._kljuc_reda(p, iid)
        if k in p["oznaceno"]:
            return self._slike_izbora["da"]
        if k in p["ucitano"]:
            return self._slike_izbora["ima"]
        return self._slike_izbora["ne"] if self._moze_skinuti(p, k) else ""     # na sajtu nema podataka za red

    def _kljucevi_panela(self, p):
        """Sve stavke parcele koje imaju 'Podatke o nepokretnosti' (parcela, zgrade, posebni delovi), redom."""
        return [k for k in dict.fromkeys(x[4] for iid, x in p["stavke"].items() if not iid.startswith("x"))
                if self._moze_skinuti(p, k)]

    def _osvezi_izbor(self, p):
        """Kvadratići u sve tri tabele i dugmad 'Skini označene' / 'Skini sve'."""
        if not self._panel_ziv(p):
            return
        prate = p.get("prate") or set()
        for tr in p["tabele"].values():
            for iid in tr.get_children(""):
                if iid != "prazno":
                    oznake = [t for t in tr.item(iid, "tags") if t != "prati"]
                    if self._kljuc_reda(p, iid) in prate:
                        oznake.append("prati")
                    tr.item(iid, image=self._slika_reda(p, iid), tags=oznake)
        ko_id, ko, broj = p.get("mesto") or ("", "", "")
        moze = bool(p["stavke"]) and bool(ko_id) and bool(broj)
        c = self._ceka_stavku
        skida = bool(self.posao and c and c["mesto"] == (ko_id, ko, broj))
        n, sve = len(p["oznaceno"]), len(self._kljucevi_panela(p)) if moze else 0
        p["btn_oznacene"].configure(text="Skini označene (%d)" % n,
                                    state="normal" if moze and n and not skida else "disabled")
        p["btn_sve"].configure(text="Skini sve (%d)" % sve if sve else "Skini sve",
                               state="normal" if moze and sve and not skida else "disabled")

    def _oznaci(self, p, kljuc):
        if not self._moze_skinuti(p, kljuc):
            return
        if kljuc in p["oznaceno"]:
            p["oznaceno"].discard(kljuc)
        else:
            p["oznaceno"].add(kljuc)
        self._osvezi_izbor(p)

    def _klik_izbora(self, p, oznaka, e):
        tr = p["tabele"][oznaka]
        if tr.identify_region(e.x, e.y) != "tree":
            return None
        iid = tr.identify_row(e.y)
        if iid and iid != "prazno":
            tr.selection_set(iid)
            tr.focus(iid)
            self._oznaci(p, self._kljuc_reda(p, iid))
        return "break"

    def _oznaci_red(self, p, oznaka):
        tr = p["tabele"][oznaka]
        iid = tr.focus() or (tr.selection() or [""])[0]
        self._oznaci(p, self._kljuc_reda(p, iid))
        return "break"

    def _skini_iz_panela(self, p, kljucevi):
        """'Skini označene' (kljucevi) ili 'Skini sve' (None)."""
        if kljucevi is None:
            kljucevi = self._kljucevi_panela(p)
        if not kljucevi:
            return
        if self._skini(p["mesto"], kljucevi, parent=p["tabele"]["parcela"].winfo_toplevel()):
            p["oznaceno"].update(kljucevi)
            p["stanje"].configure(text="Skidam sa sajta: 0 od %d..." % len(kljucevi))
            self._osvezi_izbor(p)

    # --- praćenje samo izabranih stavki (Dejan, v22) -------------------------
    def _pracena(self, mesto):
        """Red iz baze ako je parcela u praćenju, inače None."""
        ko_id, _, broj = mesto
        return next((x for x in self.baza.parcele() if str(x["ko_id"]) == str(ko_id) and x["broj"] == broj), None)

    def _osvezi_pracenje_panela(self, p):
        """Natpis „U praćenju: ...“ i podebljane stavke koje se prate."""
        if not self._panel_ziv(p):
            return
        ko_id, _, broj = p.get("mesto") or ("", "", "")
        pp = self._pracena(p["mesto"]) if ko_id and broj and p.get("sn") else None
        prate = pracene_stavke(pp) if pp else []
        p["prate"] = set(prate)
        u_tabelama = {x[4] for iid, x in p["stavke"].items() if iid[:1] in ("o", "p") and iid[1:].isdigit()}
        p["lbl_prati"].configure(text="" if pp is None else ("U praćenju: samo " + ", ".join(
            opis_stavke(k) + ("" if k == "parcela" or k in u_tabelama else " (nema je na sajtu)") for k in prate))
            if prate else "U praćenju: cela parcela")
        b = p["btn_prati_celu"]          # v27: dugme za praćenje cele parcele (skriveno kad se već prati cela)
        if ko_id and broj and p.get("sn") and (pp is None or prate):
            if not b.winfo_manager():
                b.pack(side="right", padx=(0, px(18)))
        elif b.winfo_manager():
            b.pack_forget()
        self._primeni_filter(p)
        self._osvezi_izbor(p)

    def _prati_celu_iz_panela(self, p):
        """v27: dugme „Prati celu parcelu“ u prozoru parcele - prati se sve što je pretraga našla na parceli
        (delovi, zgrade, svi posebni delovi). Ako se do sada pratio samo stan, pita pa prelazi na celu parcelu."""
        mesto = tuple(p["mesto"])
        ko_id, ko, broj = mesto
        if not ko_id or not broj or not p.get("sn"):
            return
        pp = self._pracena(mesto)
        if pp is not None:
            if pracene_stavke(pp):
                self._prati_celu(p=p)
            return
        z, _ = self._zadatak_za(mesto)
        podaci = self._dijalog_podataka("Prati celu parcelu %s %s" % (ko, broj))
        if podaci is None:
            return
        klijent, grupa, napomena = podaci
        sn = json.loads(json.dumps(p["sn"]))
        sn["nepokretnost"] = {**{x[4]: x[3] for x in p["stavke"].values() if x[3]}, **(sn.get("nepokretnost") or {})}
        self.baza.dodaj(z.get("opstina_id"), z.get("opstina") or sn.get("opstina", ""), ko_id, ko, broj, klijent,
                        grupa, napomena, snimak=sn)
        if self._pracena(mesto) is None:
            return
        self._grupisi_klijenta(klijent, grupa)
        self.log("Praćenje %s %s: prati se cela parcela." % (ko, broj), "info")
        self._osvezi_pracenje(mesto)
        n_obj, n_pos = len(sn.get("objekti") or []), len(sn.get("posebni") or [])
        messagebox.showinfo("Praćenje", "Parcela %s %s je u praćenju - cela parcela: delovi parcele, %s i %s (sve što "
                            "je pretraga našla).\n\nProvera javlja svaku promenu na parceli%s." % (
                                ko, broj, "%d zgrad%s" % (n_obj, "a" if n_obj % 10 == 1 and n_obj % 100 != 11 else "e"
                                                           if 2 <= n_obj % 10 <= 4 and not 12 <= n_obj % 100 <= 14
                                                           else "a"),
                                "%d posebnih delova" % n_pos if n_pos != 1 else "1 poseban deo",
                                ": u tabelama i kod vlasnika, tereta i napomena svih stavki (kod mnogo stanova "
                                "provera traje duže)" if self.nep_var.get() else
                                " u tabelama (vlasnici i tereti stanova se ne skidaju: Alati > Praćenje: učitaj "
                                "vlasnike...)"), parent=p["tabele"]["parcela"].winfo_toplevel())

    def _prebaci_filter(self, p):
        p["filter"] = not p.get("filter")
        self._primeni_filter(p)
        self._osvezi_izbor(p)
        p["telo"].platno.yview_moveto(0)

    def _primeni_filter(self, p):
        """v26: samo praćene stavke (praćen stan: samo njegov red i njegova zgrada; praćena parcela: delovi
        parcele) ili cela parcela kao na sajtu. Dugme menja prikaz."""
        if not self._panel_ziv(p):
            return
        prate, sn = p.get("prate") or set(), p.get("sn")
        filt = bool(p.get("filter") and prate and sn)
        b = p["btn_filter"]
        if prate and sn:
            b.configure(text="Prikaži celu parcelu" if filt else "Prikaži samo praćeno")
            if not b.winfo_manager():
                b.pack(side="right", padx=(px(10), 0), before=p["lbl_prati"])
        elif b.winfo_manager():
            b.pack_forget()
        if not filt and not p.get("filter_prikazan"):
            return                                   # cela parcela je već prikazana
        p["filter_prikazan"] = filt
        if filt:
            st = p["stavke"]
            redom = lambda iids: sorted(iids, key=lambda i: int(i[1:]))
            pos = redom(i for i, x in st.items() if i[:1] == "p" and i[1:].isdigit() and x[4] in prate)
            rod = {st[i][1] for i in pos}
            obj = redom(i for i, x in st.items() if i[:1] == "o" and i[1:].isdigit() and (x[4] in prate or i in rod))
            slika = lambda iid: self._slika_reda(p, iid)
            self._popuni_tabelu(p["tabele"]["o"], [(i, tuple(sn["objekti"][int(i[1:])]) + (p["vl"](i),))
                                                  for i in obj], slika)
            self._popuni_tabelu(p["tabele"]["p"], [(i, tuple(sn["posebni"][int(i[1:])]) + (p["vl"](i),))
                                                  for i in pos], slika)
            if pos:
                p["tabele"]["p"].selection_set(pos[0])
                p["tabele"]["p"].focus(pos[0])
            vidljive = {"parcela": "parcela" in prate, "o": bool(obj), "p": bool(pos)}
        else:
            p["deo"], p["objekat"] = None, None
            self._panel_deo(p)
            vidljive = {}
        if vidljive != p["vidljive"]:
            p["vidljive"] = vidljive
            for _, lbl, _, fr in p["sekcije"]:
                lbl.pack_forget()
                fr.pack_forget()
            p["napomena"].pack_forget()
            for oznaka, lbl, natpis, fr in p["sekcije"]:
                if vidljive.get(oznaka, True):
                    lbl.configure(text=("Праћени посебни делови" if oznaka == "p" else
                                        "Зграда у којој је праћени посебни део" if oznaka == "o" and
                                        not any(k.startswith("objekat") for k in prate) else natpis)
                                  if vidljive else natpis)
                    lbl.pack(fill="x", padx=12, pady=(10, 0))
                    fr.pack(fill="x", padx=12)
            p["napomena"].pack(fill="x", padx=12, pady=(8, 10))

    def _osvezi_pracenje(self, mesto):
        self.osvezi_listu()
        for x in self._paneli:          # po KO i broju (naziv KO posle provere je kako ga sajt piše)
            if self._panel_ziv(x) and (str(x["mesto"][0]), x["mesto"][2]) == (str(mesto[0]), mesto[2]):
                self._osvezi_pracenje_panela(x)

    def _prati(self, p, kljucevi):
        """Desni klik > Prati samo ovu stavku / Prati samo označene: provera te parcele traži parcelu, skida samo te
        stavke i javlja samo njihove promene (ne cele parcele ni ostalih stanova)."""
        mesto = tuple(p["mesto"])
        ko_id, ko, broj = mesto
        parent = p["tabele"]["parcela"].winfo_toplevel()
        kljucevi = list(dict.fromkeys(kljucevi))
        if not kljucevi or not ko_id or not broj or not p.get("sn"):
            return
        opis = ", ".join(opis_stavke(k) for k in kljucevi)
        skinuto = {x[4]: x[3] for x in p["stavke"].values() if x[3]}     # podaci koji su već skinuti
        pp = self._pracena(mesto)
        if pp is None:
            z, _ = self._zadatak_za(mesto)
            podaci = self._dijalog_podataka("Prati: %s (%s %s)" % (opis, ko, broj))
            if podaci is None:
                return
            klijent, grupa, napomena = podaci
            sn = json.loads(json.dumps(p["sn"]))
            sn["nepokretnost"] = {**skinuto, **(sn.get("nepokretnost") or {})}
            self.baza.dodaj(z.get("opstina_id"), z.get("opstina") or sn.get("opstina", ""), ko_id, ko, broj, klijent,
                            grupa, napomena, snimak=sn)
            pp = self._pracena(mesto)
            if pp is None:
                return
            self._grupisi_klijenta(klijent, grupa)
            nove = kljucevi
        else:
            stare = pracene_stavke(pp)
            if not stare and not messagebox.askyesno(
                    "Praćenje", "Parcela %s %s je već u praćenju i prati se cela parcela (delovi, zgrade i svi "
                    "stanovi).\n\nDa se od sada prati samo: %s?" % (ko, broj, opis), parent=parent):
                return
            nove = stare + [k for k in kljucevi if k not in stare]
        self.baza.postavi_stavke(pp["id"], nove)
        self.baza.dopuni_nep(pp["id"], {k: skinuto[k] for k in kljucevi if k in skinuto})
        self.log("Praćenje %s %s: prati se samo %s." % (ko, broj, ", ".join(opis_stavke(k) for k in nove)), "info")
        self._osvezi_pracenje(mesto)
        poruka = ("Parcela %s %s: prati se samo %s.\n\nProvera (Proveri sve, Proveri izabrane) traži parcelu "
                  "(captcha), skida samo %s i javlja samo %s." % (
                      ko, broj, ", ".join(opis_stavke(k) for k in nove), "te stavke" if len(nove) > 1 else "tu stavku",
                      "njihove promene" if len(nove) > 1 else "njene promene"))
        nema = [k for k in kljucevi if k not in skinuto and self._moze_skinuti(p, k)]
        if nema:
            if self._sesije.get((str(ko_id), broj)) and not self.posao:
                self._skini(mesto, nema, parent=parent)
                poruka += ("\n\nPodaci za %s se upravo skidaju sa sajta (bez captche): to je stanje sa kojim "
                           "će provera porediti." % ", ".join(opis_stavke(k) for k in nema))
            else:
                poruka += ("\n\nPodaci za %s još nisu skinuti: skinuće se pri prvoj proveri, a od sledeće provere "
                           "javljaju se promene." % ", ".join(opis_stavke(k) for k in nema))
        messagebox.showinfo("Praćenje", poruka, parent=parent)

    def _ne_prati(self, p, kljuc):
        mesto = tuple(p["mesto"])
        pp = self._pracena(mesto)
        if pp is None:
            return
        ostalo = [k for k in pracene_stavke(pp) if k != kljuc]
        if not ostalo and not messagebox.askyesno(
                "Praćenje", "%s je jedina stavka koja se prati na parceli %s %s.\n\nDa se od sada prati cela "
                "parcela (delovi, zgrade i svi stanovi)?" % (opis_stavke(kljuc).capitalize(), mesto[1], mesto[2]),
                parent=p["tabele"]["parcela"].winfo_toplevel()):
            return
        self.baza.postavi_stavke(pp["id"], ostalo)
        self.log("Praćenje %s %s: %s se više ne prati%s." % (
            mesto[1], mesto[2], opis_stavke(kljuc), ("; prati se samo " + ", ".join(opis_stavke(k) for k in ostalo))
            if ostalo else "; prati se cela parcela"), "info")
        self._osvezi_pracenje(mesto)

    def _prati_celu(self, p=None, pid=None):
        pp = self._pracena(p["mesto"]) if p is not None else (self.baza.parcele([pid]) or [None])[0]
        if pp is None or not pracene_stavke(pp):
            return
        parent = p["tabele"]["parcela"].winfo_toplevel() if p is not None else self.root
        if not messagebox.askyesno("Praćenje", "Da se od sada prati cela parcela %s %s (delovi, zgrade i svi stanovi), "
                                   "a ne samo %s?" % (pp["ko"], pp["broj"], ", ".join(
                                       opis_stavke(k) for k in pracene_stavke(pp))), parent=parent):
            return
        self.baza.postavi_stavke(pp["id"], [])
        self.log("Praćenje %s %s: prati se cela parcela." % (pp["ko"], pp["broj"]), "info")
        self._osvezi_pracenje((pp["ko_id"], pp["ko"], pp["broj"]))

    def _zadatak_za(self, mesto):
        """Zadatak za ponovnu pretragu parcele: ako je u praćenju - provera (osveži se i snimak), inače pretraga
        (red te parcele u rezultatima dobija nove podatke)."""
        ko_id, ko, broj = mesto
        p = self._pracena(mesto)
        if p is not None:
            return {"pid": p["id"], "opstina_id": p["opstina_id"], "opstina": p["opstina"], "ko_id": p["ko_id"],
                    "ko": p["ko"], "broj": p["broj"], "p": p, "stavke": pracene_stavke(p)}, "provera"
        iid, z0 = next(((i, r[0]) for i, r in self.rezultati.items()
                        if r[1] is not None and str(r[0].get("ko_id")) == str(ko_id) and r[0].get("broj") == broj),
                       (None, {}))
        oid = z0.get("opstina_id") or next(((int(o) if str(o).isdigit() else o) for o, lista in self.sif.ko.items()
                                            if any(str(k[0]) == str(ko_id) for k in lista)), None)
        z = {"opstina_id": oid, "opstina": z0.get("opstina") or self.sif.naziv_opstine(oid), "ko_id": ko_id,
             "ko": ko, "broj": broj, "zameni": iid}
        if z0.get("adresa"):
            z["adresa"] = z0["adresa"]
        return z, "pretraga"

    def _skini(self, mesto, kljucevi, prednost=None, parent=None):
        """Skida sa sajta samo izabrane stavke parcele. Ako je parcela tražena u ovom pokretanju programa, preko iste
        sesije (bez captche); inače (ili ako sesija više ne važi) parcela se traži ponovo - jedna captcha."""
        if self.posao:
            messagebox.showinfo("Skini sa sajta", "U toku je pretraga, provera ili skidanje. Sačekaj da se završi "
                                "(ili ga prekini), pa klikni ponovo.", parent=parent or self.root)
            return False
        mesto = tuple(mesto)
        ko_id, ko, broj = mesto
        kljucevi = list(dict.fromkeys(kljucevi))
        ses = self._sesije.get((str(ko_id), broj))
        if ses:                                # pretraga u ovom pokretanju: zna se šta na sajtu ima podatke
            kljucevi = [k for k in kljucevi if k in ses["nid"]]
            if not kljucevi:
                messagebox.showinfo("Skini sa sajta", "Za ovu stavku na sajtu nema „Подаци о непокретности“ (u "
                                    "poslednjoj pretrazi parcele nije bilo dugmeta za nju).", parent=parent or self.root)
                return False
        direktno = ses
        z, rezim = self._zadatak_za(mesto)
        self._ceka_stavku = {"mesto": mesto, "cekaju": {}, "stigle": set(), "trazeno": set(kljucevi),
                             "pid": z.get("pid")}
        self.log("--- Skidanje sa sajta: %s %s, stavki: %d%s, %s ---" % (
            ko, broj, len(kljucevi), "" if direktno else " (nova pretraga parcele)", sada()), "info")
        self._pokreni([z], rezim, prednost=prednost or kljucevi[0], samo=kljucevi, direktno=direktno)
        for p in self._paneli:
            if self._panel_ziv(p) and tuple(p["mesto"]) == mesto:
                self._osvezi_izbor(p)
        return True

    def _otvori_iz_panela(self, p, oznaka, e=None):
        tr = p["tabele"][oznaka]
        if e is not None and tr.identify_region(e.x, e.y) == "tree":      # brz drugi klik na kvadratić
            return self._klik_izbora(p, oznaka, e)
        sel = (tr.identify_row(e.y) if e is not None else "") or tr.focus() or (tr.selection() or [""])[0]
        if not sel or sel == "prazno":
            return None
        kljuc = "parcela" if oznaka == "parcela" else sel
        x = p["stavke"].get(kljuc)
        naziv = x[2] if x else sel
        if oznaka == "parcela":
            naziv = "Parcela %s, deo %s" % (p["mesto"][2], tr.item(sel, "values")[1])
        return self._prozor_nepokretnosti(naziv, x[3] if x else [], p["mesto"], x[4] if x else None)

    def _prozor_nepokretnosti(self, naziv, redovi, mesto=None, kljuc=None):
        """'Подаци о непокретности' u izgledu kao na eKatastru. Ako je originalna stranica sacuvana (izvodi/),
        prikazuje se cela, sa svim sekcijama kao na sajtu, i moze da se otvori u pregledacu."""
        html, vreme, putanja = ucitaj_izvod(*(mesto or ("", "", "")), kljuc) if kljuc else (None, None, None)
        sekcije = parsiraj_nepokretnost(html, sve=True) if html else None
        if not sekcije:
            sekcije = sekcije_iz_redova(redovi)
        w = tk.Toplevel(self.root)
        w.title("Подаци о непокретности  -  %s" % naziv)
        sh = self.root.winfo_screenheight()
        w.geometry("%dx%d" % (min(px(940), w.winfo_screenwidth() - 60), min(px(860), sh - 100)))
        traka = ttk.Frame(w, padding=(12, 8, 12, 8))
        traka.pack(fill="x")
        ttk.Label(traka, text=naziv, font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(traka, text="Zatvori (Esc)", style="Mali.TButton", command=w.destroy).pack(side="right")
        ttk.Button(traka, text="Kopiraj tekst", style="Mali.TButton",
                   command=lambda: self._kopiraj(getattr(w, "_tekst", ""), "Kopiran tekst izvoda")).pack(
            side="right", padx=(0, 6))
        if putanja:
            ttk.Button(traka, text="Otvori original u pregledaču (štampa)", style="Mali.TButton",
                       command=lambda: self._otvori(putanja)).pack(side="right", padx=(0, 6))
            ko_id, ko, broj = mesto or ("", "", "")
            ttk.Button(traka, text="Sačuvaj kao PDF...", style="Mali.TButton",
                       command=lambda: self.sacuvaj_jedan_pdf(putanja, "%s %s - %s" % (ko, broj, kljuc), parent=w)
                       ).pack(side="right", padx=(0, 6))
        prazno = None
        if not sekcije and kljuc and mesto and mesto[0] and mesto[2]:
            # Dejan (v20/v21): stavka koja nije skinuta skida se na zahtev - samo ona
            w._dugme_ucitaj = ttk.Button(traka, text="Skini sa sajta", style="Glavno.TButton",
                                         command=lambda: self._ucitaj_stavku(w, naziv, mesto, kljuc))
            w._dugme_ucitaj.pack(side="right", padx=(0, 6))
            prazno = ("Podaci sa sajta za ovu stavku nisu skinuti. Klikni „Skini sa sajta“: skida se samo ova stavka "
                      "(ako je parcela tražena od kad je program otvoren, odmah, bez captche; inače program ponovo "
                      "traži parcelu - jedna captcha) i prikaže se ovde čim stigne.")
            c = self._ceka_stavku
            if self.posao and c and c["mesto"] == tuple(mesto) and kljuc in c["trazeno"]:     # upravo se skida
                c["cekaju"][kljuc] = {"naziv": naziv, "w": w}
                w._dugme_ucitaj.configure(text="Skidam sa sajta...", state="disabled")
        spolja = kartica(w)
        spolja.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        unutra = skrol_okvir(spolja)
        self._poslednji_izvod = nacrtaj_izvod(unutra, sekcije, vreme, prazno)
        w._tekst = self._poslednji_izvod
        w.bind("<Escape>", lambda e: w.destroy())
        w.focus_set()
        return w

    def _ucitaj_stavku(self, w, naziv, mesto, kljuc):
        """'Skini sa sajta' u praznom prozoru izvoda: skida se samo ta stavka i prozor se odmah popuni."""
        mesto = tuple(mesto)
        c = self._ceka_stavku
        if self.posao and c and c["mesto"] == mesto and kljuc in c["trazeno"]:
            c["cekaju"][kljuc] = {"naziv": naziv, "w": w}
            w._dugme_ucitaj.configure(text="Skidam sa sajta...", state="disabled")
            return
        if self._skini(mesto, [kljuc], prednost=kljuc, parent=w):
            self._ceka_stavku["cekaju"][kljuc] = {"naziv": naziv, "w": w}
            w._dugme_ucitaj.configure(text="Skidam sa sajta...", state="disabled")

    def _stigla_strana(self, ime, html):
        """Stigla je jedna stranica 'Podaci o nepokretnosti': čuva se u izvodi/, upisuje u red rezultata i u otvorene
        prozore te parcele, a prozor koji je čeka se popuni."""
        c = self._ceka_stavku
        if not c:
            return
        ko_id, ko, broj = c["mesto"]
        ses = self._sesije.get((str(ko_id), broj))
        try:
            dodaj_izvod(ko_id, ko, broj, ime, html, list(ses["nid"]) if ses else None)
        except OSError as e:
            upisi_dnevnik("IZVOD %s: %r" % (ime, e))
            return
        c["stigle"].add(ime)
        redovi = tekst_nepokretnosti(html)
        if c.get("pid"):                    # parcela u praćenju: skinuto postaje osnova za sledeću proveru (v22)
            self.baza.dopuni_nep(c["pid"], {ime: redovi})
        for iid, (z, podaci, _) in self.rezultati.items():
            if podaci and str(z.get("ko_id")) == str(ko_id) and z.get("broj") == broj:
                nep = {**(podaci.get("nepokretnost") or {}), ime: redovi}
                red = list(podaci.get("nep_redosled") or []) + list(nep)
                podaci["nepokretnost"] = {k: nep[k] for k in dict.fromkeys(red) if k in nep}
                if self.tree_p.exists(iid):
                    self.tree_p.item(iid, values=self._vrednosti_reda(z, podaci))
        trazeno = c["trazeno"]
        for p in self._paneli:
            if not self._panel_ziv(p) or tuple(p["mesto"]) != c["mesto"]:
                continue
            for iid, x in list(p["stavke"].items()):
                if x[4] == ime:
                    p["stavke"][iid] = x[:3] + (redovi,) + x[4:]
            p["ucitano"].add(ime)
            p["oznaceno"].discard(ime)
            for oznaka, tr in p["tabele"].items():
                for iid in tr.get_children(""):
                    if self._kljuc_reda(p, iid) == ime:
                        vals = list(tr.item(iid, "values"))
                        vals[-1] = p["vl"]("parcela" if oznaka == "parcela" else iid)
                        tr.item(iid, values=vals)
            n = len(c["stigle"] & trazeno)
            p["stanje"].configure(text="Skidam sa sajta: %d od %d..." % (n, len(trazeno)) if n < len(trazeno)
                                  else "Skinuto sa sajta: %d od %d" % (n, len(trazeno)))
            self._osvezi_izbor(p)
        x = c["cekaju"].pop(ime, None)
        if not x:
            return
        polozaj = None
        try:
            if x["w"].winfo_exists():
                polozaj = x["w"].geometry()
                x["w"].destroy()
        except tk.TclError:
            pass
        if polozaj is not None:                # prozor je još otvoren - isti prozor, sada sa podacima
            novi = self._prozor_nepokretnosti(x["naziv"], redovi, c["mesto"], ime)
            novi.geometry(polozaj)

    def _stavka_nije_stigla(self):
        """Posle skidanja: dugmad ponovo rade, a za stavke koje nisu stigle kaže se zašto (ostaju označene)."""
        c, self._ceka_stavku = self._ceka_stavku, None
        if not c:
            return
        nije = c["trazeno"] - c["stigle"]
        for p in self._paneli:
            if self._panel_ziv(p) and tuple(p["mesto"]) == c["mesto"]:
                p["na_sajtu"] = self._na_sajtu(c["mesto"])      # posle nove pretrage zna se šta sajt ima
                p["oznaceno"] = {k for k in p["oznaceno"] if self._moze_skinuti(p, k)}
                if nije:
                    nema = {k for k in nije if not self._moze_skinuti(p, k)}
                    p["stanje"].configure(text="Skinuto %d od %d.%s%s" % (
                        len(c["trazeno"]) - len(nije), len(c["trazeno"]),
                        " Šta nije skinuto ostalo je označeno: klikni „Skini označene“ ponovo." if nije - nema else "",
                        " Za %d na sajtu nema podataka." % len(nema) if nema else ""))
                self._osvezi_izbor(p)
        otvoreni = []
        for kljuc, x in c["cekaju"].items():
            try:
                if x["w"].winfo_exists():
                    x["w"]._dugme_ucitaj.configure(text="Skini sa sajta", state="normal")
                    otvoreni.append(x)
            except (AttributeError, tk.TclError):
                pass
        if otvoreni:
            messagebox.showinfo("Skini sa sajta", "Nije skinuto: %s.\n\nSkidanje je prekinuto ili nije uspelo, ili "
                                "se ta stavka na sajtu sada drugačije zove (otvori parcelu ponovo, iz novog "
                                "rezultata)." % ", ".join(x["naziv"] for x in otvoreni), parent=otvoreni[0]["w"])

    # --- provera -----------------------------------------------------------
    def _izabrani_za_proveru(self):
        """Parcela koju si sam izabrao (red) proverava se uvek, i odložena i arhivirana. Iz izabrane grupe idu
        samo parcele koje nisu odložene ni u arhivi (osim u prikazima Odložena provera i Arhiva)."""
        direktno, iz_grupe = [], []
        for iid in self.tree.selection():
            if iid.startswith("g:"):
                iz_grupe += [int(c) for c in self.tree.get_children(iid)]
            else:
                direktno.append(int(iid))
        ids = list(dict.fromkeys(direktno + iz_grupe))
        if not ids:
            messagebox.showinfo("Provera", "Izaberi parcele ili grupu u listi praćenja.")
            return None
        sve = self.prikaz_var.get() in (PRIKAZI[5], PRIKAZI[6])
        parcele = [p for p in self.baza.parcele(ids) if sve or p["id"] in direktno or aktivan(p)]
        if not parcele:
            messagebox.showinfo("Provera", "Parcele u izabranoj grupi su odložene ili u arhivi.\n"
                                           "Izaberi samu parcelu (red) ako želiš da je proveriš.")
        return parcele or None

    def proveri(self, samo_izabrane, neaktivni=False):
        """samo_izabrane: izabrane u listi; neaktivni: samo odložene i arhivirane; inače "Proveri sve"
        (bez odloženih i arhiviranih)."""
        if self.posao:
            return
        preskoceno = []
        if samo_izabrane:
            parcele = self._izabrani_za_proveru()
            if not parcele:
                return
        elif neaktivni:
            parcele = [p for p in self.baza.parcele() if not aktivan(p)]
            if not parcele:
                messagebox.showinfo("Provera", "Nema parcela sa odloženom proverom ni u arhivi.")
                return
        else:
            svi = self.baza.parcele()
            parcele = [p for p in svi if aktivan(p)]
            preskoceno = [p for p in svi if not aktivan(p)]
            if svi and not parcele:
                messagebox.showinfo("Provera", "Sve parcele su odložene ili u arhivi.\n"
                                               "Provera -> Proveri odložene i arhivirane ih proverava.")
                return
        if not parcele:
            messagebox.showinfo("Provera", "Lista praćenih parcela je prazna.")
            return
        zadaci = [{"pid": p["id"], "opstina_id": p["opstina_id"], "opstina": p["opstina"], "ko_id": p["ko_id"],
                   "ko": p["ko"], "broj": p["broj"], "p": p, "stavke": pracene_stavke(p)} for p in parcele]
        self.log("--- Provera %s, %s ---" % (br_parcela(len(zadaci)), sada()), "info")
        if preskoceno:
            n_arh = sum(arhiviran(p) for p in preskoceno)
            d = (["odložena provera: %d" % (len(preskoceno) - n_arh)] if len(preskoceno) > n_arh else []) + \
                (["u arhivi: %d" % n_arh] if n_arh else [])
            self.log("    Ne proverava se (%s). Njih proverava \"Proveri izabrane\" ili "
                     "Provera -> Proveri odložene i arhivirane." % ", ".join(d), "tiho")
        self.nb.select(1)
        self._pokreni(zadaci, "provera")

    def _pokreni(self, zadaci, rezim, prednost=None, samo=None, direktno=None, nep=None):
        self._zauzet(True, rezim)
        self._korisnik_prekinuo = False
        self.napredak.configure(maximum=len(zadaci), value=0)
        self._promena_u = []
        citac = self.citac if self.auto_var.get() else None
        detaljno = self.detaljno_var.get()
        if nep is not None:                  # v32: zadatak - svi listovi (ili samo stan iz ugovora)
            pass
        elif rezim == "provera":
            nep = "sve" if self.nep_var.get() else None
        else:
            nep = "sve" if self.nep_pretraga_var.get() == "sve" else None
        if samo is not None:
            detaljno = True              # skidanje izabranih stavki: stavka može biti na bilo kom delu parcele
        self.posao = Pretraga(citac, detaljno, nep, self._trazi_odgovor_iz_niti, self._log_iz_niti,
                              lambda posao: self.root.after(0, self._gotovo, posao),
                              prikazi=lambda opis: self.root.after(0, self._prikazi_samo, opis),
                              stanje=lambda t: self.root.after(0, lambda: self.lbl_stanje.configure(text=t)))
        self.posao._citac_za_ucenje = self.citac
        self.posao.ko_za = self.sif.ko_za
        if samo is not None:
            self.posao.prednost, self.posao.samo, self.posao.direktno = prednost, set(samo), direktno
            self.posao.strana = lambda ime, html: self.root.after(0, self._stigla_strana, ime, html)
        self.posao.sacuvaj_ko = lambda oid, lista: self.root.after(0, self.sif.postavi_ko, oid, lista)
        self.posao.rezultat = lambda z, podaci, razlog: self.root.after(0, self._rezultat, z, podaci, razlog)
        self.posao.pokreni(zadaci)

    def _rezultat(self, z, podaci, razlog):
        v = float(self.napredak.cget("value")) + 1
        if v > float(self.napredak.cget("maximum")):        # adresa na kojoj je više parcela
            self.napredak.configure(maximum=v)
        self.napredak.configure(value=v)
        self._osvezi_desno()
        if podaci is not None and podaci.get("nep_id") and self.posao is not None and self.posao.sajt is not None:
            # sesija ove pretrage: iz prozora parcele izabrane stavke se skidaju bez nove pretrage i captche
            self._sesije[(str(z.get("ko_id")), z["broj"])] = {"sajt": self.posao.sajt, "nid": podaci["nep_id"],
                                                              "naslov": "%s %s" % (z["ko"], z["broj"])}
        if podaci is not None and podaci.get("nep_html"):
            try:
                sacuvaj_izvode(z.get("ko_id"), z["ko"], z["broj"], podaci["nep_html"],
                               podaci.get("nep_potpuno", False), podaci.get("nep_redosled"))
            except OSError as e:
                upisi_dnevnik("IZVODI: %r" % (e,))
        if self.rezim == "pretraga":
            self._dodaj_red_pretrage(z, podaci, razlog)
            naslov = "%s %s" % (z["ko"], z["broj"])
            if z.get("adresa") and z["adresa"] != z["broj"]:
                naslov += " (adresa %s)" % z["adresa"]
            if podaci is None:
                self.log("%s: %s" % (naslov, razlog), "neuspeh")
            else:
                sn = napravi_snimak(podaci)
                vlasnici, _ = vlasnici_tereti(sn)
                n_nep = len([k for k in (sn.get("nepokretnost") or {}) if k != "parcela"])
                self.log("%s: pronađeno - %d deo/delova, %d objek%s, %d posebnih delova%s%s%s" % (
                    naslov, len(sn["delovi"]), len(sn["objekti"]), "at" if len(sn["objekti"]) == 1 else "ta",
                    len(sn["posebni"]), ("; vlasnici: " + vlasnici) if vlasnici else "",
                    ("; učitani podaci za %d zgrada/posebnih delova" % n_nep) if n_nep else
                    ("; na sajtu %d stavki (parcela, zgrade, posebni delovi) - šta se skida biraš u prozoru parcele"
                     % len(podaci["nep_id"])) if podaci.get("nep_id") and not sn["nepokretnost"] else "",
                    ("; napomena: " + "; ".join(podaci["napomene"])) if podaci.get("napomene") else ""), "info")
            return
        p = z["p"]
        if z.get("zadatak") and self._zadatak is not None:
            self._zadatak["provera"][p["id"]] = "ok" if podaci is not None else razlog
        naslov = "%s%s %s" % ((p["klijent"] + " | ") if p["klijent"] else "", p["ko"], p["broj"])
        prate = pracene_stavke(p)
        if prate:
            naslov += " (prati se samo: %s)" % ", ".join(opis_stavke(k) for k in prate)
        ceka = self._otvori_posle if self._otvori_posle and self._otvori_posle["pid"] == p["id"] else None
        if podaci is None:
            self.baza.zabelezi_neuspeh(p["id"], razlog)
            self.log("%s: nije provereno - %s" % (naslov, razlog), "neuspeh")
            if ceka:
                ceka["rez"] = ("nije", razlog)
        else:
            sn = napravi_snimak(podaci)
            try:
                stari_sn = json.loads(p["snimak"]) if p["snimak"] else {}
            except ValueError:
                stari_sn = {}
            stari_nep = set(stari_sn.get("nepokretnost", {})) if ista_nep_verzija(stari_sn, sn) else set()
            mapa = None
            if prate:              # v22: kako se praćene stavke sada zovu na sajtu (None = nema je)
                na_sajtu = list(podaci.get("nep_redosled") or []) + list(redovi_stavki(sn))
                mapa = {k: nadji_kljuc(k, na_sajtu) for k in prate}
            if not podaci.get("nep_potpuno") and stari_nep:
                # nisu ucitane sve stavke (prekinuto, pauza sajta, iskljuceno ucitavanje): ranije ucitani podaci
                # ostalih stavki ostaju u snimku, da se ne izgube i da se porede pri sledecoj proveri
                for k, v in stari_sn["nepokretnost"].items():
                    sn["nepokretnost"].setdefault(k, v)
                for k, k2 in (mapa or {}).items():    # preimenovana praćena stavka: stari naziv ne ostaje u snimku
                    if k2 and k2 != k and k2 in podaci.get("nepokretnost", {}):
                        sn["nepokretnost"].pop(k, None)
            sumnja = sumnjiv_snimak(stari_sn, sn, podaci.get("nepokretnost") or {})
            if sumnja and not self.baza.sumnjivo_ponovljeno(p["id"], otisak_snimka(sn)):
                # v37: okrnjen odgovor sajta ne postaje promena; stanje ostaje staro. Ako isti odgovor stigne i u
                # sledećoj proveri, prihvata se kao pravo stanje (npr. zgrada stvarno srušena).
                razlog = "sumnjiv odgovor sajta: %s - stanje nije menjano, proveri ponovo" % sumnja
                self.baza.zabelezi_neuspeh(p["id"], razlog)
                self.log("%s: %s" % (naslov, razlog), "neuspeh")
                if self.posao is not None:
                    self.posao.ok -= 1
                    self.posao.neuspeli.append((naslov, razlog))
                if z.get("zadatak") and self._zadatak is not None:
                    self._zadatak["provera"][p["id"]] = razlog
                if ceka:
                    ceka["rez"] = ("nije", razlog)
                self.osvezi_listu()
                return
            prva, promene = self.baza.obradi(p, sn, mapa)
            if ceka:
                ceka["rez"] = ("prva",) if prva else ("promena", promene) if promene else ("ok",)
                ceka["prate"] = list(dict.fromkeys(list(prate) + [k2 for k2 in (mapa or {}).values() if k2]))
            novi_nep = [k for k in sn.get("nepokretnost", {}) if k not in stari_nep]
            if not prva and novi_nep:
                self.log("%s: prvi put učitani vlasnici, tereti i napomene (%d: %s) - od sledeće provere prate se i "
                         "njihove promene" % (naslov, len(novi_nep), ", ".join(novi_nep[:3]) + (", ..." if len(novi_nep) > 3 else "")),
                         "info")
            self.sesija_ok.add(p["id"])
            if prva:
                pov, nacin, obj = kratak_opis(sn)
                self.log("%s: prvi put provereno - %s m², %s, %s%s" % (
                    naslov, pov, nacin, obj, ("; podaci o nepokretnosti: %d" % len(sn["nepokretnost"]))
                    if sn["nepokretnost"] else ""), "info")
            elif promene:
                self.sesija_novo.setdefault(p["id"], []).extend(promene)
                g = p["grupa"] or BEZ_GRUPE
                if g not in self._auto_otvorene:      # grupa sa promenom se sama otvori (jednom)
                    self._auto_otvorene.add(g)
                    self._otvorene.add("g:" + g)
                self._promena_u.append(p["klijent"] or "%s %s" % (p["ko"], p["broj"]))
                jasno = promene_staro_novo(promene)
                self.log("%s: PROMENA (%d)" % (naslov, len(jasno)), "novo_naslov")
                for x in jasno[:15]:
                    self.log_promene(x)
                if len(jasno) > 15:
                    self.log("    ... i još %d (vidi Detalji)" % (len(jasno) - 15), "novo")
            else:
                self.log("%s: provereno, bez promena" % naslov, "tiho")
            for n in sn.get("napomene") or []:
                self.log("    napomena: " + n, "tiho")
        self.osvezi_listu()

    def _gotovo(self, posao):
        rezim = self.rezim
        c = self._ceka_stavku
        sveze, self._otvori_posle = self._otvori_posle, None
        self._zavrsi_posao("Završeno." if not posao.stop else "Prekinuto.")
        self._stavka_nije_stigla()            # sve stranice su već stigle (root.after redom, pre ovoga)
        if c is not None:                      # skidanje izabranih stavki (v21)
            n, uk = len(c["stigle"] & c["trazeno"]), len(c["trazeno"])
            naslov = ("Prekinuto - " if posao.stop else "") + "Skinuto sa sajta: %d od %d (%s %s)" % (
                n, uk, c["mesto"][1], c["mesto"][2])
            if posao.neuspeli:
                naslov += ", nije uspelo: %s" % posao.neuspeli[0][1]
            self.log("--- %s ---" % naslov, "uspeh" if n == uk else "neuspeh_naslov")
            self.lbl_opis.configure(text=naslov)
            return
        ukupno = posao.ok + len(posao.neuspeli)
        delovi = ["uspešno: %d od %d" % (posao.ok, ukupno)]
        if rezim == "provera":
            delovi.append("sa promenom: %d" % len(self._promena_u) if self._promena_u else "bez promena")
        if posao.neuspeli:
            delovi.append("nije uspelo: %d" % len(posao.neuspeli))
        naslov = ("Prekinuto - " if posao.stop else ("Rezultat provere - " if rezim == "provera" else "Rezultat pretrage - ")) \
            + ", ".join(delovi)
        self.log("--- %s ---" % naslov, "uspeh" if not posao.neuspeli and not posao.stop else "neuspeh_naslov")
        for naziv, razlog in posao.neuspeli[:30]:
            self.log("    nije uspelo: %s  (%s)" % (naziv, razlog), "neuspeh")
        self.lbl_opis.configure(text=naslov)
        if self._zadatak is not None and self._zadatak.get("faza") == "provera":
            self._posle_provere_zadatka(posao)
            return
        if sveze is not None:                 # v28: „Osveži sa sajta“ u prozoru - bez obaveštenja i treptanja
            self._osvezen(sveze, self._korisnik_prekinuo)
            return
        if not self._korisnik_prekinuo and os.name == "nt":
            try:
                treperi_na_taskbaru(self.root)
            except Exception:
                pass
            if self.obavestenje_var.get():
                red = ", ".join(delovi)
                drugi = ("Promene: " + ", ".join(self._promena_u[:4])) if self._promena_u else ""
                posalji_obavestenje("Asistent KATASTAR: %s %s" % ("provera" if rezim == "provera" else "pretraga",
                                                                    "prekinuta" if posao.stop else "završena"),
                                    [red] + ([drugi] if drugi else []))

    def _zauzet(self, da, rezim=None):
        self.rezim = rezim if da else None
        st = "disabled" if da else "normal"
        for b in (self.btn_sve, self.btn_izabrane, self.btn_pretrazi):
            b.configure(state=st)
        for b in (self.btn_prekini1, self.btn_prekini2):
            b.configure(state="normal" if da else "disabled")
        if not da:
            self.napredak.configure(value=0)

    def _zavrsi_posao(self, poruka):
        self.posao = None
        self._zatvori_captchu()
        self._sakrij_captchu_panel()
        self._zauzet(False)
        self.lbl_opis.configure(text=poruka)
        self.lbl_stanje.configure(text="")
        self._osvezi_desno()
        self.osvezi_listu()

    def _prekini(self):
        if self.posao:
            self.posao.stop = True
            self._korisnik_prekinuo = True
        self._zatvori_captchu()
        self._odgovor = False
        self._dogadjaj.set()

    # --- captcha -----------------------------------------------------------
    def _napravi_captcha(self):
        f = ttk.LabelFrame(self.root, text="Captcha - potreban je tvoj unos", padding=8)
        self.captcha_frame = f
        self.cv = tk.Canvas(f, width=px(400), height=px(120), bg="white", highlightthickness=1, highlightbackground="#bbb")
        self.cv.grid(row=0, column=0, rowspan=3, padx=(0, 12))
        self.lbl_cap_opis = ttk.Label(f, text="")
        self.lbl_cap_opis.grid(row=0, column=1, columnspan=4, sticky="w")
        ttk.Label(f, text="Kod sa slike (velika i mala slova):").grid(row=1, column=1, sticky="w")
        self.e_cap = ttk.Entry(f, width=10, font=("Consolas", 16), state="disabled")
        self.e_cap.grid(row=1, column=2, padx=6)
        self.e_cap.bind("<Return>", lambda e: self._potvrdi())
        self.btn_potvrdi = ttk.Button(f, text="Potvrdi (Enter)", command=self._potvrdi, state="disabled")
        self.btn_potvrdi.grid(row=1, column=3, padx=4)
        self.btn_preskoci = ttk.Button(f, text="Preskoči parcelu", command=self._preskoci, state="disabled")
        self.btn_preskoci.grid(row=1, column=4, padx=4)
        self.lbl_upoz = ttk.Label(f, text="", foreground="#b00020")
        self.lbl_upoz.grid(row=2, column=1, columnspan=4, sticky="w")
        self.lbl_predlog = ttk.Label(f, text="", foreground="#0b5394", font=("Consolas", 12))
        self.lbl_predlog.grid(row=3, column=1, columnspan=4, sticky="w")

    def _pokazi_captchu_panel(self):
        if not self.captcha_frame.winfo_manager():
            self.captcha_frame.pack(fill="x", padx=16, pady=(8, 0), before=self.paned)

    def _sakrij_captchu_panel(self):
        """Posle pretrage panel uvek nestaje (i kad je prozor bio umanjen dok se pretraga zavrsavala)."""
        if self.captcha_frame.winfo_manager():
            self.captcha_frame.pack_forget()

    def nacrtaj_captchu(self, svg, platno=None, k=None):
        """SVG captcha nacrtana na tkinter platnu (bez dodatnih biblioteka)."""
        cv = platno or self.cv
        k = k or 2.0 * SKALA
        cv.delete("all")
        p = parsiraj_svg(svg)
        if not p:
            cv.create_text(px(200), px(60), text="captcha nije mogla da se prikaze", fill="#b00020")
            return False
        for linija in p["sum"]:
            if len(linija) > 1:
                cv.create_line(*[c * k for t in linija for c in t], fill="silver", width=max(1, int(k)))
        for g in p["znaci"]:
            r = rupe(g["poligoni"])
            for i, poly in enumerate(g["poligoni"]):
                if i not in r and len(poly) > 2:
                    cv.create_polygon(*[c * k for t in poly for c in t], fill="#555555", outline="")
            for i in r:
                poly = g["poligoni"][i]
                if len(poly) > 2:
                    cv.create_polygon(*[c * k for t in poly for c in t], fill="white", outline="")
        return True

    def _trazi_odgovor_iz_niti(self, svg, opis):
        self._dogadjaj.clear()
        self._odgovor = None
        self.root.after(0, self._prikazi_captchu, svg, opis)
        self._dogadjaj.wait()
        return self._odgovor

    def _prikazi_samo(self, opis):
        self.lbl_opis.configure(text=opis)
        m = re.match(r"\[(\d+)/(\d+)\]", opis)
        if m:
            self.napredak.configure(maximum=int(m.group(2)), value=int(m.group(1)) - 1)

    def _prikazi_captchu(self, svg, opis):
        self._obavesti_za_captchu(opis)
        self._pokazi_captchu_panel()
        self.nacrtaj_captchu(svg)
        self.lbl_cap_opis.configure(text=opis)
        self._prikazi_samo(opis)
        self.lbl_upoz.configure(text="")
        try:
            predlog, _ = self.citac.procitaj(svg)
        except Exception:
            predlog = None
        if predlog and predlog.strip("?"):
            self.lbl_predlog.configure(text="Čitač prepoznaje: %s   (? = znak koji još ne zna; upiši ceo kod)"
                                       % "  ".join(predlog))
        else:
            self.lbl_predlog.configure(text="")
        for w in (self.e_cap, self.btn_potvrdi, self.btn_preskoci):
            w.configure(state="normal")
        self.e_cap.delete(0, "end")
        if predlog and "?" not in predlog:
            self.e_cap.insert(0, predlog)        # citac zna sve znakove - dovoljno je Enter (ili ispravi)
            self.e_cap.select_range(0, "end")
        self.e_cap.focus_set()
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    def _obavesti_za_captchu(self, opis):
        """Citac nije prepoznao kod, pa program ceka tebe: zvuk uvek, a ako radis u drugom prozoru jos i
        Windows obavestenje i treptanje na taskbaru (Alati > Obavestenje i zvuk kad treba da upises captchu)."""
        if not self.obavestenje_cap_var.get():
            return
        try:
            u_fokusu = prozor_u_fokusu(self.root)
        except Exception:
            u_fokusu = False
        zvuk_upozorenja(self.root)
        if u_fokusu:
            return
        parcela = re.sub(r"\s+-\s+pokusaj\s+\d+$", "", opis.strip())
        try:
            treperi_na_taskbaru(self.root)
        except Exception:
            pass
        posalji_obavestenje("Asistent KATASTAR: upiši captchu",
                            ["Čitač nije prepoznao kod, pretraga čeka tvoj unos.", parcela])

    def _zatvori_captchu(self):
        for w in (self.e_cap, self.btn_potvrdi, self.btn_preskoci):
            w.configure(state="disabled")

    def _potvrdi(self):
        if str(self.e_cap.cget("state")) == "disabled":
            return
        t = self.e_cap.get().strip()
        if not re.match(r"^[A-Za-z0-9]{4,6}$", t):
            self.lbl_upoz.configure(text="Upiši kod sa slike (5 slova i cifara, pazi na velika i mala slova).")
            self.e_cap.select_range(0, "end")
            return
        self._zatvori_captchu()
        self._odgovor = t
        self._dogadjaj.set()

    def _preskoci(self):
        self._zatvori_captchu()
        self._odgovor = None
        self._dogadjaj.set()

    # --- log ---------------------------------------------------------------
    def _napravi_log(self):
        """Poruke vise nisu u oknu na dnu glavnog prozora (Dejan: vise mesta za tabelu, ishod "uspesno 6 od 6"
        pise u statusnoj traci). Sve poruke su u posebnom prozoru: Alati > Prikazi sve poruke."""
        w = tk.Toplevel(self.root)
        w.withdraw()
        w.title("Dnevnik rada - Asistent KATASTAR")
        w.geometry("%dx%d" % (min(px(1000), w.winfo_screenwidth() - 60), min(px(520), w.winfo_screenheight() - 120)))
        w.protocol("WM_DELETE_WINDOW", w.withdraw)
        w.bind("<Escape>", lambda e: w.withdraw())
        self.log_prozor = w
        f = kartica(w)
        f.pack(fill="both", expand=True, padx=px(12), pady=px(12))
        zag = ttk.Frame(f, style="Kartica.TFrame", padding=(12, 6, 12, 4))
        zag.pack(fill="x")
        ttk.Label(zag, text="Sve poruke", style="Naslov.TLabel").pack(side="left")
        ttk.Button(zag, text="Obriši prikaz", style="Mali.TButton", command=self._obrisi_log).pack(side="right")
        ttk.Button(zag, text="Kopiraj", style="Mali.TButton", command=self._kopiraj_log).pack(side="right",
                                                                                            padx=(0, 6))
        tk.Frame(f, bg=T_IVICA, height=1).pack(fill="x")
        un = ttk.Frame(f, style="Kartica.TFrame", padding=(8, 4, 0, 4))
        un.pack(fill="both", expand=True)
        self.txt = tk.Text(un, height=12, wrap="word", font=FONT, state="disabled", highlightthickness=0, padx=4)
        sb = ttk.Scrollbar(un, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        for tag, boja, bold in (("info", "#374151", False), ("tiho", "#9ca3af", False), ("greska", BOJA_NEUSPEH, False),
                                ("novo_naslov", T_AKCENT, True), ("novo", T_AKCENT, False),
                                ("uspeh", BOJA_OK, True), ("neuspeh", "#b36b00", False),
                                ("neuspeh_naslov", "#b36b00", True)):
            self.txt.tag_configure(tag, foreground=boja, font=FONT_B if bold else FONT)
        self.txt.tag_configure("log_staro", foreground=FG_STARO, background=BG_STARO, font=FONT_B)
        self.txt.tag_configure("log_novo", foreground=FG_NOVO_IZM, background=BG_NOVO_IZM, font=FONT_B)

    def prikazi_dnevnik(self):
        self.log_prozor.deiconify()
        self.log_prozor.lift()
        self.txt.see("end")

    def _log_iz_niti(self, poruka, tag="info"):
        self.root.after(0, self.log, poruka, tag)

    def log_promene(self, pr):
        """v31: jedna promena u porukama - gde, staro (promenjeno crveno), novo (promenjeno zeleno)."""
        try:
            self.txt.configure(state="normal")
            self.txt.insert("end", "[%s]     %s%s" % (dt.datetime.now().strftime("%H:%M:%S"), pr["gde"],
                                                    "   " if pr["gde"] else ""), "novo")
            for natpis, delovi, tag in (("staro: ", pr["staro"], "log_staro"), ("   novo: ", pr["novo"], "log_novo")):
                self.txt.insert("end", natpis, "novo")
                for t, v in delovi or [("-", "")]:
                    self.txt.insert("end", t.replace("\n", ", "), tag if v == "izmena" else "info")
            self.txt.insert("end", "\n")
            self.txt.see("end")
            self.txt.configure(state="disabled")
        except tk.TclError:
            pass
        upisi_dnevnik("    " + red_promene(pr))

    def log(self, poruka, tag="info"):
        try:
            self.txt.configure(state="normal")
            self.txt.insert("end", "[%s] %s\n" % (dt.datetime.now().strftime("%H:%M:%S"), poruka), tag)
            self.txt.see("end")
            self.txt.configure(state="disabled")
        except tk.TclError:              # prozor sa porukama zatvoren pri gasenju programa: ostaje dnevnik.txt
            pass
        upisi_dnevnik(poruka)

    def _izuzetak(self, tip, vrednost, tb):
        upisi_dnevnik("".join(traceback.format_exception(tip, vrednost, tb)))
        try:
            self.lbl_stanje.configure(text="Neočekivana greška u programu (detalji u dnevnik.txt): %s" % (vrednost,))
        except Exception:
            pass

    def _kopiraj_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.txt.get("1.0", "end"))
        self.lbl_opis.configure(text="Poruke su kopirane (Ctrl+V).")

    def _obrisi_log(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")


def izvezi_csv(putanja, rezultati):
    """CSV sa ; i BOM-om, da ga Excel otvori sa cirilicom. Jedan red po delu parcele."""
    n = 0
    with open(putanja, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Opština", "KO", "Parcela", "Deo", "Površina m²", "Ulica / potes", "Način korišćenja",
                    "Vrsta zemljišta", "Evidencija", "Objekti na delu", "Posebni delovi", "Vlasnici parcele (udeo)",
                    "Tereti na parceli", "Vlasnici zgrada i stanova", "Status"])
        for z, podaci, razlog in rezultati:
            if podaci is None:
                w.writerow([z["opstina"], z["ko"], z["broj"], "", "", "", "", "", "", "", "", "", "", "",
                            "nije pronađeno: " + razlog])
                n += 1
                continue
            sn = napravi_snimak(podaci)
            vlasnici, tereti = vlasnici_tereti(sn)
            vl_obj = vlasnici_objekata(sn)
            for d in sn["delovi"]:
                obj = [o for o in sn["objekti"] if d[0] in o[0].split(", ")]
                imena = {(("%s %s" % (o[1], o[2])).strip()) for o in obj}
                pos = [x for x in sn["posebni"] if x[0] in imena]
                w.writerow([sn["opstina"] or z["opstina"], sn["ko"] or z["ko"], z["broj"], d[0], d[1], d[2], d[3],
                            d[4], d[5],
                            "; ".join("%s %s, %s m², %s" % (o[1], o[2], o[4], o[5]) for o in obj),
                            "; ".join("%s %s m²" % (x[5], x[6]) for x in pos),
                            vlasnici, tereti, vl_obj, "pronađeno"])
                n += 1
    return n


# ----------------------------------------------------------------------
# Windows: obavestenje, taskbar, ikonica
# ----------------------------------------------------------------------
APP_ID = "advokatcolja.asistentkatastar"

_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml($env:AP_TOAST_XML)
$t = New-Object Windows.UI.Notifications.ToastNotification $x
try {
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:AP_TOAST_ID).Show($t)
} catch {
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
        '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show($t)
}
"""


def registruj_aplikaciju():
    if os.name != "nt":
        return
    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\AppUserModelId\\" + APP_ID)
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Asistent KATASTAR")
        png = putanja_ikone(png=True)
        if png:
            winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, png)
        winreg.CloseKey(k)
    except Exception:
        upisi_dnevnik("Registracija za obavestenja nije uspela: " + traceback.format_exc())


def posalji_obavestenje(naslov, redovi):
    if os.name != "nt":
        return
    from xml.sax.saxutils import escape
    import subprocess
    xml = ("<toast><visual><binding template=\"ToastGeneric\">" +
           "".join("<text>%s</text>" % escape(t) for t in [naslov] + list(redovi)[:2]) +
           "</binding></visual></toast>")
    env = dict(os.environ, AP_TOAST_XML=xml, AP_TOAST_ID=APP_ID)
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                      "powershell.exe")
    kod = base64.b64encode(_TOAST_PS.encode("utf-16-le")).decode("ascii")

    def radi():
        try:
            r = subprocess.run([ps if os.path.exists(ps) else "powershell.exe", "-NoProfile", "-NonInteractive",
                                "-ExecutionPolicy", "Bypass", "-EncodedCommand", kod],
                               env=env, capture_output=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            if r.returncode:
                upisi_dnevnik("Obavestenje nije prikazano: " + r.stderr.decode("utf-8", "replace")[-500:])
        except Exception as e:
            upisi_dnevnik("Obavestenje nije prikazano: %r" % (e,))
    threading.Thread(target=radi, daemon=True).start()


def prozor_u_fokusu(root):
    """Da li radis u programu (Windows: prozor u prvom planu je neki od prozora ovog programa)."""
    if os.name == "nt":
        import ctypes
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return False
        pid = ctypes.c_ulong(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == os.getpid()
    return root.focus_displayof() is not None


def zvuk_upozorenja(root):
    if os.name == "nt":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
        except Exception:
            pass
    try:
        root.bell()
    except tk.TclError:
        pass


def treperi_na_taskbaru(root):
    if os.name != "nt":
        return
    import ctypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                    ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]
    fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), int(root.wm_frame(), 16), 0x03 | 0x0C, 0, 0)
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))


def postavi_ostru_ikonu(root, ikona):
    """Windows: Tk predaje ikonicu od 32 px koju taskbar pri 125% razvlaci na 40 px (mutno).
    Ovde se iz .ico ucitava tacna velicina za tvoje skaliranje i predaje prozoru."""
    try:
        import ctypes
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics") as k:
                dpi = int(winreg.QueryValueEx(k, "AppliedDPI")[0])
        except OSError:
            dpi = 96
        root.update_idletasks()
        hwnd = int(root.wm_frame(), 16)
        u = ctypes.windll.user32
        u.LoadImageW.restype = ctypes.c_void_p
        u.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_uint]
        u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
        root._ikone = []                            # handle-ovi moraju da zive dok radi program
        for vrsta, osnova in ((1, 32), (0, 16)):    # ICON_BIG (taskbar, Alt+Tab), ICON_SMALL (naslov)
            n = max(osnova, int(round(osnova * dpi / 96.0)))
            h = u.LoadImageW(None, ikona, 1, n, n, 0x10)      # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                root._ikone.append(h)
                u.SendMessageW(hwnd, 0x80, vrsta, h)          # WM_SETICON
    except Exception:
        pass


LOSA_VERZIJA = "losa_verzija.txt"        # v34: u rezerve/ - commit koji nije prošao probni start (ne preuzima se)
NOVA_VERZIJA = "nova_verzija.txt"        # v34: u rezerve/ - dok nova verzija ne proradi: commit na koji se vraća


def mreza_dostupna(host="github.com", port=443, cekaj=3):
    """v34: brza provera pre git-a (bez mreže program je čekao do 25 s)."""
    import socket
    try:
        socket.create_connection((host, port), timeout=cekaj).close()
        return True
    except OSError:
        return False


def _git_komanda(cekaj=25):
    kw = {"cwd": DIR, "capture_output": True, "timeout": cekaj, "env": dict(os.environ, GIT_TERMINAL_PROMPT="0")}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

    def git(*a, bajtovi=False):
        # utf-8 izricito: na Windows-u je podrazumevano cp1250/cp1252, a cirilica u kodu tada ne moze da se procita
        if bajtovi:
            return subprocess.run(["git"] + list(a), **kw)
        return subprocess.run(["git"] + list(a), encoding="utf-8", errors="replace", **kw)
    return git


def probni_start(putanja_programa, cekaj=120):
    """v34: nova verzija se pre pravog pokretanja pokrene na KOPIJI podataka (baza, šifarnik, uzorci captche) u
    privremenom folderu: učita se, otvori prozor (nevidljiv) i zatvori. Tako se pre prvog pravog pokretanja vidi i
    greška u kodu i greška u promeni šeme baze, a pravi podaci ostaju netaknuti. Vraća (True, '') ili (False, razlog)."""
    privremeni = tempfile.mkdtemp(prefix="katastar_proba_")
    try:
        if os.path.exists(DB_PATH):
            izvor, c = sqlite3.connect(DB_PATH), sqlite3.connect(os.path.join(privremeni, "katastar.db"))
            with c:
                izvor.backup(c)
            izvor.close()
            c.close()
        for ime in ("sifarnik_ko.json", "uzorci_captcha.json"):
            if os.path.exists(os.path.join(DIR, ime)):
                shutil.copy(os.path.join(DIR, ime), privremeni)
        kw = {"capture_output": True, "timeout": cekaj, "cwd": privremeni,
              "env": dict(os.environ, KATASTAR_DIR=privremeni)}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000
        r = subprocess.run([sys.executable, putanja_programa, "--bez-azuriranja", "--probni-start"], **kw)
        if r.returncode != 0:
            izlaz = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()
            return False, "probni start nije prošao (kod %d): %s" % (r.returncode, izlaz[-800:])
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "probni start nije završen za %d s" % cekaj
    except Exception:
        return False, "probni start: " + traceback.format_exc()[-800:]
    finally:
        shutil.rmtree(privremeni, ignore_errors=True)


def vrati_staru_verziju(stari, razlog, git=None):
    """v34: nova verzija ne radi -> nazad na commit `stari`, a nova se pamti kao loša (ne preuzima se ponovo dok na
    GitHub-u ne bude novija). git reset dira samo fajlove programa: baza, rezerve, zadaci, izvodi i PDF nisu u Git-u."""
    git = git or _git_komanda()
    novi = git("rev-parse", "HEAD").stdout.strip()
    r = git("reset", "--hard", "-q", stari)
    try:
        os.makedirs(REZERVE_DIR, exist_ok=True)
        with open(os.path.join(REZERVE_DIR, LOSA_VERZIJA), "w", encoding="utf-8") as f:
            f.write(novi + "\n")
        if os.path.exists(os.path.join(REZERVE_DIR, NOVA_VERZIJA)):
            os.remove(os.path.join(REZERVE_DIR, NOVA_VERZIJA))
    except OSError:
        pass
    upisi_dnevnik("GitHub: nova verzija %s NE RADI, vraćena %s (%s): %s" % (
        novi[:8], stari[:8], "uspelo" if r.returncode == 0 else "NIJE USPELO: " + r.stderr.strip()[:200], razlog))
    return r.returncode == 0


def azuriraj_sa_githuba():
    """v33: ako je folder programa povezan sa GitHub-om (.git), preuzima novu verziju. Ako je stigla nova verzija,
    stari asistent_katastar.py ide u rezerve/ i program se ponovo pokrece. Baza, rezerve, zadaci, izvodi i PDF nisu
    u repozitorijumu, pa ih pull ne dira. Bez mreze, bez Git-a ili kod lokalnih izmena: radi postojeca verzija
    (razlog u dnevnik.txt).
    v34: pre pokretanja nova verzija prolazi probni start na kopiji podataka; ako ne prođe, vraća se stara, a nova se
    ne preuzima ponovo dok na GitHub-u ne bude novija. Bez mreže se ne čeka (provera za 3 s)."""
    if "--bez-azuriranja" in sys.argv or os.environ.get("KATASTAR_TEST"):
        return False
    if not os.path.isdir(os.path.join(DIR, ".git")):
        return False
    if not mreza_dostupna():
        upisi_dnevnik("GitHub: nema mreže, radi postojeća verzija")
        return False
    git = _git_komanda()
    try:
        stari = git("rev-parse", "HEAD").stdout.strip()
        r = git("fetch", "-q", "origin", "main")
        if r.returncode != 0:
            upisi_dnevnik("GitHub: nova verzija nije preuzeta: %s" % (r.stderr or r.stdout).strip()[:500])
            return False
        vrh = git("rev-parse", "origin/main").stdout.strip()
        if not stari or not vrh or vrh == stari:
            return False
        try:
            with open(os.path.join(REZERVE_DIR, LOSA_VERZIJA), encoding="utf-8") as f:
                losa = f.read().strip()
        except OSError:
            losa = ""
        if vrh == losa:
            return False                      # već probana i nije radila; čeka se novija
        r = git("merge", "--ff-only", "-q", "origin/main")
        if r.returncode != 0:
            upisi_dnevnik("GitHub: nova verzija nije preuzeta: %s" % (r.stderr or r.stdout).strip()[:500])
            return False
        novi = git("rev-parse", "HEAD").stdout.strip()
        stari_kod = git("show", "%s:asistent_katastar.py" % stari, bajtovi=True)
        if stari_kod.returncode == 0:
            os.makedirs(REZERVE_DIR, exist_ok=True)
            with open(os.path.join(REZERVE_DIR, "asistent_katastar_%s.py" % stari[:8]), "wb") as f:
                f.write(stari_kod.stdout)
        program = os.path.join(DIR, "asistent_katastar.py")
        uspelo, razlog = probni_start(program)
        if not uspelo:
            vrati_staru_verziju(stari, razlog, git)
            return False
        os.makedirs(REZERVE_DIR, exist_ok=True)
        with open(os.path.join(REZERVE_DIR, NOVA_VERZIJA), "w", encoding="utf-8") as f:
            f.write(stari + "\n")
        opis = git("log", "--format=%s", "%s..%s" % (stari, novi)).stdout.strip().replace("\n", "; ")
        upisi_dnevnik("GitHub: preuzeta nova verzija %s (%s), probni start prošao" % (novi[:8], opis[:300]))
        subprocess.Popen([sys.executable, program, "--bez-azuriranja"] + sys.argv[1:], cwd=DIR)
        return True
    except Exception:
        upisi_dnevnik("GitHub: azuriranje: " + traceback.format_exc())
        return False


def nova_verzija_ne_radi():
    """v34: prvo pravo pokretanje nove verzije je puklo -> nazad na prethodnu i ponovo pokreni. True ako je vraćeno."""
    put = os.path.join(REZERVE_DIR, NOVA_VERZIJA)
    if os.environ.get("KATASTAR_TEST") or "--probni-start" in sys.argv or not os.path.exists(put):
        return False
    try:
        with open(put, encoding="utf-8") as f:
            stari = f.read().strip()
        if stari and vrati_staru_verziju(stari, "greška pri prvom pokretanju"):
            subprocess.Popen([sys.executable, os.path.join(DIR, "asistent_katastar.py"), "--bez-azuriranja"], cwd=DIR)
            return True
    except Exception:
        upisi_dnevnik("GitHub: vraćanje stare verzije: " + traceback.format_exc())
    return False


def nova_verzija_radi():
    """v34: program se pokrenuo bez greške - nova verzija je prihvaćena."""
    try:
        os.remove(os.path.join(REZERVE_DIR, NOVA_VERZIJA))
    except OSError:
        pass


def main():
    proba = "--probni-start" in sys.argv          # v34: samo učitaj, otvori nevidljiv prozor i zatvori (vidi probni_start)
    if not proba and azuriraj_sa_githuba():
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    if not proba:
        registruj_aplikaciju()
    ukljuci_ostar_prikaz()           # pre prozora: bez ovoga je na uvecanom ekranu sve mutno
    greske = []
    try:
        root = tk.Tk()
        if proba:
            root.withdraw()
            try:
                root.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            root.report_callback_exception = lambda *a: greske.append("".join(traceback.format_exception(*a)))
        ikona = putanja_ikone()
        if ikona:
            try:
                root.iconbitmap(default=ikona)
            except tk.TclError:
                pass
        App(root)
        if proba:
            root.withdraw()
            root.after(1500, root.destroy)
            root.mainloop()
            if greske:
                sys.stderr.write(greske[0])
                sys.exit(3)
            return
        if ikona:
            postavi_ostru_ikonu(root, ikona)
        root.after(20000, nova_verzija_radi)
        root.mainloop()
    except Exception:
        if proba:
            raise
        upisi_dnevnik("GRESKA PRI POKRETANJU:\n" + traceback.format_exc())
        if nova_verzija_ne_radi():
            return
        raise


if __name__ == "__main__":
    main()
