"""
Novità dal Parlamento: dossier dei Servizi Studi e documenti acquisiti dalle commissioni.

Fonti (pagine pubbliche, lette con garbo: poche richieste, una pausa tra l'una e l'altra):
- temi.camera.it/leg19/dossier.html  — Documentazione parlamentare: dossier della Camera e, insieme,
  quelli del Servizio Studi del Senato (il sito del Senato blocca i programmi automatici con un filtro
  anti-robot, quindi i suoi dossier si prendono da qui).
- camera.it/leg19/1347 — "Documenti acquisiti" delle commissioni permanenti (memorie e contributi
  scritti depositati nelle audizioni e sui progetti di legge).

A ogni controllo confronta quello che trova con quello già visto (data/parlamento_visti.json):
le voci mai viste prima sono le novità. Al primo avvio registra tutto come "già visto" (così non
segnala come nuove centinaia di documenti vecchi) e mostra comunque le più recenti.

Scrive data/parlamento.json, letto dal sito. Solo libreria standard.
"""
import os
import re
import sys
import json
import time
import html
import hashlib
import datetime as dt
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
DATA = "data"
OUT = os.path.join(DATA, "parlamento.json")
SEEN = os.path.join(DATA, "parlamento_visti.json")
RUN_REPORT = os.environ.get("RUN_REPORT", "run_report_parlamento.json")
KEEP_DAYS = int(os.environ.get("PARL_KEEP_DAYS", "90"))       # quanto tenere le voci sul sito
BASELINE_DAYS = int(os.environ.get("PARL_BASELINE_DAYS", "30"))  # al primo avvio: voci recenti da mostrare
MAX_ITEMS = 700
PAUSE = float(os.environ.get("PARL_PAUSE", "2"))
UA = ("Mozilla/5.0 (compatible; BollettinoGU/1.0; +https://fulgei-a11y.github.io/bollettino-gu/) "
      "Python-urllib")

DOSSIER_URL = "https://temi.camera.it/leg19/dossier.html"
DOSSIER_PAGE = "https://temi.camera.it"
# Commissioni permanenti della Camera seguite: numero romano, nome, materia del bollettino.
# L'indirizzo segue lo schema shadow_organo_parlamentare=35NN&id_tipografico=NN.
COMMISSIONI = [
    (2, "II", "Giustizia", "Giustizia"),
    (5, "V", "Bilancio", "Economico"),
    (6, "VI", "Finanze", "Economico"),
    (8, "VIII", "Ambiente", "Energia e Ambiente"),
    (10, "X", "Attività produttive", "Economico"),
]


def comm_url(n):
    return f"https://www.camera.it/leg19/1347?shadow_organo_parlamentare={3500 + n}&id_tipografico={n:02d}"


# ---------------------------------------------------------------------------
def fetch(url, data=None, timeout=90):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "it-IT,it;q=0.9",
        **({"Content-Type": "application/x-www-form-urlencoded"} if body else {})})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.status != 200 or not raw:
                    raise RuntimeError(f"risposta {r.status} vuota")
                return raw.decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def key(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:14]


def materia_da_servizio(dep):
    d = dep.lower()
    if "giustizia" in d:
        return "Giustizia"
    if "ambiente" in d or "territorio" in d:
        return "Energia e Ambiente"
    if any(k in d for k in ("finanz", "bilancio", "economia", "produttive", "tesoro")):
        return "Economico"
    return ""




def atto(text):
    m = re.search(r"\b(A\.?\s?G\.?|Atto(?: del Governo)? n\.)\s*(\d{1,5})\b", text)
    if m:
        return f"A.G. {m[2]}"
    m = re.search(r"\b(?:A\.\s?)?C\.\s*(\d{1,5})\b", text)
    if m:
        return f"C. {m[1]}"
    m = re.search(r"\b(?:A\.\s?)?S\.\s*(\d{1,5})\b", text)
    return f"S. {m[1]}" if m else ""


# ---------------------------------------------------------------------------
# Dossier (temi.camera.it)
# ---------------------------------------------------------------------------
DOSSIER_ITEM = re.compile(r'<a class="dossier-home-link" href="([^"]+)">(.*?)</a>', re.S)


def parse_dossier(page):
    out = []
    for href, inner in DOSSIER_ITEM.findall(page):
        date = re.search(r'dossier-list-date">\s*(\d{2})\s+(\d{2})\s+(\d{4})', inner)
        dep = re.search(r'dossier-list-dep">(.*?)</div>', inner, re.S)
        title = re.search(r'dossier-list-title">(.*?)(?:<div class="dossier-list-mdash"|</div>)', inner, re.S)
        note = re.search(r'dossier-list-note">(.*?)</div>', inner, re.S)
        code = re.search(r"/dossier/([A-Z0-9]+-\d+)/", href)
        if not (date and title):
            continue
        dep_t = clean(dep[1]) if dep else ""
        t = clean(title[1])
        out.append({
            "id": "d-" + (code[1] if code else key(href)),
            "fonte": "dossier",
            "organo": dep_t,
            "materia": materia_da_servizio(dep_t),
            "titolo": t,
            "tipo": clean(note[1]) if note else "",
            "data": f"{date[3]}-{date[2]}-{date[1]}",
            "link": urllib.parse.urljoin(DOSSIER_PAGE, href),
            "atto": atto(t),
        })
    return out


def read_dossier(length=60):
    params = {"start": 0, "length": length, "facets": "", "facetsValues": "", "query": "", "scrollTo": ""}
    items = parse_dossier(fetch(DOSSIER_URL, params))
    if not items:
        raise RuntimeError("nessun dossier riconosciuto nella pagina: la struttura potrebbe essere cambiata")
    time.sleep(PAUSE)
    # quali sono anche del Senato (stesso elenco, filtrato per autore "Studi Senato")
    try:
        ss = {i["id"] for i in parse_dossier(fetch(DOSSIER_URL, {**params, "length": 40,
                                                                "facets": "ss~", "facetsValues": "Studi Senato~"}))}
    except Exception as e:
        print(f"   ⚠️ elenco dossier del Senato non letto: {e}")
        ss = set()
    for i in items:
        i["senato"] = i["id"] in ss
    return items


# ---------------------------------------------------------------------------
# Documenti acquisiti dalle commissioni (camera.it)
# ---------------------------------------------------------------------------
TS_RE = re.compile(r"\.(\d{2})-(\d{2})-(\d{4})-(\d{2})-(\d{2})-(\d{2})(?:\.\d+)?\.\w+$")
DOC_RE = re.compile(r'<li class="documentoLink"><a href="([^"]+)"(?: title="([^"]*)")?>(.*?)</a>', re.S)


def doc_kind(url):
    m = re.search(r"/leg19\.com\d+\.(\w+)\.([^./]+(?: [^./]+)*)\.PUBBLICO", url)
    if not m:
        return ""
    k = m[2].strip().lower()
    return {"memoria": "Memoria", "contributo scritto": "Contributo scritto"}.get(k, m[2].strip().capitalize())


def parse_commissione(page, comm):
    n, roman, nome, materia = comm
    start = page.find('class="doc_acquisiti_video_list"')
    if start < 0:
        return []
    body = page[start:]
    end = body.find("</body>")
    body = body[:end if end > 0 else None]
    out = []
    for block in body.split('<div class="no_link_bol_seduta">')[1:]:
        head = clean(block[:block.find("</div>")])
        ctx = re.search(r'<div class="autore_titolo">(.*?)</div>', block, re.S)
        ctx_t = clean(ctx[1]) if ctx else ""
        seduta = re.search(r"(\d{2})/(\d{2})/(\d{4})", head)
        for href, title, text in DOC_RE.findall(block):
            href = html.unescape(href)
            text_t = clean(text)
            ts = TS_RE.search(href)
            if ts:
                data, ora = f"{ts[3]}-{ts[2]}-{ts[1]}", f"{ts[4]}:{ts[5]}"
            else:
                m = re.search(r"\((\d{2})/(\d{2})/(\d{4})\)", text_t) or seduta
                data, ora = (f"{m[3]}-{m[2]}-{m[1]}" if m else ""), ""
            label = re.sub(r"\s*\(\d{2}/\d{2}/\d{4}\)\s*$", "", text_t)
            out.append({
                "id": "c-" + key(href),
                "fonte": "commissione",
                "organo": f"{roman} {nome}",
                "commissioni": [roman],
                "materia": materia,
                "titolo": label,
                "tipo": doc_kind(href),
                "contesto": ctx_t[:600],
                "seduta": head if head.lower().startswith("seduta") else "",
                "data": data, "ora": ora,
                "link": urllib.parse.quote(href, safe=":/?=&%#"),
                "pagina": comm_url(n),
                "atto": atto(label) or atto(ctx_t),
            })
    return out


# ---------------------------------------------------------------------------
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main(sources=None):
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.astimezone(ROME).date()
    os.makedirs(DATA, exist_ok=True)

    seen_doc = load_json(SEEN, None)
    first_run = seen_doc is None
    seen = set((seen_doc or {}).get("ids", []))
    prev = load_json(OUT, {})
    items = {v["id"]: v for v in prev.get("voci", [])}

    fonti, errors, found = [], [], []
    plan = sources or ([("dossier", "Dossier di Camera e Senato", DOSSIER_URL, read_dossier)] +
                       [(f"comm{c[0]}", f"{c[1]} Commissione {c[2]}", comm_url(c[0]),
                         (lambda c=c: parse_commissione(fetch(comm_url(c[0])), c))) for c in COMMISSIONI])
    for k, (fid, nome, url, reader) in enumerate(plan):
        if k:
            time.sleep(PAUSE)
        try:
            got = reader()
            if not got:
                raise RuntimeError("nessun documento riconosciuto: la struttura della pagina potrebbe essere cambiata")
            found += got
            fonti.append({"id": fid, "nome": nome, "url": url, "ok": True, "trovati": len(got)})
            print(f"🏛️  {nome}: {len(got)} voci lette.")
        except Exception as e:
            fonti.append({"id": fid, "nome": nome, "url": url, "ok": False, "errore": str(e)[:200]})
            errors.append(f"Parlamento – {nome}: {str(e)[:200]}")
            print(f"❌ {nome}: {e}")

    # stesso documento in più commissioni (audizioni congiunte): una voce sola
    merged = {}
    for it in found:
        if it["id"] in merged:
            m = merged[it["id"]]
            for r in it.get("commissioni", []):
                if r not in m["commissioni"]:
                    m["commissioni"].append(r)
            continue
        merged[it["id"]] = it

    new = []
    for iid, it in merged.items():
        if iid in seen:
            if iid in items:   # aggiorna i campi ma conserva quando è stato visto la prima volta
                keep = {k: items[iid][k] for k in ("visto", "iniziale") if k in items[iid]}
                items[iid] = {**it, **keep}
            continue
        seen.add(iid)
        if first_run:
            recent = it.get("data") and (today - dt.date.fromisoformat(it["data"])).days <= BASELINE_DAYS
            if recent:
                items[iid] = {**it, "visto": now_s, "iniziale": True}
        else:
            items[iid] = {**it, "visto": now_s}
            new.append(it)

    # pulizia: si tengono le voci degli ultimi KEEP_DAYS giorni
    def when(v):
        return v.get("data") or v.get("visto", "")[:10]
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    voci = [v for v in items.values() if (v.get("visto", "")[:10] >= cutoff or when(v) >= cutoff)]
    voci.sort(key=lambda v: (v.get("visto", ""), not v.get("iniziale"), when(v), v.get("ora", "")), reverse=True)
    voci = voci[:MAX_ITEMS]

    ok_any = any(f["ok"] for f in fonti)
    controlli = prev.get("controlli", [])
    if ok_any:
        controlli = ([{"quando": now_s, "nuovi": len(new)}] + controlli)[:30]
    out = {
        "aggiornato": now_s if ok_any else prev.get("aggiornato", ""),
        "iniziato": prev.get("iniziato") or now_s,
        "controlli": controlli,
        "fonti": fonti,
        "voci": voci,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    if ok_any:
        with open(SEEN, "w", encoding="utf-8") as f:
            json.dump({"ids": sorted(seen)}, f, separators=(",", ":"))

    msg = ("prima lettura: archivio inizializzato" if first_run else f"{len(new)} novità") + f", {len(voci)} voci sul sito"
    print(f"🏛️  Parlamento: {msg}.")
    # Un sito che per una volta non risponde è solo un avviso (si riprova al controllo dopo);
    # diventa un problema da segnalare se non risponde nessuna fonte o se una pagina ha cambiato forma.
    serious = (not ok_any) or any("struttura" in e for e in errors)
    with open(RUN_REPORT, "w", encoding="utf-8") as f:
        json.dump({"nuovi": len(new), "prima_lettura": first_run,
                   "errori": errors if serious else [], "avvisi": [] if serious else errors}, f, ensure_ascii=False)
    if serious:
        sys.exit(f"{len(errors)} fonti del Parlamento non lette.")


if __name__ == "__main__":
    main()
