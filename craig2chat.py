#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["faster-whisper"]
# ///
"""craig2chat — trascrive una registrazione Craig (una traccia per persona)
e la trasforma in una chat in stile WhatsApp (chat.html + chat.txt).

Uso:
  craig2chat CARTELLA_O_ZIP [-o USCITA] [--model large-v3] [--lang it]
             [--rename vecchio=Nuovo ...] [--skip nome ...]
"""
import argparse, datetime as dt, html, json, os, re, subprocess, sys, tempfile, zipfile

AUDIO_EXT = {".aac", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".wav", ".mp3", ".wma"}
GAP = 2.0    # secondi di pausa oltre i quali si apre una nuova bolla
PAUSE = 0.8  # secondi di pausa che chiudono una frase


def load_audio(path):
    import numpy as np
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def read_info(folder):
    info = {"start": None, "title": os.path.basename(os.path.abspath(folder))}
    p = os.path.join(folder, "info.txt")
    if not os.path.exists(p):
        return info
    txt = open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r"Start time:\s*(\S+)", txt)
    if m:
        info["start"] = dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    g = re.search(r"Guild:\s*(.+?)\s*\(", txt)
    c = re.search(r"Channel:\s*(.+?)\s*\(", txt)
    if g:
        info["title"] = g.group(1) + (f" · #{c.group(1)}" if c else "")
    return info


def speaker_name(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    return re.sub(r"^\d+-", "", name)


def transcribe(files, model_name, lang, threads):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="auto", compute_type="int8", cpu_threads=threads)
    words = []
    for f, who in files:
        print(f"  trascrivo {who} …", file=sys.stderr, flush=True)
        segs, _ = model.transcribe(load_audio(f), language=lang, vad_filter=True,
                                   word_timestamps=True, beam_size=5)
        n = 0
        for s in segs:
            for w in s.words or []:
                if w.word.strip():
                    words.append({"who": who, "start": w.start, "end": w.end, "w": w.word})
                    n += 1
        print(f"    {n} parole", file=sys.stderr)
    return words


def sentences(words):
    """Taglia le parole di un parlante in frasi: a fine frase o dopo una pausa."""
    out = []
    for w in words:
        cur = out[-1] if out else None
        if cur and not cur["closed"] and w["start"] - cur["end"] <= PAUSE:
            cur["text"] += w["w"]
            cur["end"] = w["end"]
        else:
            cur = {"who": w["who"], "t": w["start"], "end": w["end"], "text": w["w"]}
            out.append(cur)
        cur["closed"] = w["w"].rstrip().endswith((".", "!", "?", "…"))
    return out


def build_messages(words):
    """Intreccia le frasi di tutti in ordine di tempo e unisce quelle vicine dello stesso parlante."""
    units = []
    for who in dict.fromkeys(w["who"] for w in words):
        units += sentences([w for w in words if w["who"] == who])
    units.sort(key=lambda u: u["t"])
    msgs = []
    for u in units:
        last = msgs[-1] if msgs else None
        if last and last["who"] == u["who"] and u["t"] - last["end"] <= GAP:
            last["text"] += u["text"]
            last["end"] = u["end"]
        else:
            msgs.append({"who": u["who"], "t": round(u["t"], 2), "end": u["end"], "text": u["text"]})
    for m in msgs:
        t = m["text"].strip()
        m["text"] = t[:1].upper() + t[1:]
        del m["end"]
    return msgs


def fmt_offset(s):
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def write_txt(path, info, msgs):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{info['title']}\n\n")
        for m in msgs:
            when = fmt_offset(m["t"])
            if info["start"]:
                when = (info["start"] + dt.timedelta(seconds=m["t"])).astimezone().strftime("%H:%M:%S")
            f.write(f"[{when}] {m['who']}: {m['text']}\n")


PALETTE = ["--n1", "--n2", "--n3", "--n4", "--n5", "--n6"]

TEMPLATE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "template.html")


def write_html(path, info, msgs, speakers):
    data = {
        "title": info["title"],
        "start": info["start"].isoformat() if info["start"] else None,
        "people": {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(speakers)},
        "msgs": msgs,
    }
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    tpl = open(TEMPLATE, encoding="utf-8").read()
    out = tpl.replace("__TITLE__", html.escape(info["title"])).replace("__DATA__", js)
    open(path, "w", encoding="utf-8").write(out)


def main():
    ap = argparse.ArgumentParser(description="Registrazione Craig → chat in stile WhatsApp")
    ap.add_argument("input", help="cartella o file .zip scaricato da Craig")
    ap.add_argument("-o", "--out", help="cartella di uscita (default: la cartella di input, o accanto allo zip)")
    ap.add_argument("--model", default="large-v3", help="modello Whisper: tiny, base, small, medium, large-v3 (default)")
    ap.add_argument("--lang", default="it", help="lingua parlata (default: it)")
    ap.add_argument("--rename", action="append", default=[], metavar="VECCHIO=NUOVO", help="rinomina un parlante")
    ap.add_argument("--skip", action="append", default=[], metavar="NOME", help="ignora una traccia (es. un bot musicale)")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()

    tmp = None
    folder = a.input
    if zipfile.is_zipfile(a.input):
        tmp = tempfile.TemporaryDirectory(prefix="craig2chat-")
        with zipfile.ZipFile(a.input) as z:
            z.extractall(tmp.name)
        folder = tmp.name
        default_out = os.path.splitext(os.path.abspath(a.input))[0] + "-chat"
    elif os.path.isdir(a.input):
        default_out = a.input
    else:
        sys.exit(f"errore: {a.input} non è né una cartella né uno zip")

    renames = dict(r.split("=", 1) for r in a.rename)
    files = []
    for root, _, names in os.walk(folder):
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in AUDIO_EXT:
                who = speaker_name(n)
                if who in a.skip:
                    continue
                files.append((os.path.join(root, n), renames.get(who, who)))
    if not files:
        sys.exit(f"errore: nessuna traccia audio trovata in {a.input}")

    info = read_info(folder)
    print(f"{len(files)} tracce, modello {a.model}", file=sys.stderr)
    msgs = build_messages(transcribe(files, a.model, a.lang, a.threads))

    out = a.out or default_out
    os.makedirs(out, exist_ok=True)
    speakers = list(dict.fromkeys(w for _, w in files))
    write_html(os.path.join(out, "chat.html"), info, msgs, speakers)
    write_txt(os.path.join(out, "chat.txt"), info, msgs)
    print(f"fatto: {os.path.join(out, 'chat.html')}\n       {os.path.join(out, 'chat.txt')}", file=sys.stderr)


if __name__ == "__main__":
    main()
