"""Compose the 45-second demo video from the rendered cards.

Six segments, slow zoom on each, crossfades between them. No audio: the cards
carry the words, and a demo that can be watched on mute is a demo that gets
watched.
"""

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(HERE, "frames")
WORK = os.path.join(HERE, "work")
OUT = os.path.join(HERE, "the-disputed-answer.mp4")
FFMPEG = "ffmpeg"

SEG_SECONDS = 7.9      # per card
FADE = 0.5             # crossfade between cards
FPS = 30


def run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(cmd)[:200])
        print(r.stderr[-1200:])
        raise SystemExit(1)


def segments() -> list:
    os.makedirs(WORK, exist_ok=True)
    cards = sorted(glob.glob(os.path.join(FRAMES, "*.png")))
    outs = []
    for i, card in enumerate(cards):
        seg = os.path.join(WORK, f"seg{i:02d}.mp4")
        frames = int(SEG_SECONDS * FPS)
        # slow zoom in from 1.00 to 1.09, centred
        vf = (
            f"scale=2560:-2,"
            f"zoompan=z='1+0.09*on/{frames}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s=1920x1080:fps={FPS},"
            f"format=yuv420p"
        )
        run([FFMPEG, "-y", "-loop", "1", "-i", card, "-t", str(SEG_SECONDS),
             "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-r", str(FPS), seg])
        outs.append(seg)
        print("segment", os.path.basename(seg))
    return outs


def compose(segs: list) -> None:
    inputs = []
    for s in segs:
        inputs += ["-i", s]

    # [0][1] -> xfade -> [a]; [a][2] -> xfade -> [b]; ...
    filters = []
    last = "[0:v]"
    for i in range(1, len(segs)):
        offset = SEG_SECONDS * i - FADE * i
        out_label = f"[x{i}]"
        filters.append(
            f"{last}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.3f}{out_label}"
        )
        last = out_label

    fc = ";".join(filters) + f";{last}format=yuv420p[v]"
    run([FFMPEG, "-y", *inputs,
         "-filter_complex", fc, "-map", "[v]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-movflags", "+faststart", "-r", str(FPS), OUT])
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


def main() -> int:
    if not glob.glob(os.path.join(FRAMES, "*.png")):
        print("render the cards first: python video/make_cards.py")
        return 1
    compose(segments())
    total = SEG_SECONDS * 6 - FADE * 5
    print(f"duration ≈ {total:.1f}s (limit 45s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
