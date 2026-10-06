import os
import json
import requests
from datetime import datetime
import google.generativeai as genai

# Configura l'API di Gemini prendendo la chiave dalle variabili d'ambiente (GitHub Secrets)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY non trovata nelle variabili d'ambiente.")

genai.configure(api_key=GEMINI_API_KEY)

today_str = datetime.now().strftime("%Y-%m-%d")
giorno_str = datetime.now().strftime("%A")

# Traduzione giorni in italiano
giorni_ita = {
    "Monday": "Lunedì",
    "Tuesday": "Martedì",
    "Wednesday": "Mercoledì",
    "Thursday": "Giovedì",
    "Friday": "Venerdì",
    "Saturday": "Sabato",
    "Sunday": "Domenica"
}
giorno_ita_str = giorni_ita.get(giorno_str, giorno_str)

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
  "id": "YYYY-MM-DD",
  "date": "YYYY-MM-DD",
  "giorno": "NomeGiorno",
  "stato": "con_schede",
  "numero_gu": "Numero Edizione (es. 235)",
  "link_gu": "[https://www.gazzettaufficiale.it/](https://www.gazzettaufficiale.it/)...",
  "updatedAt": "YYYY-MM-DDTHH:MM:SSZ",
  "scartate": [
    {
      "materia": "Materia scartata (es. Sanità)",
      "titolo": "Titolo o indicazione dell'atto scartato",
      "link": "[https://www.gazzettaufficiale.it/](https://www.gazzettaufficiale.it/)..."
    }
  ],
  "schede": [
    {
      "titolo": "Titolo sintetico ed esplicativo",
      "categoria": "Economico | Giustizia | Energia e Ambiente",
      "riferimento": "Riferimento normativo ufficiale (es. DECRETO-LEGGE 5 ottobre 2026, n. 150)",
      "iter": "In vigore / In corso di conversione",
      "contesto": "Sintesi chiara del contesto normativo e delle motivazioni.",
      "misure": [
        "Punto chiave 1",
        "Punto chiave 2"
      ],
      "chi_interessato": "Soggetti interessati (es. Imprese, Professionisti, Cittadini)",
      "decorrenza": "Data di entrata in vigore o efficacia",
      "perche_conta": "Spiegazione pratica dell'impatto e dell'importanza",
      "link": "[https://www.gazzettaufficiale.it/](https://www.gazzettaufficiale.it/)..."
    }
  ]
}

Se oggi non sono stati pubblicati atti rilevanti nelle tre categorie d'interesse, valorizza "stato": "nessuna_legge_interesse" e imposta "schede": [].
"""

def generate_daily_bulletin():
    os.makedirs("data", exist_ok=True)
    
    # Inizializzazione modello Gemini
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    prompt = f"{PROMPT_SYSTEM}\n\nOggi è il {today_str} ({giorno_ita_str}). Genera il report per la Gazzetta Ufficiale odierna."
    
    response = model.generate_content(prompt)
    raw_text = response.text.strip()
    
    # Rimuove eventuali marcatori di codice markdown
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
        print("Risposta ricevuta:\n", raw_text)
        return

    # Salva il file del giorno
    file_path = f"data/{today_str}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"File {file_path} salvato con successo.")

    # Aggiorna l'indice dei file (data/index.json)
    index_path = "data/index.json"
    index_data = []
    
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = []

    # Rimuove eventuali voci duplicate per la stessa data e inserisce la nuova in cima
    index_data = [item for item in index_data if item.get("date") != today_str]
    index_data.insert(0, {
        "id": data.get("id", today_str),
        "date": data.get("date", today_str),
        "giorno": data.get("giorno", giorno_ita_str),
        "stato": data.get("stato", "con_schede"),
        "numero_gu": data.get("numero_gu", "")
    })

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"File {index_path} aggiornato con successo.")

if __name__ == "__main__":
    generate_daily_bulletin()
