# Narration App

This repository has two Docker-based workflows:

1. **Narration app** — generates narrated MP3 audio or MP4 video with Edge TTS and optional emotion-aware ambient SFX.
2. **AnimatedDrawings** — a separate image-to-animation pipeline for animating a supplied character drawing. It uses its own model service and assets.

The workflows share one root Docker Compose file, but you only need to build or run the services for the workflow you want. No Python environment is installed on the host.

## Requirements

- Docker Engine or Docker Desktop with the Docker Compose plugin.
- Internet access when building images and when generating speech with Edge TTS.
- On Linux, export your user and group IDs before running containers so generated files are owned by your host user:

  ```bash
  export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
  ```

## Narration app

### Prepare a script

Place scripts in the root-level [`inputs/`](./inputs/) directory. For an animated video, put one supported action tag before each scene. The text following a tag is both spoken and shown as a caption:

```text
[ACTION: wave]
Siya si Dayaw, ang pinakamatapang na mandirigma ng lalawigan.

[ACTION: guard]
Naramdaman ni Dayaw ang pangangatog ng lupa. Hinawakan niya ang kampilan at humanda sa pagdating ng Bakunawa.

[ACTION: jump]
Tumalon si Dayaw patungo sa kalaban.
```

Supported actions are `wave`, `guard`, `jump`, and `dance`. A tagged scene must have narration text. The action tag selects a procedural pose; the system does not infer the action from prose.

For audio-only narration, scripts may be plain text without action tags. Tagged scripts also work in audio-only mode.

### Generate emotion-aware ambient sound

For episode scripts with `BAHAGI` sections, narration-only output uses a local Ollama model to assign an emotion and SFX to each narration paragraph. The brain reuses an existing WAV when it fits or composes a new WAV by combining supported procedural sound primitives. New WAVs and their descriptions/layer recipes are saved under [`assets/sfx/`](./assets/sfx/) and indexed in a local SQLite catalog at `assets/sfx/catalog.sqlite3`, so future runs can match and reuse generated effects. This does not require an NVIDIA GPU or a separate audio-generation model. The app writes a temporary annotated script to `temp/<script-name>_annotated_sfx.txt`, showing the current part and paragraphs as pending while Ollama analyzes them, then replacing them with annotations when that part completes. FFmpeg then mixes each bed beneath its paragraph. The original input is never changed.

For example, watch the annotations for `inputs/1_dayaw.txt` from another terminal with `tail -f temp/1_dayaw_annotated_sfx.txt`. The file is retained after the run and updated when each part's Ollama analysis completes.

Start the local Ollama service and download the text model once:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b
```

Generated effects are synthesized from built-in primitives such as wind, rain, water, fire, insects, drones, and magical tones. This is local procedural synthesis, not a new neural audio model; truly different sound physics require adding a new synthesis primitive.

Customize the brain's sound-design guidance in [`brain-instructions.md`](./brain-instructions.md). The file is mounted read-only and read for every run. The Ollama brain and procedural WAV synthesis run locally; the separate Edge TTS narration step still needs internet access and sends narration text to that service.

Run the episode:

```bash
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/1_dayaw.txt \
  --audio-only
```

The output is `output/1_dayaw.mp3`. The brain chooses existing assets or composes a new procedural sound from supported primitives when needed. Generated WAVs remain git-ignored. To use only the script's existing part-level cues without Ollama analysis, add `--no-ai-sfx`.

The narration command prints timestamped phase progress and a 15-second heartbeat while waiting for Ollama or Edge TTS. To monitor the Ollama service in a second terminal, use:

```bash
docker compose logs -f ollama
```

To create or check reusable assets without TTS or mixing, run the procedural generator directly:

```bash
docker compose run --rm tts-env \
  python scripts/generate_ambient_sfx.py \
  inputs/1_dayaw.txt
```

Missing assets are generated as descriptive names such as `assets/sfx/fire-cracking.wav` and `assets/sfx/wind-gusting-hard.wav`. Existing assets are reused rather than overwritten. Change the duration of newly generated reusable WAV assets, in seconds, with `--duration`:

```bash
docker compose run --rm tts-env \
  python scripts/generate_ambient_sfx.py \
  inputs/1_dayaw.txt \
  --duration 150
```

The standalone generator creates or reuses assets only and does not call TTS or the AI brain. Generated `.wav` files in `assets/sfx/` are git-ignored; the directory itself is retained in the repository.

### Configure narrator and output mode

Copy [`.env.example`](./.env.example) to `.env` in the repository root if you want to configure defaults:

```dotenv
NARRATOR_GENDER=female
AUDIO_ONLY=false
BRAIN_MODEL=qwen2.5:3b
```

- `NARRATOR_GENDER` can be `female` or `male`. The default is `female`.
- `AUDIO_ONLY` can be `true` for MP3-only output or `false` for a narrated MP4. The default is `false`.
- `BRAIN_MODEL` selects the local Ollama model used to annotate episode paragraphs. The default is `qwen2.5:3b`.
- Command-line `--voice female` / `--voice male` and `--audio-only` / `--video` flags override these defaults for one run.

The Filipino Edge TTS voices are `fil-PH-BlessicaNeural` (female) and `fil-PH-AngeloNeural` (male). Speech generation requires an internet connection; narration text is sent to the online Edge TTS service.

### Build and generate a video

Build the TTS image once:

```bash
docker compose build tts-env
```

Generate a video from a tagged script:

```bash
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/dayaw_actions.txt
```

The output name is generated from the input filename: `inputs/dayaw_actions.txt` becomes `output/dayaw_actions.mp4` when video mode is enabled. You do not need to provide an output path. Video input needs `[ACTION: ...]` tags; the full `inputs/1_dayaw.txt` episode is an audio-only script unless action tags are added. The MP4 contains H.264 video and AAC narration audio. Open it outside VS Code with:

```bash
xdg-open output/dayaw_actions.mp4
```

### Generate narration-only MP3

Use a plain-text or tagged script:

```bash
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/1_dayaw.txt \
  --audio-only
```

This creates `output/1_dayaw.mp3`. For a `BAHAGI` episode, Ollama analyzes each paragraph and chooses emotion-aware ambience; the annotated script is temporary and the original input remains unchanged. Start Ollama and pull the model as described in [Generate emotion-aware ambient sound](#generate-emotion-aware-ambient-sound) first. Add `--no-ai-sfx` to use only the script's existing part-level ambience cues. If `.env` has `AUDIO_ONLY=true`, the command creates an MP3 by default without needing `--audio-only`; pass `--video` to request a video instead. Conversely, `--audio-only` forces an MP3 when `AUDIO_ONLY=false`.

To select a narrator for one run:

```bash
docker compose run --rm tts-env \
  python scripts/narration.py \
  inputs/dayaw_actions.txt \
  --voice male
```

The output extension follows the selected mode (`.mp4` for video or `.mp3` for audio-only), and the basename follows the input script. You can optionally provide an explicit output path as the second positional argument when you want a custom name. Existing output with the same generated name is overwritten. Outputs are written to the root-level [`output/`](./output/) folder. The root input and output folders are mounted into the TTS container; the input mount is read-only. Generated files are ignored by Git.

More detail about the stickman renderer is in [`tts-env/README.md`](./tts-env/README.md).

## AnimatedDrawings image-to-animation

This is a separate workflow from the original stickman video generator. It uses AnimatedDrawings' image-to-animation models to infer a rig from a supplied drawing. It does not synthesize narration audio.

Put a PNG or JPEG of one full-body human-like drawing in [`AnimatedDrawings/inputs/`](./AnimatedDrawings/inputs/). A plain background and clearly separated limbs generally help pose detection.

Build both AnimatedDrawings images:

```bash
docker compose build animated-drawings torchserve
```

On Linux, export `LOCAL_UID` and `LOCAL_GID` as described above. Start TorchServe and wait for its health check:

```bash
docker compose up -d torchserve
docker compose ps
```

Run the image-to-animation pipeline, replacing the example name with your input image:

```bash
docker compose run --rm animated-drawings \
  inputs/my_drawing.png output/my_drawing
```

The animation and editable annotation files are written under [`AnimatedDrawings/output/`](./AnimatedDrawings/output/). When finished, stop the model service:

```bash
docker compose down
```

The initial TorchServe build downloads model weights and compiles MMCV; it can take several minutes and uses considerably more disk and memory than the TTS-only service. The model pipeline uses CPU inference. To try the bundled pre-rigged demo without starting TorchServe:

```bash
docker compose run --rm --no-deps --entrypoint python animated-drawings \
  -c "from animated_drawings import render; render.start('examples/config/mvc/docker_demo.yaml')"
```

That demo writes to `AnimatedDrawings/output/demo.gif`. See the [AnimatedDrawings guide](./AnimatedDrawings/README.md) for further information.

## Compose services and data locations

The root [`docker-compose.yml`](./docker-compose.yml) defines:

| Service | Purpose | Host data |
| --- | --- | --- |
| `tts-env` | Narration MP3 and stickman MP4 generation | Reads root `inputs/`; writes root `output/` |
| `torchserve` | Detector and pose-estimator model server for AnimatedDrawings | Model data is inside the image/container |
| `animated-drawings` | Converts a drawing to an animation | Reads `AnimatedDrawings/inputs/`; writes `AnimatedDrawings/output/` and logs |

Typical commands:

```bash
docker compose config --quiet       # Validate the Compose file
docker compose ps                   # View service status
docker compose logs torchserve      # Inspect model-server logs
docker compose down                 # Stop Compose services
```

Do not run `docker compose up` to use only the TTS workflow; use `docker compose run --rm tts-env ...` as shown above. This avoids starting the heavier AnimatedDrawings services.
