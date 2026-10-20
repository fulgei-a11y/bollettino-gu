"""
Notifiche sul telefono con ntfy (app "ntfy" per Android e iPhone, gratuita).

Dopo ogni controllo manda una notifica per:
- ogni nuova edizione della Gazzetta elaborata (con le leggi di interesse, o "nessuna legge di interesse"
  a priorità bassa);
- le novità dal Parlamento trovate in questo controllo (dossier e documenti delle commissioni);
- i decreti-legge in scadenza: promemoria a 15, 7, 3 e 1 giorno dal termine dei 60 giorni, e il giorno stesso;
- un controllo non riuscito (una volta sola, finché il problema dura) e il ritorno alla normalità.

Il nome del canale ntfy è nel segreto NTFY_TOPIC del repository: chi lo conosce può leggere le notifiche,
quindi non va scritto nel codice né sul sito. Senza segreto lo script non fa nulla.
Ricorda cosa ha già mandato in data/notifiche.json, così la stessa notifica non arriva due volte.
Al primo avvio registra le edizioni già presenti senza notificarle e manda solo un messaggio di benvenuto.

Solo libreria standard. Prova manuale: NTFY_TOPIC=... NTFY_TEST=1 python3 tools/notify.py
"""
import os
import re
import json
import datetime as dt
import urllib.request
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
DATA = "data"
STATE = os.path.join(DATA, "notifiche.json")
SITE = os.environ.get("SITE_URL", "https://fulgei-a11y.github.io/bollettino-gu/").rstrip("/") + "/"
SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
DRY = os.environ.get("NTFY_DRY_RUN") == "1"          # stampa invece di inviare (per le prove)
TEST = os.environ.get("NTFY_TEST", "").lower() in ("1", "true", "yes")
DL_SOGLIE = [15, 7, 3, 1, 0]
MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
CAT_EMOJI = {"Economico": "💶", "Giustizia": "⚖️", "Energia e Ambiente": "🌿"}

sent_now = []


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def fmt(d):
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month]}"


def clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def send(title, message, click="", tags=(), priority=3, actions=()):
    body = {"topic": TOPIC, "title": clip(title, 120), "message": clip(message, 3800) if "\n" not in message
            else message[:3800], "priority": priority, "tags": list(tags)}
    if click:
        body["click"] = click
    if actions:
        body["actions"] = [{"action": "view", "label": l, "url": u, "clear": True} for l, u in actions][:3]
    if DRY:
        print("📱 [prova]", json.dumps(body, ensure_ascii=False, indent=1))
        sent_now.append(body)
        return True
    req = urllib.request.Request(SERVER, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if 200 <= r.status < 300:
                    print(f"📱 Notifica inviata: {title}")
                    sent_now.append(body)
                    return True
        except Exception as e:
            print(f"⚠️ ntfy non raggiungibile ({type(e).__name__}): {e}")
    return False


# ---------------------------------------------------------------------------
def gu_notifications(state, today, baseline):
    index = load(os.path.join(DATA, "index.json"), [])
    for e in reversed(index):           # dalla più vecchia, così arrivano in ordine
        if e.get("stato") not in ("con_schede", "nessuna_legge_interesse"):
            continue
        if (today - dt.date.fromisoformat(e["date"])).days > 4:
            continue
        key = f"gu:{e['date']}:{e.get('numero_gu')}"
        if key in state["inviate"]:
            continue
        d = load(os.path.join(DATA, f"{e['date']}.json"), None)
        if not d or not d.get("atti"):
            continue                     # edizione letta a metà: si aspetta il controllo dopo
        if baseline:
            state["inviate"][key] = now_s()
            continue
        schede = d.get("schede") or []
        altri = d.get("altri_atti") or []
        n = f"GU n. {d.get('numero_gu')} – " if d.get("numero_gu") else "GU – "
        link = f"{SITE}#{d['date']}"
        actions = []
        if d.get("audio"):
            actions.append(("Ascolta", f"{SITE}{d['audio']}"))
        if d.get("pdf_gu"):
            actions.append(("PDF della Gazzetta", d["pdf_gu"]))
        if schede:
            righe = []
            for s in schede:
                em = CAT_EMOJI.get(s.get("categoria"), "•")
                righe.append(f"{em} {clip(s.get('titolo'), 140)}")
                rif = s.get("riferimento") or ""
                extra = ""
                if rif.upper().startswith("DECRETO-LEGGE") and d.get("date"):
                    scad = dt.date.fromisoformat(d["date"]) + dt.timedelta(days=60)
                    extra = f" · da convertire entro il {scad.day} {MESI[scad.month]}"
                elif s.get("vigore"):
                    extra = f" · in vigore dal {s['vigore']}"
                if rif:
                    righe.append(f"   {clip(rif, 90)}{extra}")
            if altri:
                righe.append(f"\nAltri atti segnalati: {len(altri)}")
            ok = send(f"📜 {n}{fmt(d['date'])}: {len(schede)} " + ("legge di interesse" if len(schede) == 1 else "leggi di interesse"),
                      "\n".join(righe), click=link, tags=["scroll"], priority=4, actions=actions)
        else:
            msg = "Nessuna legge di interesse per economia, giustizia, energia e ambiente."
            if altri:
                msg += f"\nAltri atti segnalati: {len(altri)} – " + "; ".join(clip(a.get("titolo"), 70) for a in altri[:3])
            ok = send(f"📜 {n}{fmt(d['date'])}", msg, click=link, tags=["scroll"], priority=2, actions=actions)
        if ok:
            state["inviate"][key] = now_s()


def parl_notifications(state, baseline):
    p = load(os.path.join(DATA, "parlamento.json"), {})
    controlli = p.get("controlli") or []
    if not controlli or not controlli[0].get("nuovi"):
        return
    quando = controlli[0]["quando"]
    key = f"parl:{quando}"
    if key in state["inviate"]:
        return
    if baseline:
        state["inviate"][key] = now_s()
        return
    nuove = [v for v in p.get("voci") or [] if v.get("visto") == quando and not v.get("iniziale")]
    if not nuove:
        return
    dossier = [v for v in nuove if v.get("fonte") == "dossier"]
    comm = [v for v in nuove if v.get("fonte") == "commissione"]
    parti = []
    if dossier:
        parti.append(f"{len(dossier)} dossier")
    if comm:
        parti.append(f"{len(comm)} " + ("documento delle commissioni" if len(comm) == 1 else "documenti delle commissioni"))
    # prima quelle delle materie seguite
    nuove.sort(key=lambda v: (not v.get("materia"), v.get("fonte") != "dossier"))
    righe = []
    for v in nuove[:7]:
        em = CAT_EMOJI.get(v.get("materia"), "•")
        t = v.get("titolo") or ""
        if v.get("fonte") == "commissione":
            org = "Comm. " + "-".join(v.get("commissioni") or [])
            if v.get("tipo") and v["tipo"].lower() not in t.lower():
                t = f"{v['tipo']} {t}"           # «Memoria COREPLA» invece di «COREPLA»
            if v.get("atto") and v["atto"] not in t:
                org += f", {v['atto']}"
        else:
            org = v.get("organo") or "Dossier"
        righe.append(f"{em} {clip(t, 120)} ({clip(org, 40)})")
    if len(nuove) > 7:
        righe.append(f"…e altre {len(nuove) - 7}")
    if send(f"🏛️ Parlamento: {' e '.join(parti)}", "\n".join(righe), click=f"{SITE}#parlamento",
            tags=["classical_building"], priority=3):
        state["inviate"][key] = now_s()


def dl_notifications(state, today, baseline):
    sc = load(os.path.join(DATA, "scadenze.json"), {})
    for x in sc.get("decreti_legge") or []:
        if x.get("stato") != "in_conversione" or not x.get("scadenza"):
            continue
        left = (dt.date.fromisoformat(x["scadenza"]) - today).days
        if left < 0:
            continue
        due = [s for s in DL_SOGLIE if left <= s]
        if not due:
            continue
        soglia = min(due)
        base = f"dl:{x['anno']}-{x['numero']}:"
        if f"{base}{soglia}" in state["inviate"]:
            continue
        for s in due:                    # le soglie più larghe già superate non vanno più mandate
            state["inviate"][f"{base}{s}"] = now_s()
        if baseline and soglia > 1:
            continue
        quando = "oggi" if left == 0 else ("domani" if left == 1 else f"tra {left} giorni")
        scad = dt.date.fromisoformat(x["scadenza"])
        link = f"{SITE}#{x['pubblicazione']}/s{x['scheda']}" if x.get("scheda") is not None else f"{SITE}#scadenze"
        send(f"⏳ Il DL n. {x['numero']}/{x['anno']} scade {quando}",
             f"{clip(x.get('titolo'), 200)}\nUltimo giorno per la conversione in legge: {fmt(scad)} {scad.year}.",
             click=link, tags=["hourglass"], priority=5 if left <= 1 else 4,
             actions=[("Scadenzario", f"{SITE}#scadenze")] + ([("Testo ufficiale", x["link"])] if x.get("link") else []))


def status_notifications(state, baseline):
    st = load(os.path.join(DATA, "status.json"), {})
    if "ok" not in st:
        return
    was_ok = state.get("ultimo_ok", True)
    if not st["ok"] and was_ok and not baseline:
        problemi = "\n".join(f"• {clip(p, 160)}" for p in (st.get("problemi") or [])[:4])
        send("⚠️ Bollettino GU: aggiornamento non riuscito",
             (problemi or "Il controllo automatico non è andato a buon fine.") +
             "\nIl prossimo controllo riproverà da solo.",
             click=st.get("esecuzione") or SITE, tags=["warning"], priority=4)
    elif st["ok"] and not was_ok and not baseline:
        send("✅ Bollettino GU di nuovo aggiornato", "Il controllo automatico è tornato a funzionare.",
             click=SITE, tags=["white_check_mark"], priority=2)
    state["ultimo_ok"] = bool(st["ok"])


def now_s():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    if not TOPIC:
        print("Notifiche non attive: manca il segreto NTFY_TOPIC.")
        return
    today = dt.datetime.now(ROME).date()
    state = load(STATE, None)
    baseline = state is None
    state = state or {"inviate": {}}

    if TEST:
        send("🔔 Prova del Bollettino GU", "Le notifiche funzionano: qui arriveranno la Gazzetta del giorno, "
             "le novità dal Parlamento e le scadenze dei decreti-legge.", click=SITE, tags=["bell"])
    if baseline:
        send("🔔 Notifiche del Bollettino GU attive",
             "Da ora ricevi: le leggi di interesse di ogni Gazzetta, le novità dal Parlamento, "
             "i promemoria delle scadenze dei decreti-legge e un avviso se l'aggiornamento non riesce.",
             click=SITE, tags=["bell"], priority=3)

    for step in (lambda: status_notifications(state, baseline),
                 lambda: gu_notifications(state, today, baseline),
                 lambda: parl_notifications(state, baseline),
                 lambda: dl_notifications(state, today, baseline)):
        try:
            step()
        except Exception as e:           # una notifica mancata non deve fermare il controllo
            print(f"⚠️ Notifica non preparata: {type(e).__name__}: {e}")

    # si dimenticano le notifiche di più di 4 mesi fa
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["inviate"] = {k: v for k, v in state["inviate"].items() if v >= cutoff}
    os.makedirs(DATA, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"📱 Notifiche inviate in questo controllo: {len(sent_now)}.")
    return state


if __name__ == "__main__":
    main()
