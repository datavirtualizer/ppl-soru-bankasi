#!/usr/bin/env python3
"""19 Annex videosunu tek dikey videoda birleştirir.

    python3 scripts/build_reel.py

Çıktı: videos/annex-reel.mp4 — 1080x1920 (9:16), her klip 6 sn,
geçişlerde 0,6 sn crossfade. Üstte "ANNEX N", altta Annex adı ve hatırlama çengeli.

Üç aşama:
  1) Her klip dikey tuvale yerleştirilir (yazısız)
  2) xfade zinciriyle birleştirilir
  3) Yazılar EN SON, zaman aralığına göre basılır

Yazı neden en sonda: kliplerin üstüne önce yazıp sonra crossfade yaparsan geçiş
anında iki klibin yazısı üst üste binip hayalet gibi görünüyor. Sonda basınca her
yazı kendi aralığında tek başına ve net duruyor; geçiş sırasında ikisi de gizli.

Türkçe karakterler için drawtext'e metin `textfile=` ile veriliyor (komut satırı
kaçışı derdi olmasın diye).
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "videos"
WORK = VIDEOS / "_reel"
OUT = VIDEOS / "annex-reel.mp4"

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"

W, H = 1080, 1920
VIDEO_TOP = 430
CLIP = 6.0
XFADE = 0.6
MARGIN = 0.25          # yazı geçişten bu kadar sonra girer / önce çıkar
BG = "0x141420"

ANNEX = {
    1: ("Personel Lisanslandırma", "1 = tek kişi, elinde lisansı"),
    2: ("Hava Kuralları", "2 = gidiş-geliş şeritli yol"),
    3: ("Meteorolojik Hizmetler", "3 = yan yatmış bulut"),
    4: ("Havacılık Haritaları", "4 = dört ana yön, pusula"),
    5: ("Ölçü Birimleri", "5 = beş parmak, karışla ölç"),
    6: ("Hava Aracının İşletilmesi", "6 = uçağın altı, tekerlek yerde"),
    7: ("Milliyet ve Tescil İşaretleri", "7 = kuyruk dikmesi, TC-ABC"),
    8: ("Uçuşa Elverişlilik", "8 = yan yatınca sonsuz, hep uçar"),
    9: ("Kolaylaştırma", "9 = uzun kuyruk, pasaport sırası"),
    10: ("Havacılık Haberleşmesi", "10 = telefon, 10-4 roger"),
    11: ("Hava Trafik Hizmetleri", "11 = iki paralel iz, ayırma"),
    12: ("Arama ve Kurtarma", "12 = 112 acil"),
    13: ("Kaza ve Olay İncelemesi", "13 = uğursuz sayı"),
    14: ("Havaalanları", "14 = pist numarası"),
    15: ("Havacılık Bilgi Hizmetleri", "15 = pist başındaki bilgi panosu"),
    16: ("Çevresel Koruma", "16 = oksijenin atom ağırlığı"),
    17: ("Havacılık Güvenliği", "17 = dedektör kapısı + X-ray bandı"),
    18: ("Tehlikeli Maddeler", "18 = 18 yaşından küçüklere tehlikeli"),
    19: ("Emniyet Yönetimi (SMS)", "19 = listenin sonu, en yeni"),
}


def run(cmd: list[str], stage: str) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"ffmpeg hatası ({stage}):\n{p.stderr[-1500:]}")


def stage1_clips() -> list[Path]:
    out = []
    for n in sorted(ANNEX):
        src = VIDEOS / f"annex-{n:02d}.mp4"
        dst = WORK / f"{n:02d}.mp4"
        vf = f"scale={W}:{W},pad={W}:{H}:0:{VIDEO_TOP}:color={BG},format=yuv420p"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf,
             "-t", str(CLIP), "-r", "24", "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(dst)], f"klip {n}")
        out.append(dst)
        print(f"  klip {n:2d}/19", flush=True)
    return out


def stage2_concat(clips: list[Path]) -> Path:
    dst = WORK / "joined.mp4"
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    step = CLIP - XFADE
    parts, prev = [], "0:v"
    for i in range(1, len(clips)):
        label = f"v{i}"
        parts.append(
            f"[{prev}][{i}:v]xfade=transition=fade:"
            f"duration={XFADE}:offset={round(step*i, 3)}[{label}]"
        )
        prev = label

    run(["ffmpeg", "-v", "error", "-y", *inputs,
         "-filter_complex", ";".join(parts), "-map", f"[{prev}]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(dst)], "birleştirme")
    return dst


def stage3_text(joined: Path) -> None:
    """Her Annex'in yazısını yalnızca kendi zaman aralığında göster."""
    step = CLIP - XFADE
    filters = []

    for idx, n in enumerate(sorted(ANNEX)):
        name, hook = ANNEX[n]
        start = idx * step + MARGIN
        end = idx * step + CLIP - XFADE - MARGIN
        if idx == len(ANNEX) - 1:
            end = idx * step + CLIP - MARGIN
        show = f":enable='between(t,{round(start,3)},{round(end,3)})'"

        for key, text, font, size, y, color in (
            ("t", f"ANNEX {n}", FONT_BOLD, 108, 215, "white"),
            ("n", name, FONT_BOLD, 52, VIDEO_TOP + W + 90, "white"),
            ("h", hook, FONT_REG, 38, VIDEO_TOP + W + 175, "0xa8a8c0"),
        ):
            tf = WORK / f"txt-{n:02d}-{key}.txt"
            tf.write_text(text, encoding="utf-8")
            filters.append(
                f"drawtext=fontfile='{font}':textfile='{tf}':fontsize={size}:"
                f"fontcolor={color}:x=(w-text_w)/2:y={y}{show}"
            )

    run(["ffmpeg", "-v", "error", "-y", "-i", str(joined),
         "-vf", ",".join(filters),
         "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], "yazılar")


def main() -> None:
    missing = [n for n in ANNEX if not (VIDEOS / f"annex-{n:02d}.mp4").exists()]
    if missing:
        sys.exit(f"eksik video: {missing} — önce scripts/generate_videos.py çalıştır")

    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    clips = stage1_clips()
    print("birleştiriliyor…", flush=True)
    joined = stage2_concat(clips)
    print("yazılar basılıyor…", flush=True)
    stage3_text(joined)
    shutil.rmtree(WORK)

    size = OUT.stat().st_size / 1_000_000
    total = CLIP * len(ANNEX) - XFADE * (len(ANNEX) - 1)
    print(f"\n{OUT}  ({size:.1f} MB, ~{total:.0f} sn, {W}x{H})")


if __name__ == "__main__":
    main()
