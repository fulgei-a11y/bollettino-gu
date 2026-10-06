import os
import json
import re
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

def get_target_dates():
    today = datetime.now()
    # Calcolo data di oggi
    today_str = today.strftime("%Y-%m-%d")
    today_giorno = giorni_ita.get(today.strftime("%A"), today.strftime("%A").lower())
    
    # Calcolo data precedente (se oggi è lunedì, il giorno precedente di GU è sabato)
    if today.weekday() == 0:  # Lunedì
        prev_date = today - timedelta(days=2)
    else:
        prev_date = today - timedelta(days=1)
        
    prev_str = prev_date.strftime("%Y-%m-%d")
    prev_giorno = giorni_ita.get(prev_date.strftime("%A"), prev_date.strftime("%A").lower())
    
    return [(today_str, today_giorno), (prev_str, prev_giorno)]

def build_system_prompt(date_str, giorno_str):
    return f"""
IMPORTANTE: Questo è un lavoro di analisi giuridico-fiscale di livello professionale.

Analizza la Gazzetta Ufficiale della Repubblica Italiana (Serie Generale) per la data: {date_str} ({giorno_str}).

PASSO 1 - INDIVIDUAZIONE ED
Esamina le Leggi e i Decreti-Legge pubblicati in questa edizione. Ignora decreti ministeriali minori, nomine, comunicati ed estratti.

PASSO 2 - MATERIE D'INTERESSE:
1. ECONOMICO / FISCALE / PA: Fisco, bilancio, finanza pubblica, lavoro, imprese, pubblica amministrazione, enti territoriali, protezione civile.
2. GIUSTIZIA: Ordinamento giudiziario, codice penale/civile, procedura, sistema carcerario.
3. ENERGIA E AMBIENTE: Energia, fonti rinnovabili, tutela del territorio, gestione dei rifiuti, imballaggi e compostabilità.

REGOLE SUI LINK ED ENDPOINT:
- L'URL principale della Gazzetta deve essere nel formato corretto: 
  "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio/home?dataPubblicazioneGazzetta={date_str}&numeroGazzetta=<NUMERO>"
- Per i singoli atti usa il link ELI ufficiale: "https://www.gazzettaufficiale.it/eli/id/{date_str.replace('-','/')}/<CODICE>/sg" oppure l'URL di consultazione valido.

Restituisci ESCLUSIVAMENTE un JSON valido con questa struttura esatta:
{{
  "date": "{date_str}",
  "giorno": "{giorno_str}",
  "stato": "con_schede",
  "numero_gu": "<Numero edizione, es. 234>",
  "link_gu": "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglio/home?dataPubblicazioneGazzetta={date_str}&numeroGazzetta=<NUMERO>",
  "note": "Report Gazzetta Ufficiale del {date_str}",
  "updatedAt": "{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
  "scartate": [
    {{
      "materia": "<Materia dell'atto scartato>",
      "titolo": "<Titolo completo e motivo dello scarto>",
      "link": "https://www.gazzettaufficiale.it/"
    }}
  ],
  "schede": [
    {{
      "titolo": "<Titolo della legge/decreto>",
      "riferimento": "<Es. Legge 6 ottobre 2026, n. 173>",
      "link": "https://www.gazzettaufficiale.it/",
      "categoria": "Economico",
      "iter": "<Iter di conversione o vigenza>",
      "contesto": "<Spiegazione del contesto e motivi della norma>",
      "misure": [
        "Art. 1, comma 1: Spiegazione dettagliata della misura...",
        "Art. 2: Spiegazione dettagliata..."
      ],
      "chi_interessato": "<Soggetti e categorie coinvolte>",
      "decorrenza": "<Data di entrata in vigore>",
      "perche_conta": "<Analisi dell'impatto pratico e criticità>"
    }}
  ]
}}

Se per la data {date_str} non risulta pubblicata alcuna edizione della Gazzetta Ufficiale (es. domenica/festivo), imposta:
"stato": "nessuna_edizione", "schede": [], "scartate": []

Se l'edizione esiste ma non contiene Leggi o Decreti-Legge nelle materie d'interesse, imposta:
"stato": "nessuna_legge_interesse", "schede": []
"""

def generate_content_with_fallback(prompt):
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]
    
    last_error = None
    for model_name in models_to_try:
        try:
            print(f"Tentativo con modello: {model_name}...")
            model = genai.GenerativeModel(
                model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Modello {model_name} non disponibile o errore: {e}")
            last_error = e
            
    raise RuntimeError(f"Nessun modello Gemini è riuscito a rispondere. Ultimo errore: {last_error}")

def sanitize_json_data(data, date_str):
    # Sanificazione link_gu da eventuali refusi tipo 'Meteo'
    if "link_gu" in data and isinstance(data["link_gu"], str):
        data["link_gu"] = data["link_gu"].replace("caricaDettaglioMeteo", "caricaDettaglio")
        data["link_gu"] = data["link_gu"].replace("carica Dettaglio", "caricaDettaglio")

    # Sanificazione schede e link
    if "schede" in data:
        for scheda in data["schede"]:
            if "link" in scheda and isinstance(scheda["link"], str):
                scheda["link"] = scheda["link"].replace("caricaDettaglioMeteo", "caricaDettaglio")
                
    return data

def process_date(date_str, giorno_str):
    print(f"\n--- ELABORAZIONE DATA: {date_str} ({giorno_str}) ---")
    prompt_system = build_system_prompt(date_str, giorno_str)
    prompt = f"{prompt_system}\n\nGenera il report JSON per la Gazzetta Ufficiale del {date_str}."
    
    raw_text = generate_content_with_fallback(prompt)
    
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"Errore nella decodifica del JSON da Gemini per {date_str}:", e)
        return None

    data = sanitize_json_data(data, date_str)

    # 1. Salva il file della giornata
    file_path = f"data/{date_str}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"File {file_path} salvato con successo.")
    return data

def update_index(processed_results):
    index_path = "data/index.json"
    index_data = []
    
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = []

    # Aggiorna o sostituisce le entrate per le date appena elaborate
    for data in processed_results:
        date_str = data.get("date")
        index_data = [item for item in index_data if item.get("date") != date_str]
        
        new_entry = {
            "date": date_str,
            "giorno": data.get("giorno", ""),
            "numero_gu": str(data.get("numero_gu", "")),
            "stato": data.get("stato", "nessuna_legge_interesse")
        }
        index_data.append(new_entry)

    # Ordina l'indice per data decrescente
    index_data.sort(key=lambda x: x.get("date", ""), reverse=True)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"File {index_path} aggiornato e ordinato con successo.")

def generate_daily_bulletin():
    os.makedirs("data", exist_ok=True)
    target_dates = get_target_dates()
    
    processed_results = []
    for date_str, giorno_str in target_dates:
        result = process_date(date_str, giorno_str)
        if result:
            processed_results.append(result)
            
    if processed_results:
        update_index(processed_results)
if __name__ == "__main__":
    generate_daily_bulletin(
