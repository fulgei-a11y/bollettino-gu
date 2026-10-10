"""
Prepara i file "di servizio" del sito, a partire dalle edizioni salvate in data/:

1. Audio: tiene online solo gli MP3 degli ultimi AUDIO_DAYS giorni (default 60), per restare
   nei limiti di spazio di GitHub Pages. Le schede restano tutte: sparisce solo la lettura audio.
2. data/index.json      elenco delle edizioni (per il menu del sito)
3. data/search.json     indice compatto per la ricerca nell'archivio
4. data/scadenze.json   scadenzario: decreti-legge (entrata in vigore e 60 giorni per la conversione)
                        ed entrate in vigore di leggi e decreti legislativi
5. data/scadenze.ics    lo stesso scadenzario come calendario a cui iscriversi
6. data/podcast.xml     feed podcast con le letture audio (Apple Podcasts, Pocket Casts, ecc.)

Usa solo la libreria standard: si può lanciare anche in locale con  python tools/build_extras.py
"""
import os
import re
import json
import datetime as dt
from email.utils import format_datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
DATA = "data"
AUDIO = "audio"
AUDIO_DAYS = int(os.environ.get("AUDIO_DAYS", "60"))
SITE = os.environ.get("SITE_URL", "https://fulgei-a11y.github.io/bollettino-gu/").rstrip("/") + "/"
TODAY = dt.date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else dt.datetime.now(ROME).date()
RUN_REPORT = os.environ.get("RUN_REPORT", "run_report_extras.json")

MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
DATE_IT = r"(\d{1,2})[°º]?\s+(" + "|".join(MESI[1:]) + r")\s+(\d{4})"
DL_HEAD = re.compile(r"^DECRETO-LEGGE\s+" + DATE_IT + r",\s*n\.\s*(\d+)\s*(.*)$", re.I | re.S)
CONV = re.compile(r"Conversione in legge(?:,\s*con modificazioni,)?\s+del decreto-legge\s+"
                  + DATE_IT + r",\s*n\.\s*(\d+)", re.I)
MANCATA = re.compile(r"Mancata conversione del decreto-legge\s+" + DATE_IT + r",\s*n\.\s*(\d+)", re.I)
LAW_HEAD = re.compile(r"^(LEGGE\s+" + DATE_IT + r",\s*n\.\s*\d+)", re.I)
COORD_GU = re.compile(r"decreto-legge\s+" + DATE_IT + r",\s*n\.\s*(\d+)\s*\(in Gazzetta Ufficiale\s*-\s*Serie generale"
                      r"\s*-\s*n\.\s*(\d+)\s+del\s+" + DATE_IT + r"\)", re.I)


# ---------------------------------------------------------------------------
def it_date(day, month_name, year):
    return dt.date(int(year), MESI.index(month_name.lower()), int(day))


def parse_ddmmyyyy(s):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(s or ""))
    if not m:
        return None
    try:
        return dt.date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None


def fmt_it(d):
    return f"{d.day} {MESI[d.month]} {d.year}" if d else ""


def load_editions():
    eds = []
    for name in sorted(os.listdir(DATA), reverse=True):
        if re.match(r"\d{4}-\d{2}-\d{2}\.json$", name):
            try:
                with open(os.path.join(DATA, name), encoding="utf-8") as f:
                    eds.append(json.load(f))
            except Exception as e:
                print(f"⚠️ {name} non leggibile: {e}")
    return eds


def write_json(name, obj, compact=False):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 1. Audio degli ultimi 60 giorni
# ---------------------------------------------------------------------------
def prune_audio(eds):
    cutoff = TODAY - dt.timedelta(days=AUDIO_DAYS)
    removed, freed = [], 0
    if os.path.isdir(AUDIO):
        for name in os.listdir(AUDIO):
            m = re.match(r"(\d{4}-\d{2}-\d{2})\.(mp3|json)$", name)
            if m and dt.date.fromisoformat(m[1]) < cutoff:
                p = os.path.join(AUDIO, name)
                freed += os.path.getsize(p)
                os.remove(p)
                if name.endswith(".mp3"):
                    removed.append(m[1])
    for d in eds:
        if d.get("audio") and dt.date.fromisoformat(d["date"]) < cutoff:
            d.pop("audio", None)
            d.pop("duration", None)
            d["audio_scaduto"] = True
            write_json(f"{d['date']}.json", d)
    if removed:
        print(f"🧹 Audio tolti (più vecchi di {AUDIO_DAYS} giorni): {', '.join(sorted(removed))} — "
              f"{freed / 1048576:.1f} MB liberati.")
    total = sum(os.path.getsize(os.path.join(AUDIO, n)) for n in os.listdir(AUDIO)) if os.path.isdir(AUDIO) else 0
    print(f"🎧 Audio online: {total / 1048576:.1f} MB.")
    return removed, total


# ---------------------------------------------------------------------------
# 2. Indice delle edizioni
# ---------------------------------------------------------------------------
def build_index(eds):
    idx = [{"date": d["date"], "giorno": d.get("giorno", ""), "numero_gu": str(d.get("numero_gu", "")),
            "stato": d.get("stato", ""), "schede": len(d.get("schede") or []),
            "audio": bool(d.get("audio")), "updatedAt": d.get("updatedAt", "")} for d in eds]
    write_json("index.json", idx)
    return idx


# ---------------------------------------------------------------------------
# 3. Ricerca
# ---------------------------------------------------------------------------
def clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def build_search(eds):
    """Una riga per ogni scheda, atto segnalato, legge scartata e atto dell'edizione.
    k: s = scheda, a = altro atto segnalato, x = scartata, t = atto dell'indice,
    p = dossier o documento del Parlamento (da data/parlamento.json)."""
    rows = []
    for d in eds:
        base = {"d": d["date"], "n": str(d.get("numero_gu", ""))}
        seen = set()
        for i, s in enumerate(d.get("schede") or []):
            seen.add(s.get("codice_atto"))
            rows.append({**base, "k": "s", "i": i, "t": clip(s.get("titolo"), 220),
                         "r": clip(s.get("riferimento"), 140), "c": s.get("categoria", ""),
                         "x": clip(" ".join([s.get("contesto") or "", " ".join(s.get("misure") or []),
                                             s.get("chi_interessato") or ""]), 900),
                         "l": s.get("link", "")})
        for a in d.get("altri_atti") or []:
            seen.add(a.get("codice_atto"))
            rows.append({**base, "k": "a", "t": clip(a.get("titolo"), 220), "c": a.get("categoria", ""),
                         "x": clip(a.get("sintesi"), 400), "l": a.get("link", "")})
        for a in d.get("scartate") or []:
            seen.add(a.get("codice_atto"))
            rows.append({**base, "k": "x", "t": clip(a.get("titolo"), 220), "c": a.get("materia", ""),
                         "l": a.get("link", "")})
        for a in d.get("atti") or []:
            if a.get("codice") in seen:
                continue
            rows.append({**base, "k": "t", "t": clip(a.get("titolo"), 320), "l": a.get("link", "")})
    parl = {}
    try:
        with open(os.path.join(DATA, "parlamento.json"), encoding="utf-8") as f:
            parl = json.load(f)
    except Exception:
        pass
    for v in parl.get("voci") or []:
        org = v.get("organo", "")
        if v.get("fonte") == "commissione":
            org = "Commissione " + " e ".join(v.get("commissioni") or [org.split(" ")[0]])
        rows.append({"d": v.get("data") or v.get("visto", "")[:10], "n": "", "k": "p",
                     "t": clip(v.get("titolo"), 220),
                     "r": clip(" – ".join(x for x in (org, v.get("tipo"), v.get("atto")) if x), 140),
                     "c": v.get("materia", ""), "x": clip(v.get("contesto"), 500), "l": v.get("link", "")})
    write_json("search.json", rows, compact=True)
    size = os.path.getsize(os.path.join(DATA, "search.json"))
    print(f"🔎 Indice di ricerca: {len(rows)} voci, {size / 1024:.0f} KB.")
    return rows


# ---------------------------------------------------------------------------
# 4. Scadenzario
# ---------------------------------------------------------------------------
def build_deadlines(eds):
    dls = {}          # (anno, numero) -> decreto-legge
    conv, mancata, coord = {}, {}, {}

    def scheda_for(d, code):
        for i, s in enumerate(d.get("schede") or []):
            if s.get("codice_atto") == code:
                return i, s
        return None, None

    for d in eds:
        pub = dt.date.fromisoformat(d["date"])
        for a in d.get("atti") or []:
            title = a.get("titolo") or ""
            m = DL_HEAD.match(title.strip())
            if m:
                dl_date = it_date(m[1], m[2], m[3])
                key = (dl_date.year, int(m[4]))
                i, s = scheda_for(d, a.get("codice"))
                vig = parse_ddmmyyyy(a.get("vigore")) or parse_ddmmyyyy((s or {}).get("vigore"))
                dls[key] = {
                    "numero": int(m[4]), "anno": dl_date.year, "data_dl": dl_date.isoformat(),
                    "riferimento": f"Decreto-legge {fmt_it(dl_date)}, n. {int(m[4])}",
                    "titolo": clip((s or {}).get("titolo") or m[5] or title, 260),
                    "pubblicazione": pub.isoformat(), "numero_gu": str(d.get("numero_gu", "")),
                    "vigore": vig.isoformat() if vig else "",
                    "scadenza": (pub + dt.timedelta(days=60)).isoformat(),
                    "categoria": (s or {}).get("categoria", ""),
                    "scheda": i, "link": a.get("link", ""),
                }
            for mm in CONV.finditer(title):
                key = (int(mm[3]), int(mm[4]))
                law = LAW_HEAD.match(title.strip())
                conv[key] = {"legge": law[1] if law else "Legge di conversione", "data_gu": pub.isoformat(),
                             "numero_gu": str(d.get("numero_gu", "")), "link": a.get("link", ""),
                             "data_dl": it_date(mm[1], mm[2], mm[3]).isoformat(),
                             "recante": clip(title[mm.end():].lstrip(", ").removeprefix("recante").strip(" :«»"), 260)}
            for mm in MANCATA.finditer(title):
                key = (int(mm[3]), int(mm[4]))
                mancata[key] = {"data_gu": pub.isoformat(), "link": a.get("link", ""),
                                "data_dl": it_date(mm[1], mm[2], mm[3]).isoformat(),
                                "recante": clip(title[mm.end():].lstrip(", ").removeprefix("recante").strip(" :«»"), 260)}
            for mm in COORD_GU.finditer(title):
                coord[(int(mm[3]), int(mm[4]))] = it_date(mm[6], mm[7], mm[8]).isoformat()

    # decreti-legge pubblicati prima dell'inizio dell'archivio, noti solo dalla conversione
    for key, info in list(conv.items()) + list(mancata.items()):
        if key in dls:
            continue
        dl_date = dt.date.fromisoformat(info["data_dl"])
        pub = coord.get(key, "")
        dls[key] = {"numero": key[1], "anno": key[0], "data_dl": info["data_dl"],
                    "riferimento": f"Decreto-legge {fmt_it(dl_date)}, n. {key[1]}",
                    "titolo": (lambda t: t[:1].upper() + t[1:])(clip(info.get("recante") or "", 260).rstrip("».")),
                    "pubblicazione": pub, "numero_gu": "", "vigore": "",
                    "scadenza": (dt.date.fromisoformat(pub) + dt.timedelta(days=60)).isoformat() if pub else "",
                    "categoria": "", "scheda": None, "link": "", "fuori_archivio": True}

    out = []
    for key, dl in dls.items():
        if key in conv:
            dl["stato"], dl["conversione"] = "convertito", {k: conv[key][k] for k in ("legge", "data_gu", "numero_gu", "link")}
        elif key in mancata:
            dl["stato"], dl["conversione"] = "non_convertito", {k: mancata[key][k] for k in ("data_gu", "link")}
        elif dl["scadenza"] and dt.date.fromisoformat(dl["scadenza"]) < TODAY:
            dl["stato"] = "termine_scaduto"
        else:
            dl["stato"] = "in_conversione"
        if dl["scadenza"]:
            dl["giorni_mancanti"] = (dt.date.fromisoformat(dl["scadenza"]) - TODAY).days
        out.append(dl)
    active = sorted([x for x in out if x["stato"] in ("in_conversione", "termine_scaduto")],
                    key=lambda x: x["scadenza"])
    # i conclusi: dal più recente
    closed = sorted([x for x in out if x["stato"] not in ("in_conversione", "termine_scaduto")],
                    key=lambda x: x.get("conversione", {}).get("data_gu", ""), reverse=True)

    # entrate in vigore di leggi e decreti legislativi (dalle schede e dagli atti principali)
    vig, seen = [], set()
    for d in eds:
        for i, s in enumerate(d.get("schede") or []):
            rif = s.get("riferimento") or ""
            v = parse_ddmmyyyy(s.get("vigore"))
            if not v or rif.upper().startswith("DECRETO-LEGGE"):
                continue
            seen.add(s.get("codice_atto"))
            vig.append({"data": v.isoformat(), "riferimento": rif, "titolo": clip(s.get("titolo"), 220),
                        "categoria": s.get("categoria", ""), "edizione": d["date"], "scheda": i,
                        "link": s.get("link", "")})
        for a in d.get("atti") or []:
            v = parse_ddmmyyyy(a.get("vigore"))
            if not v or a.get("codice") in seen or a.get("tipo") == "DECRETO-LEGGE":
                continue
            head = re.match(r"^((?:LEGGE|DECRETO LEGISLATIVO|LEGGE COSTITUZIONALE)\s+" + DATE_IT + r",\s*n\.\s*\d+)\s*(.*)$",
                            a.get("titolo") or "", re.I | re.S)
            vig.append({"data": v.isoformat(), "riferimento": head[1] if head else "",
                        "titolo": clip(head[5] if head else a.get("titolo"), 220), "categoria": "",
                        "edizione": d["date"], "scheda": None, "link": a.get("link", "")})
    vig = [v for v in vig if dt.date.fromisoformat(v["data"]) >= TODAY - dt.timedelta(days=30)]
    vig.sort(key=lambda v: v["data"])

    result = {"generato": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "oggi": TODAY.isoformat(), "decreti_legge": active + closed, "entrate_in_vigore": vig}
    write_json("scadenze.json", result)
    print(f"📅 Scadenzario: {len(active)} decreti-legge in corso, {len(closed)} conclusi, "
          f"{len(vig)} entrate in vigore.")
    return result


# ---------------------------------------------------------------------------
# 5. Calendario .ics
# ---------------------------------------------------------------------------
def ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    raw = line.encode("utf-8")
    if len(raw) <= 74:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > 73:
            out.append(cur.decode("utf-8"))
            cur = b" " + b
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def build_ics(sc):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Bollettino GU//Scadenzario//IT",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Bollettino GU – Scadenze",
             "X-WR-TIMEZONE:Europe/Rome", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]

    def event(uid, day, summary, desc, url, alarm_days=None):
        d0 = dt.date.fromisoformat(day)
        ev = ["BEGIN:VEVENT", f"UID:{uid}@bollettino-gu", f"DTSTAMP:{stamp}",
              f"DTSTART;VALUE=DATE:{d0:%Y%m%d}", f"DTEND;VALUE=DATE:{d0 + dt.timedelta(days=1):%Y%m%d}",
              f"SUMMARY:{ics_text(summary)}", f"DESCRIPTION:{ics_text(desc)}", "TRANSP:TRANSPARENT"]
        if url:
            ev.append(f"URL:{url}")
        if alarm_days:
            ev += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{ics_text(summary)}",
                   f"TRIGGER:-P{alarm_days}D", "END:VALARM"]
        ev.append("END:VEVENT")
        lines.extend(ev)

    for dl in sc["decreti_legge"]:
        if dl.get("fuori_archivio"):
            continue
        tag = f"dl-{dl['anno']}-{dl['numero']}"
        link = f"{SITE}#{dl['pubblicazione']}" if dl.get("pubblicazione") else SITE
        if dl["stato"] == "in_conversione" and dl.get("scadenza"):
            event(f"{tag}-scadenza", dl["scadenza"], f"Scade il DL n. {dl['numero']}/{dl['anno']} (60 giorni)",
                  f"{dl['riferimento']} – {dl['titolo']}\nUltimo giorno utile per la conversione in legge "
                  f"(pubblicato in GU il {fmt_it(dt.date.fromisoformat(dl['pubblicazione']))}).\n{link}",
                  link, alarm_days=7)
        if dl.get("conversione") and dl["stato"] == "convertito":
            event(f"{tag}-convertito", dl["conversione"]["data_gu"], f"Convertito il DL n. {dl['numero']}/{dl['anno']}",
                  f"{dl['conversione']['legge']} – conversione del {dl['riferimento']}.", dl["conversione"].get("link", ""))
        if dl.get("vigore"):
            event(f"{tag}-vigore", dl["vigore"], f"In vigore il DL n. {dl['numero']}/{dl['anno']}",
                  f"{dl['riferimento']} – {dl['titolo']}\n{link}", link)
    for v in sc["entrate_in_vigore"]:
        uid = re.sub(r"[^a-z0-9]+", "-", (v["riferimento"] or v["titolo"]).lower()).strip("-")[:60]
        link = f"{SITE}#{v['edizione']}"
        event(f"vigore-{uid}", v["data"], f"In vigore: {v['riferimento'] or v['titolo'][:60]}",
              f"{v['titolo']}\n{link}", link, alarm_days=1)
    lines.append("END:VCALENDAR")
    with open(os.path.join(DATA, "scadenze.ics"), "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(ics_fold(x) for x in lines) + "\r\n")


# ---------------------------------------------------------------------------
# 6. Feed podcast
# ---------------------------------------------------------------------------
def build_podcast(eds):
    items = []
    for d in eds:
        if not d.get("audio") or not os.path.exists(d["audio"]):
            continue
        day = dt.date.fromisoformat(d["date"])
        pub = dt.datetime(day.year, day.month, day.day, 21, 0, tzinfo=ROME)
        titles = [s.get("titolo", "") for s in d.get("schede") or []]
        desc = d.get("sintesi") or "Nessuna legge di interesse per le materie seguite in questa edizione."
        if titles:
            desc += "\n\nSchede:\n" + "\n".join(f"• {t}" for t in titles)
        desc += f"\n\nLeggi le schede: {SITE}#{d['date']}"
        n = f"n. {d['numero_gu']} – " if d.get("numero_gu") else ""
        dur = int(d.get("duration") or 0)
        items.append(f"""    <item>
      <title>{escape(f"GU {n}{d.get('giorno', '').capitalize()} {fmt_it(day)}")}</title>
      <description>{escape(desc)}</description>
      <itunes:summary>{escape(desc)}</itunes:summary>
      <link>{SITE}#{d['date']}</link>
      <guid isPermaLink="false">bollettino-gu-{d['date']}</guid>
      <pubDate>{format_datetime(pub)}</pubDate>
      <enclosure url="{SITE}{d['audio']}" length="{os.path.getsize(d['audio'])}" type="audio/mpeg"/>
      <itunes:duration>{dur // 3600:02d}:{dur % 3600 // 60:02d}:{dur % 60:02d}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Bollettino GU</title>
    <link>{SITE}</link>
    <atom:link href="{SITE}data/podcast.xml" rel="self" type="application/rss+xml"/>
    <language>it-it</language>
    <description>La Gazzetta Ufficiale (Serie Generale) letta ogni giorno: leggi, decreti-legge e decreti legislativi in materia economica, di giustizia, energia e ambiente. Sono disponibili le edizioni degli ultimi {AUDIO_DAYS} giorni.</description>
    <itunes:author>Bollettino GU</itunes:author>
    <itunes:summary>La Gazzetta Ufficiale (Serie Generale) letta ogni giorno: leggi, decreti-legge e decreti legislativi in materia economica, di giustizia, energia e ambiente.</itunes:summary>
    <itunes:image href="{SITE}icons/podcast-1400.png"/>
    <image><url>{SITE}icons/podcast-1400.png</url><title>Bollettino GU</title><link>{SITE}</link></image>
    <itunes:category text="Government"/>
    <itunes:category text="News"><itunes:category text="Politics"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""
    with open(os.path.join(DATA, "podcast.xml"), "w", encoding="utf-8") as f:
        f.write(feed)
    print(f"🎙️ Feed podcast: {len(items)} puntate.")


def main():
    eds = load_editions()
    removed, total = prune_audio(eds)
    eds = load_editions()
    build_index(eds)
    build_search(eds)
    sc = build_deadlines(eds)
    build_ics(sc)
    build_podcast(eds)
    with open(RUN_REPORT, "w", encoding="utf-8") as f:
        json.dump({"audio_tolti": removed, "audio_mb": round(total / 1048576, 1), "errori": []}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
