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
    1. Scarica l'homepage o la pagina 30giorni per trovare il numero di GU associato alla data.
    2. Scarica la pagina caricaDettaglio con il sommario reale delle leggi.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # Prove per recuperare il sommario diretto
    # Converti YYYY-MM-DD in formato IT
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_it = dt.strftime("%d-%m-%Y")
    
    # 1. Tenta il recupero dal listato 30 giorni o homepage
    home_url = "https://www.gazzettaufficiale.it/"
    num_gu = None
    
    try:
        req = urllib.request.Request(home_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html_home = resp.read().decode('utf-8', errors='ignore')
            # Cerca il pattern '232 del 06-10-2026'
            match = re.search(r'(\d+)\s+del\s+' + date_it, html_home)
            if match:
                num_gu = match.group(1)
    except Exception as e:
        print(f"Errore lettura homepage: {e}")

    # Se trovato il numero o se fallback su tentativi
    if num_gu:
        dettaglio_url = f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}&numeroGazzetta={num_gu}"
        try:
            req_det = urllib.request.Request(dettaglio_url, headers=headers)
            with urllib.request.urlopen(req_det, timeout=15) as resp_det:
                html_det = resp_det.read().decode('utf-8', errors='ignore')
                text_clean = re.sub('<[^<]+?>', ' ', html_det)
                text_clean = re.sub(r'\s+', ' ', text_clean)
                return num_gu, dettaglio_url, text_clean[:20000]
        except Exception as e:
            print(f"Errore scaricamento dettaglio GU {num_gu}: {e}")

    return num_gu, f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}", None

def build_prompt(date_str, giorno_str, num_gu, link_gu, summary_text):
    return f"""
Sei un analista ed esperto di diritto.
Analizza il seguente sommario estratto dalla pagina ufficiale di dettaglio della Gazzetta Ufficiale (Serie Generale) per la data {date_str} ({giorno_str}).

DATI EDIZIONE:
- Data: {date_str}
- Numero GU: {num_gu if num_gu else 'Da individuare nel testo'}
- Link Ufficiale: {link_gu}

SOMMARIO ESTRATTO DALLA PAGINA:
---
{summary_text if summary_text else 'Sommario non raggiungibile.'}
---

ISTRUZIONI:
1. Seleziona ed estrai SOLO i testi normativi (Leggi e Decreti-Legge) afferenti a:
   - Economico / Fiscale / Finanziario / Pubblica Amministrazione / Enti Territoriali
   - Giustizia / Procedura / Reati
   - Energia / Ambiente / Sostenibilità / Imballaggi / Compostabilità / Rifiuti

2. Compila la scheda per ciascun provvedimento idoneo (es. Legge 173, Legge 174).
3. Se non vi sono leggi d'interesse nel sommario, imposta "stato": "nessuna_legge_interesse".

Restituisci ESCLUSIVAMENTE un JSON con questa struttura esatta:
{{
  "date": "{date_str}",
  "giorno": "{giorno_str}",
  "stato": "con_schede",
  "numero_gu": "{num_gu if num_gu else ''}",
  "link_gu": "{link_gu}",
  "note": "Report Gazzetta Ufficiale del {date_str}",
  "updatedAt": "{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
  "scartate": [],
  "schede": [
    {{
      "titolo": "<Titolo sintetico>",
      "riferimento": "<Es. LEGGE 6 ottobre 2026, n. 173>",
      "link": "{link_gu}",
      "categoria": "Energia e Ambiente",
      "iter": "In vigore",
      "contesto": "<Contesto normativo>",
      "misure": [
        "Art. 1: Disposizione..."
      ],
      "chi_interessato": "<Soggetti interessati>",
      "decorrenza": "<Data entrata in vigore>",
      "perche_conta": "<Impatto pratico>"
    }}
  ]
}}
"""

def generate_content_with_fallback(prompt):
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    for m in models:
        try:
            model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"})
            res = model.generate_content(prompt)
            return res.text.strip()
        except Exception as e:
            print(f"Modello {m} fallito: {e}")
    raise RuntimeError("Tutti i modelli Gemini hanno fallito.")

def process_date(date_str, giorno_str):
    print(f"Elaborazione per la data {date_str}...")
    num_gu, link_gu, summary_text = get_gu_details_for_date(date_str)
    
    prompt = build_prompt(date_str, giorno_str, num_gu, link_gu, summary_text)
    raw_text = generate_content_with_fallback(prompt)
    
    try:
        data = json.loads(raw_text)
        # Forza l'URL pulito
        if num_gu:
            data["link_gu"] = f"https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio?dataPubblicazioneGazzetta={date_str}&numeroGazzetta={num_gu}"
            data["numero_gu"] = str(num_gu)
    except Exception as e:
        print(f"Errore parsing JSON: {e}")
        return None

    file_path = f"data/{date_str}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"File salvato: {file_path}")
    return data

def get_target_dates():
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_giorno = giorni_ita.get(today.strftime("%A"), today.strftime("%A").lower())
    
    if today.weekday() == 0:  # Lunedì -> cerca sabato
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
