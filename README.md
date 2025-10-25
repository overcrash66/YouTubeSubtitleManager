# YouTubeSubtitleManager

A lightweight web app to download, transcribe, validate and save subtitles for YouTube videos. It can extract available captions, fall back to English captions, or transcribe audio locally using Whisper. The app exposes a polished Gradio UI for easy usage and saves output SRT/TXT files to a configurable output directory.

Key capabilities
- Download existing YouTube captions (by language)
- Transcribe video audio locally using Whisper when captions are unavailable
- Validate and adjust SRT timing gaps
- Export subtitles as .srt and optional plain .txt paragraph files
- Simple UI built with Gradio for local use

---

Table of contents
- Features
- Requirements
- Installation
- Run / Usage
- UI options explained
- Output files and naming
- Troubleshooting
- Contributing
- License

---

Features
- Fetches captions from YouTube if available (supports language fallback)
- Local Whisper transcription (configurable model) for videos without captions
- Timing validation/adjustment to ensure minimum gap between subtitle segments
- Option to save text-only paragraph files derived from SRT
- Logs both to console and to timestamped log files in ./logs
- Clean Gradio-based UI with language selector and processing options

Requirements
- Python 3.10+
- ffmpeg (required by Whisper and audio processing)
- pip (for Python package installation)
- Optional: GPU + CUDA if using Whisper with GPU for faster transcription

Suggested packages (contents of requirements.txt provided in the repository)
- gradio
- yt-dlp or google-api dependencies used internally (see repo)
- whisper or openai-whisper + torch (if using local transcription)

Note: Installing and configuring Whisper (and torch) may require extra steps depending on your OS and whether you want GPU support. See official Whisper and Torch installation docs for platform-specific instructions.

---

Quick install (Windows example)
1. Clone the repo
   git clone https://github.com/overcrash66/YouTubeSubtitleManager.git
   cd YouTubeSubtitleManager

2. Create and activate a Python virtual environment
   py -3.10 -m venv venv
   venv\Scripts\activate

3. Install dependencies
   pip install -r requirements.txt

4. Ensure ffmpeg is installed and on PATH (ffmpeg --version)

---

Run the app
Start the Gradio UI:
python ./app.py

Then open the web UI at:
http://127.0.0.1:7864

The app will display inputs for the YouTube URL / Video ID and the processing options described below.

---

UI options explained
- YouTube URL or Video ID
  Paste the full YouTube link (https://www.youtube.com/watch?v=...) or just the video ID.

- Source Language
  Choose the language code / display—for fetching captions or for informing transcription. If captions are not available in the chosen language, the app will attempt an English fallback.

- Output Directory
  Where generated files will be saved (default: ./subtitles)

- Minimum Gap (ms)
  The minimal allowed gap between subtitle segments, used by the timing validator. Default is 100 ms.

- Download Only
  If checked, the app only downloads/fetches the .srt (or transcribes it locally) and saves the SRT without converting to text or performing further processing.

- Save Text Version
  If checked, the SRT will be converted into a plain paragraph .txt file alongside the .srt file.

- Use Local Transcription (Whisper)
  Toggles local transcription. If disabled, the app will only attempt fetching captions from YouTube (and the English fallback).

- Whisper Model
  Choose the Whisper model to use for transcription. Smaller models are faster but less accurate; larger models give better results but require more resources. (tiny, base, small, medium, large)

- Enable Debug Logging
  Enable more verbose logs to help diagnose issues.

---

Output files & naming
Files are saved under the chosen output directory using the pattern:
{output_dir}/{video_id}_{lang}.srt
Optional text output:
{output_dir}/{video_id}_{lang}.txt

Example:
subtitles/dQw4w9WgXcQ_en.srt
subtitles/dQw4w9WgXcQ_en.txt

Log files are created in ./logs with names like:
subtitles_YYYYMMDD_HHMMSS.log

---

Troubleshooting
- "Cannot reach YouTube" / network errors:
  Ensure your machine has access to the internet and YouTube is not blocked. The app checks network access before attempting downloads.

- No captions and transcription fails:
  If local transcription cannot run, confirm ffmpeg is installed and that Whisper + torch dependencies are correctly installed. Watch for memory / GPU issues when using large Whisper models.

- Whisper model download issues:
  Large models must be downloaded (may take time). Consider using smaller models for initial testing.

- Permission errors writing files:
  Verify the output directory is writable. Running with insufficient permissions can prevent file creation.

- JavaScript or Gradio UI errors:
  Ensure your browser can access the local server (127.0.0.1:7864) and that no other process is using the port.

---

Developers / Contributing
Contributions and improvements are welcome. Suggested ways to help:
- Add unit tests for timing validation and SRT parsing
- Support additional output formats (VTT, JSON)
- Add CI checks and a license file
- Improve multi-language caption fetching logic

If you add features or refactors, please:
- Open a branch and create a PR with descriptive title and changelog
- Keep changes backwards compatible where possible

---

Security & Privacy
- Audio/video content and generated subtitles are processed locally (when using local transcription). If you enable any cloud-based transcription or third-party APIs, be mindful of privacy and terms of service.

---

License
No license file is present in this repository. Add a LICENSE file (for example, MIT or Apache-2.0) to make reuse terms explicit.

---

Example usage scenario
1. Start app:
   python app.py

2. Paste YouTube URL into the UI, choose Source Language (or leave English), leave "Use Local Transcription" enabled, click "Process Video".

3. After processing, download any files shown in the "Generated Files" box or inspect them in your configured output directory.
