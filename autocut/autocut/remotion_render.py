import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

import srt

from . import utils
from .auto_edit import REMOVE_TOKEN
from .cut import Cutter


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

        output_fn = self._resolve_output(media_fn)
        # Render mode should always regenerate final output to stay in sync with
        # the latest optimized SRT and cut timeline.
        if os.path.exists(output_fn):
            logging.info(f"{output_fn} exists. Will overwrite it")

        remotion_dir = self._resolve_remotion_dir()
        self._ensure_node_ready(remotion_dir)
        cut_source = self._prepare_cut_source(remotion_dir, media_fn)

        kept_subs = self._load_kept_subtitles(srt_fn, self.args.encoding)
        if not kept_subs:
            raise RuntimeError("No kept subtitles found in optimized SRT.")

        filtered_srt = self._write_filtered_srt(remotion_dir, media_fn, kept_subs)
        cut_video = self._run_existing_cut(cut_source, filtered_srt)
        cut_video = self._retag_bt709(cut_video)

        captions = self._build_remapped_captions(kept_subs)
        if not captions:
            raise RuntimeError("No captions available after remapping subtitle timeline.")

        meta = self._load_video_metadata(cut_video)
        fps = self._resolve_fps(meta)
        width, height = self._resolve_dimensions(meta)
        duration_s = float(meta.get("duration") or captions[-1]["end"])
        duration_frames = max(1, int(math.ceil(duration_s * fps)))

        public_name = self._prepare_public_video(remotion_dir, cut_video)
        props = {
            "src": public_name,
            "captions": captions,
            "fps": fps,
            "width": width,
            "height": height,
            "durationInFrames": duration_frames,
        }
        props_path = self._write_props(remotion_dir, media_fn, props)

        self._render_with_node(remotion_dir, props_path, output_fn)
        output_fn = self._retag_bt709(output_fn)
        logging.info(f"Saved remotion video to {output_fn}")

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

    def _load_kept_subtitles(self, srt_fn: str, encoding: str) -> List[srt.Subtitle]:
        with open(srt_fn, encoding=encoding) as f:
            subs = list(srt.parse(f.read()))

        kept: List[srt.Subtitle] = []
        for sub in subs:
            text = (sub.content or "").strip()
            if not text:
                continue
            if text.startswith(REMOVE_TOKEN):
                continue
            if sub.end <= sub.start:
                continue
            kept.append(sub)

        kept.sort(key=lambda x: x.start)
        return kept

    def _write_filtered_srt(
        self, remotion_dir: Path, media_fn: str, kept_subs: List[srt.Subtitle]
    ) -> str:
        cache_dir = remotion_dir / ".cache" / "render"
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{Path(media_fn).stem}.kept.srt"
        with open(path, "w", encoding=self.args.encoding) as f:
            f.write(srt.compose(kept_subs))
        return str(path)

    def _run_existing_cut(self, media_fn: str, filtered_srt: str) -> str:
        cut_args = SimpleNamespace(
            inputs=[media_fn, filtered_srt],
            bitrate=self.args.bitrate,
            # Always rebuild cut clips during render to avoid stale media reuse
            # when optimized subtitles change.
            force=True,
            encoding=self.args.encoding,
        )
        Cutter(cut_args).run()

        output_fn = utils.change_ext(utils.add_cut(media_fn), "mp4")
        if not os.path.exists(output_fn):
            raise RuntimeError(f"Failed to generate cut video: {output_fn}")
        return output_fn

    def _build_remapped_captions(self, kept_subs: List[srt.Subtitle]) -> List[Dict[str, object]]:
        segments = self._build_cut_segments(kept_subs)
        captions: List[Dict[str, object]] = []

        seg_idx = 0
        eps = 1e-4
        for sub in kept_subs:
            start = sub.start.total_seconds()
            end = sub.end.total_seconds()

            while seg_idx + 1 < len(segments) and start > segments[seg_idx]["end"] + eps:
                seg_idx += 1

            seg = segments[seg_idx]
            if start < seg["start"] - eps or end > seg["end"] + eps:
                logging.warning(
                    "Subtitle %.3f-%.3f is out of cut segment %.3f-%.3f",
                    start,
                    end,
                    seg["start"],
                    seg["end"],
                )
                continue

            out_start = seg["out_start"] + (start - seg["start"])
            out_end = seg["out_start"] + (end - seg["start"])
            if out_end <= out_start:
                continue

            captions.append(
                {
                    "start": round(out_start, 3),
                    "end": round(out_end, 3),
                    "text": (sub.content or "").strip(),
                }
            )

        return captions

    def _build_cut_segments(self, kept_subs: List[srt.Subtitle]) -> List[Dict[str, float]]:
        segments: List[Dict[str, float]] = []
        for sub in kept_subs:
            start = sub.start.total_seconds()
            end = sub.end.total_seconds()
            if not segments:
                segments.append({"start": start, "end": end})
                continue

            # Keep exactly the same merge behavior as Cutter.
            if start - segments[-1]["end"] < 0.5:
                segments[-1]["end"] = end
            else:
                segments.append({"start": start, "end": end})

        cursor = 0.0
        for seg in segments:
            seg["out_start"] = cursor
            cursor += seg["end"] - seg["start"]

        return segments

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
        proxy = cache_dir / f"{src.stem}.std_1080p30_sdr709_hable_v2.mp4"
        if proxy.exists() and proxy.stat().st_mtime >= src.stat().st_mtime:
            return str(proxy)

        logging.info("Standardizing source to mp4/h264 SDR Rec.709 1080p30 before cut.")
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
        subprocess.run(cmd, check=True)
        return str(proxy)

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
        root = Path(__file__).resolve().parents[2]
        remotion_dir = root / "remotion"
        if not remotion_dir.exists():
            raise RuntimeError(
                f"Remotion project not found at {remotion_dir}. Please ensure it exists."
            )
        return remotion_dir

    def _ensure_node_ready(self, remotion_dir: Path):
        if shutil.which("node") is None:
            raise RuntimeError("Node.js not found. Install Node.js to use Remotion rendering.")
        if not self._ffmpeg_bin or not self._ffprobe_bin:
            raise RuntimeError("ffmpeg/ffprobe not found. Install ffmpeg to use Remotion rendering.")
        if not (remotion_dir / "node_modules").exists():
            raise RuntimeError(
                "Remotion dependencies not installed. Run `cd remotion && npm install` first."
            )

    def _prepare_public_video(self, remotion_dir: Path, media_fn: str) -> str:
        public_dir = remotion_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_public_symlinks(public_dir)

        media_path = Path(media_fn).resolve()
        stamp = self._file_stamp(media_path)
        safe_name = f"{media_path.stem}_{stamp}{media_path.suffix}"
        target = public_dir / safe_name

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
        subprocess.run(cmd, cwd=str(remotion_dir), check=True)

    def _resolve_ffmpeg_bin(self) -> str:
        env_ffmpeg = os.environ.get("AUTOCUT_FFMPEG")
        if env_ffmpeg and os.path.exists(env_ffmpeg):
            return env_ffmpeg

        root = Path(__file__).resolve().parents[2]
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

        root = Path(__file__).resolve().parents[2]
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
        root = Path(__file__).resolve().parents[2]
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
