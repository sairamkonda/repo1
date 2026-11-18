"""Synthesise the soundtrack for a reel from a cue sheet. No samples, no paid services.

Usage: python3 music.py <reel.json> <out.wav>
The cue sheet's "music" block lists sections and hits by time (seconds).
"""
import json
import sys

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
RNG = np.random.default_rng(7)

CHORDS = {
    # name: (bass midi, pad midis)
    "Am": (33, [57, 60, 64, 69]),
    "F": (29, [53, 57, 60, 65]),
    "C": (36, [55, 60, 64, 67]),
    "G": (31, [55, 59, 62, 67]),
    "Cadd9": (36, [55, 60, 62, 64, 67, 72]),
}


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tvec(dur):
    return np.arange(int(dur * SR)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


class Mix:
    def __init__(self, dur):
        self.n = int(dur * SR)
        self.dry = np.zeros((2, self.n))
        self.wet = np.zeros((2, self.n))  # send to reverb
        self.duck = np.ones(self.n)  # sidechain gain applied to "duckable" bus
        self.music = np.zeros((2, self.n))  # duckable bus (pad, bass, pluck)

    def add(self, start, sig, gain=1.0, pan=0.0, send=0.0, bus="dry"):
        i = int(start * SR)
        if i >= self.n:
            return
        sig = sig[: self.n - i] * gain
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        tgt = self.music if bus == "music" else self.dry
        tgt[0, i : i + len(sig)] += sig * l * 1.414
        tgt[1, i : i + len(sig)] += sig * r * 1.414
        if send:
            self.wet[0, i : i + len(sig)] += sig * l * send
            self.wet[1, i : i + len(sig)] += sig * r * send

    def duck_at(self, start, depth=0.55, release=0.22):
        i = int(start * SR)
        t = tvec(release * 2.5)
        env = 1 - depth * np.exp(-t / release)
        seg = self.duck[i : i + len(env)]
        self.duck[i : i + len(env)] = np.minimum(seg, env[: len(seg)])


# ---------- instruments ----------

def saw(freq, dur, harmonics=24, bright=8.0):
    t = tvec(dur)
    out = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        if freq * k > SR / 2.2:
            break
        out += np.sin(2 * np.pi * freq * k * t + RNG.uniform(0, 6.28)) / k * np.exp(-(k - 1) / bright)
    return out


def adsr(n, a, r, sustain=1.0):
    env = np.full(n, sustain)
    na, nr = int(a * SR), int(r * SR)
    na, nr = min(na, n), min(nr, n)
    env[:na] = np.linspace(0, sustain, na)
    if nr:
        env[-nr:] *= np.linspace(1, 0, nr)
    return env


def pad(chord, dur, bright=5.0, attack=0.6, release=0.8):
    _, notes = CHORDS[chord]
    voices = []
    for m in notes:
        for det, pan in ((-0.08, -0.6), (0.0, 0.0), (0.08, 0.6)):
            f = hz(m) * 2 ** (det / 12)
            v = saw(f, dur, harmonics=16, bright=bright)
            voices.append((v, pan))
    n = int(dur * SR)
    env = adsr(n, attack, release)
    return [(v * env / len(notes) / 2.2, p) for v, p in voices]


def kick(punch=1.0):
    t = tvec(0.45)
    f = 45 + 110 * np.exp(-t / 0.04)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t / 0.18)
    click = hp(RNG.standard_normal(len(t)), 2500) * np.exp(-t / 0.004) * 0.3
    return np.tanh((body + click) * 1.6 * punch)


def clap():
    t = tvec(0.35)
    noise = bp(RNG.standard_normal(len(t)), 900, 5000)
    env = np.zeros_like(t)
    for off in (0.0, 0.011, 0.022):
        env += np.where(t >= off, np.exp(-(t - off) / 0.012), 0) * 0.6
    env += np.where(t >= 0.03, np.exp(-(t - 0.03) / 0.09), 0)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05) * 0.5
    return (noise * env + body) * 0.7


def hat(open_=False):
    t = tvec(0.25 if open_ else 0.06)
    return hp(RNG.standard_normal(len(t)), 7000) * np.exp(-t / (0.07 if open_ else 0.015)) * 0.5


def tick(high=True):
    t = tvec(0.03)
    f = 3200 if high else 2400
    return np.sin(2 * np.pi * f * t) * np.exp(-t / 0.004)


def heartbeat():
    t = tvec(0.6)
    out = np.zeros_like(t)
    for off, a in ((0.0, 1.0), (0.17, 0.7)):
        tt = np.clip(t - off, 0, None)
        f = 40 + 40 * np.exp(-tt / 0.03)
        ph = 2 * np.pi * np.cumsum(f) / SR
        out += np.where(t >= off, np.sin(ph) * np.exp(-tt / 0.09) * a, 0)
    # a little mid content so phone speakers carry it
    out += lp(np.tanh(out * 3), 400) * 0.35
    return out


def impact(size=1.0):
    dur = 3.0 * size
    t = tvec(dur)
    f = 28 + 40 * np.exp(-t / 0.15)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(ph) * np.exp(-t / (0.9 * size))
    boom = lp(RNG.standard_normal(len(t)), 900) * np.exp(-t / 0.35) * 0.8
    crack = hp(RNG.standard_normal(len(t)), 1500) * np.exp(-t / 0.06) * 0.5
    grit = lp(np.tanh(sub * 4), 600) * 0.4
    return np.tanh((sub * 1.3 + boom + crack + grit) * 1.2)


def riser(dur):
    t = tvec(dur)
    x = t / dur
    noise = RNG.standard_normal(len(t))
    # sweep a band-pass upward chunk by chunk
    out = np.zeros_like(t)
    chunk = int(0.04 * SR)
    for i in range(0, len(t), chunk):
        c = (i / len(t))
        lo = 200 + 5000 * c**2
        seg = bp(noise[max(0, i - 2000) : i + chunk], lo, lo * 2.2)[-min(chunk, len(t) - i):]
        out[i : i + len(seg)] = seg
    f = 150 + 1100 * x**2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * (4 + 18 * x) * t)
    return (out * 0.9 + tone) * x**2.2 * trem


def glitch():
    t = tvec(0.5)
    sq = np.sign(np.sin(2 * np.pi * 110 * t)) * 0.3
    noise = RNG.standard_normal(len(t))
    gate = (np.floor(t * 40) % 3 != 1).astype(float)
    crushed = np.round(noise * 3) / 3
    return (bp(crushed, 400, 4000) * 0.7 + sq) * gate * np.exp(-t / 0.18)


def whoosh(dur=0.8):
    t = tvec(dur)
    x = t / dur
    env = np.sin(np.pi * x) ** 2
    return bp(RNG.standard_normal(len(t)), 500, 3500) * env * 0.6


def reverse_swell(dur):
    t = tvec(dur)
    x = t / dur
    noise = lp(RNG.standard_normal(len(t)), 6000)
    return noise * x**3 * 0.7


def pluck(m, dur=0.35):
    t = tvec(dur)
    f = hz(m)
    tone = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t))
    return tone * np.exp(-t / 0.12) * 0.5


def bass_note(m, dur):
    t = tvec(dur)
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) + 0.25 * np.sin(6 * np.pi * f * t)
    env = adsr(len(t), 0.005, 0.05) * np.exp(-t / 0.5)
    return np.tanh(s * env * 1.5) * 0.6


def drone(dur):
    t = tvec(dur)
    a1 = np.sin(2 * np.pi * 55 * t) * 0.5
    a2 = lp(saw(110, dur, harmonics=12, bright=3), 700) * 0.35
    shimmer = np.sin(2 * np.pi * 880 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t)) * 0.03
    env = adsr(len(t), 1.5, 0.4)
    return (a1 + a2 + shimmer) * env


# ---------- arrangement ----------

def render(cfg):
    mc = cfg["music"]
    dur = cfg["duration"]
    mix = Mix(dur)
    beat = 60.0 / mc["bpm"]

    for s in mc.get("drone", []):
        mix.add(s[0], drone(s[1] - s[0]), gain=0.5, send=0.25)
    for s in mc.get("pads", []):
        start, end, chord = s[:3]
        for v, p in pad(chord, end - start + 0.6, bright=s[3] if len(s) > 3 else 5.0):
            mix.add(start, v, gain=0.55, pan=p, send=0.5, bus="music")
    for t in mc.get("heartbeats", []):
        mix.add(t, heartbeat(), gain=0.9)
    for s in mc.get("ticks", []):
        k = 0
        t = s[0]
        while t < s[1] - 1e-6:
            mix.add(t, tick(k % 2 == 0), gain=0.35, pan=0.3 if k % 2 else -0.3, send=0.2)
            t += beat / 2
            k += 1
    for t in mc.get("glitches", []):
        mix.add(t, glitch(), gain=0.5, send=0.3)
    for t in mc.get("whooshes", []):
        mix.add(t - 0.4, whoosh(), gain=0.5, send=0.4)
    for s in mc.get("risers", []):
        mix.add(s[0], riser(s[1] - s[0]), gain=0.6, send=0.3)
    for s in mc.get("swells", []):
        mix.add(s[0], reverse_swell(s[1] - s[0]), gain=0.5, send=0.2)
    for s in mc.get("impacts", []):
        t, size = (s, 1.0) if not isinstance(s, list) else s
        mix.add(t, impact(size), gain=1.0, send=0.6)
        mix.duck_at(t, depth=0.8, release=0.5)

    for s in mc.get("drums", []):
        start, end = s
        t, k = start, 0
        while t < end - 1e-6:
            mix.add(t, kick(), gain=0.95)
            mix.duck_at(t)
            if k % 2 == 1:
                mix.add(t, clap(), gain=0.55, send=0.35)
            mix.add(t + beat / 2, hat(open_=(k % 4 == 3)), gain=0.3, pan=0.35)
            mix.add(t, hat(), gain=0.15, pan=-0.35)
            t += beat
            k += 1

    for s in mc.get("bass", []):
        start, end, chord = s
        root = CHORDS[chord][0]
        t = start
        while t < end - 1e-6:
            mix.add(t, bass_note(root, beat / 2), gain=0.7, bus="music")
            t += beat / 2

    for s in mc.get("plucks", []):
        start, end, chord = s[:3]
        step = s[3] if len(s) > 3 else 0.5
        _, notes = CHORDS[chord]
        pattern = [notes[0] + 12, notes[1] + 12, notes[2] + 12, notes[-1] + 12, notes[2] + 12, notes[1] + 12]
        t, k = start, 0
        while t < end - 1e-6:
            mix.add(t, pluck(pattern[k % len(pattern)]), gain=0.35, pan=(-0.4 if k % 2 else 0.4), send=0.45, bus="music")
            t += beat * step
            k += 1

    for s in mc.get("stabs", []):
        t, chord = s
        for v, p in pad(chord, 0.9, bright=9.0, attack=0.005, release=0.5):
            mix.add(t, v * np.exp(-tvec(0.9) / 0.35), gain=1.3, pan=p, send=0.6)
        mix.add(t, kick(1.3), gain=1.0)
        mix.add(t, clap(), gain=0.6, send=0.5)
        mix.duck_at(t, depth=0.7, release=0.3)

    # sidechain the music bus, then sum
    mix.dry += mix.music * mix.duck
    mix.wet += mix.music * mix.duck * 0.35

    # silence windows (hard mutes for drama), with short fades
    for s in mc.get("mutes", []):
        i0, i1 = int(s[0] * SR), int(s[1] * SR)
        fade = int(0.03 * SR)
        g = np.ones(mix.n)
        g[i0:i1] = 0
        g[max(i0 - fade, 0) : i0] = np.linspace(1, 0, min(fade, i0))
        mix.dry *= g

    # reverb: decaying stereo noise impulse
    ir_t = tvec(2.6)
    ir = np.stack([lp(RNG.standard_normal(len(ir_t)), 5000) * np.exp(-ir_t / 0.6) for _ in range(2)])
    ir /= np.abs(ir).sum(axis=1, keepdims=True) / 6
    wet = np.stack([fftconvolve(mix.wet[c], ir[c])[: mix.n] for c in range(2)])
    out = mix.dry + wet * 0.5

    # master: gentle high-pass, soft clip, fade out
    out = np.stack([hp(out[c], 28) for c in range(2)])
    fo = mc.get("fade_out", 1.5)
    nfo = int(fo * SR)
    out[:, -nfo:] *= np.linspace(1, 0, nfo) ** 1.5
    out = np.tanh(out / np.abs(out).max() * 1.6) / np.tanh(1.6)
    return out * 0.95


def write_wav(path, stereo):
    import wave

    data = (np.clip(stereo.T, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    write_wav(sys.argv[2], render(cfg))
    print("wrote", sys.argv[2])
