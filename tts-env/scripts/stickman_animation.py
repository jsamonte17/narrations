#!/usr/bin/env python3
"""Create a short, original stickman animation from tagged script scenes."""

import argparse
import asyncio
import math
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont


WIDTH = 800
HEIGHT = 600
FPS = 12
TAG_PATTERN = re.compile(r"\[ACTION:\s*([a-z_]+)\s*\]", re.IGNORECASE)
ACTION_NAMES = ("wave", "guard", "jump", "dance")
VOICE_IDS = {
    "female": "fil-PH-BlessicaNeural",
    "male": "fil-PH-AngeloNeural",
}
BACKGROUND = (247, 244, 235)
INK = (29, 28, 27)
PENCIL = (82, 78, 71)


def parse_scenes(script_text):
    tags = list(TAG_PATTERN.finditer(script_text))
    if not tags:
        raise ValueError("No action tags found. Add tags such as [ACTION: wave].")

    scenes = []
    for index, tag in enumerate(tags):
        action = tag.group(1).lower()
        if action not in ACTION_NAMES:
            raise ValueError(
                f"Unknown action '{action}'. Choose from: {', '.join(ACTION_NAMES)}."
            )
        end = tags[index + 1].start() if index + 1 < len(tags) else len(script_text)
        narration = " ".join(script_text[tag.end():end].split())
        if not narration:
            raise ValueError(f"The '{action}' scene has no narration text.")
        scenes.append((action, narration))
    return scenes


def parse_audio_scenes(script_text):
    if not TAG_PATTERN.search(script_text):
        narration = " ".join(script_text.split())
        if not narration:
            raise ValueError("The narration script is empty.")
        return [("wave", narration)]
    return parse_scenes(script_text)


def clean_caption(text):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return ascii_text or " "


def segment(start, angle, length):
    return (
        start[0] + math.sin(angle) * length,
        start[1] + math.cos(angle) * length,
    )


def pose_for(action, phase):
    wave = math.sin(phase * math.tau * 2)
    bounce = max(0, math.sin(phase * math.tau))
    if action == "wave":
        return {
            "lift": 0,
            "left_arm": (-2.45, 0.25 + wave * 0.72),
            "right_arm": (-0.35, 0.2),
            "legs": (-0.08, 0.08),
        }
    if action == "guard":
        pulse = math.sin(phase * math.tau * 2)
        return {
            "lift": abs(pulse) * 3,
            "left_arm": (-2.25 + pulse * 0.06, 1.65 + pulse * 0.12),
            "right_arm": (-0.8 - pulse * 0.06, -1.55 - pulse * 0.12),
            "legs": (-0.24, 0.24),
        }
    if action == "jump":
        return {
            "lift": bounce * 110,
            "left_arm": (2.7, 0.35),
            "right_arm": (-2.7, -0.35),
            "legs": (-0.52 if bounce > 0.3 else -0.1, 0.52 if bounce > 0.3 else 0.1),
        }
    sway = math.sin(phase * math.tau)
    return {
        "lift": abs(sway) * 15,
        "left_arm": (-1.0 + sway * 0.8, 0.2),
        "right_arm": (0.4 - sway * 0.8, -0.2),
        "legs": (-0.2 + sway * 0.25, 0.2 - sway * 0.25),
    }


def draw_dayaw(draw, action, phase):
    pose = pose_for(action, phase)
    center_x = 270
    hip_y = 360 - pose["lift"]
    head_y = hip_y - 190
    shoulder_left = (center_x - 4, head_y + 66)
    shoulder_right = (center_x + 4, head_y + 66)
    hip = (center_x, hip_y)
    stroke = 7

    hand_points = []
    for shoulder, (upper_angle, lower_angle) in (
        (shoulder_left, pose["left_arm"]),
        (shoulder_right, pose["right_arm"]),
    ):
        elbow = segment(shoulder, upper_angle, 78)
        hand = segment(elbow, upper_angle + lower_angle, 73)
        hand_points.append(hand)
        draw.line((shoulder, elbow, hand), fill=INK, width=stroke, joint="curve")
        draw.ellipse((elbow[0] - 4, elbow[1] - 4, elbow[0] + 4, elbow[1] + 4), fill=INK)
        for finger in range(3):
            start = (hand[0] + finger * 2, hand[1])
            draw.line((start, (start[0] - 4 + finger * 5, start[1] - 10)),
                      fill=INK, width=2)

    for side, angle in zip((-1, 1), pose["legs"]):
        hip_point = (hip[0] + side * 5, hip[1])
        knee = segment(hip_point, angle, 68)
        foot_angle = angle + (0.16 if angle >= 0 else -0.16)
        foot = segment(knee, foot_angle, 70)
        draw.line((hip_point, knee, foot), fill=INK, width=stroke, joint="curve")
        draw.line((foot[0] - 10, foot[1], foot[0] + 15, foot[1] - 3), fill=INK, width=5)

    draw.line((center_x, head_y + 39, hip[0], hip[1]), fill=INK, width=8)
    draw.line((center_x - 9, head_y + 77, center_x + 9, head_y + 77), fill=INK, width=4)
    draw.ellipse((center_x - 20, head_y - 20, center_x + 20, head_y + 20),
                 fill=INK)
    for offset in range(5):
        draw.arc(
            (center_x - 20 + offset, head_y - 20 + offset,
             center_x + 20 - offset, head_y + 20 - offset),
            start=35 + offset * 13, end=325 - offset * 9,
            fill=PENCIL if offset % 2 == 0 else BACKGROUND, width=2,
        )

    if action in ("guard", "jump"):
        hand = hand_points[1]
        blade_tip = (hand[0] + 87, hand[1] - 112)
        blade_base = (hand[0] + 4, hand[1] - 6)
        draw.line((blade_base, blade_tip), fill=INK, width=7)
        draw.line((blade_base[0] - 13, blade_base[1] + 12,
                   blade_base[0] + 13, blade_base[1] - 12), fill=INK, width=5)
        draw.line((blade_base[0] - 4, blade_base[1] + 5,
                   blade_base[0] + 3, blade_base[1] - 5), fill=PENCIL, width=2)


def draw_bakunawa(draw, action, phase):
    sway = math.sin(phase * math.tau)
    head_x = 565
    head_y = 160 + abs(sway) * 5
    shoulder = (head_x, head_y + 28)
    hip = (head_x + sway * 8, 350)
    draw.line((shoulder, hip), fill=INK, width=9)

    for side, upper_angle in ((-1, -2.15), (1, -0.9)):
        elbow = segment(shoulder, upper_angle + sway * 0.12, 65)
        hand = segment(elbow, upper_angle + 1.15, 58)
        draw.line((shoulder, elbow, hand), fill=INK, width=7, joint="curve")
        for claw in range(3):
            claw_start = (hand[0] + claw * 4, hand[1])
            draw.line((claw_start, (claw_start[0] + side * 9, claw_start[1] + 12)),
                      fill=INK, width=3)

    for side, angle in ((-1, -0.28 + sway * 0.06), (1, 0.3 - sway * 0.06)):
        hip_point = (hip[0] + side * 5, hip[1])
        knee = segment(hip_point, angle, 68)
        foot = segment(knee, angle + side * 0.12, 68)
        draw.line((hip_point, knee, foot), fill=INK, width=8, joint="curve")
        draw.line((foot[0] - 8, foot[1], foot[0] + 15, foot[1] - 2),
                  fill=INK, width=5)

    radius = 25
    draw.ellipse((head_x - radius, head_y - radius,
                  head_x + radius, head_y + radius), fill=INK)
    for offset in range(5):
        draw.arc(
            (head_x - radius + offset, head_y - radius + offset,
             head_x + radius - offset, head_y + radius - offset),
            start=20 + offset * 12, end=330 - offset * 10,
            fill=PENCIL if offset % 2 == 0 else BACKGROUND, width=2,
        )
    draw.line(((head_x - 18, head_y - 15), (head_x - 30, head_y - 39)),
              fill=INK, width=6)
    draw.line(((head_x + 12, head_y - 18), (head_x + 28, head_y - 42)),
              fill=INK, width=6)
    draw.line(((head_x - 14, head_y + 3), (head_x + 15, head_y + 7)),
              fill=BACKGROUND, width=3)
    for tooth in range(4):
        x = head_x - 10 + tooth * 7
        draw.line(((x, head_y + 3), (x + 2, head_y + 7)),
                  fill=BACKGROUND, width=2)
    tail = [(hip[0], hip[1] - 4), (610, 380), (590, 410), (625, 430)]
    draw.line(tail, fill=INK, width=6, joint="curve")
    draw.polygon(((625, 430), (612, 425), (621, 414)), fill=INK)


def wrap_caption(draw, text, font, max_width):
    words = clean_caption(text).split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_frame(action, narration, phase):
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.line((75, 480, WIDTH - 75, 480), fill=(126, 120, 109), width=2)
    draw_dayaw(draw, action, phase)
    draw_bakunawa(draw, action, phase)

    caption_lines = wrap_caption(draw, narration, font, WIDTH - 100)[:3]
    line_height = 17
    caption_y = HEIGHT - 84
    draw.rounded_rectangle(
        (40, caption_y - 10, WIDTH - 40, HEIGHT - 24),
        radius=14,
        fill=BACKGROUND,
        outline=(177, 169, 155),
        width=1,
    )
    for line_number, line in enumerate(caption_lines):
        box = draw.textbbox((0, 0), line, font=font)
        x = (WIDTH - (box[2] - box[0])) // 2
        draw.text((x, caption_y + line_number * line_height), line, fill=INK, font=font)
    return image


async def synthesize_scene_audio(scenes, voice, audio_directory):
    audio_paths = []
    for index, (_, narration) in enumerate(scenes):
        audio_path = audio_directory / f"scene_{index:04d}.mp3"
        await edge_tts.Communicate(narration, voice).save(str(audio_path))
        audio_paths.append(audio_path)
    return audio_paths


def run_command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(arguments[:2])} failed: {detail}")


def probe_duration(audio_path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError(f"Could not read audio duration for {audio_path}.") from error


def concat_audio(audio_paths, audio_directory):
    concat_list = audio_directory / "scenes.txt"
    with concat_list.open("w", encoding="utf-8") as file:
        for audio_path in audio_paths:
            escaped_path = str(audio_path).replace("'", "'\\''")
            file.write(f"file '{escaped_path}'\n")
    narration_path = audio_directory / "narration.mp3"
    run_command(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c:a", "libmp3lame", "-q:a", "3",
            str(narration_path),
        ]
    )
    return narration_path


def export_mp3(audio_paths, output_path, audio_directory):
    concat_list = audio_directory / "audio_only_scenes.txt"
    with concat_list.open("w", encoding="utf-8") as file:
        for audio_path in audio_paths:
            escaped_path = str(audio_path).replace("'", "'\\''")
            file.write(f"file '{escaped_path}'\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c:a", "libmp3lame", "-q:a", "3",
            str(output_path),
        ]
    )


def render_video(scenes, durations, narration_path, output_path, frame_directory):
    frame_number = 0
    for (action, narration), duration in zip(scenes, durations):
        frame_count = max(1, math.ceil(duration * FPS))
        for local_frame in range(frame_count):
            phase = (local_frame / frame_count) % 1.0
            frame = render_frame(action, narration, phase)
            frame.save(frame_directory / f"frame_{frame_number:06d}.png")
            frame_number += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg", "-y", "-v", "error",
            "-framerate", str(FPS),
            "-i", str(frame_directory / "frame_%06d.png"),
            "-i", str(narration_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart", str(output_path),
        ]
    )


def main():
    parser = argparse.ArgumentParser(
        description="Create a narrated MP4 or narration-only MP3."
    )
    parser.add_argument(
        "script", type=Path,
        help="UTF-8 narration text; use [ACTION: ...] tags when creating a video",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Output path (default: output/<script-name>.mp4 or .mp3)",
    )
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--audio-only",
        dest="audio_only",
        action="store_const",
        const=True,
        help="Create an MP3 only; input may be plain narration text or action-tagged scenes",
    )
    output_mode.add_argument(
        "--video",
        dest="audio_only",
        action="store_const",
        const=False,
        help="Create a narrated MP4 even when AUDIO_ONLY=true",
    )
    parser.add_argument(
        "--voice",
        default=os.environ.get("NARRATOR_GENDER", "female"),
        help="Narrator gender (female or male); defaults to NARRATOR_GENDER or female",
    )
    args = parser.parse_args()
    configured_audio_only = os.environ.get("AUDIO_ONLY", "false").strip().lower()
    if configured_audio_only not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        parser.error("AUDIO_ONLY must be true or false.")
    audio_only = (
        args.audio_only
        if args.audio_only is not None
        else configured_audio_only in {"true", "1", "yes", "on"}
    )
    voice = VOICE_IDS.get(args.voice.lower())
    if voice is None:
        parser.error("--voice must be 'female' or 'male'.")
    script_path = args.script
    expected_extension = ".mp3" if audio_only else ".mp4"
    output_path = args.output or Path("output") / f"{script_path.stem}{expected_extension}"
    if output_path.suffix.lower() != expected_extension:
        parser.error(f"Output must have a {expected_extension} extension.")

    try:
        script_text = script_path.read_text(encoding="utf-8")
        scenes = parse_audio_scenes(script_text) if audio_only else parse_scenes(script_text)
        with tempfile.TemporaryDirectory(prefix="stickman-video-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            audio_directory = temporary_path / "audio"
            audio_directory.mkdir()
            audio_paths = asyncio.run(
                synthesize_scene_audio(scenes, voice, audio_directory)
            )
            if audio_only:
                export_mp3(audio_paths, output_path, audio_directory)
            else:
                frame_directory = temporary_path / "frames"
                frame_directory.mkdir()
                durations = [probe_duration(path) for path in audio_paths]
                narration_path = concat_audio(audio_paths, audio_directory)
                render_video(
                    scenes, durations, narration_path, output_path, frame_directory
                )
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    output_type = "MP3 narration" if audio_only else "narrated MP4"
    print(f"Created {output_type} with {len(scenes)} scene(s): {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
