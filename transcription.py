import os
import sys
import logging
import tempfile
import subprocess
import shutil
import torch
import gc
from utils import format_timestamp
import wave

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# use CUDA if available
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# Use yt-dlp Python API instead of pytube
try:
    import yt_dlp
    HAS_YTDLP_PY = True
except ImportError:
    HAS_YTDLP_PY = False

def setup_logger(name=__name__, level=logging.INFO, log_file=None, console=True):
    """
    Configure a logger with optional file output and colored console output.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level
        log_file: Optional path to log file
        console: Whether to output to console
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                    datefmt='%Y-%m-%d %H:%M:%S')
    
    # Add file handler if specified
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Add console handler if requested
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

# Initialize logger early
logger = logging.getLogger(__name__)

# Optional online-API fallback
try:
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
    HAS_API = True
except ImportError:
    HAS_API = False

# Local Whisper libraries
try:
    import whisper
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

# Try to import faster_whisper
try:
    from faster_whisper import WhisperModel
    HAS_FASTER = True
except ImportError:
    HAS_FASTER = False

# -- model caches with size limit --
_whisper_models = {}
_faster_models = {}
MAX_CACHED_MODELS = 1  # Limit to only one model at a time to avoid memory issues

# Available model sizes for validation
VALID_MODEL_SIZES = ["tiny", "base", "small", "medium", "large", "large-v1", "large-v2", "large-v3"]

def validate_model_size(model_size):
    """Validate that the requested model size is supported."""
    if model_size not in VALID_MODEL_SIZES:
        logger.error(f"Invalid model size: {model_size}. Valid options are: {', '.join(VALID_MODEL_SIZES)}")
        return False
    return True

def clean_model_cache():
    """Clean up model caches to free memory."""
    global _whisper_models, _faster_models
    
    for model_name in list(_whisper_models.keys()):
        del _whisper_models[model_name]
    
    for model_name in list(_faster_models.keys()):
        del _faster_models[model_name]
    
    _whisper_models = {}
    _faster_models = {}
    
    # Force garbage collection and CUDA cache clearing
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
    logger.info("Cleared model caches and freed memory")

def check_audio_file(file_path):
    """
    Validate if the audio file exists and is valid.
    Returns True if file is valid, False otherwise.
    """
    if not os.path.exists(file_path):
        logger.error(f"Audio file does not exist: {file_path}")
        return False
        
    if os.path.getsize(file_path) < 1000:  # Less than 1KB
        logger.error(f"Audio file too small, likely corrupt: {file_path}")
        return False
        
    # Check file extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ['.mp3', '.wav', '.m4a', '.flac']:
        logger.error(f"Unsupported audio format: {ext}")
        return False
    
    return True

def _download_with_yt_dlp_api(url: str, outdir: str, video_id: str, debug: bool=False) -> str:
    """
    Download audio via the yt_dlp Python API.
    Returns the path to the downloaded file or empty string on failure.
    """
    if not HAS_YTDLP_PY:
        logger.error("yt_dlp Python API not available")
        return ""
        
    ydl_opts = {
        "format": "bestaudio",
        "quiet": not debug,
        "no_warnings": True,
        "outtmpl": os.path.join(outdir, f"{video_id}.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Use the actual downloaded file path from info dict if available
            if info and 'requested_downloads' in info and info['requested_downloads']:
                # Get the actual file path from the downloader
                audio_path = info['requested_downloads'][0].get('filepath')
                if audio_path and os.path.exists(audio_path):
                    if debug:
                        logger.debug(f"Downloaded audio to: {audio_path}")
                    return audio_path
            
            # Fallback to constructed path if actual path not found
            ext = "mp3"  # Always mp3 due to the postprocessor
            audio_path = os.path.join(outdir, f"{video_id}.{ext}")
            
            if os.path.exists(audio_path):
                if debug:
                    logger.debug(f"Downloaded audio to: {audio_path}")
                return audio_path
            else:
                logger.warning(f"Expected audio file not found at: {audio_path}")
                return ""
    except yt_dlp.utils.DownloadError as e:
        logger.warning(f"yt_dlp API download error: {e}")
        return ""
    except Exception as e:
        logger.warning(f"yt_dlp API unexpected error: {e}")
        return ""

def download_audio(video_id: str, outdir: str, debug: bool=False) -> str:
    """Download audio via yt-dlp CLI or API fallback."""
    os.makedirs(outdir, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    if debug:
        logger.debug(f"Attempting to download audio for {video_id}")

    # 1) yt-dlp CLI if available
    ytdlp_cmd = shutil.which("yt-dlp") or shutil.which("yt_dlp")
    if not ytdlp_cmd:
        ytdlp_cmd = sys.executable + " -m yt_dlp"
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)  # Increase timeout to 10 minutes
    try:
        temp_dir = tempfile.mkdtemp(dir=outdir)
        out_tmpl = os.path.join(temp_dir, f"{video_id}.%(ext)s")
        cmd = (
            ytdlp_cmd.split()
            + ["-f", "bestaudio", "--quiet", "--no-warnings",
               "--extract-audio", "--audio-format", "mp3",
               "-o", out_tmpl, url]
        )
        if debug: 
            logger.debug(f"Running yt-dlp: {' '.join(cmd)}")
            
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=240)
        
        if debug and result.stderr:
            logger.debug(f"yt-dlp stderr: {result.stderr}")
            
        for fname in os.listdir(temp_dir):
            if fname.startswith(video_id) and fname.split('.')[-1] in ("mp3","m4a","wav"):
                audio_path = os.path.join(temp_dir, fname)
                if check_audio_file(audio_path):
                    return audio_path
                else:
                    logger.warning(f"Audio file validation failed: {audio_path}")
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp download timed out for video {video_id}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"yt-dlp CLI error (code {e.returncode}): {e.stderr}")
    except Exception as e:
        logger.warning(f"yt-dlp download unexpected error: {e}")

    # 2) yt-dlp Python API fallback
    logger.info("Trying yt-dlp Python API fallback...")
    api_path = _download_with_yt_dlp_api(url, outdir, video_id, debug)
    if api_path and check_audio_file(api_path):
        if debug: 
            logger.debug(f"yt-dlp API audio: {api_path}")
        return api_path
    
    logger.warning(f"All download methods failed for video {video_id}")
    return ""

def _get_whisper_model(size: str):
    """Get or load a Whisper model, respecting cache limits."""
    if not validate_model_size(size):
        raise ValueError(f"Invalid model size: {size}")
        
    # Clear cache if we're at the limit and loading a new model
    if len(_whisper_models) >= MAX_CACHED_MODELS and size not in _whisper_models:
        logger.info(f"Cache limit reached. Clearing model cache before loading {size}")
        clean_model_cache()
        
    if size not in _whisper_models:
        logger.info(f"Loading Whisper model: {size}")
        try:
            _whisper_models[size] = whisper.load_model(size)
            logger.info(f"Successfully loaded Whisper model: {size}")
        except Exception as e:
            logger.error(f"Failed to load Whisper model {size}: {e}")
            raise
            
    return _whisper_models[size]

def _get_faster_model(size: str):
    """Get or load a Faster Whisper model, respecting cache limits."""
    if not validate_model_size(size):
        raise ValueError(f"Invalid model size: {size}")
        
    # Clear cache if we're at the limit and loading a new model
    if len(_faster_models) >= MAX_CACHED_MODELS and size not in _faster_models:
        logger.info(f"Cache limit reached. Clearing model cache before loading {size}")
        clean_model_cache()
        
    if size not in _faster_models:
        logger.info(f"Loading Faster Whisper model: {size}")
        try:
            _faster_models[size] = WhisperModel(size, device=DEVICE, compute_type="int8")
            logger.info(f"Successfully loaded Faster Whisper model: {size}")
        except Exception as e:
            logger.error(f"Failed to load Faster Whisper model {size}: {e}")
            raise
            
    return _faster_models[size]

def get_youtube_api_transcript(video_id: str) -> str:
    """Fetch autogenerated transcript via YouTubeTranscriptApi."""
    if not HAS_API:
        logger.warning("YouTube Transcript API not available")
        return ""
        
    try:
        logger.info(f"Fetching YouTube transcript for {video_id}")
        data = YouTubeTranscriptApi.get_transcript(video_id)
        logger.info(f"Successfully retrieved {len(data)} transcript segments")
    except NoTranscriptFound:
        logger.warning(f"No transcript found for video {video_id}")
        return ""
    except Exception as e:
        logger.warning(f"YouTube Transcript API error: {e}")
        return ""
        
    srt_blocks = []
    for i, seg in enumerate(data, 1):
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["start"] + seg["duration"])
        text = seg["text"].strip()
        srt_blocks.append(f"{i}\n{start} --> {end}\n{text}\n")
        
    return "\n".join(srt_blocks)

def transcribe_whisper(path: str, lang: str, model_size="large-v3") -> str:
    """Transcribe audio using OpenAI Whisper."""
    if not check_audio_file(path):
        return ""
        
    try:
        logger.info(f"Transcribing with OpenAI Whisper ({model_size})")
        model = _get_whisper_model(model_size)
        result = model.transcribe(path, language=lang)
        segments = result.get("segments", [])
        
        if not segments:
            logger.warning("Whisper transcription returned no segments")
            return ""
            
        logger.info(f"Whisper transcription successful: {len(segments)} segments")
        
        lines = []
        for i, seg in enumerate(segments, 1):
            start = format_timestamp(seg["start"])
            end = format_timestamp(seg["end"])
            text = seg["text"].strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
            
        # Unload the model to free memory
        if model_size in _whisper_models:
            logger.info(f"Unloading Whisper model {model_size}")
            del _whisper_models[model_size]
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
        return "".join(lines)
    except torch.cuda.OutOfMemoryError:
        logger.error(f"CUDA out of memory error with Whisper model {model_size}")
        clean_model_cache()  # Force cleanup
        return ""
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return ""

def transcribe_faster(path: str, lang: str, model_size="large-v3") -> str:
    """Transcribe audio using Faster Whisper."""
    if not check_audio_file(path):
        return ""
        
    try:
        logger.info(f"Transcribing with Faster Whisper ({model_size})")
        model = _get_faster_model(model_size)
        segments, _ = model.transcribe(path, language=lang)
        
        # Convert generator to list to validate
        segments_list = list(segments)
        
        if not segments_list:
            logger.warning("Faster Whisper transcription returned no segments")
            return ""
            
        logger.info(f"Faster Whisper transcription successful: {len(segments_list)} segments")
        
        lines = []
        for i, seg in enumerate(segments_list, 1):
            start = format_timestamp(seg.start)
            end = format_timestamp(seg.end)
            text = seg.text.strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
            
        # Unload the model to free memory (this was missing in the original code)
        if model_size in _faster_models:
            logger.info(f"Unloading Faster Whisper model {model_size}")
            del _faster_models[model_size]
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
        return "".join(lines)
    except torch.cuda.OutOfMemoryError:
        logger.error(f"CUDA out of memory error with Faster Whisper model {model_size}")
        clean_model_cache()  # Force cleanup
        return ""
    except Exception as e:
        logger.error(f"Faster Whisper transcription error: {e}")
        return ""

def transcribe_local(
    video_id: str,
    outdir: str,
    lang: str,
    model_size: str,
    logger_level: int = logging.INFO,
    debug: bool = False
) -> str:
    """
    Download audio, try faster-whisper, whisper, then YouTube-API fallback.
    Returns SRT or empty string on failure.
    """
    logging.getLogger().setLevel(logger_level)
    
    # Validate model size early
    if not validate_model_size(model_size):
        logger.error(f"Invalid model size: {model_size}")
        return ""

    # Check available memory before starting
    if torch.cuda.is_available():
        free_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()
        logger.info(f"Available CUDA memory: {free_memory / (1024**3):.2f} GB")

    # 1) Download
    logger.info(f"Downloading audio for {video_id}")
    audio_path = download_audio(video_id, outdir, debug=debug)
    
    if not audio_path or not os.path.exists(audio_path):
        logger.error("Audio download failed or file doesn't exist.")
        # Try YouTube API directly without audio
        logger.info("Trying YouTubeTranscriptApi without audio...")
        return get_youtube_api_transcript(video_id)

    # Make sure we have a clean state
    clean_model_cache()
    
    srt = ""
    # 2) faster-whisper
    if HAS_FASTER:
        try:
            if debug: 
                logger.debug("Running Faster Whisper...")
            srt = transcribe_faster(audio_path, lang, model_size)
            if debug: 
                logger.debug(f"Faster SRT length: {len(srt)}")
        except Exception as e:
            logger.warning(f"Faster Whisper error: {e}")
            # Make sure we clean up if there was an error
            clean_model_cache()

    # 3) openai-whisper fallback
    if not srt and HAS_WHISPER:
        try:
            if debug: 
                logger.debug("Running OpenAI Whisper...")
            srt = transcribe_whisper(audio_path, lang, model_size)
            if debug: 
                logger.debug(f"Whisper SRT length: {len(srt)}")
        except Exception as e:
            logger.warning(f"OpenAI Whisper error: {e}")
            # Make sure we clean up if there was an error
            clean_model_cache()
            
    # 4) YouTube API fallback if everything else fails
    if not srt and HAS_API:
        logger.info("Local transcription failed, trying YouTube API...")
        srt = get_youtube_api_transcript(video_id)

    # 5) Cleanup
    try:
        if os.path.exists(audio_path):
            logger.info(f"Cleaning up audio file: {audio_path}")
            os.remove(audio_path)
            # Try to remove parent directory if it's empty
            parent_dir = os.path.dirname(audio_path)
            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
    except Exception as e:
        logger.warning(f"Failed to remove audio file: {e}")

    # Final cleanup of models
    clean_model_cache()

    if not srt:
        logger.error("Could not obtain any transcript.")
        
    return srt