# Bollettino GU

Sito: **https://fulgei-a11y.github.io/bollettino-gu/**

Ogni giorno (dal lunedì al sabato) un controllo automatico legge la Gazzetta Ufficiale, Serie Generale,
e pubblica le schede delle leggi, dei decreti-legge e dei decreti legislativi in materia economica,
di giustizia, energia e ambiente, con la lettura audio.

## Cosa c'è sul sito

- **Edizioni**: schede, altri atti segnalati, elenco completo, audio con velocità regolabile e ripresa dal punto lasciato, PDF, condivisione (anche della singola scheda: `#2026-10-08/s0`).
- **Cerca**: ricerca in tutto l'archivio (schede, atti segnalati, elenco degli atti), con filtro per materia. Link diretto: `#cerca=imballaggi`.
- **Scadenze**: conto alla rovescia dei 60 giorni per la conversione dei decreti-legge, esito della conversione, entrate in vigore di leggi e decreti legislativi. Iscrivibile come calendario (`data/scadenze.ics`).
- **App**: installabile su telefono (manifest + service worker), consultabile anche senza rete.
- **Podcast**: `data/podcast.xml`, da aggiungere a qualunque app di podcast.
- **Stato**: in testata "Aggiornato …"; avviso sul sito se l'ultimo controllo è fallito o se il bollettino è fermo.

## Come funziona il controllo (`.github/workflows/daily_update.yml`)

1. `generate.py` — trova l'edizione, legge gli atti, Gemini scrive le schede (`data/AAAA-MM-GG.json`).
2. `tools/make_audio.py` + `tools/build_audio.py` — lettura audio (voce Paola), solo per gli ultimi 60 giorni.
3. `tools/build_extras.py` — **toglie gli MP3 più vecchi di 60 giorni** (le schede restano), rigenera indice, ricerca, scadenzario, calendario e podcast.
4. `tools/report_status.py` — scrive `data/status.json`. Se qualcosa non va **apre un avviso tra le Issues** del repository (GitHub lo notifica per email e nell'app GitHub); l'avviso si chiude da solo al primo controllo riuscito.

Per rifare un'edizione: *Actions* → *Aggiornamento Automatico Bollettino GU* → *Run workflow* e indica la data.
