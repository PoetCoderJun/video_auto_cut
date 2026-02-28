import argparse
import logging
import os

from . import utils
from .type import WhisperMode, WhisperModel


def main():
    parser = argparse.ArgumentParser(
        description="Edit videos based on transcribed subtitles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    logging.basicConfig(
        format="[autocut:%(filename)s:L%(lineno)d] %(levelname)-6s %(message)s"
    )
    logging.getLogger().setLevel(logging.INFO)

    parser.add_argument("inputs", type=str, nargs="+", help="Inputs filenames/folders")
    parser.add_argument(
        "-t",
        "--transcribe",
        help="Transcribe videos/audio into subtitles",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-c",
        "--cut",
        help="Cut a video based on subtitles",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-d",
        "--daemon",
        help="Monitor a folder to transcribe and cut",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-s",
        help="Convert .srt to a compact format for easier editing",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-m",
        "--to-md",
        help="Convert .srt to .md for easier editing",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-e",
        "--auto-edit",
        help="Auto edit: LLM semantic edit -> optimized SRT + EDL",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--render",
        help="Render video with pipeline: existing autocut stitch + Remotion subtitle overlay",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="zh",
        choices=[
            "zh",
            "en",
            "Afrikaans",
            "Arabic",
            "Armenian",
            "Azerbaijani",
            "Belarusian",
            "Bosnian",
            "Bulgarian",
            "Catalan",
            "Croatian",
            "Czech",
            "Danish",
            "Dutch",
            "Estonian",
            "Finnish",
            "French",
            "Galician",
            "German",
            "Greek",
            "Hebrew",
            "Hindi",
            "Hungarian",
            "Icelandic",
            "Indonesian",
            "Italian",
            "Japanese",
            "Kannada",
            "Kazakh",
            "Korean",
            "Latvian",
            "Lithuanian",
            "Macedonian",
            "Malay",
            "Marathi",
            "Maori",
            "Nepali",
            "Norwegian",
            "Persian",
            "Polish",
            "Portuguese",
            "Romanian",
            "Russian",
            "Serbian",
            "Slovak",
            "Slovenian",
            "Spanish",
            "Swahili",
            "Swedish",
            "Tagalog",
            "Tamil",
            "Thai",
            "Turkish",
            "Ukrainian",
            "Urdu",
            "Vietnamese",
            "Welsh",
        ],
        help="The output language of transcription",
    )
    parser.add_argument(
        "--prompt", type=str, default="", help="initial prompt feed into whisper"
    )
    parser.add_argument(
        "--whisper-mode",
        type=str,
        default=WhisperMode.WHISPER.value,
        choices=WhisperMode.get_values(),
        help="Transcription mode: whisper/faster/openai/qwen3.",
    )
    parser.add_argument(
        "--openai-rpm",
        type=int,
        default=3,
        choices=[3, 50],
        help="Openai Whisper API REQUESTS PER MINUTE(FREE USERS: 3RPM; PAID USERS: 50RPM). "
        "More info: https://platform.openai.com/docs/guides/rate-limits/overview",
    )
    parser.add_argument(
        "--whisper-model",
        type=str,
        default=WhisperModel.SMALL.value,
        choices=WhisperModel.get_values(),
        help="The whisper model used to transcribe.",
    )
    parser.add_argument(
        "--qwen3-model",
        type=str,
        default=None,
        help="Qwen3 ASR model id or local path (used when --whisper-mode=qwen3)",
    )
    parser.add_argument(
        "--qwen3-aligner",
        type=str,
        default=None,
        help="Qwen3 forced aligner model id or local path (used when --whisper-mode=qwen3)",
    )
    parser.add_argument(
        "--qwen3-language",
        type=str,
        default=None,
        help="Force Qwen3 language (e.g. Chinese/English). Leave empty for auto.",
    )
    parser.add_argument(
        "--qwen3-use-modelscope",
        action=argparse.BooleanOptionalAction,
        help="Resolve Qwen3 model ids via ModelScope snapshot_download",
    )
    parser.add_argument(
        "--qwen3-offline",
        action=argparse.BooleanOptionalAction,
        help="Do not access network for Qwen3; use local files only",
    )
    parser.add_argument(
        "--qwen3-gap",
        type=float,
        default=0.6,
        help="Gap (seconds) to split Qwen3 subtitles",
    )
    parser.add_argument(
        "--qwen3-max-seg",
        type=float,
        default=20.0,
        help="Max segment length (seconds) for Qwen3 subtitles",
    )
    parser.add_argument(
        "--qwen3-max-chars",
        type=int,
        default=0,
        help="Max characters per Qwen3 subtitle line",
    )
    parser.add_argument(
        "--qwen3-no-speech-gap",
        type=float,
        default=1.0,
        help="Insert < No Speech > when gap exceeds this value (seconds)",
    )
    parser.add_argument(
        "--qwen3-use-punct",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Insert punctuation from ASR text and use it to split subtitles",
    )
    parser.add_argument(
        "--llm-base-url",
        type=str,
        default=None,
        help="OpenAI-compatible base URL for LLM (e.g. http://localhost:8000)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="LLM model name for auto-edit",
    )
    parser.add_argument(
        "--llm-api-key",
        type=str,
        default=None,
        help="LLM API key (optional for local servers)",
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=300,
        help="LLM request timeout (seconds)",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=0.2,
        help="LLM sampling temperature",
    )
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=None,
        help="Optional LLM max tokens for responses (omit to use model default)",
    )
    parser.add_argument(
        "--auto-edit-llm",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use LLM to edit full text and map back to SRT (required)",
    )
    parser.add_argument(
        "--auto-edit-min-quality",
        type=float,
        default=60.0,
        help="Minimum quality score to keep a segment",
    )
    parser.add_argument(
        "--auto-edit-merge-gap",
        type=float,
        default=0.5,
        help="Merge adjacent kept segments if gap <= this (seconds)",
    )
    parser.add_argument(
        "--auto-edit-pad-head",
        type=float,
        default=0.0,
        help="Pad kept segment start time (seconds)",
    )
    parser.add_argument(
        "--auto-edit-pad-tail",
        type=float,
        default=0.0,
        help="Pad kept segment end time (seconds)",
    )
    parser.add_argument(
        "--auto-edit-output",
        type=str,
        default=None,
        help="Output base path for auto-edit results",
    )
    parser.add_argument(
        "--bitrate",
        type=str,
        default="10m",
        help="The bitrate to export the cutted video, such as 10m, 1m, or 500k",
    )
    parser.add_argument(
        "--cut-merge-gap",
        type=float,
        default=0.0,
        help="Merge adjacent kept subtitle segments when their gap is smaller than this value (seconds)",
    )
    parser.add_argument(
        "--render-output",
        type=str,
        default=None,
        help="Output filename for final render (default: <video>_remotion.mp4)",
    )
    parser.add_argument(
        "--render-fps",
        type=float,
        default=None,
        help="Override FPS for Remotion render (default: capped at 30fps)",
    )
    parser.add_argument(
        "--render-preview",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable preview render (caps to 720p/15fps unless overridden)",
    )
    parser.add_argument(
        "--render-codec",
        type=str,
        default=None,
        help="Codec for Remotion render (e.g. h264, h265, prores)",
    )
    parser.add_argument(
        "--render-crf",
        type=int,
        default=None,
        help="CRF for Remotion render (lower is higher quality)",
    )
    parser.add_argument(
        "--vad", help="If or not use VAD", choices=["1", "0", "auto"], default="auto"
    )
    parser.add_argument(
        "--force",
        help="Force write even if files exist",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--encoding", type=str, default="utf-8", help="Document encoding format"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cpu", "cuda", "mps"],
        help="Force to CPU or GPU for transcribing. In default automatically use GPU if available.",
    )

    args = parser.parse_args()

    if args.transcribe:
        from .transcribe import Transcribe

        Transcribe(args).run()
    elif args.to_md:
        from .utils import trans_srt_to_md

        if len(args.inputs) == 2:
            [input_1, input_2] = args.inputs
            base, ext = os.path.splitext(input_1)
            if ext != ".srt":
                input_1, input_2 = input_2, input_1
            trans_srt_to_md(args.encoding, args.force, input_1, input_2)
        elif len(args.inputs) == 1:
            trans_srt_to_md(args.encoding, args.force, args.inputs[0])
        else:
            logging.warning(
                "Wrong number of files, please pass in a .srt file or an additional video file"
            )
    elif args.cut:
        from .cut import Cutter

        Cutter(args).run()
    elif args.auto_edit:
        from .auto_edit import AutoEdit

        AutoEdit(args).run()
    elif args.render:
        from .remotion_render import RemotionRenderer

        RemotionRenderer(args).run()
    elif args.daemon:
        from .daemon import Daemon

        Daemon(args).run()
    elif args.s:
        utils.compact_rst(args.inputs[0], args.encoding)
    else:
        logging.warning("No action, use -c, -t or -d")


if __name__ == "__main__":
    main()
