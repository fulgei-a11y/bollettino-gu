"""Prova del lettore del Parlamento su pagine vere salvate in tests/fixtures (python -I tests/test_parlamento.py)."""
import os, sys, json, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import parlamento as P

fx = lambda n: open(os.path.join(HERE, "fixtures", n), encoding="utf-8").read()
d = P.parse_dossier(fx("dossier.html"))
assert len(d) == 4, d
assert d[1]["organo"] == "Studi - Attività produttive" and d[1]["materia"] == "Economico"
assert d[1]["tipo"] == "Elementi per l'esame in Assemblea"
assert d[1]["titolo"].endswith("centri storici"), d[1]["titolo"]
assert d[2]["materia"] == "Giustizia" and d[2]["data"] == "2026-10-06"
assert d[0]["id"] == "d-OCD18-23715" and d[0]["link"].startswith("https://temi.camera.it/leg19/dossier/")
c = P.parse_commissione(fx("commissione_02.html"), P.COMMISSIONI[0])
assert len(c) == 7, len(c)
assert c[0]["titolo"] == "C. 2720 - Memoria UCPI" and c[0]["data"] == "2026-10-07" and c[0]["ora"] == "14:55"
assert c[0]["tipo"] == "Memoria" and c[0]["seduta"] == "Seduta del 07/10/2026"
assert c[1]["titolo"] == "C. 2880 Governo - Contributo scritto CNOP" and c[1]["tipo"] == "Contributo scritto"
assert "%20" in c[1]["link"] and c[1]["atto"] == "C. 2880"
assert c[-1]["atto"] == "A.G. 419" and c[-1]["link"].endswith(".docx")
assert "Ore 10.15" in c[4]["contesto"] and c[4]["seduta"] == "Seduta del 30/09/2026"

# due controlli di seguito: il primo registra, il secondo trova solo la novità
tmp = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(tmp)
try:
    P.PAUSE = 0; P.BASELINE_DAYS = 10000
    src = lambda extra=[]: [("dossier", "Dossier", "u", lambda: d + extra),
                            ("comm2", "II Giustizia", "u", lambda: c)]
    P.main(src())
    out = json.load(open("data/parlamento.json"))
    assert len(out["voci"]) == 11 and all(v.get("iniziale") for v in out["voci"]), out["voci"][:1]
    assert out["controlli"][0]["nuovi"] == 0
    nuovo = dict(d[0], id="d-OCD18-99999", titolo="Dossier nuovissimo")
    P.main(src([nuovo]))
    out = json.load(open("data/parlamento.json"))
    assert out["controlli"][0]["nuovi"] == 1
    assert out["voci"][0]["id"] == "d-OCD18-99999" and not out["voci"][0].get("iniziale")
    # una fonte che non risponde: errore riportato, le voci restano
    def boom(): raise RuntimeError("timeout")
    P.main([("dossier", "Dossier", "u", boom), ("comm2", "II Giustizia", "u", lambda: c)])
    rep = json.load(open("run_report_parlamento.json"))
    assert rep["avvisi"] and not rep["errori"] and len(json.load(open("data/parlamento.json"))["voci"]) == 12
    # nessuna fonte risponde: è un problema da segnalare
    try:
        P.main([("dossier", "Dossier", "u", boom)]); raise AssertionError("doveva fallire")
    except SystemExit as e:
        assert "1 fonti" in str(e)
    assert json.load(open("run_report_parlamento.json"))["errori"]
finally:
    os.chdir(cwd); shutil.rmtree(tmp)
print("OK: tutte le prove del lettore del Parlamento superate")
