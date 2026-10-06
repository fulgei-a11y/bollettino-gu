import os
import json
import re
import urllib.request
from datetime import datetime, timedelta
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("Errore: GEMINI_API_KEY non trovata nelle variabili d'ambiente.")

genai.configure(api_key=GEMINI_API_KEY)

giorni_ita = {
    "Monday": "lunedì",
    "Tuesday": "martedì",
    "Wednesday": "mercoledì",
    "Thursday": "giovedì",
    "Friday": "venerdì",
    "Saturday": "sabato",
    "Sunday": "domenica"
}

def get_gu_details_for_date(date_str):
    """
    1. Legge la pagina della Gazzetta per identificare il numero di edizione associato alla data.
    2. Scarica la pagina caricaDettaglio con il sommario reale delle leggi.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_it = dt.strftime("%d-%m-%Y")
    
    home_url = "https://www.gazzettaufficiale.it/"
    num_gu = None
    
    try:
        req = urllib.request.Request(home_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html_home = resp.read().decode('utf-8', errors='ignore')
            # Cerca il pattern es. '232 del 06-10-2026'
            match = re.search(r'(\d+)\s+del\s+' + date_it, html_home)
            if match:
                num_gu = match.group(1)
    except Exception as e:
        print(f"Errore lettura homepage: {e}")

    if num_gu:
        dettaglio_url = f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}&numeroGazzetta={num_gu}"
        try:
            req_det = urllib.request.Request(dettaglio_url, headers=headers)
            with urllib.request.urlopen(req_det, timeout=15) as resp_det:
                html_det = resp_det.read().decode('utf-8', errors='ignore')
                text_clean = re.sub('<[^<]+?>', ' ', html_det)
                text_clean = re.sub(r'\s+', ' ', text_clean)
                return num_gu, dettaglio_url, text_clean[:25000]
        except Exception as e:
            print(f"Errore scaricamento dettaglio GU {num_gu}: {e}")

    fallback_url = f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}"
    return num_gu, fallback_url, None

def build_prompt(date_str, giorno_str, num_gu, link_gu, summary_text):
    date_formatted_eli = date_str.replace("-", "/")
    
    return f"""
Sei un analista ed esperto di diritto italiano.
Analizza il seguente sommario estratto dalla pagina ufficiale di dettaglio della Gazzetta Ufficiale (Serie Generale) del {date_str} ({giorno_str}).

DATI EDIZIONE:
- Data: {date_str}
- Numero GU: {num_gu if num_gu else 'Da individuare nel testo'}
- Link Ufficiale Sommario: {link_gu}

SOMMARIO ESTRATTO DALLA PAGINA:
---
{summary_text if summary_text else 'Sommario non raggiungibile direttamente.'}
---

ISTRUZIONI PER L'ANALISI:
1. Seleziona ed estrai SOLO i testi normativi (Leggi e Decreti-Legge) afferenti a queste 3 materie:
   - Economico / Fiscale / Finanziario / Pubblica Amministrazione / Enti Territoriali
   - Giustizia / Procedura / Reati
   - Energia / Ambiente / Sostenibilità / Imballaggi / Compostabilità / Rifiuti

2. Individua per ciascun atto il relativo CODICE REDAZIONALE (es. 26G00185 o 26A05123) presente nel sommario accanto al titolo/riferimento.
3. Se trovi il codice redazionale, componi il campo "link" nel formato ELI specifico per quell'atto:
   "https://www.gazzettaufficiale.it/eli/id/{date_formatted_eli}/<CODICE_REDAZIONALE>/sg"
   Se non riesci a individuare il codice redazionale singolo, imposta "link": "{link_gu}".

4. Se un'altra legge/decreto viene individuato ma appartiene a materie escluse, inseriscilo nell'array "scartate".
5. Se non vi sono leggi di interesse nel sommario, imposta "stato": "nessuna_legge_interesse", "schede": [].

Restituisci ESCLUSIVAMENTE un JSON valido con questa struttura esatta:
{{
  "date": "{date_str}",
  "giorno": "{giorno_str}",
  "stato": "con_schede",
  "numero_gu": "{num_gu if num_gu else ''}",
  "link_gu": "{link_gu}",
  "note": "Report Gazzetta Ufficiale del {date_str}",
  "updatedAt": "{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
  "scartate": [
    {{
      "materia": "<Materia>",
      "titolo": "<Titolo atto scartato>",
      "link": "{link_gu}"
    }}
  ],
  "schede": [
    {{
      "titolo": "<Titolo esplicativo del provvedimento>",
      "riferimento": "<Es. LEGGE 5 ottobre 2026, n. 173>",
      "codice_atto": "<Es. 26G00185>",
      "link": "https://www.gazzettaufficiale.it/eli/id/{date_formatted_eli}/<CODICE_REDAZIONALE>/sg",
      "categoria": "Energia e Ambiente",
      "iter": "In vigore",
      "contesto": "<Spiegazione del contesto e del decreto convertito>",
      "misure": [
        "Art. 1: Dettaglio della misura..."
      ],
      "chi_interessato": "<Soggetti e categorie coinvolte>",
      "decorrenza": "<Data di entrata in vigore>",
      "perche_conta": "<Analisi dell'impatto pratico>"
    }}
  ]
}}
"""

def generate_content_with_fallback(prompt):
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    last_error = None
    for model_name in models:
        try:
            print(f"Tentativo di generazione con modello: {model_name}...")
            model = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "application/json"})
            res = model.generate_content(prompt)
            return res.text.strip()
        except Exception as e:
            print(f"Modello {model_name} non disponibile o errore: {e}")
            last_error = e
    raise RuntimeError(f"Tutti i modelli Gemini hanno fallito. Ultimo errore: {last_error}")

def sanitize_data(data, date_str):
    """ Rimuove spazi, andate a capo e assicura che i link ELI siano formattati correttamente """
    num_gu = str(data.get("numero_gu", "")).strip()
    date_formatted_eli = date_str.replace("-", "/")
    
    clean_base_url = f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}&numeroGazzetta={num_gu}" if num_gu else f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}"
    
    data["link_gu"] = clean_base_url.replace(" ", "").replace("\n", "")

    if "schede" in data:
        for s in data["schede"]:
            link_val = s.get("link", "")
            codice = s.get("codice_atto", "").strip()
            
            # Se abbiamo un codice redazionale valido, costruiamo il link ELI diretto
            if codice and re.match(r'^[0-9A-Za-z]+$', codice):
                s["link"] = f"https://www.gazzettaufficiale.it/eli/id/{date_formatted_eli}/{codice}/sg"
            elif isinstance(link_val, str) and link_val.strip():
                s["link"] = re.sub(r'\s+', '', link_val)
                if not s["link"].startswith("http"):
                    s["link"] = data["link_gu"]
            else:
                s["link"] = data["link_gu"]
                
    if "scartate" in data:
        for sc in data["scartate"]:
            if "link" in sc and isinstance(sc["link"], str):
                sc["link"] = re.sub(r'\s+', '', sc["link"])
                if not sc["link"].startswith("http"):
                    sc["link"] = data["link_gu"]

    return data

def process_date(date_str, giorno_str):
    print(f"\n--- ELABORAZIONE DATA: {date_str} ({giorno_str}) ---")
    num_gu, link_gu, summary_text = get_gu_details_for_date(date_str)
    
    prompt = build_prompt(date_str, giorno_str, num_gu, link_gu, summary_text)
    raw_text = generate_content_with_fallback(prompt)
    
    try:
        data = json.loads(raw_text)
        data = sanitize_data(data, date_str)
    except Exception as e:
        print(f"Errore nella decodifica del JSON per {date_str}: {e}")
        return None

    file_path = f"data/{date_str}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"File {file_path} salvato con successo.")
    return data

def get_target_dates():
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_giorno = giorni_ita.get(today.strftime("%A"), today.strftime("%A").lower())
    
    if today.weekday() == 0:
        prev_date = today - timedelta(days=2)
    else:
        prev_date = today - timedelta(days=1)
        
    prev_str = prev_date.strftime("%Y-%m-%d")
    prev_giorno = giorni_ita.get(prev_date.strftime("%A"), prev_date.strftime("%A").lower())
    
    return [(today_str, today_giorno), (prev_str, prev_giorno)]

def update_index(results):
    index_path = "data/index.json"
    index_data = []
    
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = []

    for data in results:
        d_str = data.get("date")
        index_data = [x for x in index_data if x.get("date") != d_str]
        index_data.append({
            "date": d_str,
            "giorno": data.get("giorno", ""),
            "numero_gu": str(data.get("numero_gu", "")),
            "stato": data.get("stato", "nessuna_legge_interesse")
        })

    index_data.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"File {index_path} aggiornato e ordinato con successo.")

def generate_daily_bulletin():
    os.makedirs("data", exist_ok=True)
    results = []
    for date_str, giorno_str in get_target_dates():
        res = process_date(date_str, giorno_str)
        if res:
            results.append(res)
    if results:
        update_index(results)

if __name__ == "__main__":
    generate_daily_bulletin()
