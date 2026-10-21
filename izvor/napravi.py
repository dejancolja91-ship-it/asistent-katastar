# Sastavlja program: izvor.py + opstine.json + seme_min.json -> asistent_katastar.py (u izvor/ za testove i u
# glavnom folderu, koji preuzima Dejanov racunar). Pokreni iz foldera izvor: python napravi.py
import os
D = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(D, 'izvor.py'), encoding='utf-8').read()
s = s.replace('__OPSTINE__', open(os.path.join(D, 'opstine.json'), encoding='utf-8').read()).replace(
    '__SEME__', open(os.path.join(D, 'seme_min.json'), encoding='utf-8').read())
for cilj in (os.path.join(D, 'asistent_katastar.py'), os.path.join(D, '..', 'asistent_katastar.py')):
    open(cilj, 'w', encoding='utf-8').write(s)
