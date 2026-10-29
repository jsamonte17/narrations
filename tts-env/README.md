# Narration app

The narration app creates narrated MP3 audio or MP4 video using online Edge TTS by default, with an optional local Tagalog MMS backend. Episode scripts can use the local AI brain to select ambient SFX for each narration paragraph; tagged scripts can also be rendered as videos. The separate AnimatedDrawings pipeline is documented in the root README.

Keep narration scripts in the repository's root-level `inputs/` directory. Generated videos and audio go into the root-level `output/` directory. From the repository root, build and render a video with Docker Compose:

```bash
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"  # Linux
docker compose build tts-env
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/dayaw_actions.txt
```

The MP4 is written to `output/dayaw_actions.mp4`. The output basename is automatically taken from the input filename; you do not need to specify an output path. Start with [inputs/dayaw_actions.txt](../inputs/dayaw_actions.txt), or save your own tagged script in `inputs/` and use that path. The full Episode 1 script is structured for audio-only narration unless you add `[ACTION: ...]` tags.

Put one supported action tag before each scene. The words after the tag are both spoken and shown as a caption:

```text
[ACTION: wave]
Siya si Dayaw, ang pinakamatapang na mandirigma ng lalawigan.

[ACTION: guard]
Naramdaman ni Dayaw ang pangangatog ng lupa. Hinawakan niya ang kampilan at humanda sa pagdating ng Bakunawa.

[ACTION: jump]
Tumalon si Dayaw patungo sa kalaban.
```

Supported tags are `[ACTION: wave]`, `[ACTION: guard]`, `[ACTION: jump]`, and `[ACTION: dance]`. Every tagged scene needs narration text. The narrator defaults to female. To choose male for one run:

```bash
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/dayaw_actions.txt \
  --voice male
```

To make male the default narrator, copy `.env.example` to `.env` in the repository root and set `NARRATOR_GENDER=male`. Set it to `female` to use the default Filipino female voice. The `--voice female` or `--voice male` option overrides this setting for an individual run.

Speech uses the online `edge-tts` service by default, so the text for each scene is sent to that service during generation. To use the local Tagalog model, pass `--tts-engine mms`; its first run downloads the selected Hugging Face model automatically, caches it under `assets/huggingface/`, and then performs CPU inference locally. Set `TTS_MODEL_ID` in `.env` to try another Hugging Face repository without rebuilding the image. This backend requires a Transformers `VitsModel`-compatible checkpoint and tokenizer; arbitrary TTS repositories may use incompatible architectures or lack Tagalog support. Check each model card and license. The default MMS model has one bundled voice, no direct emotion controls, and a CC-BY-NC 4.0 license, so it is noncommercial only. For a cue-free `BAHAGI` script, pass `--no-ai-sfx` to synthesize narration without Ollama or ambience. Output video and audio are stored in the root-level `output/` directory.

## Local AI ambient SFX

For audio-only `BAHAGI` episodes, a local Ollama model assigns an emotion and SFX to each narration paragraph, and may adjust punctuation in the temporary TTS text to suggest natural pauses and emphasis. It must preserve every original word, spelling, capitalization, and word order; the app rejects altered words. Punctuation may help Edge TTS phrasing, but does not provide direct emotion or speaking-style controls. A paragraph can combine up to five catalog assets, with continuous beds listed before sparse point events (for example, soft wind and crickets with occasional night-creature calls or distant wild-dog howls when the setting supports them). The model reuses matching catalog entries or creates a new, named WAV by combining procedural synthesis primitives. Generated WAVs, descriptions, and layer recipes are indexed in `assets/sfx/catalog.sqlite3`, a local SQLite database persisted through the `assets/` Docker mount. Later runs include those generated sounds in the brain's available SFX catalog, so it can match and reuse them. The procedural renderer creates sound textures using filtered noise, evolving envelopes, chirp sweeps, and transient crackles rather than relying on fixed pitched tones for natural ambience. This can approximate SFX but does not make field recordings. Analysis uses compact two-paragraph batches and caps generated tokens to reduce CPU inference time. The temporary annotation script is updated after each batch, so completed annotations and TTS-ready text appear while later paragraphs are still processing. If Ollama returns malformed JSON for a multi-paragraph batch, the app retries in smaller batches; if a single-paragraph response remains malformed, the error includes a bounded preview and Ollama completion reason. Invalid custom recipes are repaired without substituting generic ambience. If no valid recipe can be produced, the app reports an error and does not create a misleading WAV. The original script is unchanged. This process needs no NVIDIA GPU or separate audio-generation model.

To monitor an episode from another terminal, for example:

```bash
tail -f temp/1_dayaw_annotated_sfx.txt
```

The file is visible in the project root, remains after the narration run, and updates as each part starts and finishes Ollama analysis.

Customize sound-design choices in the root `brain-instructions.md`; it is mounted read-only and loaded on every run. Start Ollama and download the text brain once:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b
```

Set `BRAIN_MODEL` in `.env` to select another Ollama text model. The Ollama brain runs locally; speech uses online Edge TTS by default, or local MMS when `TTS_ENGINE=mms` is configured.

The brain prefers matching the reusable sound catalog. If no catalog entry fits, Ollama chooses and layers supported sound primitives to create a descriptively named custom WAV. New assets are saved in `assets/sfx/` and registered in SQLite for later matching. Add `--no-ai-sfx` to skip paragraph-level analysis and use the script's section-level cues.

The procedural renderer provides reusable assets including `fire-cracking.wav`, `wind-gusting-hard.wav`, `wind-gusting-soft.wav`, `waves-gentle.wav`, `waves-crashing.wav`, `river-flowing.wav`, `crickets-chirping.wav`, `crickets-fading.wav`, `rain-falling-hard.wav`, `rain-falling-soft.wav`, `rain-fading.wav`, `ominous-low-drone.wav`, and `agimat-humming.wav`. Exact catalog IDs reuse those assets. An uncatalogued free-text cue is sent to Ollama for a custom procedural recipe; the resulting WAV and cue description are saved in SQLite and reused on later runs. Invalid recipes are sent back to Ollama for repair, not replaced with an unrelated existing effect. If repair fails, generation stops with an error. Custom sound physics are still limited to implemented synthesis primitives, so a genuinely different synthesis technique requires adding a primitive.

To create or check reusable assets without generating narration (start Ollama first if the script contains uncatalogued free-text cues):

```bash
docker compose run --rm tts-env \
  python scripts/generate_ambient_sfx.py \
  inputs/1_dayaw.txt
```

Assets are generated at 30 seconds by default and stored under `assets/sfx/`; existing asset files are reused rather than overwritten. Use `--duration 45` to change the duration of newly generated assets. The `assets/` folder is mounted into Docker, and generated WAVs are git-ignored.

## Narration-only MP3

To create speech without rendering the characters or video, use `--audio-only`. It accepts a plain text script, an action-tagged script, or an episode script split into `BAHAGI` sections with ambient cues. For the full episode script:

```bash
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/1_dayaw.txt \
  --audio-only
```

This creates `output/1_dayaw.mp3` and automatically analyzes each paragraph, writes temporary emotion/SFX annotations, then reuses or generates the selected WAV files and mixes them beneath their narration. The same `--voice female` / `--voice male` options and `NARRATOR_GENDER` default apply. Add `--no-ai-sfx` to use the original section-level cues instead. The output extension is selected automatically from the output mode: `.mp4` for video or `.mp3` for audio-only. An explicit output path is optional if you want a custom filename.

The foreground narration command prints timestamped phase progress and a heartbeat every 15 seconds during long model or TTS requests. To monitor Ollama in another terminal:

```bash
docker compose logs -f ollama
```

You can also make MP3-only output the default in the root `.env` by setting `AUDIO_ONLY=true`. Set `AUDIO_ONLY=false` (the default) to create MP4 videos. The command-line `--audio-only` and `--video` flags override the `.env` setting for one run. For example, with `AUDIO_ONLY=true`, pass `--video` to create an MP4.
