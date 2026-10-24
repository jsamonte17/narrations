# Narration and Animation

This repository has two Docker-based workflows:

1. **Narrated stickman videos or MP3 narration** — uses original, procedurally drawn stickman characters and Edge TTS.
2. **AnimatedDrawings** — a separate image-to-animation pipeline for animating a supplied character drawing. It uses its own model service and assets.

The workflows share one root Docker Compose file, but you only need to build or run the services for the workflow you want. No Python environment is installed on the host.

## Requirements

- Docker Engine or Docker Desktop with the Docker Compose plugin.
- Internet access when building images and when generating speech with Edge TTS.
- On Linux, export your user and group IDs before running containers so generated files are owned by your host user:

  ```bash
  export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
  ```

## Narrated stickman video or MP3

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

### Configure narrator and output mode

Copy [`.env.example`](./.env.example) to `.env` in the repository root if you want to configure defaults:

```dotenv
NARRATOR_GENDER=female
AUDIO_ONLY=false
```

- `NARRATOR_GENDER` can be `female` or `male`. The default is `female`.
- `AUDIO_ONLY` can be `true` for MP3-only output or `false` for a narrated MP4. The default is `false`.
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
  python scripts/stickman_animation.py \
  inputs/dayaw_actions.txt \
  output/dayaw.mp4
```

The MP4 contains H.264 video and AAC narration audio. Open it outside VS Code with:

```bash
xdg-open output/dayaw.mp4
```

### Generate narration-only MP3

Use a plain-text or tagged script:

```bash
docker compose run --rm tts-env \
  python scripts/stickman_animation.py \
  inputs/narration.txt \
  output/narration.mp3 \
  --audio-only
```

If `.env` has `AUDIO_ONLY=true`, the command creates an MP3 by default; pass `--video` to request an MP4 instead. Conversely, `--audio-only` forces an MP3 when `AUDIO_ONLY=false`.

To select a narrator for one run:

```bash
docker compose run --rm tts-env \
  python scripts/stickman_animation.py \
  inputs/dayaw_actions.txt \
  output/dayaw_male.mp4 \
  --voice male
```

The script writes outputs to the root-level [`output/`](./output/) folder. The root input and output folders are mounted into the TTS container; the input mount is read-only. Generated files are ignored by Git.

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

