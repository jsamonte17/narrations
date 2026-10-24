# Narrated stickman video

The system creates an MP4 with the original black-ink stickman characters and spoken narration. It reads one action-tagged scene at a time, generates speech for that scene, animates it for the speech duration, then combines the scenes into a video. Dayaw performs each tagged action while the horned Bakunawa moves in the scene. The characters are drawn by `scripts/stickman_animation.py`; no AnimatedDrawings characters, motion files, or model service are used.

Keep narration scripts in the repository's root-level `inputs/` directory. Generated videos and audio go into the root-level `output/` directory. From the repository root, build and render a video with Docker Compose:

```bash
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"  # Linux
docker compose build tts-env
docker compose run --rm tts-env \
  python scripts/stickman_animation.py \
  inputs/dayaw_actions.txt \
  output/dayaw.mp4
```

The MP4 is written to `output/dayaw.mp4`. Start with [inputs/dayaw_actions.txt](../inputs/dayaw_actions.txt), or save your own tagged script in `inputs/` and use that path.

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
  python scripts/stickman_animation.py \
  inputs/dayaw_actions.txt \
  output/dayaw_male.mp4 \
  --voice male
```

To make male the default narrator, copy `.env.example` to `.env` in the repository root and set `NARRATOR_GENDER=male`. Set it to `female` to use the default Filipino female voice. The `--voice female` or `--voice male` option overrides this setting for an individual run.

Speech is synthesized using the online `edge-tts` service, so the text for each scene is sent to that service during generation. Output video and audio are stored in the root-level `output/` directory.

## Narration-only MP3

To create speech without rendering the characters or video, use `--audio-only`. This accepts either a plain text narration file or the tagged scene script shown above. For a plain text narration, save the script in `inputs/` and run:

```bash
docker compose run --rm tts-env \
  python scripts/stickman_animation.py \
  inputs/narration.txt \
  output/narration.mp3 \
  --audio-only
```

The same `--voice female` / `--voice male` options and `NARRATOR_GENDER` default apply. When the output argument is omitted, audio-only mode writes `output/<script-name>.mp3`.

You can also make MP3-only output the default in the root `.env` by setting `AUDIO_ONLY=true`. Set `AUDIO_ONLY=false` (the default) to create MP4 videos. The command-line `--audio-only` and `--video` flags override the `.env` setting for one run. For example, with `AUDIO_ONLY=true`, pass `--video` to create an MP4.
