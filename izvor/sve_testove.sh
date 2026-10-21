#!/bin/bash
# svi testovi: :98 (100%), pa :97 (150%); izlaz u out_<ime>.txt
cd "$(dirname "$0")"
for t in test_prati_celu test_sveze test_meni_liste test_skrol test_pracenje_stavke test_izbor test_nepokretnosti test_zamke test_logika test_grupe test_panel test_pdf test_prozor test_adresa test_zadaci; do
  DISPLAY=:98 timeout 900 /usr/bin/python3.12 $t.py > out_$t.txt 2>&1
  echo "$t: $(grep -a 'UKUPNO GRESAKA' out_$t.txt | tail -1)"
done
env -u DISPLAY timeout 900 /usr/bin/python3.12 test_raspored.py > out_test_raspored.txt 2>&1
echo "test_raspored: $(grep -a 'UKUPNO GRESAKA' out_test_raspored.txt | tail -1)"
for t in test_prati_celu test_sveze test_skrol test_pracenje_stavke test_izbor test_prozor test_adresa test_zadaci; do
  DISPLAY=:97 TEST_UVECANJE=1.5 timeout 900 /usr/bin/python3.12 $t.py > out_${t}_150.txt 2>&1
  echo "$t 150%: $(grep -a 'UKUPNO GRESAKA' out_${t}_150.txt | tail -1)"
done
echo KRAJ
