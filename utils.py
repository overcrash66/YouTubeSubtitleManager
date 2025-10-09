import re
import unicodedata
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL or raw ID."""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})',
        r'^([A-Za-z0-9_-]{11})$'
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    logger.error("Invalid YouTube URL or ID: %s", url)
    return ""

def check_youtube_access() -> bool:
    """Quick check to verify we can reach YouTube."""
    import requests
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            timeout=5,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        return resp.status_code == 200
    except Exception as e:
        logger.warning("YouTube access check failed: %s", e)
        return False

def parse_srt_time(ts: str) -> datetime:
    """Parse SRT timestamp into datetime."""
    ts = ts.replace('.', ',')
    for fmt in ("%H:%M:%S,%f", "%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid SRT time format: {ts}")

def time_to_ms(dt: datetime) -> int:
    return (dt.hour*3600 + dt.minute*60 + dt.second)*1000 + dt.microsecond//1000

def ms_to_time(ms: int) -> str:
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms_rem = ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms_rem:03}"

def format_timestamp(seconds: float) -> str:
    """Convert seconds (float) to SRT timestamp string."""
    ms = int(seconds * 1000)
    return ms_to_time(ms)

def validate_and_adjust_timings(srt: str, min_gap: int = 100) -> str:
    """Ensure no overlaps, enforce min duration/gaps."""
    blocks = [b for b in srt.strip().split("\n\n") if "-->" in b]
    out = []
    prev_end = 0
    for blk in blocks:
        lines = blk.splitlines()
        idx, timing, *text = lines
        start_s, end_s = timing.split(" --> ")
        start_dt = parse_srt_time(start_s)
        end_dt = parse_srt_time(end_s)
        start_ms = max(time_to_ms(start_dt), prev_end + min_gap)
        end_ms = time_to_ms(end_dt)
        if end_ms <= start_ms:
            end_ms = start_ms + 500
        prev_end = end_ms
        new_t = f"{ms_to_time(start_ms)} --> {ms_to_time(end_ms)}"
        out.append("\n".join([idx, new_t, *text]))
    return "\n\n".join(out) + "\n"

def srt_to_paragraph(srt: str) -> str:
    """Flatten SRT blocks into a continuous paragraph."""
    paras = []
    for blk in srt.strip().split("\n\n"):
        lines = blk.splitlines()
        if len(lines) >= 3:
            text = " ".join(lines[2:]).strip()
            paras.append(text)
    text = " ".join(paras)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def normalize_arabic(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'ـ+', '', text)
    text = re.sub(r'[\u064B-\u065F]', '', text)
    return text