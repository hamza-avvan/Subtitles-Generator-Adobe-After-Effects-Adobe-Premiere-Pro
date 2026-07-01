# After Effects Subtitle Generator

This project transcribes speech from a video file with Whisper and produces subtitle output that can be used in Adobe After Effects or other subtitle workflows.

### Example / experiment

A related example of this workflow was shared on YouTube:

[![YouTube thumbnail](img/maxresdefault.jpg)](https://www.youtube.com/watch?v=wF6TsrSQZ3I&t=9s)

It is a useful reference, although some manual tweaking was still needed to get the timing and styling to look right in practice.


## What it does

- Extracts audio from a video file using ffmpeg
- Transcribes the audio with OpenAI Whisper
- Groups words into subtitle lines with timing information
- Can be used to create speech-synced subtitles where words are highlighted as they are spoken
- Exports either:
  - JSON subtitle data for further processing
  - An ExtendScript .jsx file that creates a subtitle composition in After Effects

## Project files

- [generate_subtitle_json.py](generate_subtitle_json.py) – transcribes audio and writes subtitle JSON
- [subtitles_to_jsx.py](subtitles_to_jsx.py) – generates an After Effects .jsx script from subtitle text
- [new_subtitles_to_jsx.py](new_subtitles_to_jsx.py) – alternative workflow with SRT-based alignment
- [requirements.txt](requirements.txt) – Python dependencies

## Requirements

- Python 3.9 or newer
- ffmpeg installed and available on your PATH, or the packaged release assets from the dist folder
- Internet access for the first Whisper model download if you are not using the bundled release files

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Using the release package

The release archive contains the core runtime assets needed by the tool:

- [dist/bin/ffmpeg.exe](dist/bin/ffmpeg.exe) – bundled ffmpeg executable
- [dist/base.pt](dist/base.pt) – bundled Whisper base model file

If you download the release zip, extract it into the project root so the tool can find these files. This is the easiest option on Windows because it avoids manually downloading ffmpeg and the Whisper model.

If you prefer to install the Whisper model yourself instead of using the bundled file, you can also use the official Whisper package and let it download the model on first run. In that case, you do not need the bundled [dist/base.pt](dist/base.pt) file.

## Usage

### 1. Generate subtitle JSON

```bash
python generate_subtitle_json.py "path/to/video.mp4" --output subtitles.json --model base
```

Optional: use a corrected SRT file to improve alignment:

```bash
python generate_subtitle_json.py "path/to/video.mp4" --srt "path/to/subtitles.srt" --output subtitles.json
```

### 2. Generate an After Effects JSX script

```bash
python subtitles_to_jsx.py "path/to/video.mp4" -o subtitles.jsx --model base
```

You can tune the layout and timing with options such as --max-chars, --max-gap, --max-dur, --font, and --font-size.

## Building a standalone executable

If you want to package the tool as a Windows executable, use PyInstaller and bundle ffmpeg plus the Whisper model assets.

Example:

```powershell
pyinstaller --onedir --name AfterEffectSubtitlePlugin --add-data "dist\bin\ffmpeg.exe;." --add-data "dist\base.pt;whisper_models" generate_subtitle_json.py
```

Adjust the paths to match your local environment and Python installation.