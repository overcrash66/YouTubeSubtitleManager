import os
import tempfile
import logging
import subprocess

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from youtube_transcript_api.formatters import SRTFormatter
from pytube import YouTube
from pytube.exceptions import PytubeError, VideoUnavailable

logger = logging.getLogger(__name__)

def fetch_via_transcript_api(video_id: str, lang: str) -> str:
    transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
    try:
        tr = transcripts.find_transcript([lang])
    except NoTranscriptFound:
        tr = transcripts.find_transcript(['en'])
        logger.info("Falling back to English via transcript-api")
    data = tr.fetch()
    return SRTFormatter().format_transcript(data)

def fetch_via_ytdlp(video_id: str, lang: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        cmd = [
            'yt-dlp', '--skip-download',
            '--write-subs', '--write-auto-subs',
            '--sub-langs', f'{lang},en',
            '--sub-format', 'srt',
            '-o', os.path.join(td, '%(id)s.%(ext)s'),
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            logger.warning("yt-dlp failed: %s", res.stderr.strip())
            return ""
        for fn in os.listdir(td):
            if fn.endswith('.srt'):
                return open(os.path.join(td, fn), encoding='utf-8').read()
    return ""

def fetch_via_pytube(video_id: str, lang: str) -> str:
    try:
        yt = YouTube(f'https://www.youtube.com/watch?v={video_id}')
        caps = yt.captions
        # exact -> auto -> any
        key = lang if lang in caps else f"a.{lang}" if f"a.{lang}" in caps else None
        if key:
            text = caps[key].generate_srt_captions()
            if text.strip():
                return text
        # fallback any
        for c in caps.values():
            text = c.generate_srt_captions()
            if text.strip():
                logger.info("Using pytube fallback caption")
                return text
    except (PytubeError, VideoUnavailable) as e:
        logger.warning("pytube failed: %s", e)
    return ""

def get_captions(video_id: str, lang: str="ar") -> str:
    """Try online caption methods in order."""
    for fn in (fetch_via_transcript_api, fetch_via_ytdlp, fetch_via_pytube):
        try:
            srt = fn(video_id, lang)
            if srt and srt.strip():
                return srt
        except Exception as e:
            logger.debug("Method %s error: %s", fn.__name__, e)
    return ""