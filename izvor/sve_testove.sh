#!/bin/bash
# svi testovi: :98 (100%), pa :97 (150%); izlaz u out_<ime>.txt
# v34: python po izboru (PYTHON=...), Xvfb se podiže sam ako ne radi, izlazni kod 1 ako ijedan test nije prošao
# (za GitHub Actions); KRATKO=1 preskače ponavljanje na 150%.
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" napravi.py || exit 1
for d in 98:1600x1000 97:2880x1620 96:1920x1080 95:1366x768; do   # :96 i :95 za test_raspored
  n="${d%%:*}"
  if [ ! -e "/tmp/.X11-unix/X$n" ]; then
    Xvfb ":$n" -screen 0 "${d#*:}x24" >/dev/null 2>&1 &
    sleep 1
  fi
done
LOSE=0
proveri() {   # ime_izlaza opis
  local r
  r="$(grep -a 'UKUPNO GRESAKA' "$1" | tail -1)"
  echo "$2: ${r:-NIJE ZAVRSEN}"
  [ "$r" = "UKUPNO GRESAKA: 0" ] || { LOSE=1; tail -25 "$1"; }
}
for t in test_prati_celu test_sveze test_meni_liste test_skrol test_pracenje_stavke test_izbor test_nepokretnosti test_zamke test_logika test_grupe test_panel test_pdf test_prozor test_adresa test_zadaci test_azuriranje test_baza test_sumnjivo; do
  DISPLAY=:98 timeout 900 "$PY" $t.py > out_$t.txt 2>&1
  proveri out_$t.txt "$t"
done
env -u DISPLAY timeout 900 "$PY" test_raspored.py > out_test_raspored.txt 2>&1
proveri out_test_raspored.txt test_raspored
if [ -z "$KRATKO" ]; then
  for t in test_prati_celu test_sveze test_skrol test_pracenje_stavke test_izbor test_prozor test_adresa test_zadaci; do
    DISPLAY=:97 TEST_UVECANJE=1.5 timeout 900 "$PY" $t.py > out_${t}_150.txt 2>&1
    proveri out_${t}_150.txt "$t 150%"
  done
fi
echo KRAJ
exit $LOSE
