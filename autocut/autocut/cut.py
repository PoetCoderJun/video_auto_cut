import logging
import os
import re
import shutil
import subprocess
from typing import List, Dict, Optional, Tuple

import srt
from moviepy.video.compositing.CompositeVideoClip import concatenate_videoclips
from moviepy.video.io.VideoFileClip import VideoFileClip

from . import utils

REMOVE_TOKEN = "<<REMOVE>>"
DECISION_HEADER_PATTERN = re.compile(r"^\[(KEEP|REMOVE)\b[^\]]*\]\s*$", re.IGNORECASE)
CUT_MERGE_GAP_DEFAULT = 0.0


def parse_decision_and_text(content: str) -> Tuple[Optional[str], str]:
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if not lines:
        return None, ""
    first = lines[0]
    match = DECISION_HEADER_PATTERN.match(first)
    if not match:
        return None, "\n".join(lines).strip()

    decision = match.group(1).upper()
    text = "\n".join(lines[1:]).strip()
    return decision, text


def filter_kept_subtitles(subs: List[srt.Subtitle]) -> List[srt.Subtitle]:
    kept: List[srt.Subtitle] = []
    for sub in subs:
        decision, text = parse_decision_and_text(sub.content or "")
        if decision == "REMOVE":
            continue
        if text.startswith(REMOVE_TOKEN):
            continue
        if not text:
            continue
        if sub.end <= sub.start:
            continue

        kept.append(
            srt.Subtitle(
                index=sub.index,
                start=sub.start,
                end=sub.end,
                content=text,
            )
        )

    kept.sort(key=lambda x: x.start)
    return kept


def build_merged_segments(
    subs: List[srt.Subtitle], merge_gap_s: float = 0.5
) -> List[Dict[str, float]]:
    segments: List[Dict[str, float]] = []
    for sub in subs:
        start = max(0.0, sub.start.total_seconds())
        end = max(start, sub.end.total_seconds())
        if end <= start:
            continue

        if not segments:
            segments.append({"start": start, "end": end})
            continue

        if start - segments[-1]["end"] < merge_gap_s:
            segments[-1]["end"] = max(segments[-1]["end"], end)
        else:
            segments.append({"start": start, "end": end})
    return segments


def resolve_cut_merge_gap(args) -> float:
    raw = getattr(args, "cut_merge_gap", CUT_MERGE_GAP_DEFAULT)
    try:
        gap = float(raw)
    except (TypeError, ValueError):
        return CUT_MERGE_GAP_DEFAULT
    return max(0.0, gap)


# Merge videos
class Merger:
    def __init__(self, args):
        self.args = args

    def write_md(self, videos):
        md = utils.MD(self.args.inputs[0], self.args.encoding)
        num_tasks = len(md.tasks())
        # Not overwrite if already marked as down or no new videos
        if md.done_editing() or num_tasks == len(videos) + 1:
            return

        md.clear()
        md.add_done_editing(False)
        md.add("\nSelect the files that will be used to generate `autocut_final.mp4`\n")
        base = lambda fn: os.path.basename(fn)
        for f in videos:
            md_fn = utils.change_ext(f, "md")
            video_md = utils.MD(md_fn, self.args.encoding)
            # select a few words to scribe the video
            desc = ""
            if len(video_md.tasks()) > 1:
                for _, t in video_md.tasks()[1:]:
                    m = re.findall(r"\] (.*)", t)
                    if m and "no speech" not in m[0].lower():
                        desc += m[0] + " "
                    if len(desc) > 50:
                        break
            md.add_task(
                False,
                f'[{base(f)}]({base(md_fn)}) {"[Edited]" if video_md.done_editing() else ""} {desc}',
            )
        md.write()

    def run(self):
        md_fn = self.args.inputs[0]
        md = utils.MD(md_fn, self.args.encoding)
        if not md.done_editing():
            return

        videos = []
        for m, t in md.tasks():
            if not m:
                continue
            m = re.findall(r"\[(.*)\]", t)
            if not m:
                continue
            fn = os.path.join(os.path.dirname(md_fn), m[0])
            logging.info(f"Loading {fn}")
            videos.append(VideoFileClip(fn))

        dur = sum([v.duration for v in videos])
        logging.info(f"Merging into a video with {dur / 60:.1f} min length")

        merged = concatenate_videoclips(videos)
        fn = os.path.splitext(md_fn)[0] + "_merged.mp4"
        merged.write_videofile(
            fn, audio_codec="aac", bitrate=self.args.bitrate
        )  # logger=None,
        logging.info(f"Saved merged video to {fn}")


# Cut media
class Cutter:
    def __init__(self, args):
        self.args = args
        self._ffmpeg_bin = self._resolve_bin("ffmpeg")
        self._ffprobe_bin = self._resolve_bin("ffprobe")

    def run(self):
        fns = {"srt": None, "media": None, "md": None}
        for fn in self.args.inputs:
            ext = os.path.splitext(fn)[1][1:]
            fns[ext if ext in fns else "media"] = fn

        assert fns["media"], "must provide a media filename"
        assert fns["srt"], "must provide a srt filename"

        is_video_file = utils.is_video(fns["media"].lower())
        outext = "mp4" if is_video_file else "mp3"
        output_fn = utils.change_ext(utils.add_cut(fns["media"]), outext)
        if utils.check_exists(output_fn, self.args.force):
            return

        with open(fns["srt"], encoding=self.args.encoding) as f:
            subs = list(srt.parse(f.read()))

        if fns["md"]:
            md = utils.MD(fns["md"], self.args.encoding)
            if not md.done_editing():
                return
            index = []
            for mark, sent in md.tasks():
                if not mark:
                    continue
                m = re.match(r"\[(\d+)", sent.strip())
                if m:
                    index.append(int(m.groups()[0]))
            subs = [s for s in subs if s.index in index]
            logging.info(f'Cut {fns["media"]} based on {fns["srt"]} and {fns["md"]}')
        else:
            logging.info(f'Cut {fns["media"]} based on {fns["srt"]}')

        subs = filter_kept_subtitles(subs)
        merge_gap_s = resolve_cut_merge_gap(self.args)
        segments = build_merged_segments(subs, merge_gap_s=merge_gap_s)
        if not segments:
            raise RuntimeError(
                "No valid kept subtitle segments to cut. Check optimized SRT decisions."
            )

        total_duration = sum([s["end"] - s["start"] for s in segments])
        src_duration = self._probe_duration(fns["media"])
        logging.info(f"Cut merge gap: {merge_gap_s:.3f}s")
        if src_duration is not None:
            logging.info(f"Reduced duration from {src_duration:.1f} to {total_duration:.1f}")
        else:
            logging.info(f"Target cut duration: {total_duration:.1f} sec")

        if is_video_file:
            self._cut_video_with_ffmpeg(fns["media"], segments, output_fn)
        else:
            self._cut_audio_with_ffmpeg(fns["media"], segments, output_fn)

        logging.info(f"Saved media to {output_fn}")

    @staticmethod
    def _resolve_bin(name: str) -> str:
        bin_path = shutil.which(name)
        if not bin_path:
            raise RuntimeError(f"{name} not found in PATH")
        return bin_path

    def _probe_duration(self, media_fn: str) -> Optional[float]:
        cmd = [
            self._ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            media_fn,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        raw = (result.stdout or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _has_audio_stream(self, media_fn: str) -> bool:
        cmd = [
            self._ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            media_fn,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False
        return bool((result.stdout or "").strip())

    def _cut_video_with_ffmpeg(
        self, media_fn: str, segments: List[Dict[str, float]], output_fn: str
    ) -> None:
        has_audio = self._has_audio_stream(media_fn)
        filters: List[str] = []
        concat_inputs: List[str] = []

        for i, seg in enumerate(segments):
            start = f'{seg["start"]:.6f}'
            end = f'{seg["end"]:.6f}'
            filters.append(
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]"
            )
            concat_inputs.append(f"[v{i}]")

            if has_audio:
                filters.append(
                    f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
                )
                concat_inputs.append(f"[a{i}]")

        if has_audio:
            filters.append(
                f'{"".join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[vout][aout]'
            )
        else:
            filters.append(
                f'{"".join(concat_inputs)}concat=n={len(segments)}:v=1:a=0[vout]'
            )

        cmd = [
            self._ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            media_fn,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
        ]

        if has_audio:
            cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-an"]

        cmd += [
            "-c:v",
            "libx264",
            "-b:v",
            self.args.bitrate,
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_fn,
        ]

        self._run_ffmpeg(cmd, "video cut")

    def _cut_audio_with_ffmpeg(
        self, media_fn: str, segments: List[Dict[str, float]], output_fn: str
    ) -> None:
        filters: List[str] = []
        concat_inputs: List[str] = []
        for i, seg in enumerate(segments):
            start = f'{seg["start"]:.6f}'
            end = f'{seg["end"]:.6f}'
            filters.append(
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
            )
            concat_inputs.append(f"[a{i}]")
        filters.append(f'{"".join(concat_inputs)}concat=n={len(segments)}:v=0:a=1[aout]')

        cmd = [
            self._ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            media_fn,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-c:a",
            "libmp3lame",
            "-ar",
            "44100",
            "-b:a",
            self.args.bitrate,
            output_fn,
        ]
        self._run_ffmpeg(cmd, "audio cut")

    @staticmethod
    def _run_ffmpeg(cmd: List[str], stage: str) -> None:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"ffmpeg failed during {stage}: {exc.stderr.strip()}") from exc
