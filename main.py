import os
import sys
import argparse
import logging

from utils import extract_video_id, check_youtube_access, validate_and_adjust_timings, srt_to_paragraph
from caption_fetch import get_captions
from transcription import transcribe_local
from translation import setup_argos, setup_transformer, translate_srt

def configure_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=level
    )

def main():
    parser = argparse.ArgumentParser(description="YouTube Subtitle Manager")
    parser.add_argument("url", help="YouTube URL or ID")
    parser.add_argument("--source-lang", default="ar", help="Source language code")
    parser.add_argument("--translate", nargs="*", help="Target language codes")
    parser.add_argument("--output-dir", default="./subtitles", help="Output directory")
    parser.add_argument("--min-gap", type=int, default=100, help="Min gap ms between subtitles")
    parser.add_argument("--save-txt", action="store_true", help="Save plain text")
    parser.add_argument("--use-local-transcription", action="store_true")
    parser.add_argument("--use-local-translation", action="store_true")
    parser.add_argument("--whisper-model", default="base", choices=["tiny","base","small","medium","large"])
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    configure_logging(args.debug)
    logger = logging.getLogger("main")

    if not check_youtube_access():
        logger.error("Cannot reach YouTube. Check network.")
        sys.exit(1)

    vid = extract_video_id(args.url)
    if not vid:
        sys.exit("Invalid video URL/ID")

    os.makedirs(args.output_dir, exist_ok=True)
    srt = ""

    # Online captions
    if not args.use_local_transcription:
        srt = get_captions(vid, args.source_lang)
        if not srt and args.source_lang != "en":
            logger.info("No %s captions, falling back to English", args.source_lang)
            srt = get_captions(vid, "en")
            args.source_lang = "en"

    # Local transcription
    if not srt and args.use_local_transcription:
        srt = transcribe_local(vid, args.output_dir, args.source_lang, args.whisper_model, logger.level)

    if not srt:
        logger.error("Failed to obtain captions/transcript.")
        sys.exit(1)

    # Adjust timings
    srt = validate_and_adjust_timings(srt, args.min_gap)

    # Save original SRT
    base = os.path.join(args.output_dir, vid)
    orig_path = f"{base}_{args.source_lang}.srt"
    with open(orig_path, "w", encoding="utf-8") as f:
        f.write(srt)
    logger.info("Saved SRT: %s", orig_path)

    # Save plain text
    if args.save_txt:
        txt = srt_to_paragraph(srt)
        txt_path = f"{base}_{args.source_lang}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt)
        logger.info("Saved TXT: %s", txt_path)

    # Translation
    for tgt in args.translate or []:
        if tgt == args.source_lang:
            logger.info("Skipping translation to same language %s", tgt)
            continue
        if args.use_local_translation:
            transformer = setup_transformer(args.source_lang, tgt)
            logger.debug("Using local transformer for %s->%s", args.source_lang, tgt)
        else:
            if not setup_argos(args.source_lang, tgt):
                logger.warning("Argos model %s->%s unavailable, skipping", args.source_lang, tgt)
                continue
            transformer = None
        srt_tr = translate_srt(srt, args.source_lang, tgt, transformer)
        srt_tr = validate_and_adjust_timings(srt_tr, args.min_gap)
        out_path = f"{base}_{tgt}.srt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(srt_tr)
        logger.info("Saved translated SRT: %s", out_path)
        if args.save_txt:
            txt_tr = srt_to_paragraph(srt_tr)
            path_txt = f"{base}_{tgt}.txt"
            with open(path_txt, "w", encoding="utf-8") as f:
                f.write(txt_tr)
            logger.info("Saved translated TXT: %s", path_txt)

if __name__ == "__main__":
    main()