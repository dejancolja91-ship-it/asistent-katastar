# Pravi ikonicu Asistent KATASTAR u stilu Asistent PRO: plava zaobljena plocica (gore svetlija),
# bela parcela sa medjama u perspektivi i beli pin na izabranoj parceli, zelena znacka sa kvacicom.
# Upotreba: python3 ikona.py <folder>  -> asistent_katastar.ico i asistent_katastar_ikona.png
import sys
import os
from PIL import Image, ImageDraw, ImageChops

GORE = (30, 72, 138, 255)
DOLE = (22, 56, 110, 255)
BELA = (255, 255, 255, 255)
SVETLA = (190, 212, 245, 255)
ZELENA = (47, 160, 68, 255)


def crtaj(n, debljina=1.0):
    """Crta na 4x vecem platnu pa smanjuje (glatke ivice). debljina > 1 za male velicine."""
    S = n * 4
    k = S / 256.0
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def p(x, y):
        return (x * k, y * k)

    # plocica: zaobljen kvadrat, gornji deo svetliji (kao kod Asistent PRO)
    r = 44 * k
    d.rounded_rectangle([p(8, 8), p(248, 248)], radius=r, fill=DOLE)
    maska = Image.new("L", (S, S), 0)
    ImageDraw.Draw(maska).rounded_rectangle([p(8, 8), p(248, 248)], radius=r, fill=255)
    pola = Image.new("L", (S, S), 0)
    ImageDraw.Draw(pola).rectangle([p(0, 0), p(256, 124)], fill=255)
    im.paste(GORE, (0, 0), ImageChops.multiply(maska, pola))
    d = ImageDraw.Draw(im)

    # zemljiste u perspektivi (trapez) podeljeno na parcele
    w = max(1.0, 7 * debljina) * k
    A, B, C, D = (40, 196), (216, 196), (184, 128), (72, 128)       # dole levo, dole desno, gore desno, gore levo
    izabrana = [(128, 196), (216, 196), (200, 162), (128, 162)]     # parcela sa pinom (dole desno)
    d.polygon([p(*t) for t in izabrana], fill=SVETLA)
    d.line([p(*A), p(*B), p(*C), p(*D), p(*A)], fill=BELA, width=int(round(w)), joint="curve")
    # medje: jedna popreko (sredina visine), jedna uzduz (ka nedogledu)
    d.line([p(56, 162), p(200, 162)], fill=BELA, width=int(round(w * 0.8)))
    d.line([p(128, 196), p(128, 128)], fill=BELA, width=int(round(w * 0.8)))
    d.line([p(86, 196), p(100, 128)], fill=BELA, width=int(round(w * 0.55)))

    # pin (bela kap) koji stoji na izabranoj parceli
    cx, cy, R = 168, 92, 30
    vrh = (168, 176)
    d.ellipse([p(cx - R, cy - R), p(cx + R, cy + R)], fill=BELA)
    d.polygon([p(cx - R * 0.86, cy + R * 0.5), p(cx + R * 0.86, cy + R * 0.5), p(*vrh)], fill=BELA)
    rr = 12
    d.ellipse([p(cx - rr, cy - rr), p(cx + rr, cy + rr)], fill=GORE)

    # zelena znacka sa kvacicom (isto mesto kao kod Asistent PRO)
    zx, zy, zr = 206, 206, 38
    d.ellipse([p(zx - zr - 5, zy - zr - 5), p(zx + zr + 5, zy + zr + 5)], fill=BELA)
    d.ellipse([p(zx - zr, zy - zr), p(zx + zr, zy + zr)], fill=ZELENA)
    d.line([p(zx - 18, zy + 1), p(zx - 5, zy + 14), p(zx + 19, zy - 12)], fill=BELA,
           width=int(round(max(1.0, 9 * debljina) * k)), joint="curve")
    return im.resize((n, n), Image.LANCZOS)


def main(folder):
    velicine = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256)
    slike = {n: crtaj(n, 1.6 if n <= 24 else 1.25 if n <= 40 else 1.0) for n in velicine}
    slike[256].save(os.path.join(folder, "asistent_katastar_ikona.png"))
    slike[256].save(os.path.join(folder, "asistent_katastar.ico"), sizes=[(n, n) for n in velicine],
                    append_images=[slike[n] for n in velicine if n != 256])
    for n in (16, 24, 32, 48):
        slike[n].save(os.path.join(folder, "_ikona_%d.png" % n))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
