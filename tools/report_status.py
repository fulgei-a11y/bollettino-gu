"""
Riassume l'esito del controllo automatico e scrive data/status.json, letto dal sito per la scritta
"Aggiornato alle…" e per l'avviso in caso di problemi.

Legge gli esiti dei passaggi del workflow (variabili *_OUTCOME) e i run_report_*.json scritti dagli
script. Se qualcosa non va scrive report.md (testo dell'avviso su GitHub) e problem=true in
GITHUB_OUTPUT. Solo libreria standard: funziona anche se l'installazione delle dipendenze è fallita.
"""
import os
import re
import json
import datetime as dt
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
DATA = "data"
STEPS = [("SETUP_OUTCOME", "Preparazione (Python e dipendenze)"),
         ("GEN_OUTCOME", "Analisi della Gazzetta"),
         ("AUDIO_OUTCOME", "Lettura audio"),
         ("PARL_OUTCOME", "Novità dal Parlamento"),
         ("EXTRAS_OUTCOME", "Archivio, ricerca e scadenzario")]
REPORTS = ["run_report_generate.json", "run_report_audio.json", "run_report_parlamento.json",
           "run_report_extras.json"]
FIXED_HOLIDAYS = {(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)}


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def previous_publication_day(today):
    d = today - dt.timedelta(days=1)
    while d.weekday() == 6 or (d.month, d.day) in FIXED_HOLIDAYS:
        d -= dt.timedelta(days=1)
    return d


def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    today = now.astimezone(ROME).date()
    problems, warnings = [], []

    for env, label in STEPS:
        outcome = os.environ.get(env, "")
        if outcome and outcome not in ("success", "skipped"):
            esito = {"failure": "errore", "cancelled": "annullato"}.get(outcome, outcome)
            problems.append(f"Il passaggio «{label}» è terminato con: {esito}.")

    reports = {}
    for name in REPORTS:
        r = read_json(name)
        if r:
            reports[name] = r
            problems += r.get("errori") or []
            warnings += r.get("avvisi") or []

    gen = reports.get("run_report_generate.json", {})
    if gen and not gen.get("feed_rss"):
        warnings.append("Il feed RSS della Gazzetta non ha risposto: il numero dell'edizione è stato stimato.")

    # l'edizione del giorno di pubblicazione precedente deve essere completa
    prev = previous_publication_day(today)
    d = read_json(os.path.join(DATA, f"{prev.isoformat()}.json"))
    if d is None:
        problems.append(f"Manca del tutto l'edizione del {prev.strftime('%d/%m/%Y')}.")
    elif d.get("stato") == "non_disponibile" or not d.get("atti"):
        problems.append(f"L'edizione del {prev.strftime('%d/%m/%Y')} non risulta ancora elaborata "
                        f"(stato: {d.get('stato')}, atti letti: {len(d.get('atti') or [])}).")

    old = read_json(os.path.join(DATA, "status.json"), {}) or {}
    ok = not problems
    index = read_json(os.path.join(DATA, "index.json"), []) or []
    status = {
        "ultimoControllo": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ultimoSuccesso": now.strftime("%Y-%m-%dT%H:%M:%SZ") if ok else old.get("ultimoSuccesso", ""),
        "ok": ok,
        "problemi": problems,
        "avvisi": warnings,
        "ultimaEdizione": next((e["date"] for e in index if e.get("stato") not in ("non_disponibile",)), ""),
        "elaborate": gen.get("elaborate", []),
        "audioMB": reports.get("run_report_extras.json", {}).get("audio_mb"),
        "esecuzione": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
                       f"{os.environ['GITHUB_RUN_ID']}") if os.environ.get("GITHUB_RUN_ID") else "",
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    when = now.astimezone(ROME).strftime("%d/%m/%Y alle %H:%M")
    if ok:
        body = f"✅ Controllo del {when} riuscito."
    else:
        body = "\n".join([
            f"Il controllo automatico del {when} (ora italiana) non è andato a buon fine.", "",
            "**Cosa è successo**", *[f"- {p}" for p in problems], "",
            *([f"**Avvisi**", *[f"- {w}" for w in warnings], ""] if warnings else []),
            f"Dettagli dell'esecuzione: {status['esecuzione']}" if status["esecuzione"] else "", "",
            "Il controllo successivo riproverà da solo. Per rifarlo subito: scheda *Actions* → "
            "*Aggiornamento Automatico Bollettino GU* → *Run workflow*.",
            "Questo avviso si chiude automaticamente al primo controllo riuscito.",
        ])
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(body + "\n")
    print(body)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"problem={'false' if ok else 'true'}\n")


if __name__ == "__main__":
    main()
