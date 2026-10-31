"""Original procedural music for URALIA (project-owned, no third-party samples).

Inspired by the timbre of the Bashkir kurai (end-blown flute: breathy tone, strong
odd harmonics, wide vibrato, pentatonic melodies) over a low drone reminiscent of
uzlyau. This is an artistic homage, not a recording or transcription of any
existing melody. Run: python3 tools/gen_music.py <out_dir>
"""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 32000
rng = np.random.default_rng(1771)
  # fixed seed => reproducible output


def env(n, a=0.08, r=0.25):
    t = np.linspace(0, 1, n)
    e = np.minimum(1, t / max(a, 1e-3)) * np.minimum(1, (1 - t) / max(r, 1e-3))
    return np.clip(e, 0, 1)


def kurai(freq, dur, amp=0.35):
    n = int(SR * dur)
    t = np.arange(n) / SR
    vib = 1 + 0.012 * np.sin(2 * np.pi * 5.2 * t) * np.minimum(1, t / 0.4)
    phase = 2 * np.pi * np.cumsum(freq * vib) / SR
    tone = np.sin(phase) + 0.45 * np.sin(3 * phase) + 0.18 * np.sin(5 * phase) + 0.08 * np.sin(2 * phase)
    breath = rng.normal(0, 1, n)
    breath = np.convolve(breath, np.ones(6) / 6, mode="same") * 0.22
    sig = (tone * 0.8 + breath * (0.6 + 0.4 * np.sin(phase))) * env(n, 0.12, 0.3)
    return sig * amp


def drone(freq, dur, amp=0.18):
    n = int(SR * dur)
    t = np.arange(n) / SR
    s = sum((0.6 ** k) * np.sin(2 * np.pi * freq * (k + 1) * t + k) for k in range(6))
    s *= 1 + 0.15 * np.sin(2 * np.pi * 0.11 * t)
    return s * amp * env(n, 0.05, 0.05)


def drum(dur, amp=0.5, pitch=70):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = pitch * (1 + 2.5 * np.exp(-t * 30))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    skin = rng.normal(0, 1, n) * np.exp(-t * 40) * 0.25
    return (body + skin) * amp


def place(buf, sig, at):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def reverb(x, mix=0.25):
    out = x.copy()
    for d, g in ((0.031, 0.5), (0.047, 0.42), (0.071, 0.35), (0.113, 0.28), (0.173, 0.2), (0.257, 0.14)):
        k = int(d * SR)
        out[k:] += x[:-k] * g * mix * 2
    return out


# D minor pentatonic-ish: D F G A C
BASE = 293.66
SCALE = [0, 3, 5, 7, 10, 12, 15, 17]


def note(step):
    return BASE * 2 ** (SCALE[step % len(SCALE)] / 12) * (2 ** (step // len(SCALE)))


def phrase(steps_durs, start, buf, amp=0.33, octave=0):
    t = start
    for st, du in steps_durs:
        if st is not None:
            place(buf, kurai(note(st) * 2 ** octave, du * 1.05, amp), t)
        t += du
    return t


def hub_theme(length=72.0):
    buf = np.zeros(int(SR * length))
    for s in np.arange(0, length, 12):
        place(buf, drone(BASE / 4, 12.4), s)
        place(buf, drone(BASE / 4 * 1.5, 12.4, 0.07), s)
    motifs = [
        [(4, 1.5), (3, 0.75), (2, 0.75), (3, 2.0), (None, 0.5), (2, 0.75), (1, 0.75), (0, 2.5), (None, 1.0)],
        [(2, 1.0), (4, 1.0), (5, 1.5), (4, 0.5), (3, 1.0), (2, 2.0), (None, 0.5), (1, 1.0), (2, 2.5), (None, 1.0)],
        [(5, 0.75), (6, 0.75), (5, 0.75), (4, 0.75), (3, 1.5), (4, 0.5), (2, 2.5), (None, 0.5), (0, 3.0)],
    ]
    t = 2.0
    i = 0
    while t < length - 12:
        t = phrase(motifs[i % 3], t, buf) + 1.0
        i += 1
    buf = reverb(buf, 0.3)
    fade = int(SR * 3)
    buf[:fade] *= np.linspace(0, 1, fade)
    buf[-fade:] *= np.linspace(1, 0, fade)
    return buf


def battle_theme(length=48.0, bpm=118):
    buf = np.zeros(int(SR * length))
    beat = 60 / bpm
    for s in np.arange(0, length, 8):
        place(buf, drone(BASE / 4, 8.3, 0.16), s)
    pattern = [1.0, 0, 0.5, 0.6, 1.0, 0, 0.6, 0.4]
    t, k = 0.0, 0
    while t < length:
        a = pattern[k % 8]
        if a:
            place(buf, drum(0.4, 0.42 * a, 62 if k % 4 == 0 else 85), t)
        t += beat / 2
        k += 1
    riff = [(0, 0.5), (2, 0.5), (3, 1.0), (2, 0.5), (4, 0.5), (3, 1.0), (2, 0.5), (1, 0.5), (0, 1.0), (None, 1.0)]
    t = beat * 8
    while t < length - 6:
        t = phrase([(s, d * beat) if s is not None else (None, d * beat) for s, d in riff], t, buf, 0.3, octave=0)
        t = phrase([(s + 2 if s is not None else None, d * beat) for s, d in riff], t, buf, 0.28)
    buf = reverb(buf, 0.18)
    fade = int(SR * 2)
    buf[-fade:] *= np.linspace(1, 0, fade)
    return buf


def victory_sting():
    buf = np.zeros(int(SR * 4.0))
    phrase([(0, 0.25), (2, 0.25), (4, 0.25), (5, 1.6)], 0.1, buf, 0.4)
    place(buf, drum(0.6, 0.5, 60), 0.1)
    place(buf, drum(0.6, 0.5, 60), 0.85)
    return reverb(buf, 0.35)


def write(path: Path, x):
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.85
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def autumn_theme():
    """Variant for the 'Autumn fair' content package: lower key, slower, more drone."""
    global BASE
    old, BASE = BASE, 261.63  # C
    try:
        return hub_theme(64.0)
    finally:
        BASE = old


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--autumn":
        out = Path(sys.argv[1])
        out.parent.mkdir(parents=True, exist_ok=True)
        write(out, autumn_theme())
        print("ok", out)
        sys.exit(0)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "client/assets/audio/music")
    out.mkdir(parents=True, exist_ok=True)
    write(out / "hub_kurai_theme.wav", hub_theme())
    write(out / "battle_kurai_drums.wav", battle_theme())
    write(out / "victory_sting.wav", victory_sting())
    print("ok", out)
