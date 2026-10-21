# -*- coding: utf-8 -*-
"""Simulirani eKatastar sa pravim oblicima odgovora (HTML i UpdatePanel delte iz Dejanovih HAR snimaka)."""
import http.server
import json
import os
import random
import re
import sys
import threading
import urllib.parse
import uuid

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fix")
rd = lambda f: open(os.path.join(D, f), encoding="utf-8", newline="").read()
CAPTCHE = {"b200c5be": "v0a8h", "bc8b2524": "SDYYP", "31e71c1e": "ndZaS", "617fc8be": "r75NZ", "2879ffa5": "ftfpw"}
SVG = {k: rd(k + ".svg") for k in CAPTCHE}
STANJE = {"vlasnik": "ПЕТРОВИЋ ПЕТАР", "teret": "", "zahtevi": [], "429": 0, "nep_captcha": False,
          "captcha_red": None, "nep_upiti": [], "stan_vlasnik": "НИКОЛИЋ МИЛИЦА", "napomena": "",
          "stanova": 0, "nep_kasni": 0.0, "nep_sesija": False,
          # v22: promene pojedinacnih stanova velike zgrade {broj stana: vrednost}, i stanovi kojih vise nema
          "vlasnik_stana": {}, "povrsina_stana": {}, "nacin_stana": {}, "bez_stana": set()}
# v21: STANJE["nep_sesija"] = True - nepID vazi samo u sesiji koja je videla rezultat (SESIJE.clear() = istekle)
# v20: zgrada sa mnogo stanova (kao parcela 13662 KO Земун, 193 stavke): STANJE["stanova"] = N na parceli 10383
# nepID iz fiksnih rezultata -> koja prava stranica "Podaci o nepokretnosti" (iz Dejanovih HAR snimaka 07.10.2026)
NEP_VRSTA = {"g+3wBfRKrlQ=": "zemljiste", "aomZVVU7jzg=": "zemljiste", "p028YfJ2E8w=": "zgrada",
             "bzBIIaV8NWA=": "zgrada", "YnIOQAvrE34=": "poseban", "2oYMqzJeqjQ=": "poseban"}
BROJ_NEP = [0]


def nepokretnost(vrsta):
    """Prava stranica sa zamenjenim vlasnikom, teretom i napomenom; vreme izvoda i azurnost se menjaju svaki put."""
    import datetime
    t = rd("nep_%s.html" % vrsta)
    BROJ_NEP[0] += 1
    sad = datetime.datetime.now() + datetime.timedelta(minutes=BROJ_NEP[0])
    t = t.replace("7.10.2026. 17:12:58", "%d.%d.%d. %s" % (sad.day, sad.month, sad.year, sad.strftime("%H:%M:%S")))
    t = t.replace("06.10.2026. 16:18", sad.strftime("%d.%m.%Y. %H:%M"))
    t = t.replace("ПЕТРОВИЋ ПЕТАР", STANJE["vlasnik"]).replace("НИКОЛИЋ МИЛИЦА</span>", STANJE["stan_vlasnik"] + "</span>")
    t = re.sub(r'__VIEWSTATE" value="[^"]*"', '__VIEWSTATE" value="%s"' % uuid.uuid4().hex, t)
    if STANJE["teret"]:
        teret = ('<table><tbody class="print_group"><tr><td class="print_form_item_v"><strong>Опис:</strong></td>'
                 '<td class="print_form_item_v"><span>%s</span></td></tr></tbody></table>' % STANJE["teret"])
        t = t.replace('<p class="body_text">*** Нема терета ***</p>', teret, 1)
    if STANJE["napomena"]:
        nap = ('<tbody class="print_group"><tr><td class="print_form_item_v"><strong>Опис:</strong></td>'
               '<td class="print_form_item_v"><span>%s</span></td></tr></tbody>' % STANJE["napomena"])
        t = re.sub(r'(Напомене на парцели.*?<table[^>]*>)', lambda m: m.group(1) + nap, t, count=1, flags=re.S)
    return t
SESIJE = {}
# pretraga po adresi (oblik stranica iz Dejanovog HAR-a 08.10.2026: FindAdresa.aspx, PretragaUlica, FindAdresaResult.aspx)
ULICE = {"70106": [("БЕОГРАД (ВОЖДОВАЦ), ВОЈВОДЕ СТЕПЕ", "791106000101"),
                   ("БЕОГРАД (ВОЖДОВАЦ), ВОЈИСЛАВА ИЛИЋА", "791106000102"),
                   ("БЕОГРАД (ВОЖДОВАЦ), УСТАНИЧКА", "791106000103")],
         "70254": [("БЕОГРАД (ЧУКАРИЦА), ГРУЈЕ МИШКОВИЋА", "791113003725"),
                   ("БЕОГРАД (ЧУКАРИЦА), ЈАНКА МИШИЋА", "791113033258")]}
# (ID ulice, kucni broj) -> delovi parcela na adresi: (KO, broj parcele, deo)
ADRESE = {("791106000101", "5"): [("ВОЖДОВАЦ", "4415", "1")],
          ("791106000101", "7"): [("ВОЖДОВАЦ", "4415", "1"), ("ВОЖДОВАЦ", "4415", "2"), ("КУМОДРАЖ", "10383", "1")],
          ("791106000102", "3"): [("ЗЕМУН", "10383", "1")],
          ("791113003725", "5"): [("ЧУКАРИЦА", "10572/2", "2")]}
_LAT = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e", "ж": "z", "з": "z",
                      "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o",
                      "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "c", "у": "u", "ф": "f", "х": "h", "ц": "c",
                      "ч": "c", "џ": "dz", "ш": "s", "š": "s", "č": "c", "ć": "c", "ž": "z", "đ": "dj"})


def ulice(opstina, prefiks):
    """Kao sajt: ulice cija neka rec pocinje upisanim tekstom (cirilica ili latinica)."""
    p = prefiks.lower().translate(_LAT)
    return [(n, i) for n, i in ULICE.get(str(opstina), [])
            if any(r.startswith(p) for r in re.split(r"[\s(),]+", n.split(", ", 1)[-1].lower().translate(_LAT)))]


def rezultat_adrese(opstina, kljuc):
    html = rd("adresa_rez.html")
    m = re.search(r'(<table[^>]*id="ContentPlaceHolder1_Parcele".*?</tr>)(<tr class="selected">.*?</tr>)(\s*</table>)',
                  html, re.S)
    red = m.group(2)
    redovi = []
    for n, (ko, broj, deo) in enumerate(ADRESE[kljuc]):
        r = red.replace(">5</td>", ">%s</td>" % kljuc[1]).replace(">ЧУКАРИЦА</td>", ">%s</td>" % ko)
        r = r.replace("10572/2", broj).replace('style="width:60px;">2</td>', 'style="width:60px;">%s</td>' % deo)
        r = r.replace("ctl02", "ctl%02d" % (n + 2)).replace("Imagebutton1_0", "Imagebutton1_%d" % n)
        if n:
            r = r.replace('class="selected"', 'class="%s"' % ("alternate" if n % 2 else "normal"))
        redovi.append(r)
    html = html[:m.start(2)] + "".join(redovi) + html[m.end(2):]
    naziv = {"70106": "ВОЖДОВАЦ", "70254": "ЧУКАРИЦА"}.get(str(opstina), "")
    return html.replace('lblOpstinaNaziv">ЧУКАРИЦА<', 'lblOpstinaNaziv">%s<' % naziv)


def delta(delovi):
    return "".join("%d|%s|%s|%s|" % (len(s), t, i, s) for t, i, s in delovi)


def parsiraj(t):
    out, i = [], 0
    while i < len(t):
        j = t.find("|", i); n = int(t[i:j]); k = t.find("|", j + 1); m = t.find("|", k + 1)
        out.append((t[j + 1:k], t[k + 1:m], t[m + 1:m + 1 + n])); i = m + 2 + n
    return out


def zameni_svg(t, svg):
    return re.sub(r"<svg.*?</svg>", lambda m: svg, t, count=1, flags=re.S)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ses(self):
        c = self.headers.get("Cookie", "")
        m = re.search(r"ASP\.NET_SessionId=(\w+)", c)
        if m and m.group(1) in SESIJE:
            return m.group(1), False
        sid = uuid.uuid4().hex[:12]
        SESIJE[sid] = {}
        return sid, True

    def _posalji(self, telo, tip="text/html; charset=utf-8", sid=None, nova=False, kod=200):
        b = telo.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(b)))
        if nova:
            self.send_header("Set-Cookie", "ASP.NET_SessionId=%s; path=/; HttpOnly" % sid)
        self.end_headers()
        self.wfile.write(b)

    def _nova_captcha(self, s):
        red = STANJE.get("captcha_red")
        k = red.pop(0) if red else random.choice(list(CAPTCHE))
        s["captcha"] = k
        return SVG[k]

    def do_GET(self):
        sid, nova = self._ses()
        s = SESIJE[sid]
        u = urllib.parse.urlparse(self.path)
        STANJE["zahtevi"].append(("GET", u.path.split("/")[-1], u.query))
        if STANJE["429"] > 0:
            STANJE["429"] -= 1
            return self._posalji("Too many", sid=sid, nova=nova, kod=429)
        ime = u.path.split("/")[-1]
        if ime == "PublicAccess.aspx":
            return self._posalji(rd("public.html"), sid=sid, nova=nova)
        if ime == "FindParcela.aspx":
            s["ko"] = urllib.parse.parse_qs(u.query).get("KoID", [""])[0]
            return self._posalji(zameni_svg(rd("find.html"), self._nova_captcha(s)), sid=sid, nova=nova)
        if ime == "FindAdresa.aspx":
            s["opstina_adr"] = urllib.parse.parse_qs(u.query).get("OpstinaID", [""])[0]
            return self._posalji(zameni_svg(rd("adresa.html"), self._nova_captcha(s)), sid=sid, nova=nova)
        if ime == "FindAdresaResult.aspx":
            if "adresa" not in s:
                return self._posalji("<html>sesija istekla</html>", sid=sid, nova=nova)
            return self._posalji(rezultat_adrese(s.get("opstina_adr"), s["adresa"]), sid=sid, nova=nova)
        if ime == "FindParcelaResult.aspx":
            if "broj" not in s:
                return self._posalji("<html>sesija istekla</html>", sid=sid, nova=nova)
            s["nep_ok"] = True
            return self._posalji(rezultat(s["broj"]), sid=sid, nova=nova)
        if ime == "NepokretnostProperties.aspx":
            nid = u.query.split("nepID=", 1)[-1]
            STANJE["nep_upiti"].append(nid)
            if STANJE["nep_kasni"]:
                import time
                time.sleep(STANJE["nep_kasni"])
            if STANJE["nep_captcha"]:
                return self._posalji(zameni_svg(rd("find.html"), SVG["b200c5be"]), sid=sid, nova=nova)
            if STANJE["nep_sesija"] and not s.get("nep_ok"):
                return self._posalji("<html><head><title>Грешка</title></head><body><p>Сесија је истекла.</p>"
                                     "</body></html>", sid=sid, nova=nova)
            m = re.match(r"^S(\d+)=$", nid)
            if m:                                # stan iz velike zgrade: vlasnik nosi broj stana
                i = int(m.group(1))
                t = nepokretnost("poseban").replace(STANJE["stan_vlasnik"] + "</span>",
                                                    STANJE["vlasnik_stana"].get(i, "ВЛАСНИК СТАНА %d" % i) + "</span>")
                return self._posalji(t, sid=sid, nova=nova)
            return self._posalji(nepokretnost(NEP_VRSTA.get(nid, "zemljiste")), sid=sid, nova=nova)
        self._posalji("nema", sid=sid, nova=nova, kod=404)

    def do_POST(self):
        sid, nova = self._ses()
        s = SESIJE[sid]
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        telo = self.rfile.read(n).decode("utf-8")
        ime = u.path.split("/")[-1]
        if ime == "PretragaUlica":
            assert u.path.endswith("/FindAdresa.aspx/PretragaUlica"), u.path
            assert self.headers.get("Content-Type", "").startswith("application/json"), self.headers.get("Content-Type")
            j = json.loads(telo)
            assert set(j) == {"prefixText", "count", "contextKey"}, j
            STANJE.setdefault("ulice_upiti", []).append(j)
            d = [json.dumps({"First": n_, "Second": i_}, ensure_ascii=False)
                 for n_, i_ in ulice(j["contextKey"], j["prefixText"])[:j["count"]]]
            return self._posalji(json.dumps({"d": d}, ensure_ascii=False), "application/json; charset=utf-8", sid, nova)
        f = dict(urllib.parse.parse_qsl(telo, keep_blank_values=True))
        STANJE["zahtevi"].append(("POST", ime, {k: v for k, v in f.items() if not k.startswith("__V")}))
        if STANJE["429"] > 0:
            STANJE["429"] -= 1
            return self._posalji('{"error":"Too Many Requests"}', sid=sid, nova=nova, kod=429)
        tip = "text/plain; charset=utf-8"
        if ime == "PublicAccess.aspx":
            assert f.get("__VIEWSTATE"), "nema viewstate"
            assert f.get("__EVENTTARGET") == "ctl00$ContentPlaceHolder1$getOpstinaKO$dropOpstina"
            return self._posalji(rd("public_ko.txt"), tip, sid, nova)
        if ime == "FindParcela.aspx":
            assert self.headers.get("X-MicrosoftAjax") == "Delta=true"
            assert f.get("__VIEWSTATE") and f.get("__EVENTVALIDATION")
            tekst = f.get("ctl00$ContentPlaceHolder1$SVGCaptchaControl$CaptchaText", "")
            broj = f.get("ctl00$ContentPlaceHolder1$txtBrParcele", "")
            ocekivano = CAPTCHE.get(s.get("captcha"))
            if tekst != ocekivano:
                d = parsiraj(rd("find_lose.txt"))
                d = [(t, i, zameni_svg(c, self._nova_captcha(s)) if t == "updatePanel" else c) for t, i, c in d]
                return self._posalji(delta(d), tip, sid, nova)
            if broj not in ("10383", "4415"):
                d = parsiraj(rd("find_lose.txt"))
                out = []
                for t, i, c in d:
                    if t == "updatePanel":
                        c = re.sub(r'(<div id="ContentPlaceHolder1_ValidationSummary1">).*?(</div>)', r"\1\2", c, flags=re.S)
                        c = re.sub(r'(<p class="err-warning">)\s*(</p>)', r"\1Парцела није пронађена.\2", c)
                        c = zameni_svg(c, self._nova_captcha(s))
                    out.append((t, i, c))
                return self._posalji(delta(out), tip, sid, nova)
            s["broj"] = broj
            s["izbor"] = None
            return self._posalji(rd("find_ok.txt"), tip, sid, nova)
        if ime == "FindAdresa.aspx":
            p = "ctl00$ContentPlaceHolder1$"
            assert self.headers.get("X-MicrosoftAjax") == "Delta=true"
            assert f.get("__VIEWSTATE") and f.get("__EVENTVALIDATION")
            assert f.get(p + "ToolkitScriptManager") == p + "UpdatePanel1|" + p + "btnSubmit", f
            assert f.get(p + "btnSubmit") == "Прикажи"
            tekst = f.get(p + "SVGCaptchaControl$CaptchaText", "")
            uid = f.get(p + "ucAdresa$hdnUlicaID", "")
            kbr = f.get(p + "ucAdresa$txtKucniBroj", "")
            naziv = f.get(p + "ucAdresa$txtUlica", "")
            if tekst != CAPTCHE.get(s.get("captcha")):
                d = parsiraj(rd("adresa_lose.txt"))
                d = [(t, i, zameni_svg(c, self._nova_captcha(s)) if t == "updatePanel" else c) for t, i, c in d]
                return self._posalji(delta(d), tip, sid, nova)
            poznata = dict(ULICE.get(s.get("opstina_adr", ""), []))
            if naziv not in poznata or poznata[naziv] != uid or (uid, kbr) not in ADRESE:
                out = []
                for t, i, c in parsiraj(rd("adresa_lose.txt")):
                    if t == "updatePanel":
                        c = re.sub(r'(<div id="ContentPlaceHolder1_ValidationSummary1">).*?(</div>)', r"\1\2", c, flags=re.S)
                        c = re.sub(r'(<p class="err-warning">)\s*(</p>)', r"\1Нема података за унету адресу.\2", c)
                        c = zameni_svg(c, self._nova_captcha(s))
                    out.append((t, i, c))
                return self._posalji(delta(out), tip, sid, nova)
            s["adresa"] = (uid, kbr)
            return self._posalji(rd("adresa_ok.txt"), tip, sid, nova)
        if ime == "FindParcelaResult.aspx":
            dugme = next((k[:-2] for k in f if k.endswith(".x")), None)
            assert f.get("ctl00$ContentPlaceHolder1$ToolkitScriptManager1", "").endswith(dugme or "#")
            html = rezultat(s.get("broj"), dugme)
            m = re.search(r'(<div id="ContentPlaceHolder1_UpdatePanel1">)(.*?)(<!-- END: Sadržaj -->\s*</div>)', html, re.S)
            sadrzaj = m.group(2) + m.group(3)[:-6]
            d = [("#", "", "1"), ("updatePanel", "ContentPlaceHolder1_UpdatePanel1", sadrzaj),
                 ("hiddenField", "__VIEWSTATE", "VS" + uuid.uuid4().hex), ("hiddenField", "__EVENTVALIDATION", "EV1")]
            return self._posalji(delta(d), tip, sid, nova)
        self._posalji("nema", sid=sid, nova=nova, kod=404)


def rezultat(broj, dugme=None):
    """Rezultat pretrage; izbor drugog dela parcele 10383 vraca drugi objekat (garaza) i dva posebna dela."""
    html = rd("rez_%s.html" % broj)
    if broj == "10383" and STANJE.get("stanova") and not dugme:
        m = re.search(r'(id="ContentPlaceHolder1_GridView3".*?</tr>)(\s*<tr class="normal">.*?</tr>)', html, re.S)
        red = m.group(2)
        redovi = []
        for i in range(1, STANJE["stanova"] + 1):
            if i in STANJE["bez_stana"]:
                continue
            r = red.replace("YnIOQAvrE34=", "S%03d=" % i).replace(
                '220px;">106<', '220px;">%s<' % STANJE["povrsina_stana"].get(i, 40 + i % 50))
            if i in STANJE["nacin_stana"]:
                r = r.replace(">СТАН<", ">%s<" % STANJE["nacin_stana"][i])
            r = re.sub(r'(<td[^>]*>)1(</td><td[^>]*>)1(</td><td[^>]*>)1(</td>)', r"\g<1>%d\g<2>1\g<3>%d\g<4>" % (i, i), r,
                       count=1)
            if i % 2 == 0:
                r = r.replace('class="normal"', 'class="alternate"')
            redovi.append(r)
        html = html[:m.start(2)] + "".join(redovi) + html[m.end(2):]
    if broj == "10383" and STANJE.get("dodat_deo"):
        html = re.sub(r">(\s*)121(\s*)</td>", r">\g<1>125\g<2></td>", html)
    if dugme and "GridView1$ctl03" in dugme:
        html = html.replace("ПОРОДИЧНА СТАМБЕНА ЗГРАДА<", "ПОМОЋНА ЗГРАДА - ГАРАЖА<").replace(">203</td><td align=\"left\" valign=\"top\" style=\"width:200px;\">", ">18</td><td align=\"left\" valign=\"top\" style=\"width:200px;\">")
        html = html.replace(">СТАН<", ">ГАРАЖНИ ПРОСТОР<")
    if dugme and "GridView1$ctl04" in dugme:
        # kao na sajtu za neke delove: objekat nije izabran i posebni delovi se ne vide dok se objekat ne klikne
        html = html.replace('class="selected"', "")
        html = re.sub(r'(id="ContentPlaceHolder1_GridView3".*?</tr>).*?(</table>)', r"\1\2", html, count=1, flags=re.S)
        html = html.replace("ПОРОДИЧНА СТАМБЕНА ЗГРАДА<", "СТАМБЕНА ЗГРАДА ДЕО 3<")
    return html


def pokreni(port=0):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    s = pokreni(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print("mock na portu", s.server_address[1])
    threading.Event().wait()
