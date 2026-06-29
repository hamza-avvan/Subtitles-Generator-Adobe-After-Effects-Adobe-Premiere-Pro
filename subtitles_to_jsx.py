import argparse
import os
import subprocess
import whisper
from pathlib import Path


def extract_audio(video_path: str, audio_path: str = "temp_audio.wav"):
    """Extract mono 16kHz wav from video using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",               # no video
        "-ac", "1",          # mono
        "-ar", "16000",      # 16 kHz sample rate (whisper default)
        audio_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_path


def transcribe_audio(audio_path: str, model_name: str = "base"):
    """Return list of {'word': str, 'start': float, 'end': float} sorted by start time."""
    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path, word_timestamps=True)
    segments = result.get("segments", [])
    words = []
    for seg in segments:
        for w in seg.get("words", []):
            # Whisper sometimes returns empty word strings; skip them
            if w["word"].strip():
                words.append({
                    "word": w["word"].strip(),
                    "start": w["start"],
                    "end": w["end"]
                })
    return words


def group_into_subtitles(words, max_chars=40, max_gap=0.5, max_duration=4.0):
    """
    Group words into subtitle lines.
    Returns list of dicts: {'text': str, 'start': float, 'end': float}
    """
    if not words:
        return []

    subtitles = []
    current_line = []
    line_start = None

    for i, w in enumerate(words):
        if not current_line:
            # start a new line
            current_line = [w["word"]]
            line_start = w["start"]
            continue

        # decide whether to add word to current line
        char_count = sum(len(x) for x in current_line) + len(current_line) - 1  # spaces between words
        gap = w["start"] - words[i-1]["end"] if i > 0 else 0.0

        if (char_count + len(w["word"]) + 1 > max_chars and char_count > 0) or gap > max_gap:
            # finalise the previous line
            text = " ".join(current_line)
            subtitles.append({
                "text": text,
                "start": line_start,
                "end": words[i-1]["end"]   # end of last word in line
            })
            # start new line
            current_line = [w["word"]]
            line_start = w["start"]
        else:
            current_line.append(w["word"])

    # add the last line
    if current_line:
        text = " ".join(current_line)
        subtitles.append({
            "text": text,
            "start": line_start,
            "end": words[-1]["end"]
        })

    # enforce maximum duration – split lines that are too long
    final_subtitles = []
    for sub in subtitles:
        dur = sub["end"] - sub["start"]
        if dur > max_duration:
            # simple split: cut at the middle time (real solution would re‑group words)
            mid = sub["start"] + max_duration
            final_subtitles.append({"text": sub["text"], "start": sub["start"], "end": mid})
            final_subtitles.append({"text": "", "start": mid, "end": sub["end"]})  # blank
        else:
            final_subtitles.append(sub)
    return final_subtitles


def generate_jsx(subtitles, output_path: str, comp_width=1920, comp_height=1080, fps=30.0,
                 font="Arial", font_size=60, color=[1,1,1], stroke_color=[0,0,0], stroke_width=2,
                 vertical_position=0.85):
    """
    Write an ExtendScript file that creates an AE composition and adds
    a text layer for each subtitle line.
    vertical_position: 0 (top) to 1 (bottom), 0.85 = near bottom
    """
    # Create comp name from input filename
    comp_duration = subtitles[-1]["end"] + 0.5 if subtitles else 10.0

    js_lines = []
    js_lines.append('// Auto‑generated subtitle composition')
    js_lines.append('app.beginUndoGroup("Create Subtitles");')
    js_lines.append('')
    js_lines.append(f'var comp = app.project.items.addComp("Subtitles", {comp_width}, {comp_height}, 1, {comp_duration:.3f}, {fps});')

    # Add a black solid as background (optional, makes it easier to see)
    js_lines.append('var bg = comp.layers.addSolid([0,0,0], "Background", comp.width, comp.height, 1);')
    js_lines.append('bg.inPoint = 0;')
    js_lines.append('bg.outPoint = comp.duration;')

    # Prepare text styles
    js_lines.append('var textLayer;')
    js_lines.append(f'var textColor = {color};')
    js_lines.append(f'var strokeColor = {stroke_color};')
    js_lines.append(f'var fontSize = {font_size};')

    for i, sub in enumerate(subtitles):
        if not sub["text"].strip():
            continue  # skip blank lines
        # Escape quotes in text
        escaped_text = sub["text"].replace('"', '\\"')
        start = sub["start"]
        end = sub["end"]

        js_lines.append(f'// Subtitle {i+1}: "{escaped_text}"')
        js_lines.append(f'textLayer = comp.layers.addText("{escaped_text}");')
        js_lines.append(f'textLayer.inPoint = {start:.3f};')
        js_lines.append(f'textLayer.outPoint = {end:.3f};')

        # Text formatting
        js_lines.append('var textProp = textLayer.property("Source Text");')
        js_lines.append('var textDoc = textProp.value;')
        js_lines.append(f'textDoc.font = "{font}";')
        js_lines.append(f'textDoc.fontSize = {font_size};')
        js_lines.append(f'textDoc.fillColor = textColor;')
        js_lines.append(f'textDoc.strokeColor = strokeColor;')
        js_lines.append(f'textDoc.strokeWidth = {stroke_width};')
        js_lines.append('textDoc.justification = ParagraphJustification.CENTER_JUSTIFY;')
        js_lines.append('textProp.setValue(textDoc);')

        # Position: centered horizontally, near bottom
        y_pos = int(comp_height * vertical_position)
        js_lines.append(f'textLayer.property("Position").setValue([{comp_width//2}, {y_pos}]);')
        js_lines.append('')

    js_lines.append('app.endUndoGroup();')
    js_lines.append('"Subtitle composition created";')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(js_lines))
    print(f"JSX file written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate After Effects .jsx subtitle script from a video.")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("-o", "--output", default="subtitles.jsx", help="Output .jsx file (default: subtitles.jsx)")
    parser.add_argument("--model", default="base", help="Whisper model (tiny, base, small, medium, large)")
    parser.add_argument("--width", type=int, default=1920, help="Composition width")
    parser.add_argument("--height", type=int, default=1080, help="Composition height")
    parser.add_argument("--fps", type=float, default=30.0, help="Composition frame rate")
    parser.add_argument("--font", default="Arial", help="Font name")
    parser.add_argument("--font-size", type=int, default=60, help="Font size")
    parser.add_argument("--max-chars", type=int, default=40, help="Max characters per subtitle line")
    parser.add_argument("--max-gap", type=float, default=0.5, help="Max gap between words in same line (seconds)")
    parser.add_argument("--max-dur", type=float, default=4.0, help="Max subtitle line duration (seconds)")
    parser.add_argument("--keep-audio", action="store_true", help="Keep extracted audio file")
    args = parser.parse_args()

    audio_path = "temp_audio.wav"
    try:
        extract_audio(args.video, audio_path)
        words = transcribe_audio(audio_path, args.model)
        subtitles = group_into_subtitles(words, args.max_chars, args.max_gap, args.max_dur)
        generate_jsx(
            subtitles,
            args.output,
            comp_width=args.width,
            comp_height=args.height,
            fps=args.fps,
            font=args.font,
            font_size=args.font_size
        )
    finally:
        if not args.keep_audio and os.path.exists(audio_path):
            os.remove(audio_path)


if __name__ == "__main__":
    main()