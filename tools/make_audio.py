"""
Crea la lettura audio (voce Paola) delle edizioni che non ce l'hanno ancora.
Per ogni data/AAAA-MM-GG.json senza "audio": scrive il testo da leggere, chiama build_audio.py
e salva nel JSON il percorso dell'MP3 e la durata.
Solo per le edizioni degli ultimi AUDIO_DAYS giorni (default 60): quelle più vecchie vengono
tolte da tools/build_extras.py per restare nei limiti di spazio di GitHub Pages.
"""
import os
import re
import json
import subprocess
import sys
import tempfile
import datetime as dt

DATA = "data"
MAX_AUDIO = int(os.environ.get("MAX_AUDIO", "4"))
AUDIO_DAYS = int(os.environ.get("AUDIO_DAYS", "60"))
RUN_REPORT = os.environ.get("RUN_REPORT", "run_report_audio.json")
MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
ORD = ["Prima", "Seconda", "Terza", "Quarta", "Quinta", "Sesta", "Settima", "Ottava", "Nona", "Decima"]


def speakable(s):
    s = str(s or "")
    s = re.sub(r"\bn\.\s*(\d)", r"numero \1", s)
    s = re.sub(r"\bArtt?\.\s*", "articolo ", s)
    s = re.sub(r"\bcomma\s", "comma ", s)
    s = re.sub(r"\bd\.?\s?lgs\.?", "decreto legislativo", s, flags=re.I)
    s = re.sub(r"\bd\.?\s?l\.\s", "decreto-legge ", s, flags=re.I)
    s = re.sub(r"\b(UE)\b", "U E", s)
    s = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
               lambda m: f"{int(m[1])} {MESI[int(m[2])]} {m[3]}" if 1 <= int(m[2]) <= 12 else m[0], s)
    s = s.strip()
    if s and s[-1] not in ".!?":
        s += "."
    return s


def narration(d):
    day = dt.date.fromisoformat(d["date"])
    parts = [f"Bollettino della Gazzetta Ufficiale, serie generale numero {d.get('numero_gu', '')}, "
             f"di {d.get('giorno', '')} {day.day} {MESI[day.month]} {day.year}."]
    if d.get("sintesi"):
        parts.append(speakable(d["sintesi"]))
    schede = d.get("schede") or []
    if schede:
        parts.append(f"Le schede di oggi sono {len(schede)}." if len(schede) > 1 else "C'è una scheda.")
        for i, s in enumerate(schede):
            parts.append(f"{ORD[i] if i < len(ORD) else 'Scheda'} scheda. {speakable(s.get('titolo'))}")
            rif = str(s.get("riferimento") or "").lower()
            parts.append(speakable(rif[:1].upper() + rif[1:]))
            parts.append(speakable(s.get("contesto")))
            if s.get("misure"):
                parts.append("Le misure principali.")
                parts += [speakable(m) for m in s["misure"]]
            if s.get("chi_interessato"):
                parts.append("Chi è interessato. " + speakable(s["chi_interessato"]))
            if s.get("decorrenza"):
                parts.append("Decorrenza. " + speakable(s["decorrenza"]))
            if s.get("perche_conta"):
                parts.append("Perché conta. " + speakable(s["perche_conta"]))
    else:
        parts.append("In questa edizione non ci sono leggi o decreti di interesse per le materie seguite.")
    altri = d.get("altri_atti") or []
    if altri:
        parts.append("Altri atti da segnalare.")
        parts += [speakable(f"{a.get('titolo', '')}. {a.get('sintesi', '')}") for a in altri]
    parts.append("Fine del bollettino.")
    return "\n".join(p for p in parts if p and p != ".")


def main():
    from zoneinfo import ZoneInfo
    oldest = dt.datetime.now(ZoneInfo("Europe/Rome")).date() - dt.timedelta(days=AUDIO_DAYS)
    done, errors = 0, []
    for name in sorted(os.listdir(DATA), reverse=True):
        if done >= MAX_AUDIO or not re.match(r"\d{4}-\d{2}-\d{2}\.json$", name):
            continue
        if dt.date.fromisoformat(name[:10]) < oldest:
            continue
        path = os.path.join(DATA, name)
        d = json.load(open(path, encoding="utf-8"))
        if d.get("audio") or d.get("stato") not in ("con_schede", "nessuna_legge_interesse"):
            continue
        if not d.get("atti"):
            continue   # indice non ancora completo: niente audio vuoto
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(narration(d))
        print(f"🎙️ Audio per {d['date']}...")
        r = subprocess.run([sys.executable, "tools/build_audio.py", "--text", f.name,
                            "--date", d["date"], "--out", "audio"])
        if r.returncode != 0:
            print(f"⚠️ Audio non riuscito per {d['date']}")
            errors.append(f"Audio dell'edizione del {d['date']} non riuscito (codice {r.returncode}).")
            continue
        meta = json.load(open(os.path.join("audio", f"{d['date']}.json"), encoding="utf-8"))
        d["audio"], d["duration"] = meta["audio"], meta["duration"]
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        done += 1

    with open(RUN_REPORT, "w", encoding="utf-8") as f:
        json.dump({"audio_creati": done, "errori": errors}, f, ensure_ascii=False, indent=2)
    if errors:
        raise SystemExit(f"{len(errors)} audio non riusciti.")


if __name__ == "__main__":
    main()
