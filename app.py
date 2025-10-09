import os
import sys
import time
import logging
from typing import List, Tuple

# Add the current directory to path to ensure modules can be found
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

import gradio as gr

from utils import (
    extract_video_id,
    check_youtube_access,
    validate_and_adjust_timings,
    srt_to_paragraph,
)
from caption_fetch import get_captions
from transcription import transcribe_local

# Enhanced logging utilities
def format_log_message(message, status=None):
    """Format log message with status indicators for better visibility"""
    if status == "success":
        return f"✅ {message}"
    elif status == "error":
        return f"❌ {message}"
    elif status == "warning":
        return f"⚠️ {message}"
    elif status == "info":
        return f"ℹ️ {message}"
    elif status == "processing":
        return f"⏳ {message}"
    else:
        return message

# Setup file logging in addition to console
def setup_file_logging(logger, log_dir="./logs"):
    """Add file logging handler to logger"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"subtitles_{time.strftime('%Y%m%d_%H%M%S')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    return log_file
# configure root logger
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("YouTubeSubtitleManager")

def process_video(
    url: str,
    source_lang: str,
    output_dir: str,
    min_gap: int,
    download_only: bool,
    save_txt: bool,
    use_local_transcription: bool,
    whisper_model: str,
    debug: bool
) -> Tuple[List[str], str]:
    """Main processing function for Gradio UI."""
    if debug:
        logger.setLevel(logging.DEBUG)
    start = time.time()
    logs: List[str] = []
    files: List[str] = []

    # 1. validate YouTube access
    logs.append("Checking YouTube access...")
    if not check_youtube_access():
        logs.append("❌ Cannot reach YouTube. Check your network.")
        return [], "\n".join(logs)

    # 2. extract video ID
    vid = extract_video_id(url.strip())
    if not vid:
        logs.append(f"❌ Invalid YouTube URL or ID: {url}")
        return [], "\n".join(logs)
    logs.append(f"✔ Extracted video ID: {vid}")

    # ensure output dir
    os.makedirs(output_dir, exist_ok=True)

    # 3. obtain SRT
    srt_content = ""
    actual_source = source_lang

    if not use_local_transcription:
        logs.append("Attempting to fetch online captions...")
        srt_content = get_captions(vid, source_lang)
        if not srt_content and source_lang != "en":
            logs.append(f"No captions for '{source_lang}', falling back to English")
            srt_content = get_captions(vid, "en")
            actual_source = "en"

    if not srt_content and use_local_transcription:
        logs.append("❗ No online captions, transcribing locally with Whisper...")
        srt_content = transcribe_local(
            vid, output_dir, source_lang, whisper_model, logger.level
        )
        actual_source = source_lang
        if srt_content:
            logs.append("✔ Local transcription succeeded")
        else:
            logs.append("❌ Local transcription failed")

    if not srt_content:
        logs.append("❌ Could not obtain subtitles or transcript.")
        return [], "\n".join(logs)

    # 4. validate timings
    logs.append("Validating and adjusting timings...")
    srt_content = validate_and_adjust_timings(srt_content, min_gap)

    # 5. save original SRT
    base = os.path.join(output_dir, vid)
    orig_srt = f"{base}_{actual_source}.srt"
    with open(orig_srt, "w", encoding="utf-8") as f:
        f.write(srt_content)
    files.append(orig_srt)
    logs.append(f"✔ Saved original SRT: {orig_srt}")

    # if download_only, return early
    if download_only:
        logs.append("💾 Download only, skipping further processing.")
        duration = time.time() - start
        logs.append(f"\n✅ Completed in {duration:.2f}s")
        return files, "\n".join(logs)

    # 6. save text if requested
    if save_txt:
        txt = srt_to_paragraph(srt_content)
        orig_txt = f"{base}_{actual_source}.txt"
        with open(orig_txt, "w", encoding="utf-8") as f:
            f.write(txt)
        files.append(orig_txt)
        logs.append(f"✔ Saved original text: {orig_txt}")

    duration = time.time() - start
    logs.append(f"\n✅ Completed in {duration:.2f}s")

    return files, "\n".join(logs)

# ======================
#           UI
# ======================
custom_css = """
:root {
    --primary: #4f46e5;
    --secondary: #6366f1;
    --accent: #ec4899;
    --dark: #1e293b;
    --light: #f8fafc;
    --success: #10b981;
    --warning: #f59e0b;
    --error: #ef4444;
}

body {
    background: linear-gradient(135deg, #f0f4ff 0%, #e6f7ff 100%);
    min-height: 100vh;
}

#component-0 {
    max-width: 1200px !important;
    margin: 2rem auto;
    padding: 2rem;
    background: black;
    border-radius: 16px;
    box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1);
}

.header {
    text-align: center;
    margin-bottom: 2rem;
    background: linear-gradient(90deg, var(--primary), var(--secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: red;
    padding-bottom: 1rem;
    border-bottom: 1px solid #e2e8f0;
}

.card {
    background: black;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.05);
    margin-bottom: 1.5rem;
    border: 1px solid #e2e8f0;
}

.card-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--dark);
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.btn-primary {
    background: linear-gradient(90deg, var(--primary), var(--secondary)) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.5rem !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.3) !important;
}

.log-output {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.9rem;
    padding: 1.25rem;
    background: #1e293b;
    color: #f1f5f9;
    border-radius: 8px;
    max-height: 400px;
    overflow-y: auto;
    display: block !important;
}

.success { color: var(--success); }
.warning { color: var(--warning); }
.error { color: var(--error); }
.info { color: #60a5fa; }

.divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
    margin: 1.5rem 0;
}

.footer {
    text-align: center;
    margin-top: 2rem;
    color: #64748b;
    font-size: 0.9rem;
}

/* Fix for dropdown emojis */
.emoji-font {
    font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif !important;
}

/* Style for language dropdown items */
.language-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
}
"""

# List of supported languages with flags
languages = [
    {"value": "en", "label": "English", "flag": "🇬🇧"},
    {"value": "fr", "label": "French", "flag": "🇫🇷"},
    {"value": "de", "label": "German", "flag": "🇩🇪"},
    {"value": "es", "label": "Spanish", "flag": "🇪🇸"},
    {"value": "it", "label": "Italian", "flag": "🇮🇹"},
    {"value": "pt", "label": "Portuguese", "flag": "🇵🇹"},
    {"value": "zh", "label": "Chinese", "flag": "🇨🇳"},
    {"value": "ja", "label": "Japanese", "flag": "🇯🇵"},
    {"value": "ko", "label": "Korean", "flag": "🇰🇷"},
    {"value": "ru", "label": "Russian", "flag": "🇷🇺"},
    {"value": "ar", "label": "Arabic", "flag": "🇸🇦"}
]

def create_language_dropdown():
    """Create language dropdown with proper flag display"""
    choices = []
    for lang in languages:
        # Use raw string for dropdown choice
        choices.append(f"{lang['flag']} {lang['label']}")
    return choices

def get_lang_code_from_display(display_str):
    """Get language code from display string"""
    for lang in languages:
        if display_str.startswith(lang['flag']):
            return lang["value"]
    return "en"  # default to English

# Gradio UI with enhanced design
with gr.Blocks(
    theme=gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="blue",
        neutral_hue="slate"
    ),
    title="YouTube Subtitle Manager",
    css=custom_css
) as demo:
    
    # Header Section
    gr.HTML("""
    <div class="header">
        <h1>YouTube Subtitle Manager</h1>
        <p>Professional tool for downloading, transcribing, and translating YouTube subtitles</p>
    </div>
    """)
    
    # Main Content
    with gr.Row():
        # Left Column - Inputs
        with gr.Column(scale=6):
            # Video Information Card
            with gr.Group(elem_classes="card"):
                gr.Markdown("""<div class="card-title">📺 Video Information</div>""")
                url_input = gr.Textbox(
                    label="YouTube URL or Video ID",
                    placeholder="https://www.youtube.com/watch?v=... or Video ID",
                    elem_classes="emoji-font"
                )
                
                with gr.Row():
                    # Language selection with fixed emoji display
                    source_lang = gr.Dropdown(
                        label="Source Language",
                        choices=create_language_dropdown(),
                        value=f"{languages[0]['flag']} {languages[0]['label']}",
                        elem_classes="emoji-font",
                        interactive=True
                    )
            
            # Output Settings Card
            with gr.Group(elem_classes="card"):
                gr.Markdown("""<div class="card-title">⚙️ Output Settings</div>""")
                with gr.Row():
                    output_dir = gr.Textbox(
                        label="Output Directory",
                        value="./subtitles",
                        scale=3
                    )
                    min_gap = gr.Number(
                        label="Minimum Gap (ms)",
                        value=100,
                        precision=0,
                        scale=1
                    )
                
                with gr.Row():
                    download_only = gr.Checkbox(
                        label="Download Only", 
                        value=False,
                        interactive=True
                    )
                    save_txt = gr.Checkbox(
                        label="Save Text Version", 
                        value=True,
                        interactive=True
                    )
            
            # Processing Options Card
            with gr.Group(elem_classes="card"):
                gr.Markdown("""<div class="card-title">🔧 Processing Options</div>""")
                use_local_trans = gr.Checkbox(
                    label="Use Local Transcription (Whisper)", 
                    value=True,
                    interactive=True
                )
                
                with gr.Row(visible=True) as whisper_settings:
                    whisper_model = gr.Dropdown(
                        label="Whisper Model",
                        choices=["tiny", "base", "small", "medium", "large"],
                        value="large",
                        interactive=True
                    )
                    debug = gr.Checkbox(
                        label="Enable Debug Logging", 
                        value=True,
                        interactive=True
                    )
                
                # Show/hide Whisper settings based on checkbox
                use_local_trans.change(
                    lambda x: gr.update(visible=x),
                    [use_local_trans],
                    [whisper_settings]
                )
        
        # Right Column - Outputs
        with gr.Column(scale=4):
            # Results Card
            with gr.Group(elem_classes="card"):
                gr.Markdown("""<div class="card-title">📤 Results</div>""")
                file_output = gr.Files(
                    label="Generated Files",
                    interactive=False
                )
                
                with gr.Accordion("Process Logs", open=True):
                    log_output = gr.HTML(
                        label="",
                        value="<div class='log-output'>Processing logs will appear here...</div>"
                    )
    
    # Action Button
    with gr.Row():
        submit_btn = gr.Button(
            "Process Video", 
            variant="primary",
            elem_classes="btn-primary"
        )
    
    # Footer
    gr.HTML("""
    <div class="footer">
        <div class="divider"></div>
        <p>YouTube Subtitle Manager v1.2 · Built with Gradio</p>
    </div>
    """)
    
    # ======================
    # LOG FORMATTING AND PROCESSING
    # ======================
    def format_logs(log_text):
        formatted = []
        for line in log_text.split("\n"):
            if "❌" in line:
                formatted.append(f"<span class='error'>{line}</span>")
            elif "✔" in line or "✅" in line:
                formatted.append(f"<span class='success'>{line}</span>")
            elif "❗" in line or "⚠" in line:
                formatted.append(f"<span class='warning'>{line}</span>")
            elif "..." in line or "..." in line:
                formatted.append(f"<span class='info'>{line}</span>")
            else:
                formatted.append(line)
        return f"<div class='log-output'>{'<br>'.join(formatted)}</div>"

    def process_wrapper(
        url: str,
        lang_display: str,
        output_dir: str,
        min_gap: int,
        download_only: bool,
        save_txt: bool,
        use_local_trans: bool,
        whisper_model: str,
        debug: bool
    ) -> Tuple[gr.Files, gr.HTML]:
        """Wrapper function to handle processing and log formatting"""
        # Convert display string to language code
        lang_code = get_lang_code_from_display(lang_display)
        
        files, logs = process_video(
            url=url,
            source_lang=lang_code,
            output_dir=output_dir,
            min_gap=min_gap,
            download_only=download_only,
            save_txt=save_txt,
            use_local_transcription=use_local_trans,
            whisper_model=whisper_model,
            debug=debug
        )
        
        return files, format_logs(logs)
    
    # Event Handlers
    submit_btn.click(
        fn=process_wrapper,
        inputs=[
            url_input, 
            source_lang,
            output_dir,
            min_gap, 
            download_only,
            save_txt, 
            use_local_trans,
            whisper_model,
            debug
        ],
        outputs=[file_output, log_output]
    )

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1", 
        server_port=7864,
        share=False, 
        show_error=True
    )