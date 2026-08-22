#!/usr/bin/env python3
"""cards/annex-NN.png kartlarını 6 saniyelik videoya çevirir.

Grok CLI'nin `image_to_video` aracını KULLANMAZ — o araç ZDR hesaplarında
HTTP 400 (output.upload_url) veriyor. Bunun yerine ~/.grok/bin/grok-image-to-video
script'ini çağırır; o da doğrudan https://api.x.ai/v1/videos/generations API'sine
gidip işi poll eder ve mp4'ü indirir.

    python3 scripts/generate_videos.py            # eksik olan tüm videolar
    python3 scripts/generate_videos.py 3 7        # sadece belirli Annex'ler
    python3 scripts/generate_videos.py --force 5  # var olanı yeniden üret

Çıktı: videos/annex-01.mp4 … annex-19.mp4  (544x544, 24 fps, 6 sn, ~2 MB)
Kart başına ~35 saniye.

Hareket promptları kısa ve tek eylemli tutuldu: Imagine skill'i karmaşık hareketin
bozulduğunu, asıl işi kompozisyon ve tek net kamera hareketinin yaptığını söylüyor.
Rakam her karede okunaklı kalmalı — hareket rakamı değil, sahneyi taşımalı.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
OUT_DIR = ROOT / "videos"
SCRIPT = Path.home() / ".grok" / "bin" / "grok-image-to-video"
DURATION = 6

# Kamera hareketi rakamı kırpıyor ya da bozuyor. İlk turda 1, 9, 14, 17'de rakam
# kadraj dışında kaldı; 3, 5, 6, 11'de formu bozuldu; 15'te tabela "20" yazdı.
# Çözüm: kamerayı sabitle, rakamın değişmeyeceğini açıkça söyle, sadece küçük bir
# öğeyi hareket ettir. HOLD öneki bunu her prompta taşıyor.
HOLD = "camera holds completely still, no zoom and no pan, "

MOTION = {
    1: HOLD + "the giant numeral 1 stays fully in frame and unchanged, only the pilot lowers the license card and gives a small salute",
    2: "the two airliners glide along the road lanes in opposite directions, slow camera pan",
    3: HOLD + "the cloud keeps its exact numeral 3 shape and never changes form, only the rain falls and the sunbeams flicker",
    4: "the compass needle rotates and settles, the chart edges flutter, slow camera push-in",
    5: HOLD + "the numeral 5 stays fully in frame and unchanged, only the hand's fingers flex slightly and a gauge needle twitches",
    6: HOLD + "the numeral 6 stays fully in frame and unchanged, only the wheel spins and a puff of smoke rises",
    7: "sunlight travels across the tail fin while the aircraft silhouette drifts behind",
    8: "the small airplane flies a continuous loop around the infinity symbol",
    9: HOLD + "the giant numeral 9 stays fully in frame and unchanged, only the queue of passengers shuffles forward",
    10: "radio waves ripple outward from the headset in steady pulses, slow camera push-in",
    11: HOLD + "the two vapour trails stay as two clean straight parallel strokes forming 11 and never gain extra lines, only the aircraft edge forward slightly and the radar sweep rotates",
    12: "the helicopter rotor spins and the searchlight beam slowly sweeps across the water",
    13: "the cracks in the numeral widen slowly while the caution tape flutters",
    14: HOLD + "the numeral 14 painted on the runway stays fully in frame and unchanged, only the approach lights blink in sequence and a windsock sways",
    15: HOLD + "the board keeps displaying exactly the number 15 and the digits never change or flip, only a soft glow pulses across the screen and a status light blinks",
    16: "clean air streams flow through the jet engine while the leaves sway gently",
    17: HOLD + "both the detector arch and the scanner belt stay fully in frame forming 17 and unchanged, only the belt rolls slowly and the arch lights blink",
    18: "the cargo crate rocks slightly under moving cargo-hold lighting, slow push-in",
    19: "the dashboard needles sweep and the indicator lights blink in sequence, slow push-in",
}


def main() -> None:
    if not SCRIPT.exists():
        sys.exit(f"hata: {SCRIPT} bulunamadı")

    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    wanted = [int(a) for a in args] or sorted(MOTION)
    OUT_DIR.mkdir(exist_ok=True)

    ok = 0
    for n in wanted:
        card = CARDS / f"annex-{n:02d}.png"
        out = OUT_DIR / f"annex-{n:02d}.mp4"

        if not card.exists():
            print(f"Annex {n:2d}: kart yok, atlandı", flush=True)
            continue
        if out.exists() and not force:
            print(f"Annex {n:2d}: zaten var, atlandı", flush=True)
            ok += 1
            continue

        t0 = time.time()
        proc = subprocess.run(
            [str(SCRIPT), str(card), MOTION[n], str(out), str(DURATION)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and out.exists():
            size = out.stat().st_size // 1024
            print(f"Annex {n:2d}: ok  {int(time.time()-t0):3d}s  {size:5d} KB", flush=True)
            ok += 1
        else:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["bilinmeyen hata"]
            print(f"Annex {n:2d}: HATA — {tail[0][:120]}", flush=True)

    print(f"\n{ok}/{len(wanted)} video hazır → {OUT_DIR}")


if __name__ == "__main__":
    main()
