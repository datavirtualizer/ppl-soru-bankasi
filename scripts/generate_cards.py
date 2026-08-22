#!/usr/bin/env python3
"""notes/annex-kart-promptlari.md içindeki 19 prompt'u yerel `grok` CLI ile üretir.

Grok Build'in içindeki `image_gen` aracını kullanır — ayrı bir API anahtarı gerekmez,
CLI'de zaten açık olan oturumu kullanır (yani senin Grok kotandan harcar).

    python3 scripts/generate_cards.py            # eksik olan tüm kartlar
    python3 scripts/generate_cards.py 3 7 12     # sadece belirli Annex'ler
    python3 scripts/generate_cards.py --force 15 # var olanı yeniden üret

Görüntüler cards/annex-01.png ... cards/annex-19.png olarak kaydedilir.
Var olan dosyanın üstüne yazmaz (--force hariç).

Neden bu kadar dolambaçlı: `grok` bir TUI; iş bittikten sonra kendiliğinden çıkmıyor
ve TTY olmadan başlamıyor. Bu yüzden `script` ile sahte bir terminal veriyoruz,
hedef dosyanın oluşmasını bekliyoruz ve süreci kendimiz sonlandırıyoruz.
"""

import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = ROOT / "notes" / "annex-kart-promptlari.md"
OUT_DIR = ROOT / "cards"

STYLE = (
    "Flat vector illustration, bold clean outlines, single centered subject, solid pastel "
    "background, aviation flashcard style, high contrast, "
    "no words or letters anywhere in the image."
)

TIMEOUT = 300          # tek kart için üst sınır (saniye)
MIN_SIZE = 10_000      # bundan küçük dosya yarım yazılmış sayılır


def parse_prompts() -> dict[int, tuple[str, str]]:
    """Markdown'dan {annex_no: (baslik, prompt)} çıkarır."""
    text = PROMPT_FILE.read_text(encoding="utf-8")
    pattern = re.compile(r"\*\*(\d{1,2}) — ([^*]+)\*\*\s*\n```\n(.*?)\n```", re.DOTALL)
    return {
        int(m.group(1)): (m.group(2).strip(), " ".join(m.group(3).split()))
        for m in pattern.finditer(text)
    }


def generate(n: int, body: str) -> str:
    out = OUT_DIR / f"annex-{n:02d}.png"
    instruction = (
        f"Use the image_gen tool to create ONE image with aspect_ratio 1:1, then save "
        f"the resulting image file to {out} using your file tools. "
        f"Prompt for image_gen: '{body} {STYLE}' "
        f"Do not ask any questions and do not do anything else."
    )

    proc = subprocess.Popen(
        ["script", "-q", "/dev/null", "grok", "--no-alt-screen", "--always-approve", instruction],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,   # kendi süreç grubu → tek seferde öldürülebilir
    )

    deadline = time.time() + TIMEOUT
    done = False
    while time.time() < deadline:
        if out.exists() and out.stat().st_size > MIN_SIZE:
            time.sleep(3)         # yazma bitsin
            done = True
            break
        if proc.poll() is not None:
            break
        time.sleep(2)

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    if done:
        return "ok"
    return "zaman aşımı" if time.time() >= deadline else "üretilemedi"


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv

    prompts = parse_prompts()
    if not prompts:
        sys.exit(f"hata: {PROMPT_FILE} içinde prompt bulunamadı")

    wanted = [int(a) for a in args] or sorted(prompts)
    OUT_DIR.mkdir(exist_ok=True)

    ok = 0
    for n in wanted:
        if n not in prompts:
            print(f"Annex {n:2d}: prompt yok, atlandı", flush=True)
            continue
        out = OUT_DIR / f"annex-{n:02d}.png"
        if out.exists() and not force:
            print(f"Annex {n:2d}: zaten var, atlandı", flush=True)
            ok += 1
            continue
        if force and out.exists():
            out.unlink()

        title, body = prompts[n]
        t0 = time.time()
        result = generate(n, body)
        print(f"Annex {n:2d}: {result:12s} {int(time.time()-t0):3d}s  ({title})", flush=True)
        if result == "ok":
            ok += 1

    print(f"\n{ok}/{len(wanted)} kart hazır → {OUT_DIR}")


if __name__ == "__main__":
    main()
