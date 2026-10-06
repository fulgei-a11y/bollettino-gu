import os
import json
import requests
from datetime import datetime
import google.generativeai as genai

# Recupera la chiave API dai Secrets di GitHub
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

PROMPT_SYSTEM = """
Sei un analista ed esperto di diritto. Il tuo compito è analizzare la Gazzetta Ufficiale della Repubblica Italiana (Serie Generale) pubblicata oggi.
Devi selezionare unicamente i testi normativi (Legge, Decreto-Legge, Decreto Legislativo, D.P.R., D.P.C.M., Decreto Ministeriale) che rientrano nelle seguenti materie d'interesse:
1. Economico / Fiscale / Finanziario
2. Giustizia / Reati / Procedura
3. Energia / Ambiente / Sostenibilità

Istruzioni per l'output:
Restituisci ESCLUSIVAMENTE un oggetto JSON valido (senza testo prima o dopo, e senza blocchi markdown ```json).

Il JSON deve seguire questo schema rigoroso:
{
  "date": "YYYY-MM-DD",
  "giorno": "nome_giorno_minuscolo",
  "stato": "con_schede",
  "numero_gu": "Numero Edizione (es. 231)",
  "link_gu": "[https://www.gazzettaufficiale.it/](https://www.gazzettaufficiale.it/)...",
  "updatedAt": "YYYY-MM-DDTHH:MM:SSZ",
  "scartate": [
    {
      "materia": "Materia scartata",
      "titolo": "Titolo o indicazione dell'atto scartato",
      "link": "[https://www.gazzettaufficiale.it/](https://www.gazzettaufficiale.it/)..."
    }
  ],
  "schede": [
    {
      "titolo": "Titolo sintetico ed esplicativo",
      "categoria": "Economico | Giustizia | Energia e Ambiente",
      "riferimento": "Riferimento normativo ufficiale",
      "iter": "In vigore / In corso di conversione",
      "contesto": "Sintesi chiara del contesto normativo.",
      "misure": [
        "Punto chiave 1",
        "Punto chiave 2"
      ],
      "chi_interessato": "Soggetti interessati",
      "decorrenza": "Data di entrata in vigore",
      "perche_conta": "Impatto della misura",
      "link": "[https://www.gazzettaufficiale.it/](https://www.gazzettaufficiale.it/)..."
    }
  ]
}

Se oggi non sono stati pubblicati atti rilevanti nelle tre categorie d'interesse, imposta:
"stato": "nessuna_legge_interesse", "schede": [] e "scartate": [].
"""

def generate_daily_bulletin():
    os.makedirs("data", exist_ok=True)
    
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"{PROMPT_SYSTEM}\n\nOggi è {giorno_ita} {today_str}. Genera il report per la Gazzetta Ufficiale odierna."
    
    response = model.generate_content(prompt)
    raw_text = response.text.strip()
    
    # Pulizia dai blocchi di codice markdown
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print("Errore nella decodifica del JSON da Gemini:", e)
        print("Risposta grezzo:\n", raw_text)
        return

    # 1. Salva il file di dettaglio del giorno (es. data/2026-10-06.json)
    file_path = f"data/{today_str}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"File {file_path} creato/aggiornato.")

    # 2. Aggiorna data/index.json mantenendo la struttura esistente
    index_path = "data/index.json"
    index_data = []
    
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = []

    # Rimuove l'eventuale voce per la data di oggi se già presente
    index_data = [item for item in index_data if item.get("date") != today_str]

    # Prepara la voce dell'indice secondo il formato del tuo progetto
    new_entry = {
        "date": data.get("date", today_str),
        "giorno": data.get("giorno", giorno_ita),
        "numero_gu": str(data.get("numero_gu", "")),
        "stato": data.get("stato", "nessuna_legge_interesse")
    }

    # Inserisce la nuova giornata in cima alla lista
    index_data.insert(0, new_entry)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"File {index_path} aggiornato con successo.")

if __name__ == "__main__":
    generate_daily_bulletin()
