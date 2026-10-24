#!/usr/bin/env python3
"""Use a local Ollama model to annotate narration blocks with ambience cues."""

import json
import re
import urllib.error
import urllib.request

if __package__:
    from .generate_ambient_sfx import (
        ASSET_CUES,
        CUE_PATTERN,
        PART_PATTERN,
        available_sfx_assets,
        ensure_composite_asset,
    )
    from .progress import progress_heartbeat, report_progress
else:
    from generate_ambient_sfx import (
        ASSET_CUES,
        CUE_PATTERN,
        PART_PATTERN,
        available_sfx_assets,
        ensure_composite_asset,
    )
    from progress import progress_heartbeat, report_progress


EMOTIONS = (
    "calm",
    "joyful",
    "sad",
    "fearful",
    "angry",
    "suspenseful",
    "awe",
    "neutral",
)


def extract_paragraphs(script_text):
    headers = list(PART_PATTERN.finditer(script_text))
    if not headers:
        raise ValueError("AI SFX needs episode headings like '### [BAHAGI 1: ...]'.")

    parts = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(script_text)
        section = script_text[header.end():end]
        section = CUE_PATTERN.sub("", section)
        section = re.sub(r"(?m)^\s*#+\s*.*$", "", section)
        paragraphs = [" ".join(block.split()) for block in re.split(r"\n\s*\n", section)]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]
        if not paragraphs:
            raise ValueError(f"Episode part {header.group(1)} has no narration text.")
        parts.append((int(header.group(1)), header.group(2).strip(), paragraphs))
    return parts


def read_brain_instructions(instruction_path):
    try:
        instructions = instruction_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError(
            f"Could not read AI brain instructions from {instruction_path}: {error}"
        ) from error
    if not instructions:
        raise ValueError(f"AI brain instructions file is empty: {instruction_path}")
    return instructions


def generate_new_asset(name, description, layers, assets_dir):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 56:
        raise RuntimeError(f"Ollama returned an invalid new SFX asset name: {name!r}.")
    if not isinstance(layers, list) or not 1 <= len(layers) <= 4:
        raise RuntimeError(f"Ollama returned an invalid sound recipe for {name}.")
    normalized_layers = []
    for layer in layers:
        if (
            not isinstance(layer, dict)
            or not isinstance(layer.get("asset"), str)
            or layer.get("asset") not in ASSET_CUES
            or not isinstance(layer.get("gain"), (int, float))
            or isinstance(layer.get("gain"), bool)
            or not 0.1 <= layer["gain"] <= 1.0
        ):
            raise RuntimeError(f"Ollama returned an unsupported sound layer for {name}.")
        normalized_layers.append((layer["asset"], float(layer["gain"])))

    report_progress(
        f"Building '{name}.wav' from procedural layers: "
        + ", ".join(asset_name for asset_name, _ in normalized_layers)
    )
    with progress_heartbeat(f"Building procedural SFX '{name}'"):
        try:
            asset_path = ensure_composite_asset(
                name,
                normalized_layers,
                assets_dir,
                description=description,
            )
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Could not build custom SFX '{name}': {error}") from error
    report_progress(f"Custom procedural SFX asset is ready: {asset_path}")
    return name


def valid_sfx_recipe(recipe):
    if not isinstance(recipe, dict):
        return False
    name = recipe.get("name")
    description = recipe.get("description")
    layers = recipe.get("layers")
    return (
        isinstance(name, str)
        and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is not None
        and len(name) <= 56
        and isinstance(description, str)
        and bool(description.strip())
        and len(description) <= 160
        and isinstance(layers, list)
        and 1 <= len(layers) <= 4
        and all(
            isinstance(layer, dict)
            and isinstance(layer.get("asset"), str)
            and layer["asset"] in ASSET_CUES
            and isinstance(layer.get("gain"), (int, float))
            and not isinstance(layer.get("gain"), bool)
            and 0.1 <= layer["gain"] <= 1.0
            for layer in layers
        )
    )


def repair_sfx_recipe(
    recipe, paragraph, emotion, model, base_url, part_title, paragraph_index
):
    primitives = list(ASSET_CUES)
    response_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$",
                "maxLength": 56,
            },
            "description": {"type": "string", "minLength": 1, "maxLength": 160},
            "layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "asset": {"type": "string", "enum": primitives},
                        "gain": {"type": "number", "minimum": 0.1, "maximum": 1.0},
                    },
                    "required": ["asset", "gain"],
                    "additionalProperties": False,
                },
                "minItems": 1,
                "maxItems": 4,
            },
        },
        "required": ["name", "description", "layers"],
        "additionalProperties": False,
    }
    prompt = (
        "Repair this procedural sound design into a valid JSON recipe. Preserve the "
        "requested sound concept; do not replace it with an unrelated generic ambience. "
        "Choose 1-4 layers only from the supported primitives, with gains from 0.1 to "
        "1.0. Use a concise lowercase hyphenated filename and a faithful description. "
        f"Supported primitives: {primitives}\n"
        f"Emotion: {emotion}\nNarration paragraph: {paragraph}\n"
        f"Original sound design request: {json.dumps(recipe, ensure_ascii=False)}\n"
        "Return only the recipe JSON object."
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "format": response_schema,
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    report_progress(
        f"Repairing the generated SFX recipe for paragraph {paragraph_index} "
        f"in '{part_title}' without substituting a built-in sound."
    )
    try:
        with progress_heartbeat(f"Repairing SFX recipe for paragraph {paragraph_index}"):
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
        repaired = json.loads(result["response"])
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Ollama could not repair the SFX recipe ({error.code}): {details}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Could not connect to Ollama to repair the SFX recipe.") from error
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Ollama returned a malformed SFX recipe repair.") from error
    if not valid_sfx_recipe(repaired):
        raise RuntimeError(
            f"Ollama could not produce a valid custom SFX recipe for paragraph "
            f"{paragraph_index} in '{part_title}'. No substitute WAV was generated."
        )
    return repaired


def annotate_paragraphs(
    paragraphs, part_title, model, base_url, instructions, assets_dir
):
    available_assets = available_sfx_assets(assets_dir)
    primitive_assets = list(ASSET_CUES)
    catalog_asset_names = list(available_assets)
    prompt = (
        "Sound-design Filipino narration. Return compact JSON with one annotation per "
        "paragraph in input order. Fields: emotion, sounds, sound, layers. For known "
        "effects, sounds is an ARRAY of 1-5 exact asset IDs from the catalog; sound is "
        "an empty string and layers is empty. Order continuous background beds before "
        "sparse point events. If multiple audible sources are described or established, "
        "put each matching asset in sounds; do not collapse a multi-source scene to one "
        "cue. For a paragraph mentioning bonfire, sea breeze, and nearby water, sounds "
        "must include fire-cracking, wind-gusting-soft, and waves-gentle; add "
        "crickets-chirping for an established outdoor night. Add night-creatures or "
        "wild-dogs-howling only when supported by the setting. Do not add effects just "
        "because they fit the mood. For one important effect with no matching catalog "
        "asset, sounds is empty, sound is one short description, and layers contains "
        "1-3 best-fitting procedural IDs. Approximate it; do not claim it is a recording. "
        "No narration text, indices, explanations, or extra keys. Return exactly "
        f"{len(paragraphs)} annotations.\n"
        f"Existing catalog: {list(available_assets.items())}\n"
        f"User guidance: {instructions}\n"
        f"Part: {part_title}\n"
        "Paragraphs:\n"
        + json.dumps(paragraphs, ensure_ascii=False, separators=(",", ":"))
    )
    response_schema = {
        "type": "object",
        "properties": {
            "annotations": {
                "type": "array",
                "minItems": len(paragraphs),
                "maxItems": len(paragraphs),
                "items": {
                    "type": "object",
                    "properties": {
                        "emotion": {"type": "string", "enum": list(EMOTIONS)},
                        "sounds": {
                            "type": "array",
                            "items": {"type": "string", "enum": catalog_asset_names},
                            "minItems": 0,
                            "maxItems": 5,
                        },
                        "sound": {"type": "string", "maxLength": 80},
                        "layers": {
                            "type": "array",
                            "items": {"type": "string", "enum": primitive_assets},
                            "minItems": 0,
                            "maxItems": 3,
                        },
                    },
                    "required": ["emotion", "sounds", "sound", "layers"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["annotations"],
        "additionalProperties": False,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "format": response_schema,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": min(192, 40 + 48 * len(paragraphs)),
                },
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        report_progress(
            f"Analyzing {len(paragraphs)} narration paragraph(s) in '{part_title}' "
            f"with Ollama model '{model}'."
        )
        with progress_heartbeat(f"AI analysis for '{part_title}'"):
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise RuntimeError(
                f"Ollama model '{model}' is unavailable. Start Ollama and run "
                f"'docker compose exec ollama ollama pull {model}'."
            ) from error
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama request failed ({error.code}): {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Could not connect to Ollama. Start it with 'docker compose up -d ollama'."
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError("Ollama returned an invalid JSON response.") from error

    raw_response = result.get("response")
    try:
        decoded_response = json.loads(raw_response)
        annotations = decoded_response["annotations"]
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError) as error:
        if len(paragraphs) > 1:
            midpoint = len(paragraphs) // 2
            report_progress(
                f"Ollama returned malformed JSON for {len(paragraphs)} paragraphs "
                f"in '{part_title}'; retrying as smaller batches."
            )
            return annotate_paragraphs(
                paragraphs[:midpoint],
                part_title,
                model,
                base_url,
                instructions,
                assets_dir,
            ) + annotate_paragraphs(
                paragraphs[midpoint:],
                part_title,
                model,
                base_url,
                instructions,
                assets_dir,
            )
        preview = repr(raw_response)[:600] if raw_response is not None else repr(result)[:600]
        reason = "response was truncated" if result.get("done_reason") == "length" else str(error)
        raise RuntimeError(
            "Ollama returned malformed SFX annotations for a single paragraph "
            f"({reason}; done_reason={result.get('done_reason')!r}). "
            f"Response preview: {preview}"
        ) from error
    if not isinstance(annotations, list) or len(annotations) != len(paragraphs):
        if len(paragraphs) == 1:
            returned_count = len(annotations) if isinstance(annotations, list) else "a non-list"
            raise RuntimeError(
                "Ollama did not return one SFX annotation for the paragraph "
                f"(received {returned_count}). Try another model with BRAIN_MODEL."
            )
        returned_count = len(annotations) if isinstance(annotations, list) else "a non-list"
        midpoint = len(paragraphs) // 2
        report_progress(
            f"Ollama returned {returned_count} annotations for {len(paragraphs)} "
            f"paragraphs in '{part_title}'; retrying as smaller batches."
        )
        return annotate_paragraphs(
            paragraphs[:midpoint],
            part_title,
            model,
            base_url,
            instructions,
            assets_dir,
        ) + annotate_paragraphs(
            paragraphs[midpoint:],
            part_title,
            model,
            base_url,
            instructions,
            assets_dir,
        )

    ordered_annotations = []
    for position, item in enumerate(annotations, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(
                f"Ollama returned a malformed compact annotation for paragraph {position}."
            )
        emotion = item.get("emotion")
        sounds = item.get("sounds")
        sound = item.get("sound")
        layers = item.get("layers")
        if sounds is None and isinstance(sound, str):
            sounds = [candidate.strip() for candidate in sound.split(",") if candidate.strip()]
            sound = ""
        if (
            not isinstance(emotion, str)
            or emotion not in EMOTIONS
            or not isinstance(sound, str)
            or len(sound) > 80
            or not isinstance(sounds, list)
            or len(sounds) > 5
            or not isinstance(layers, list)
        ):
            raise RuntimeError(
                f"Ollama returned an incomplete compact annotation for paragraph {position}."
            )

        sound = sound.strip()
        if sounds:
            if any(
                not isinstance(asset_name, str) or asset_name not in available_assets
                for asset_name in sounds
            ):
                raise RuntimeError(
                    f"Ollama returned an unsupported catalog SFX for paragraph {position}."
                )
            selected_assets = list(dict.fromkeys(sounds))
        else:
            normalized_sound = re.sub(
                r"[^a-z0-9]+", "-", sound.lower()
            ).strip("-")
            catalog_match = next(
                (
                    asset_name
                    for asset_name, description in available_assets.items()
                    if normalized_sound
                    in {
                        asset_name.casefold(),
                        re.sub(r"[^a-z0-9]+", "-", description.casefold()).strip("-"),
                    }
                ),
                None,
            )
            if catalog_match is not None and not layers:
                selected_assets = [catalog_match]
                ordered_annotations.append((emotion, selected_assets))
                continue

            if (
                not sound
                or not 1 <= len(layers) <= 3
                or any(not isinstance(layer, str) or layer not in ASSET_CUES for layer in layers)
            ):
                recipe = repair_sfx_recipe(
                    {"description": sound, "layers": layers},
                    paragraphs[position - 1],
                    emotion,
                    model,
                    base_url,
                    part_title,
                    position,
                )
            else:
                name = normalized_sound[:56].strip("-")
                if not name:
                    raise RuntimeError(
                        f"Ollama returned no usable name for the new SFX in paragraph {position}."
                    )
                recipe = {
                    "name": name,
                    "description": sound[:160],
                    "layers": [
                        {"asset": asset_name, "gain": 0.65}
                        for asset_name in dict.fromkeys(layers)
                    ],
                }
            if recipe["name"] in available_assets:
                selected_assets = [recipe["name"]]
            else:
                selected_assets = [
                    generate_new_asset(
                        recipe["name"],
                        recipe["description"],
                        recipe["layers"],
                        assets_dir,
                    )
                ]
        ordered_annotations.append((emotion, selected_assets))
    report_progress(f"AI analysis finished for '{part_title}'.")
    return ordered_annotations


def create_annotated_script(
    script_text, model, base_url, instructions, assets_dir, on_part=None,
    on_part_start=None,
):
    completed_lines = []
    for part_number, title, paragraphs in extract_paragraphs(script_text):
        report_progress(
            f"Starting SFX analysis for part {part_number}: '{title}' "
            f"({len(paragraphs)} paragraph(s))."
        )
        if on_part_start is not None:
            on_part_start(part_number, title, paragraphs, completed_lines)
        part_lines = []
        for batch_start in range(0, len(paragraphs), 2):
            batch = paragraphs[batch_start:batch_start + 2]
            annotations = annotate_paragraphs(
                batch, title, model, base_url, instructions, assets_dir
            )
            for offset, (paragraph, (emotion, sfx)) in enumerate(
                zip(batch, annotations), start=batch_start + 1
            ):
                cue_assets = [
                    asset_name if asset_name in ASSET_CUES else f"custom:{asset_name}"
                    for asset_name in sfx
                ]
                part_lines.extend(
                    (
                        f"### [BAHAGI {part_number}: {title} - LINE {offset} - EMOTION: {emotion}]",
                        f"(AMBIENT SFX: {', '.join(cue_assets)})",
                        paragraph,
                        "",
                    )
                )
            remaining = paragraphs[batch_start + len(batch):]
            snapshot = list(completed_lines) + part_lines
            if remaining:
                snapshot.append(
                    "\n".join(
                        [
                            f"### [BAHAGI {part_number}: {title} - AI ANALYSIS IN PROGRESS]",
                            *[
                                line
                                for pending_index, pending_paragraph in enumerate(
                                    remaining,
                                    start=batch_start + len(batch) + 1,
                                )
                                for line in (
                                    f"# Paragraph {pending_index}: emotion and SFX pending",
                                    pending_paragraph,
                                )
                            ],
                        ]
                    )
                )
            if on_part is not None:
                on_part("\n".join(snapshot) + "\n")
        completed_lines.extend(part_lines)
    return "\n".join(completed_lines)


def write_annotated_script(
    script_text, temporary_path, model, base_url, instruction_path,
    assets_dir
):
    instructions = read_brain_instructions(instruction_path)
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_text("", encoding="utf-8")
    def update_script(text):
        temporary_path.write_text(text, encoding="utf-8")

    def show_part_in_progress(part_number, title, paragraphs, completed_lines):
        pending_lines = [
            f"### [BAHAGI {part_number}: {title} - AI ANALYSIS IN PROGRESS]"
        ]
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            pending_lines.extend(
                (
                    f"# Paragraph {paragraph_index}: emotion and SFX pending",
                    paragraph,
                )
            )
        temporary_path.write_text(
            "\n".join((*completed_lines, *pending_lines, "")),
            encoding="utf-8",
        )

    report_progress(
        f"Creating a temporary, paragraph-level SFX annotation script at {temporary_path}."
    )
    create_annotated_script(
        script_text,
        model,
        base_url,
        instructions,
        assets_dir,
        on_part=update_script,
        on_part_start=show_part_in_progress,
    )
    report_progress(f"Temporary SFX annotation script is ready: {temporary_path}")
    return temporary_path
