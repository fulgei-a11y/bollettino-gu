import os
import json
import re
from datetime import datetime
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("Errore: GEMINI_API_KEY non trovata nelle variabili d'ambiente.")

genai.configure(api_key=GEMINI_API_KEY)

today_str = datetime.now().strftime("%Y-%m-%d")
giorno_en = datetime.now().strftime("%A")

giorni_ita = {
    "Monday": "lunedì",
    "Tuesday": "martedì",
    "Wednesday": "mercoledì",
    "Thursday": "giovedì",
    "Friday": "venerdì",
    "Saturday": "sabato",
    "Sunday": "domenica"
}
giorno_ita = giorni_ita.get(giorno_en, giorno_en.lower())

PROMPT_SYSTEM = f"""
Sei un analista ed esperto di diritto. Il tuo compito è analizzare la Gazzetta Ufficiale della Repubblica Italiana (Serie Generale) pubblicata oggi ({today_str}).
Seleziona unicamente i testi normativi (Legge, Decreto-Legge, Decreto Legislativo, D.P.R., D.P.C.M., Decreto Ministeriale) che rientrano nelle seguenti materie d'interesse:
1. Economico / Fiscale / Finanziario
2. Giustizia / Reati / Procedura
3. Energia / Ambiente / Sostenibilità

REGOLE PER I LINK:
- Il campo "link_gu" DEVE essere: "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglioMeteo/home"
- I campi "link" nelle schede e nelle leggi scartate DEVONO essere sempre URL validi di ricerca o consultazione della Gazzetta Ufficiale. Usa come fallback l'URL principale "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglioMeteo/home" se non hai il link specifico al singolo articolo.

Restituisci ESCLUSIVAMENTE un JSON valido con questa struttura esatta:
{{
  "date": "{today_str}",
  "giorno": "{giorno_ita}",
  "stato": "con_schede",
  "numero_gu": "Numero Edizione (es. 233)",
  "link_gu": "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglioMeteo/home",
  "updatedAt": "{today_str}T19:00:00Z",
  "scartate": [
    {{
      "materia": "Materia scartata",
      "titolo": "Titolo o indicazione dell'atto scartato",
      "link": "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglioMeteo/home"
    }}
  ],
  "schede": [
    {{
      "titolo": "Titolo sintetico ed esplicativo",
      "categoria": "Economico",
      "riferimento": "DECRETO-LEGGE 5 ottobre 2026, n. 150",
      "iter": "In vigore",
      "contesto": "Sintesi chiara del contesto normativo.",
      "misure": [
        "Punto chiave 1",
        "Punto chiave 2"
      ],
      "chi_interessato": "Soggetti interessati",
      "decorrenza": "Data di entrata in vigore",
      "perche_conta": "Impatto della misura",
      "link": "https://www.gazzettaufficiale.it/gazzetta/serie_generale/caricaDettaglioMeteo/home"
    }}
  ]
}}

Se oggi non sono stati pubblicati atti rilevanti nelle tre categorie d'interesse, imposta "stato": "nessuna_legge_interesse", "schede": [] e "scartate": [].
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

def generate_daily_bulletin():
    os.makedirs("data", exist_ok=True)
    
    prompt = f"{PROMPT_SYSTEM}\n\nGenera il report JSON per la Gazzetta Ufficiale del {today_str}."
    
    raw_text = generate_content_with_fallback(prompt)
    
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print("Errore nella decodifica del JSON da Gemini:", e)
        print("Risposta ricevuta:\n", raw_text)
        return

    # 1. Salva il file della giornata
    file_path = f"data/{today_str}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"File {file_path} salvato con successo.")

    # 2. Aggiorna data/index.json
    index_path = "data/index.json"
    index_data = []
    
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = []

    index_data = [item for item in index_data if item.get("date") != today_str]

    new_entry = {
        "date": data.get("date", today_str),
        "giorno": data.get("giorno", giorno_ita),
        "numero_gu": str(data.get("numero_gu", "")),
        "stato": data.get("stato", "nessuna_legge_interesse")
    }

    index_data.insert(0, new_entry)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"File {index_path} aggiornato con successo.")
if __name__ == "__main__":
    generate_daily_bulletin()
