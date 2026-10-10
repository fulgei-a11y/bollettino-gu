# Bollettino GU

Sito: **https://fulgei-a11y.github.io/bollettino-gu/**

Ogni giorno (dal lunedì al sabato) un controllo automatico legge la Gazzetta Ufficiale, Serie Generale,
e pubblica le schede delle leggi, dei decreti-legge e dei decreti legislativi in materia economica,
di giustizia, energia e ambiente, con la lettura audio.

## Cosa c'è sul sito

- **Edizioni**: schede, altri atti segnalati, elenco completo, audio con velocità regolabile e ripresa dal punto lasciato, PDF, condivisione (anche della singola scheda: `#2026-10-08/s0`).
- **Cerca**: ricerca in tutto l'archivio (schede, atti segnalati, elenco degli atti), con filtro per materia. Link diretto: `#cerca=imballaggi`.
- **Scadenze**: conto alla rovescia dei 60 giorni per la conversione dei decreti-legge, esito della conversione, entrate in vigore di leggi e decreti legislativi. Iscrivibile come calendario (`data/scadenze.ics`).
- **Parlamento**: novità dai dossier dei Servizi Studi di Camera e Senato (temi.camera.it) e dai documenti acquisiti dalle commissioni II Giustizia, V Bilancio, VI Finanze, VIII Ambiente e X Attività produttive della Camera. A ogni controllo si confronta con quanto già visto: le voci nuove sono segnate "Nuovo" e contate sulla scheda. Commissioni seguite: `COMMISSIONI` in `tools/parlamento.py`.
- **Preferiti**: stellina su schede, decreti-legge, atti segnalati e documenti del Parlamento, con note personali; per i decreti-legge salvati mostra i giorni che mancano alla conversione. Restano nel browser del dispositivo; si spostano su un altro con il link "Trasferisci" o con esporta/importa file.
- **App**: installabile su telefono (manifest + service worker), consultabile anche senza rete.
- **Podcast**: `data/podcast.xml`, da aggiungere a qualunque app di podcast.
- **Stato**: in testata "Aggiornato …"; avviso sul sito se l'ultimo controllo è fallito o se il bollettino è fermo.

## Come funziona il controllo (`.github/workflows/daily_update.yml`)

1. `generate.py` — trova l'edizione, legge gli atti, Gemini scrive le schede (`data/AAAA-MM-GG.json`).
2. `tools/make_audio.py` + `tools/build_audio.py` — lettura audio (voce Paola), solo per gli ultimi 60 giorni.
3. `tools/parlamento.py` — legge dossier e documenti delle commissioni e registra le novità (`data/parlamento.json`; l'elenco di ciò che è già stato visto è in `data/parlamento_visti.json`). Al primo avvio registra tutto senza segnalarlo come nuovo. Se un sito non risponde una volta è solo un avviso; se non risponde nessuna fonte o una pagina cambia struttura, parte l'avviso tra le Issues.
4. `tools/build_extras.py` — **toglie gli MP3 più vecchi di 60 giorni** (le schede restano), rigenera indice, ricerca, scadenzario, calendario e podcast.
5. `tools/report_status.py` — scrive `data/status.json`. Se qualcosa non va **apre un avviso tra le Issues** del repository (GitHub lo notifica per email e nell'app GitHub); l'avviso si chiude da solo al primo controllo riuscito.

Per rifare un'edizione: *Actions* → *Aggiornamento Automatico Bollettino GU* → *Run workflow* e indica la data.

Prova del lettore del Parlamento (su pagine vere salvate): `python3 -I tests/test_parlamento.py`

Nota: le pagine del Senato sono protette da un filtro anti-robot e non vengono lette; i dossier del Senato arrivano dal portale comune della documentazione parlamentare.
