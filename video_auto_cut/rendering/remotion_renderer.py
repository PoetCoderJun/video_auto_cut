import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import srt

from ..editing.topic_segment import TopicSegmenter
from ..shared import media as utils
from .cut import Cutter, resolve_cut_merge_gap
from .cut_srt import build_cut_srt_from_optimized_srt

_NODE_RENDER_PROGRESS_RE = re.compile(r"RENDER_PROGRESS_PCT=([0-9]+(?:\.[0-9]+)?)")


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here.parent] + list(here.parents):
        if (
            (candidate / "remotion").exists()
            and ((candidate / "main.py").exists() or (candidate / "video_auto_cut").exists())
        ):
            return candidate
    return here.parents[2]


class RemotionRenderer:
    def __init__(self, args):
        self.args = args
        self._ffmpeg_bin = self._resolve_ffmpeg_bin()
        self._ffprobe_bin = self._resolve_ffprobe_bin()

    def run(self):
        media_fn, srt_fn = self._select_inputs(self.args.inputs)
        media_fn = os.path.abspath(media_fn)
        srt_fn = os.path.abspath(srt_fn)

        if not utils.is_video(media_fn):
            raise RuntimeError(f"Remotion render requires a video file, got: {media_fn}")

        self._emit_progress("init", 0.0)
        output_fn = self._resolve_output(media_fn)
        # Render mode should always regenerate final output to stay in sync with
        # the latest optimized SRT and cut timeline.
        if os.path.exists(output_fn):
            logging.info(f"{output_fn} exists. Will overwrite it")

        remotion_dir = self._resolve_remotion_dir()
        self._ensure_node_ready(remotion_dir)
        self._cleanup_stale_render_artifacts(remotion_dir, media_fn)
        self._emit_progress("prepare_source", 0.0)
        render_source = self._prepare_cut_source(remotion_dir, media_fn)
        self._emit_progress("prepare_source", 1.0)

        merge_gap_s = resolve_cut_merge_gap(self.args)
        self._emit_progress("cut_timeline", 0.0)
        cut_timeline = build_cut_srt_from_optimized_srt(
            source_srt_path=srt_fn,
            output_srt_path=self._resolve_cut_srt_output(srt_fn),
            encoding=self.args.encoding,
            merge_gap_s=merge_gap_s,
        )
        cut_srt = str(cut_timeline["cut_srt_path"])
        kept_subs = list(cut_timeline["kept_subtitles"])
        segments = list(cut_timeline["segments"])
        captions = list(cut_timeline["captions"])
        self._emit_progress("cut_timeline", 1.0)

        self._emit_progress("prepare_props", 0.0)
        manual_topics_input = getattr(self.args, "render_topics_input", None)
        if manual_topics_input:
            topics = self._load_topics(str(manual_topics_input))
        else:
            topics_path = self._maybe_generate_topics_from_cut_srt(cut_srt)
            if topics_path:
                topics = self._load_topics(topics_path)
            elif bool(getattr(self.args, "render_topics", True)):
                topics = self._load_topics(self._resolve_topic_output(cut_srt))
            else:
                topics = []
        self._write_timeline_debug(
            remotion_dir, media_fn, kept_subs, segments, captions, merge_gap_s, topics
        )

        meta = self._load_video_metadata(render_source)
        fps = self._resolve_fps(meta)
        width, height = self._resolve_dimensions(meta)
        cut_duration_s = sum(max(0.0, float(seg["end"]) - float(seg["start"])) for seg in segments)
        caption_duration_s = float(captions[-1]["end"]) if captions else 0.0
        topic_duration_s = max((float(item["end"]) for item in topics), default=0.0)
        duration_s = max(0.0, cut_duration_s, caption_duration_s, topic_duration_s)
        if duration_s <= 0:
            duration_s = float(meta.get("duration") or 0.0)
        if duration_s <= 0:
            raise RuntimeError("invalid render duration")
        duration_frames = max(1, int(math.ceil(duration_s * fps)))

        public_name = self._prepare_public_video(remotion_dir, render_source)
        props = {
            "src": public_name,
            "captions": captions,
            "segments": segments,
            "topics": topics,
            "fps": fps,
            "width": width,
            "height": height,
            "durationInFrames": duration_frames,
        }
        props_path = self._write_props(remotion_dir, media_fn, props)
        self._emit_progress("prepare_props", 1.0)

        self._emit_progress("node_render", 0.0)
        self._render_with_node(remotion_dir, props_path, output_fn)
        self._emit_progress("node_render", 1.0)
        output_fn = self._retag_bt709(output_fn)
        self._emit_progress("finalize", 1.0)
        logging.info(f"Saved remotion video to {output_fn}")

    def warmup_cut_video(self) -> str:
        media_fn, srt_fn = self._select_inputs(self.args.inputs)
        media_fn = os.path.abspath(media_fn)
        srt_fn = os.path.abspath(srt_fn)

        if not utils.is_video(media_fn):
            raise RuntimeError(f"Remotion render requires a video file, got: {media_fn}")

        remotion_dir = self._resolve_remotion_dir()
        self._cleanup_stale_render_artifacts(remotion_dir, media_fn)
        self._emit_progress("prepare_source", 0.0)
        cut_source = self._prepare_cut_source(remotion_dir, media_fn)
        self._emit_progress("prepare_source", 1.0)
        merge_gap_s = resolve_cut_merge_gap(self.args)
        self._emit_progress("cut_video", 0.0)
        cut_video = self._run_existing_cut(cut_source, srt_fn, merge_gap_s, force_rebuild=False)
        cut_video = self._retag_bt709(cut_video)
        self._emit_progress("cut_video", 1.0)
        return cut_video

    def _emit_progress(self, stage: str, ratio: Optional[float]) -> None:
        callback = getattr(self.args, "render_progress_callback", None)
        if not callable(callback):
            return

        normalized: Optional[float] = None
        if ratio is not None:
            try:
                normalized = max(0.0, min(1.0, float(ratio)))
            except (TypeError, ValueError):
                normalized = None

        try:
            callback(stage, normalized)
        except Exception:
            logging.exception("render progress callback failed at stage=%s", stage)

    def _maybe_generate_topics_from_cut_srt(self, cut_srt: str) -> Optional[str]:
        if not bool(getattr(self.args, "render_topics", True)):
            return None

        topic_output = self._resolve_topic_output(cut_srt)
        try:
            segmenter = TopicSegmenter(self.args)
        except Exception as exc:
            logging.warning("Skip cut-SRT topic segmentation: %s", exc)
            return None

        try:
            return segmenter.run_for_srt(cut_srt, output_path=topic_output)
        except Exception as exc:
            if bool(getattr(self.args, "topic_strict", False)):
                raise
            logging.warning("Cut-SRT topic segmentation failed: %s", exc)
            return None

    def _resolve_topic_output(self, cut_srt: str) -> str:
        explicit = getattr(self.args, "topic_output", None)
        if explicit:
            return os.path.abspath(explicit)

        source = Path(cut_srt).resolve()
        stem = source.stem
        return str(source.with_name(f"{stem}.topics.json"))

    def _load_topics(self, topics_path: Optional[str]) -> List[Dict[str, Any]]:
        if not topics_path:
            return []

        path = Path(topics_path)
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Failed to read topics JSON %s: %s", path, exc)
            return []

        items = data.get("topics")
        if not isinstance(items, list):
            return []

        topics: List[Dict[str, Any]] = []
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"章节{idx}").strip()
            summary = str(item.get("summary") or "").strip()
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
            except Exception:
                continue

            if end <= start:
                continue

            topics.append(
                {
                    "title": title,
                    "summary": summary,
                    "start": round(start, 3),
                    "end": round(end, 3),
                }
            )

        topics.sort(key=lambda x: float(x["start"]))
        return topics

    def _select_inputs(self, inputs: List[str]) -> Tuple[str, str]:
        media_fn = None
        srt_fn = None
        for fn in inputs:
            ext = os.path.splitext(fn)[1].lower()
            if ext == ".srt":
                srt_fn = fn
            else:
                media_fn = fn
        if not media_fn or not srt_fn:
            raise RuntimeError("Remotion render requires a video file and an optimized .srt file")
        return media_fn, srt_fn

    def _run_existing_cut(
        self, media_fn: str, srt_fn: str, merge_gap_s: float, *, force_rebuild: bool
    ) -> str:
        output_fn = utils.change_ext(utils.add_cut(media_fn), "mp4")
        cache_manifest = self._cut_cache_manifest_path(output_fn)
        if (
            not force_rebuild
            and os.path.exists(output_fn)
            and self._is_cut_cache_valid(cache_manifest, media_fn, srt_fn, merge_gap_s)
        ):
            logging.info("Reusing prepared cut video: %s", output_fn)
            return output_fn

        cut_args = SimpleNamespace(
            inputs=[media_fn, srt_fn],
            bitrate=self.args.bitrate,
            force=True,
            encoding=self.args.encoding,
            cut_merge_gap=merge_gap_s,
            cut_progress_callback=lambda ratio: self._emit_progress("cut_video", ratio),
        )
        Cutter(cut_args).run()

        if not os.path.exists(output_fn):
            raise RuntimeError(f"Failed to generate cut video: {output_fn}")
        self._write_cut_cache_manifest(cache_manifest, media_fn, srt_fn, merge_gap_s)
        return output_fn

    def _cut_cache_manifest_path(self, output_fn: str) -> Path:
        return Path(f"{output_fn}.cutmeta.json")

    def _is_cut_cache_valid(
        self, manifest_path: Path, media_fn: str, srt_fn: str, merge_gap_s: float
    ) -> bool:
        if not manifest_path.exists():
            return False

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        if not isinstance(payload, dict):
            return False

        expected = {
            "media": self._file_fingerprint(Path(media_fn)),
            "srt": self._file_fingerprint(Path(srt_fn)),
            "merge_gap_s": round(float(merge_gap_s), 6),
            "bitrate": str(self.args.bitrate),
        }
        return payload == expected

    def _write_cut_cache_manifest(
        self, manifest_path: Path, media_fn: str, srt_fn: str, merge_gap_s: float
    ) -> None:
        payload = {
            "media": self._file_fingerprint(Path(media_fn)),
            "srt": self._file_fingerprint(Path(srt_fn)),
            "merge_gap_s": round(float(merge_gap_s), 6),
            "bitrate": str(self.args.bitrate),
        }
        try:
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logging.warning("Failed to write cut cache manifest %s: %s", manifest_path, exc)

    def _file_fingerprint(self, path: Path) -> Dict[str, object]:
        stat = path.stat()
        return {
            "path": str(path.resolve()),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    def _write_timeline_debug(
        self,
        remotion_dir: Path,
        media_fn: str,
        kept_subs: List[srt.Subtitle],
        segments: List[Dict[str, float]],
        captions: List[Dict[str, object]],
        merge_gap_s: float,
        topics: List[Dict[str, Any]],
    ) -> None:
        cache_dir = remotion_dir / ".cache" / "render"
        cache_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(media_fn).stem
        out_path = cache_dir / f"{stem}.timeline.json"

        merged: List[Dict[str, float]] = []
        cursor = 0.0
        for seg in segments:
            start = float(seg["start"])
            end = float(seg["end"])
            merged.append(
                {
                    "start": round(start, 6),
                    "end": round(end, 6),
                    "out_start": round(cursor, 6),
                    "out_end": round(cursor + (end - start), 6),
                    "duration": round(end - start, 6),
                }
            )
            cursor += end - start

        kept_lines: List[Dict[str, object]] = []
        for sub in kept_subs:
            text = (sub.content or "").strip()
            kept_lines.append(
                {
                    "index": int(sub.index),
                    "start": round(sub.start.total_seconds(), 6),
                    "end": round(sub.end.total_seconds(), 6),
                    "duration": round(sub.end.total_seconds() - sub.start.total_seconds(), 6),
                    "text": text,
                }
            )

        payload = {
            "source": media_fn,
            "summary": {
                "kept_subtitles": len(kept_lines),
                "merged_segments": len(merged),
                "captions": len(captions),
                "topics": len(topics),
                "cut_duration": round(sum(s["duration"] for s in merged), 6),
                "cut_merge_gap": round(merge_gap_s, 6),
            },
            "kept_subtitles": kept_lines,
            "merged_segments": merged,
            "captions": captions,
            "topics": topics,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _load_video_metadata(self, media_fn: str) -> Dict[str, object]:
        cmd = [
            self._ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate,codec_name,pix_fmt,color_space,color_transfer,color_primaries:format=duration",
            "-of",
            "json",
            media_fn,
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"ffprobe failed to read video metadata: {exc.stderr.strip()}"
            ) from exc

        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            raise RuntimeError("ffprobe did not return any video streams.")

        stream = streams[0]
        width = stream.get("width")
        height = stream.get("height")
        if width is None or height is None:
            raise RuntimeError("ffprobe missing width/height in video stream.")

        fps = self._parse_rate(stream.get("avg_frame_rate")) or self._parse_rate(
            stream.get("r_frame_rate")
        )
        duration_str = (data.get("format") or {}).get("duration")
        try:
            duration = float(duration_str) if duration_str is not None else None
        except ValueError:
            duration = None

        return {
            "width": int(width),
            "height": int(height),
            "fps": float(fps) if fps else 30.0,
            "duration": duration,
            "codec_name": stream.get("codec_name"),
            "pix_fmt": stream.get("pix_fmt"),
            "color_space": stream.get("color_space"),
            "color_transfer": stream.get("color_transfer"),
            "color_primaries": stream.get("color_primaries"),
        }

    def _prepare_cut_source(self, remotion_dir: Path, media_fn: str) -> str:
        cache_dir = remotion_dir / ".cache" / "render"
        cache_dir.mkdir(parents=True, exist_ok=True)
        src = Path(media_fn).resolve()
        meta = self._load_video_metadata(media_fn)
        is_hdr = self._is_hdr_source(meta)
        standard_suffix = "std_1080p30_sdr709_hable_v2"
        source_stamp = self._file_stamp(src)
        proxy_name = f"{src.stem}_{source_stamp}.{standard_suffix}.mp4"
        proxy = cache_dir / proxy_name
        self._cleanup_render_cache_stale_files(
            cache_dir,
            src.stem,
            keep_name=proxy_name,
            marker=f".{standard_suffix}.",
        )
        if proxy.exists():
            return str(proxy)

        logging.info("Standardizing source to mp4/h264 SDR Rec.709 1080p30 for render ingest.")
        scale_pad = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
        if is_hdr:
            self._ensure_zscale_available()
            # Community-proven HDR->SDR path (HLG/PQ -> linear -> tone map -> Rec.709).
            vf = ",".join(
                [
                    "zscale=t=linear:npl=100",
                    "format=gbrpf32le",
                    "zscale=p=bt709",
                    "tonemap=tonemap=hable:desat=0",
                    "zscale=t=bt709:m=bt709:r=tv",
                    scale_pad,
                    "format=yuv420p",
                ]
            )
        else:
            vf = ",".join([scale_pad, "colorspace=all=bt709:fast=0", "format=yuv420p"])

        cmd = [
            self._ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            vf,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-movflags",
            "+faststart+write_colr",
            "-color_range",
            "tv",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            str(proxy),
        ]
        expected_duration = float(meta.get("duration") or 0.0) or None
        self._run_ffmpeg_with_stage_progress(
            cmd,
            stage="prepare_source",
            expected_duration_s=expected_duration,
        )
        return str(proxy)

    def _cleanup_render_cache_stale_files(
        self, cache_dir: Path, stem: str, *, keep_name: str, marker: str
    ) -> None:
        prefix = f"{stem}_"
        for item in cache_dir.iterdir():
            if not item.is_file():
                continue
            if item.name == keep_name:
                continue
            if item.name.startswith(prefix) and marker in item.name:
                try:
                    item.unlink()
                except OSError:
                    logging.warning("Failed to remove stale render cache file: %s", item)

    def _run_ffmpeg_with_stage_progress(
        self, cmd: List[str], *, stage: str, expected_duration_s: Optional[float] = None
    ) -> None:
        cmd_with_progress = list(cmd)
        if cmd_with_progress and "-progress" not in cmd_with_progress:
            # The output path is the final argument; inject progress flags before it.
            cmd_with_progress[-1:-1] = ["-progress", "pipe:1", "-nostats"]

        process = subprocess.Popen(
            cmd_with_progress,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        last_ratio = -1.0
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue

            key, sep, value = line.partition("=")
            if sep != "=":
                continue

            if key in {"out_time_ms", "out_time_us"}:
                if expected_duration_s is None or expected_duration_s <= 0:
                    continue
                try:
                    out_time_s = float(value) / 1_000_000.0
                except ValueError:
                    continue
                ratio = max(0.0, min(1.0, out_time_s / expected_duration_s))
                if ratio - last_ratio >= 0.01:
                    self._emit_progress(stage, ratio)
                    last_ratio = ratio
                continue

            if key == "progress" and value == "end":
                self._emit_progress(stage, 1.0)

        stderr_text = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"ffmpeg failed during {stage}: {(stderr_text or '').strip()}")

    def _retag_bt709(self, media_fn: str) -> str:
        path = Path(media_fn)
        if not path.exists():
            return media_fn

        tmp = path.with_suffix(".retag.mp4")
        cmd = [
            self._ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-movflags",
            "+faststart+write_colr",
            "-color_range",
            "tv",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            str(tmp),
        ]
        try:
            subprocess.run(cmd, check=True)
            os.replace(str(tmp), str(path))
        except subprocess.CalledProcessError as exc:
            if tmp.exists():
                tmp.unlink()
            logging.warning("Retag bt709 failed for %s: %s", media_fn, exc)
        return str(path)

    def _is_hdr_source(self, meta: Dict[str, object]) -> bool:
        transfer = str(meta.get("color_transfer") or "").lower()
        primaries = str(meta.get("color_primaries") or "").lower()
        return transfer in ("arib-std-b67", "smpte2084") or primaries == "bt2020"

    def _parse_rate(self, rate: Optional[str]) -> Optional[float]:
        if not rate or rate == "0/0":
            return None
        if "/" in rate:
            num, den = rate.split("/", 1)
            try:
                den_f = float(den)
                if den_f == 0:
                    return None
                return float(num) / den_f
            except ValueError:
                return None
        try:
            return float(rate)
        except ValueError:
            return None

    def _resolve_output(self, media_fn: str) -> str:
        if getattr(self.args, "render_output", None):
            return os.path.abspath(self.args.render_output)
        base, _ = os.path.splitext(media_fn)
        return os.path.abspath(base + "_remotion.mp4")

    def _resolve_cut_srt_output(self, source_srt: str) -> str:
        explicit = getattr(self.args, "render_cut_srt_output", None)
        if explicit:
            return os.path.abspath(explicit)
        source = Path(source_srt).resolve()
        stem = source.stem
        if stem.endswith(".optimized"):
            stem = stem[: -len(".optimized")]
        return str(source.with_name(f"{stem}.cut.srt"))

    def _resolve_fps(self, meta: Dict[str, object]) -> float:
        override = getattr(self.args, "render_fps", None)
        if override:
            return float(override)
        fps = float(meta.get("fps") or 30.0)
        if fps <= 0:
            fps = 30.0
        max_fps = 15.0 if bool(getattr(self.args, "render_preview", False)) else 30.0
        return min(fps, max_fps)

    def _resolve_dimensions(self, meta: Dict[str, object]) -> Tuple[int, int]:
        width = int(meta["width"])
        height = int(meta["height"])
        max_height = 720 if bool(getattr(self.args, "render_preview", False)) else 1080
        if height <= max_height:
            return self._ensure_even(width), self._ensure_even(height)
        scale = max_height / height
        scaled_width = int(round(width * scale))
        return self._ensure_even(scaled_width), self._ensure_even(max_height)

    def _ensure_even(self, value: int) -> int:
        if value % 2 == 0:
            return value
        return max(2, value - 1)

    def _resolve_remotion_dir(self) -> Path:
        root = _find_repo_root()
        remotion_dir = root / "remotion"
        if not remotion_dir.exists():
            raise RuntimeError(
                f"Remotion project not found at {remotion_dir}. Please ensure it exists."
            )
        return remotion_dir

    def _cleanup_stale_render_artifacts(self, remotion_dir: Path, media_fn: str) -> None:
        stem = Path(media_fn).stem
        render_dir = remotion_dir / ".cache" / "render"
        stale_kept = render_dir / f"{stem}.kept.srt"
        if stale_kept.exists():
            try:
                stale_kept.unlink()
            except OSError:
                logging.warning("Failed to remove stale artifact: %s", stale_kept)

    def _ensure_node_ready(self, remotion_dir: Path):
        if shutil.which("node") is None:
            raise RuntimeError("Node.js not found. Install Node.js to use Remotion rendering.")
        if shutil.which("npm") is None:
            raise RuntimeError("npm not found. Install Node.js/npm to use Remotion rendering.")
        if not self._ffmpeg_bin or not self._ffprobe_bin:
            raise RuntimeError("ffmpeg/ffprobe not found. Install ffmpeg to use Remotion rendering.")
        node_modules = remotion_dir / "node_modules"
        if not node_modules.exists():
            logging.info("Remotion dependencies missing; running npm install...")
            self._install_remotion_deps(remotion_dir)
            return

        if self._remotion_deps_healthy(remotion_dir):
            return

        logging.info("Remotion dependencies are incomplete/corrupted; running npm install...")
        self._install_remotion_deps(remotion_dir)

    def _remotion_deps_healthy(self, remotion_dir: Path) -> bool:
        required_files = [
            remotion_dir / "node_modules" / "@remotion" / "bundler" / "package.json",
            remotion_dir / "node_modules" / "@remotion" / "renderer" / "package.json",
            remotion_dir / "node_modules" / "remotion" / "package.json",
        ]
        if not all(path.exists() for path in required_files):
            return False

        probe_script = (
            "Promise.all(["
            "import('@remotion/bundler'),"
            "import('@remotion/renderer'),"
            "import('remotion')"
            "]).then(() => process.exit(0)).catch((e) => {"
            "console.error((e && e.message) || e);"
            "process.exit(1);"
            "});"
        )
        result = subprocess.run(
            ["node", "-e", probe_script],
            cwd=str(remotion_dir),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _install_remotion_deps(self, remotion_dir: Path) -> None:
        cmd = ["npm", "install"]
        result = subprocess.run(cmd, cwd=str(remotion_dir), capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "Failed to install Remotion dependencies with npm install: "
                f"{(result.stderr or '').strip()}"
            )
        if not self._remotion_deps_healthy(remotion_dir):
            raise RuntimeError(
                "Remotion dependencies are still invalid after npm install. "
                "Try removing remotion/node_modules and rerun."
            )

    def _prepare_public_video(self, remotion_dir: Path, media_fn: str) -> str:
        public_dir = remotion_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_public_symlinks(public_dir)

        media_path = Path(media_fn).resolve()
        stamp = self._file_stamp(media_path)
        safe_name = f"{media_path.stem}_{stamp}{media_path.suffix}"
        target = public_dir / safe_name
        self._cleanup_public_stale_files(public_dir, media_path.stem, safe_name)

        if target.exists():
            try:
                if target.is_file() and os.path.samefile(target, media_path):
                    return safe_name
            except OSError:
                pass
            target.unlink()

        shutil.copy2(media_path, target)
        return safe_name

    def _cleanup_public_symlinks(self, public_dir: Path) -> None:
        for item in public_dir.iterdir():
            if item.is_symlink():
                item.unlink()

    def _cleanup_public_stale_files(
        self, public_dir: Path, stem: str, keep_name: str
    ) -> None:
        # Remove stale copied media from previous runs to keep public/ deterministic.
        prefix = f"{stem}_"
        for item in public_dir.iterdir():
            if not item.is_file():
                continue
            if item.name == keep_name:
                continue
            if item.name.startswith(prefix):
                try:
                    item.unlink()
                except OSError:
                    logging.warning("Failed to remove stale public asset: %s", item)

    def _file_stamp(self, path: Path) -> str:
        stat = path.stat()
        payload = f"{path}-{stat.st_size}-{stat.st_mtime_ns}".encode("utf-8")
        import hashlib

        return hashlib.md5(payload).hexdigest()[:8]

    def _write_props(self, remotion_dir: Path, media_fn: str, props: Dict[str, object]) -> str:
        cache_dir = remotion_dir / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        base = Path(media_fn).stem
        props_path = cache_dir / f"{base}.props.json"
        with open(props_path, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False, indent=2)
        return str(props_path)

    def _render_with_node(self, remotion_dir: Path, props_path: str, output_fn: str):
        render_script = remotion_dir / "render.mjs"
        os.makedirs(os.path.dirname(output_fn), exist_ok=True)
        cmd = [
            "node",
            str(render_script),
            "--props",
            props_path,
            "--output",
            output_fn,
        ]
        codec = getattr(self.args, "render_codec", None)
        crf = getattr(self.args, "render_crf", None)
        if codec:
            cmd += ["--codec", str(codec)]
        if crf is not None:
            cmd += ["--crf", str(crf)]
        process = subprocess.Popen(
            cmd,
            cwd=str(remotion_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        recent_logs: List[str] = []
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            recent_logs.append(line)
            if len(recent_logs) > 40:
                recent_logs.pop(0)
            match = _NODE_RENDER_PROGRESS_RE.search(line)
            if match:
                try:
                    ratio = float(match.group(1)) / 100.0
                except ValueError:
                    continue
                self._emit_progress("node_render", ratio)
                continue
            logging.info("[remotion] %s", line)

        return_code = process.wait()
        if return_code != 0:
            tail = "\n".join(recent_logs[-20:])
            raise RuntimeError(
                f"Remotion render failed (exit={return_code}). Recent output:\n{tail}"
            )

    def _resolve_ffmpeg_bin(self) -> str:
        env_ffmpeg = os.environ.get("AUTOCUT_FFMPEG")
        if env_ffmpeg and os.path.exists(env_ffmpeg):
            return env_ffmpeg

        root = _find_repo_root()
        bundled = root / ".tools" / "ffmpeg-evermeet" / "ffmpeg"
        if bundled.exists():
            return str(bundled)

        maybe_path = shutil.which("ffmpeg")
        if maybe_path:
            return maybe_path

        return "ffmpeg"

    def _resolve_ffprobe_bin(self) -> str:
        env_ffprobe = os.environ.get("AUTOCUT_FFPROBE")
        if env_ffprobe and os.path.exists(env_ffprobe):
            return env_ffprobe

        root = _find_repo_root()
        bundled = root / ".tools" / "ffmpeg-evermeet" / "ffprobe"
        if bundled.exists():
            return str(bundled)

        maybe_path = shutil.which("ffprobe")
        if maybe_path:
            return maybe_path

        return "ffprobe"

    def _ensure_zscale_available(self) -> None:
        if self._ffmpeg_supports_filter("zscale"):
            return

        self._bootstrap_ffmpeg_evermeet()
        self._ffmpeg_bin = self._resolve_ffmpeg_bin()
        if self._ffmpeg_supports_filter("zscale"):
            return

        raise RuntimeError(
            "HDR source requires ffmpeg with zscale filter. "
            "Set AUTOCUT_FFMPEG to a build with --enable-libzimg."
        )

    def _ffmpeg_supports_filter(self, filter_name: str) -> bool:
        cmd = [self._ffmpeg_bin, "-hide_banner", "-filters"]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except Exception:
            return False
        return f" {filter_name} " in result.stdout

    def _bootstrap_ffmpeg_evermeet(self) -> None:
        root = _find_repo_root()
        tools_dir = root / ".tools" / "ffmpeg-evermeet"
        ffmpeg_bin = tools_dir / "ffmpeg"
        if ffmpeg_bin.exists():
            return

        tools_dir.mkdir(parents=True, exist_ok=True)
        url = "https://evermeet.cx/ffmpeg/getrelease/zip"
        zip_path = tools_dir / "ffmpeg.zip"
        logging.info("Downloading ffmpeg static build with zscale support from evermeet.cx")
        urllib.request.urlretrieve(url, zip_path)

        with tempfile.TemporaryDirectory() as td:
            extract_dir = Path(td)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
            extracted = extract_dir / "ffmpeg"
            if not extracted.exists():
                raise RuntimeError("Downloaded ffmpeg bundle does not contain ffmpeg binary.")
            shutil.move(str(extracted), str(ffmpeg_bin))
            ffmpeg_bin.chmod(0o755)
