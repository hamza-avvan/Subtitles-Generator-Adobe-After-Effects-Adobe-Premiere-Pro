

## Command to Build
```pwsh
pyinstaller --onedir --name AfterEffectSubtitlePlugin --add-data "dist\bin\ffmpeg.exe;." --add-data "dist\base.pt;whisper_models" generate_subtitle_json.py --add-data "C:\Users\Midnight09x\AppData\Local\Programs\Python\Python314\Lib\site-packages\whisper\assets;whisper/assets"
```