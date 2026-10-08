#!/usr/bin/env python3
"""Genera l'MP3 di narrazione di un'edizione del "Bollettino GU" con la voce
italiana Paola (sherpa-onnx, offline, gia' usata per Rassegna ER / Digest Radicale).

Uso:  python3 build_audio.py --text AAAA-MM-GG.txt --date AAAA-MM-GG --out ./audio_out
Input: un file di testo semplice con la narrazione completa dell'edizione (gia' in
italiano discorsivo, frasi separate da punteggiatura normale).
Produce: out/AAAA-MM-GG.mp3 e out/AAAA-MM-GG.json = {"date","audio","duration"}.
"""
import argparse, json, os, re, subprocess, sys, tarfile, tempfile, wave, shutil

SHERPA_VER = "1.12.14"
SHERPA_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/v{SHERPA_VER}/sherpa-onnx-v{SHERPA_VER}-linux-x64-shared.tar.bz2"
VOICE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-it_IT-paola-medium.tar.bz2"
CACHE = os.path.expanduser("~/.cache/bollettino-gu-tts")


def ensure_engine():
    root = os.path.join(CACHE, f"sherpa-onnx-v{SHERPA_VER}-linux-x64-shared")
    vdir = os.path.join(CACHE, "vits-piper-it_IT-paola-medium")
    os.makedirs(CACHE, exist_ok=True)
    for url, check in ((SHERPA_URL, root), (VOICE_URL, vdir)):
        if not os.path.isdir(check):
            arc = os.path.join(CACHE, os.path.basename(url))
            subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "-o", arc, url], check=True)
            with tarfile.open(arc) as t:
                t.extractall(CACHE)
    return root, vdir


def normalize(s):
    s = re.sub(r"\s+", " ", s)
    s = s.replace("€", " euro").replace("%", " per cento")
    s = re.sub(r"(^|[\s(:])\+(\d)", r"\1più \2", s)
    s = re.sub(r"(^|[\s(:])-(\d)", r"\1meno \2", s)
    s = re.sub(r"\s[—–]\s", ". ", s).replace("—", ", ").replace("·", ",")
    s = re.sub(r"[\"«»“”*_#]", "", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def split_long(text, limit=600):
    parts, buf = [], ""
    for p in re.split(r"(?<=[.!?;])\s+", text):
        if len(buf) + len(p) + 1 > limit and buf:
            parts.append(buf); buf = p
        else:
            buf = (buf + " " + p).strip()
    if buf:
        parts.append(buf)
    return parts


def synth_all(jobs, root, vdir, workers=3):
    from concurrent.futures import ThreadPoolExecutor
    exe = os.path.join(root, "bin", "sherpa-onnx-offline-tts")
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(root, "lib"))
    base = [exe, f"--vits-model={vdir}/it_IT-paola-medium.onnx", f"--vits-tokens={vdir}/tokens.txt",
            f"--vits-data-dir={vdir}/espeak-ng-data", "--num-threads=1", "--vits-length-scale=1.0"]

    def one(job):
        text, out = job
        for _ in range(2):
            r = subprocess.run(base + [f"--output-filename={out}", text], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0 and os.path.exists(out):
                return True
        return False
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, jobs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root, vdir = ensure_engine()
    os.makedirs(a.out, exist_ok=True)
    raw = open(a.text, encoding="utf-8").read()
    pieces = split_long(normalize(raw))
    if not pieces:
        sys.exit("Testo vuoto")
    tmp = tempfile.mkdtemp()
    jobs = [(p, os.path.join(tmp, f"{i:04d}.wav")) for i, p in enumerate(pieces)]
    ok = synth_all(jobs, root, vdir)
    if sum(ok) < len(jobs) * 0.95:
        sys.exit(f"Sintesi fallita per {len(jobs) - sum(ok)} pezzi su {len(jobs)}")
    rate, t = None, 0.0
    full = os.path.join(tmp, "full.wav")
    with wave.open(full, "wb") as w:
        for _, p in jobs:
            if not os.path.exists(p):
                continue
            with wave.open(p, "rb") as r:
                if rate is None:
                    rate = r.getframerate()
                    w.setnchannels(1); w.setsampwidth(r.getsampwidth()); w.setframerate(rate)
                w.writeframes(r.readframes(r.getnframes())); t += r.getnframes() / rate
                w.writeframes(b"\x00\x00" * int(rate * 0.25)); t += 0.25
    mp3 = os.path.join(a.out, f"{a.date}.mp3")
    for br in ("40k", "32k", "24k"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", full, "-ac", "1", "-ar", "22050",
                        "-codec:a", "libmp3lame", "-b:a", br, mp3], check=True)
        if os.path.getsize(mp3) < 14 * 1024 * 1024:
            break
    meta = {"date": a.date, "audio": f"audio/{a.date}.mp3", "duration": round(t, 1)}
    json.dump(meta, open(os.path.join(a.out, f"{a.date}.json"), "w"), ensure_ascii=False)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"OK {mp3} {os.path.getsize(mp3)//1024} KB, {t/60:.1f} min")


if __name__ == "__main__":
    main()
