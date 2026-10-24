#!/usr/bin/env python3
"""Create procedural ambience beds from episode cues."""

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import wave
from pathlib import Path

import numpy as np


PART_PATTERN = re.compile(
    r"(?m)^###\s*\[BAHAGI\s*(\d+):\s*([^\]]+)\]\s*$",
    re.IGNORECASE,
)
CUE_PATTERN = re.compile(r"\(AMBIENT SFX:\s*(.*?)\)", re.IGNORECASE | re.DOTALL)
SAMPLE_RATE = 22050
ASSET_CUES = {
    "wind-gusting-soft": "banayad na simoy ng hangin",
    "wind-gusting-hard": "malakas na unos at hangin",
    "fire-cracking": "siga apoy fire",
    "waves-gentle": "marahang alon tubig",
    "waves-crashing": "malalakas na alon karagatan",
    "river-flowing": "ilog tubig",
    "crickets-chirping": "kuliglig huni",
    "crickets-fading": "kuliglig huni fading",
    "birds-chirping": "ibon huni",
    "rain-falling-soft": "mahinang ulan patak",
    "rain-falling-hard": "malakas na ulan patak",
    "rain-fading": "ulan patak fading",
    "ominous-low-drone": "low drone ugong dagundong",
    "agimat-humming": "mystical hum agimat",
    "wild-dogs-howling": "howling wild dogs at night",
    "night-creatures": "small nocturnal creatures calling",
}
CUSTOM_ASSET_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def load_sfx_catalog(assets_dir):
    assets_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = assets_dir / "catalog.sqlite3"
    try:
        connection = sqlite3.connect(catalog_path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sfx_assets (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                layers_json TEXT NOT NULL
            )
            """
        )
        for asset_path in assets_dir.glob("*.wav"):
            name = asset_path.stem
            if (
                name not in ASSET_CUES
                and CUSTOM_ASSET_PATTERN.fullmatch(name)
            ):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO sfx_assets (name, description, layers_json)
                    VALUES (?, ?, '[]')
                    """,
                    (name, name.replace("-", " ")),
                )
        connection.commit()
        rows = connection.execute(
            "SELECT name, description FROM sfx_assets ORDER BY name"
        ).fetchall()
    except sqlite3.Error as error:
        raise RuntimeError(f"Could not read SFX catalog {catalog_path}: {error}") from error
    finally:
        if "connection" in locals():
            connection.close()
    return {
        name: description
        for name, description in rows
        if (assets_dir / f"{name}.wav").is_file()
    }


def available_sfx_assets(assets_dir):
    assets = dict(ASSET_CUES)
    assets.update(load_sfx_catalog(assets_dir))
    return assets


def register_sfx_asset(name, description, layers, assets_dir):
    if (
        not CUSTOM_ASSET_PATTERN.fullmatch(name)
        or name in ASSET_CUES
        or not isinstance(description, str)
        or not description.strip()
        or len(description) > 160
    ):
        raise ValueError(f"Invalid SFX catalog metadata for {name!r}.")
    catalog_path = assets_dir / "catalog.sqlite3"
    layers_json = json.dumps(
        [{"asset": asset_name, "gain": gain} for asset_name, gain in layers]
    )
    try:
        with sqlite3.connect(catalog_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sfx_assets (
                    name TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    layers_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO sfx_assets (name, description, layers_json)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    layers_json = excluded.layers_json
                """,
                (name, description.strip(), layers_json),
            )
    except sqlite3.Error as error:
        raise RuntimeError(f"Could not update SFX catalog {catalog_path}: {error}") from error


def parse_parts(script_text):
    headers = list(PART_PATTERN.finditer(script_text))
    if not headers:
        raise ValueError("No episode parts found. Expected headings like '### [BAHAGI 1: ...]'.")

    parts = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(script_text)
        section = script_text[header.end():end]
        cue = CUE_PATTERN.search(section)
        if cue is None:
            raise ValueError(f"Part {header.group(1)} has no '(AMBIENT SFX: ...)' cue.")
        parts.append((int(header.group(1)), header.group(2).strip(), cue.group(1).strip()))

    if not parts:
        raise ValueError("The episode script has no parts with ambient cues.")
    return parts


def generate_dynamic_cue_asset(cue, assets_dir):
    if __package__:
        from .brain_sfx import repair_sfx_recipe
    else:
        from brain_sfx import repair_sfx_recipe

    model = os.environ.get("BRAIN_MODEL", "qwen2.5:3b")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
    recipe = repair_sfx_recipe(
        {"description": cue, "name": "", "layers": []},
        cue,
        "neutral",
        model,
        base_url,
        "uncatalogued SFX cue",
        1,
    )
    layers = [
        (layer["asset"], float(layer["gain"]))
        for layer in recipe["layers"]
    ]
    asset_path = ensure_composite_asset(
        recipe["name"],
        layers,
        assets_dir,
        description=cue,
    )
    print(
        f"Created and cataloged custom SFX for cue '{cue}': {asset_path}",
        flush=True,
    )
    return asset_path


def slow_noise(rng, sample_count, rate_hz, sample_rate):
    knot_count = max(2, math.ceil(sample_count * rate_hz / sample_rate))
    knot_positions = np.linspace(0, sample_count - 1, knot_count)
    knots = rng.normal(0, 1, knot_count)
    values = np.interp(np.arange(sample_count), knot_positions, knots)
    peak = np.max(np.abs(values))
    return values / peak if peak else values


def filtered_noise(rng, sample_count, low_hz, high_hz):
    frequencies = np.fft.rfftfreq(sample_count, 1 / SAMPLE_RATE)
    spectrum = np.fft.rfft(rng.normal(0, 1, sample_count))
    low_cut = 1 / (1 + (low_hz / np.maximum(frequencies, 1)) ** 8)
    high_cut = 1 / (1 + (frequencies / high_hz) ** 8)
    noise = np.fft.irfft(spectrum * low_cut * high_cut, n=sample_count)
    rms = float(np.sqrt(np.mean(noise**2)))
    return noise / rms if rms else noise


def add_bird_chirps(audio, rng):
    sample_count = len(audio)
    time = 0
    while time < sample_count:
        note_count = int(rng.integers(2, 5))
        for _ in range(note_count):
            note_length = int(rng.uniform(0.045, 0.13) * SAMPLE_RATE)
            start = time + int(rng.uniform(0.025, 0.09) * SAMPLE_RATE)
            end = min(start + note_length, sample_count)
            if start >= sample_count:
                return
            positions = np.arange(end - start, dtype=np.float32) / SAMPLE_RATE
            duration = (end - start) / SAMPLE_RATE
            frequency = rng.uniform(1900, 3600) + rng.uniform(-700, 700) * (
                positions / max(duration, 1e-6)
            )
            phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
            envelope = np.maximum(
                0,
                np.sin(
                    np.pi * np.arange(end - start) / max(end - start - 1, 1)
                ),
            ) ** 1.5
            chirp = np.sin(phase) + 0.18 * np.sin(2 * phase)
            audio[start:end] += (0.10 * envelope * chirp).astype(np.float32)
            time = end + int(rng.uniform(0.025, 0.08) * SAMPLE_RATE)
        time += int(rng.uniform(0.12, 0.55) * SAMPLE_RATE)


def add_night_creature_calls(audio, rng):
    sample_count = len(audio)
    for start in rng.integers(0, sample_count, int(sample_count / SAMPLE_RATE * 1.8)):
        note_count = int(rng.integers(2, 5))
        time = start
        for _ in range(note_count):
            length = int(rng.uniform(0.025, 0.075) * SAMPLE_RATE)
            end = min(time + length, sample_count)
            if end <= time:
                break
            positions = np.arange(end - time, dtype=np.float32) / SAMPLE_RATE
            frequency = rng.uniform(850, 1900) + rng.uniform(-450, 450) * (
                positions / max(len(positions) / SAMPLE_RATE, 1e-6)
            )
            phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
            envelope = np.sin(np.pi * np.arange(end - time) / max(end - time - 1, 1))
            audio[time:end] += (
                0.055 * envelope * (np.sin(phase) + 0.15 * np.sin(2 * phase))
            ).astype(np.float32)
            time = end + int(rng.uniform(0.025, 0.11) * SAMPLE_RATE)


def add_wild_dog_howls(audio, rng):
    sample_count = len(audio)
    start = int(rng.uniform(0.8, 3.5) * SAMPLE_RATE)
    while start < sample_count:
        length = int(rng.uniform(1.5, 3.0) * SAMPLE_RATE)
        end = min(start + length, sample_count)
        positions = np.arange(end - start, dtype=np.float32) / SAMPLE_RATE
        progress = positions / max(length / SAMPLE_RATE, 1e-6)
        frequency = rng.uniform(370, 500) - rng.uniform(100, 190) * progress
        phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
        envelope = np.sin(np.pi * np.arange(end - start) / max(end - start - 1, 1)) ** 1.4
        howl = (
            np.sin(phase)
            + 0.38 * np.sin(2 * phase + 0.2)
            + 0.12 * np.sin(3 * phase + 0.5)
        )
        audio[start:end] += (0.075 * envelope * howl).astype(np.float32)
        start = end + int(rng.uniform(7, 15) * SAMPLE_RATE)


def add_fire_crackle(audio, rng):
    sample_count = len(audio)
    audio += (0.035 * filtered_noise(rng, sample_count, 90, 9000)).astype(np.float32)
    event_count = int(len(audio) / SAMPLE_RATE * 9)
    for start in rng.integers(0, sample_count, event_count):
        length = int(rng.uniform(0.004, 0.035) * SAMPLE_RATE)
        end = min(start + length, sample_count)
        envelope = np.exp(-np.linspace(0, 6, end - start))
        audio[start:end] += (
            rng.uniform(0.08, 0.35)
            * envelope
            * rng.normal(0, 1, end - start)
        ).astype(np.float32)


def render_soundscape(cue, duration, seed):
    rng = np.random.default_rng(seed)
    sample_count = round(duration * SAMPLE_RATE)
    time = np.arange(sample_count, dtype=np.float32) / SAMPLE_RATE
    audio = np.zeros(sample_count, dtype=np.float32)
    cue_text = cue.casefold()

    if any(word in cue_text for word in ("hangin", "wind", "unos", "simoy")):
        intensity = 1.6 if any(word in cue_text for word in ("malakas", "unos", "storm")) else 0.65
        gusts = 0.42 + 0.58 * (
            0.5 + 0.5 * np.sin(2 * np.pi * 0.055 * time + rng.uniform(0, 2 * np.pi))
        )
        wind = filtered_noise(rng, sample_count, 45, 1600)
        turbulence = filtered_noise(rng, sample_count, 500, 7000)
        audio += (intensity * 0.045 * wind * gusts).astype(np.float32)
        audio += (intensity * 0.006 * turbulence * gusts).astype(np.float32)

    if any(word in cue_text for word in ("alon", "wave", "karagatan", "tubig")):
        intensity = 1.8 if any(word in cue_text for word in ("malalakas", "crashing")) else 0.65
        period = rng.uniform(5, 9)
        phase = rng.uniform(0, 2 * np.pi)
        swell = np.maximum(0, np.sin(2 * np.pi * time / period + phase)) ** 2
        surf = filtered_noise(rng, sample_count, 55, 1200)
        foam = filtered_noise(rng, sample_count, 900, 9500)
        audio += (intensity * 0.055 * surf * (0.08 + 0.92 * swell)).astype(np.float32)
        audio += (intensity * 0.018 * foam * swell**1.5).astype(np.float32)

    if any(word in cue_text for word in ("ulan", "rain", "patak")):
        rain = filtered_noise(rng, sample_count, 450, 10000)
        rain_modulation = 0.78 + 0.22 * slow_noise(rng, sample_count, 2.5, SAMPLE_RATE)
        if "fading" in cue_text:
            rain_modulation *= np.clip(1 - time / duration, 0, 1)
        audio += (0.028 * rain * rain_modulation).astype(np.float32)

    if any(word in cue_text for word in ("ibon", "birds")):
        add_bird_chirps(audio, rng)

    if any(word in cue_text for word in ("kuliglig", "crickets")):
        cricket_carrier = np.sin(2 * np.pi * rng.uniform(3900, 4800) * time)
        trill_gate = np.maximum(0, np.sin(2 * np.pi * 5.5 * time)) ** 5
        fade = np.clip(1 - time / duration, 0, 1) if "fading" in cue_text else 1
        audio += (0.035 * trill_gate * cricket_carrier * fade).astype(np.float32)

    if any(word in cue_text for word in ("night creatures", "nocturnal creatures")):
        add_night_creature_calls(audio, rng)

    if any(word in cue_text for word in ("wild dogs", "dog howling", "dogs howling")):
        add_wild_dog_howls(audio, rng)

    if any(word in cue_text for word in ("ilog", "lagaslas")):
        flow = 0.72 + 0.28 * slow_noise(rng, sample_count, 0.7, SAMPLE_RATE)
        river = filtered_noise(rng, sample_count, 80, 6500)
        ripples = filtered_noise(rng, sample_count, 1400, 9500)
        ripple_gate = 0.55 + 0.45 * np.maximum(
            0, np.sin(2 * np.pi * 0.32 * time + rng.uniform(0, 2 * np.pi))
        )
        audio += (0.045 * river * flow).astype(np.float32)
        audio += (0.009 * ripples * ripple_gate).astype(np.float32)

    if any(word in cue_text for word in ("drone", "ugong", "dagundong")):
        drone_modulation = 0.78 + 0.22 * np.sin(2 * np.pi * 0.08 * time)
        low_drone = filtered_noise(rng, sample_count, 35, 260)
        audio += (0.025 * drone_modulation * low_drone).astype(np.float32)

    if any(word in cue_text for word in ("mystical", "hum", "agimat", "mahiwaga")):
        shimmer = 0.7 + 0.3 * np.sin(2 * np.pi * 0.19 * time)
        hum = filtered_noise(rng, sample_count, 130, 900)
        audio += (0.022 * shimmer * hum).astype(np.float32)

    if any(word in cue_text for word in ("siga", "apoy", "fire")):
        add_fire_crackle(audio, rng)

    peak = float(np.max(np.abs(audio)))
    if peak < 1e-6:
        raise ValueError(f"No supported sound cues recognized in: {cue}")
    audio *= 0.28 / peak
    return np.clip(audio, -1, 1)


def render_composite_soundscape(layers, duration, seed):
    if not 1 <= len(layers) <= 4:
        raise ValueError("A generated ambience must combine 1 to 4 supported sound layers.")
    sample_count = round(duration * SAMPLE_RATE)
    composite = np.zeros(sample_count, dtype=np.float32)
    for index, (asset_name, gain) in enumerate(layers):
        if asset_name not in ASSET_CUES:
            raise ValueError(f"Unsupported procedural sound primitive: {asset_name}")
        if not math.isfinite(gain) or not 0.1 <= gain <= 1.0:
            raise ValueError(f"Layer gain for {asset_name} must be between 0.1 and 1.0.")
        primitive = render_soundscape(
            ASSET_CUES[asset_name],
            duration,
            seed + (index + 1) * 1009,
        )
        composite += primitive * gain

    peak = float(np.max(np.abs(composite)))
    if peak < 1e-6:
        raise ValueError("The generated ambience recipe produced silence.")
    composite *= 0.28 / peak
    return np.clip(composite, -1, 1)


def write_wav(audio, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (audio * 32767).astype("<i2")
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm.tobytes())


def ensure_cue_assets(cue, assets_dir, duration=30):
    assets_dir.mkdir(parents=True, exist_ok=True)
    normalized_cue = " ".join(cue.casefold().split())
    catalog = load_sfx_catalog(assets_dir)
    for name, description in catalog.items():
        if normalized_cue in {
            " ".join(name.replace("-", " ").casefold().split()),
            " ".join(description.casefold().split()),
        }:
            asset_path = assets_dir / f"{name}.wav"
            print(f"Reusing cataloged SFX for cue '{cue}': {asset_path}", flush=True)
            return [asset_path]

    normalized_assets = {
        " ".join(name.casefold().split()): name for name in ASSET_CUES
    }
    normalized_assets.update(
        {
            " ".join(description.casefold().split()): name
            for name, description in ASSET_CUES.items()
        }
    )
    asset_names = []
    for candidate in (item.strip() for item in cue.split(",")):
        normalized_candidate = " ".join(candidate.casefold().split())
        custom_match = re.fullmatch(
            r"custom:([a-z0-9]+(?:-[a-z0-9]+)*)", normalized_candidate
        )
        if custom_match:
            asset_names.append(custom_match.group(1))
        elif normalized_candidate in normalized_assets:
            asset_names.append(normalized_assets[normalized_candidate])
        else:
            asset_path = generate_dynamic_cue_asset(cue, assets_dir)
            return [asset_path]

    if not asset_names:
        raise ValueError("Ambient SFX cue is empty.")

    asset_paths = []
    for asset_name in asset_names:
        asset_path = assets_dir / f"{asset_name}.wav"
        if asset_path.exists():
            print(f"Reusing SFX asset: {asset_path}")
        elif asset_name not in ASSET_CUES:
            raise FileNotFoundError(f"Generated SFX asset is missing: {asset_path}.")
        else:
            seed = sum((index + 1) * ord(char) for index, char in enumerate(asset_name))
            audio = render_soundscape(ASSET_CUES[asset_name], duration, seed)
            write_wav(audio, asset_path)
            print(f"Generated reusable SFX asset: {asset_path}")
        asset_paths.append(asset_path)
    return asset_paths


def ensure_composite_asset(name, layers, assets_dir, duration=30, description=None):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 56:
        raise ValueError(f"Invalid generated SFX asset name: {name!r}.")
    if name in ASSET_CUES:
        raise ValueError(f"Generated SFX name '{name}' conflicts with a built-in asset.")

    asset_path = assets_dir / f"{name}.wav"
    if asset_path.exists():
        print(f"Reusing generated SFX asset: {asset_path}", flush=True)
        register_sfx_asset(
            name,
            description or name.replace("-", " "),
            layers,
            assets_dir,
        )
        return asset_path

    seed = sum((index + 1) * ord(char) for index, char in enumerate(name))
    audio = render_composite_soundscape(layers, duration, seed)
    write_wav(audio, asset_path)
    register_sfx_asset(
        name,
        description or name.replace("-", " "),
        layers,
        assets_dir,
    )
    print(f"Generated custom procedural SFX asset: {asset_path}", flush=True)
    return asset_path


def main():
    parser = argparse.ArgumentParser(
        description="Create reusable procedural SFX assets from episode ambient cues."
    )
    parser.add_argument("script", type=Path, help="Episode script with BAHAGI headings and SFX cues")
    parser.add_argument(
        "--duration",
        type=float,
        default=30,
        help="Duration in seconds for each reusable WAV asset (default: 30)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path("assets") / "sfx",
        help="Reusable asset directory (default: assets/sfx)",
    )
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0 or args.duration > 600:
        parser.error("--duration must be greater than 0 and at most 600 seconds.")

    try:
        parts = parse_parts(args.script.read_text(encoding="utf-8"))
        for part_number, title, cue in parts:
            assets = ensure_cue_assets(cue, args.assets_dir, args.duration)
            print(f"Part {part_number}: {title} -> " + ", ".join(path.name for path in assets))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
