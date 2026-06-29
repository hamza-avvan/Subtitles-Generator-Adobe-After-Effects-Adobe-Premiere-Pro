import argparse
import json
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

import whisper


def extract_audio(video_path: str, audio_path: str = "temp_audio.wav"):
    """Extract mono 16kHz wav from video using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
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
            if w["word"].strip():
                words.append({
                    "word": w["word"].strip(),
                    "start": w["start"],
                    "end": w["end"]
                })
    return words


def parse_srt(srt_path: str):
    """
    Parse an SRT file and return list of dicts:
        {'index': int, 'start': float (seconds), 'end': float (seconds), 'text': str}
    """
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    pattern = re.compile(
        r"(\d+)\s*\n"                         # index
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"  # start time
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n"      # end time
        r"([\s\S]+?)(?=\n\n|\Z)"               # text (lazy)
    )
    blocks = []
    for m in re.finditer(pattern, content):
        idx = int(m.group(1))
        start = (int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4)) + int(m.group(5)) / 1000.0)
        end = (int(m.group(6)) * 3600 + int(m.group(7)) * 60 + int(m.group(8)) + int(m.group(9)) / 1000.0)
        text = m.group(10).strip().replace("\n", " ")
        blocks.append({"index": idx, "start": start, "end": end, "text": text})
    return blocks


def clean_word(w):
    """Remove punctuation and lowercase for alignment."""
    return re.sub(r'[^\w\s]', '', w).lower()


def align_words(srt_words, whisper_words):
    """
    Align two sequences of words (cleaned) using difflib.
    Returns list of tuples: (whisper_word_index or None, srt_word_index or None)
    Only srt_word_index != None are kept for final mapping.
    """
    cleaned_srt = [clean_word(w) for w in srt_words]
    cleaned_whisper = [clean_word(w["word"]) for w in whisper_words]
    sm = SequenceMatcher(None, cleaned_srt, cleaned_whisper)
    matches = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                matches.append((j1 + k, i1 + k))   # (whisper_idx, srt_idx)
        elif op == "replace":
            # handle partial matching later, but for now we'll align as best we can
            pass
        elif op == "insert":
            # SRT has extra words not in Whisper
            for k in range(i2 - i1):
                matches.append((None, i1 + k))     # no whisper match
        elif op == "delete":
            # Whisper has words not in SRT – ignore
            pass
    return matches


def align_srt_with_whisper(srt_blocks, whisper_words):
    """
    Combine SRT blocks with Whisper timestamps.
    Returns a list of all words (in subtitle block order) with start/end times.
    """
    all_aligned = []  # list of dicts: word, start, end

    whisper_idx = 0
    for block in srt_blocks:
        # Collect Whisper words that fall within the block time
        block_whisper = []
        while whisper_idx < len(whisper_words) and whisper_words[whisper_idx]["start"] <= block["end"]:
            w = whisper_words[whisper_idx]
            if w["end"] >= block["start"]:
                block_whisper.append(w)
            whisper_idx += 1
            if w["start"] > block["end"]:
                break

        # Split SRT text into words (preserve original punctuation)
        srt_raw_words = block["text"].split()
        # Also create a version without punctuation for matching
        srt_clean_words = [clean_word(w) for w in srt_raw_words]
        block_whisper_clean = [clean_word(w["word"]) for w in block_whisper]

        # Use SequenceMatcher on the whole block (as lists of words)
        sm = SequenceMatcher(None, srt_clean_words, block_whisper_clean)
        # Build alignment
        align_pairs = []  # (srt_idx, whisper_idx) or (srt_idx, None)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for k in range(i2 - i1):
                    align_pairs.append((i1 + k, j1 + k))
            elif op == "replace":
                # try to match as many as possible, one-to-one
                min_len = min(i2 - i1, j2 - j1)
                for k in range(min_len):
                    align_pairs.append((i1 + k, j1 + k))
                # extra SRT words (unmatched)
                for k in range(min_len, i2 - i1):
                    align_pairs.append((i1 + k, None))
                # extra Whisper words are ignored for SRT
            elif op == "insert":
                for k in range(i2 - i1):
                    align_pairs.append((i1 + k, None))
            elif op == "delete":
                pass  # Whisper extra words, ignore

        # Now assign times
        last_time = block["start"]
        for srt_idx, whis_idx in align_pairs:
            word_text = srt_raw_words[srt_idx]
            if whis_idx is not None:
                start = block_whisper[whis_idx]["start"]
                end = block_whisper[whis_idx]["end"]
            else:
                # Estimate: take proportional share of block
                total_chars = sum(len(w) for w in srt_raw_words)
                pos = sum(len(srt_raw_words[j]) for j in range(srt_idx)) / max(total_chars, 1)
                duration = block["end"] - block["start"]
                start = block["start"] + pos * duration * 0.5   # rough
                end = block["start"] + (pos + len(word_text)/total_chars) * duration
            all_aligned.append({"word": word_text, "start": start, "end": end})

    return all_aligned


def group_into_subtitles(words, max_chars=40, max_gap=0.5, max_duration=4.0):
    """Group words into subtitle lines, preserving word-level data."""
    if not words:
        return []

    subtitles = []
    current_words = []
    line_start = None

    for i, w in enumerate(words):
        if not current_words:
            current_words = [w]
            line_start = w["start"]
            continue

        char_count = sum(len(wd["word"]) for wd in current_words) + len(current_words) - 1
        gap = w["start"] - words[i-1]["end"]

        if (char_count + len(w["word"]) + 1 > max_chars) or gap > max_gap:
            text = " ".join(wd["word"] for wd in current_words)
            subtitles.append({
                "text": text,
                "start": line_start,
                "end": words[i-1]["end"],
                "words": current_words
            })
            current_words = [w]
            line_start = w["start"]
        else:
            current_words.append(w)

    if current_words:
        text = " ".join(wd["word"] for wd in current_words)
        subtitles.append({
            "text": text,
            "start": line_start,
            "end": words[-1]["end"],
            "words": current_words
        })

    # enforce max duration (simple split)
    final_subtitles = []
    for sub in subtitles:
        dur = sub["end"] - sub["start"]
        if dur > max_duration:
            mid = sub["start"] + max_duration
            split_idx = len(sub["words"]) // 2
            if split_idx == 0:
                final_subtitles.append(sub)
                continue
            first_words = sub["words"][:split_idx]
            second_words = sub["words"][split_idx:]
            final_subtitles.append({
                "text": " ".join(wd["word"] for wd in first_words),
                "start": sub["start"], "end": mid,
                "words": first_words
            })
            final_subtitles.append({
                "text": " ".join(wd["word"] for wd in second_words),
                "start": mid, "end": sub["end"],
                "words": second_words
            })
        else:
            final_subtitles.append(sub)
    return final_subtitles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Input video file")
    parser.add_argument("--srt", help="Path to SRT file (corrected text)", default=None)
    parser.add_argument("-o", "--output", default="subtitles.json", help="Output JSON file")
    parser.add_argument("--model", default="base", help="Whisper model")
    parser.add_argument("--max-chars", type=int, default=40)
    parser.add_argument("--max-gap", type=float, default=0.5)
    parser.add_argument("--max-dur", type=float, default=4.0)
    parser.add_argument("--keep-audio", action="store_true")
    args = parser.parse_args()

    audio_path = "temp_audio.wav"
    try:
        extract_audio(args.video, audio_path)
        whisper_words = transcribe_audio(audio_path, args.model)

        if args.srt:
            srt_blocks = parse_srt(args.srt)
            aligned_words = align_srt_with_whisper(srt_blocks, whisper_words)
            subtitles = group_into_subtitles(aligned_words, args.max_chars, args.max_gap, args.max_dur)
        else:
            subtitles = group_into_subtitles(whisper_words, args.max_chars, args.max_gap, args.max_dur)

        # Prepare JSON
        duration = subtitles[-1]["end"] + 0.5 if subtitles else 10.0
        json_data = {
            "duration": duration,
            "subtitles": subtitles
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        print(f"JSON saved to {args.output}")
    finally:
        if not args.keep_audio and os.path.exists(audio_path):
            os.remove(audio_path)


if __name__ == "__main__":
    main()