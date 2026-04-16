from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .filetrans_like import (
    FiletransResult,
    FiletransSegment,
    FiletransSubmitResponse,
    FiletransTask,
)

SEGMENT_PUNCT_LIMIT = 2
HTTP_REQUEST_MAX_ATTEMPTS = 3
HTTP_RETRY_BACKOFF_SECONDS = 1.0
HTTP_RETRY_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
# Only count clause-ending/sub-clause punctuation for forced split.
# Do NOT count list separator "、".
SEGMENT_PUNCT_CHARS = set("，,。！？!?；;")


@dataclass(frozen=True)
class DashScopeFiletransConfig:
    base_url: str
    api_key: str
    model: str
    task: str | None
    poll_seconds: float
    timeout_seconds: float
    language: str | None
    language_hints: tuple[str, ...]
    text: str
    enable_itn: bool
    enable_words: bool
    channel_ids: tuple[int, ...]
    word_split_enabled: bool
    word_split_on_comma: bool
    word_split_comma_pause_s: float
    word_split_min_chars: int
    word_vad_gap_s: float
    word_max_segment_s: float


class DashScopeFiletransClient:
    def __init__(self, config: DashScopeFiletransConfig) -> None:
        self._config = config
        if not self._config.api_key:
            raise RuntimeError("DashScope API key missing for ASR.")

    @property
    def poll_seconds(self) -> float:
        return self._config.poll_seconds

    @property
    def timeout_seconds(self) -> float:
        return self._config.timeout_seconds

    def submit(
        self,
        *,
        file_url: str,
        lang: str | None,
        prompt: str,
    ) -> FiletransSubmitResponse:
        language = self._resolve_language(lang)
        legacy_language_hints = self._build_legacy_language_hints(lang)
        text = (prompt or self._config.text or "").strip()
        payload = self._build_submit_payload(
            file_url=file_url,
            language=language,
            legacy_language_hints=legacy_language_hints,
            text=text,
            use_file_urls=False,
        )
        logging.info(
            "[asr] dashscope submit start model=%s file_url_prefix=%s language=%s channel_ids=%s",
            self._config.model,
            str(file_url)[:80],
            language or legacy_language_hints,
            self._config.channel_ids,
        )
        try:
            data = self._post_json(
                "/api/v1/services/audio/asr/transcription",
                payload,
            )
        except RuntimeError as exc:
            error_text = str(exc)
            # Compatibility fallback for API variants expecting input.file_urls.
            if "InvalidParameter" not in error_text or "url" not in error_text.lower():
                raise
            fallback_payload = self._build_submit_payload(
                file_url=file_url,
                language=language,
                legacy_language_hints=legacy_language_hints,
                text=text,
                use_file_urls=True,
            )
            data = self._post_json(
                "/api/v1/services/audio/asr/transcription",
                fallback_payload,
            )
        output = data.get("output")
        if not isinstance(output, dict):
            raise RuntimeError(f"Unexpected submit response from DashScope: {data}")
        task_id = str(output.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError(f"Missing task_id in DashScope response: {data}")
        return FiletransSubmitResponse(task_id=task_id)

    def _build_submit_payload(
        self,
        *,
        file_url: str,
        language: str | None,
        legacy_language_hints: list[str],
        text: str,
        use_file_urls: bool,
    ) -> dict[str, Any]:
        input_payload: dict[str, Any]
        if use_file_urls:
            input_payload = {"file_urls": [file_url]}
        else:
            input_payload = {"file_url": file_url}

        payload: dict[str, Any] = {
            "model": self._config.model,
            "input": input_payload,
            "parameters": {},
        }
        task = (self._config.task or "").strip()
        if task:
            payload["task"] = task
        if language:
            payload["parameters"]["language"] = language
        elif legacy_language_hints:
            # Backward compatibility for legacy env names; the documented field is `language`.
            payload["parameters"]["language_hints"] = legacy_language_hints
        if text:
            payload["parameters"]["text"] = text
        payload["parameters"]["enable_itn"] = bool(self._config.enable_itn)
        payload["parameters"]["enable_words"] = bool(self._config.enable_words)
        if self._config.channel_ids:
            payload["parameters"]["channel_id"] = [int(item) for item in self._config.channel_ids]
        if not payload["parameters"]:
            payload.pop("parameters")
        return payload

    def poll(self, task_id: str) -> FiletransTask:
        logging.info("[asr] dashscope poll task_id=%s", task_id)
        data = self._get_json(f"/api/v1/tasks/{task_id}")
        output = data.get("output")
        if not isinstance(output, dict):
            return FiletransTask(task_id=task_id, task_status="RUNNING")

        status = str(output.get("task_status") or "").strip().upper() or "RUNNING"
        task_status = _normalize_status(status)
        transcription_url = _extract_transcription_url(output)
        error_message = (
            str(output.get("message") or data.get("message") or "").strip() or None
        )
        return FiletransTask(
            task_id=task_id,
            task_status=task_status,
            transcription_url=transcription_url,
            error_message=error_message,
        )

    def load_result(self, transcription_url: str) -> FiletransResult:
        logging.info("[asr] dashscope fetch result url=%s", transcription_url)
        payload = self._open_json_url(transcription_url, headers={})
        segments = self._parse_segments(payload)
        logging.info("[asr] dashscope result parsed segments=%s", len(segments))
        return FiletransResult(task_id="", segments=segments)

    def _parse_segments(self, payload: dict[str, Any]) -> list[FiletransSegment]:
        segments: list[FiletransSegment] = []
        seen = set()
        for row in _candidate_rows(payload):
            row_segments = self._segments_from_row(row)
            for seg in row_segments:
                key = (round(seg.start, 3), round(seg.end, 3), seg.text)
                if key in seen:
                    continue
                seen.add(key)
                segments.append(seg)
        segments.sort(key=lambda item: (item.start, item.end))
        return self._cleanup_segments(segments)

    def _segments_from_row(self, row: dict[str, Any]) -> list[FiletransSegment]:
        words = row.get("words")
        if (
            bool(self._config.enable_words)
            and bool(self._config.word_split_enabled)
            and isinstance(words, list)
            and words
        ):
            split_segments = self._split_by_words(words)
            if split_segments:
                return split_segments

        text = _first_text(row)
        if not text:
            return []
        start = _read_time_s(row, ("begin_time", "sentence_begin_time", "start_time"), ms=True)
        end = _read_time_s(row, ("end_time", "sentence_end_time", "stop_time"), ms=True)
        if start is None:
            start = _read_time_s(row, ("start_ms",), ms=True)
        if end is None:
            end = _read_time_s(row, ("end_ms",), ms=True)
        if start is None:
            start = _read_time_s(row, ("start", "begin"), ms=False)
        if end is None:
            end = _read_time_s(row, ("end", "stop"), ms=False)
        if start is None or end is None or end <= start:
            return []
        return [FiletransSegment(start=float(start), end=float(end), text=text)]

    def _split_by_words(self, words: list[dict[str, Any]]) -> list[FiletransSegment]:
        normalized = self._normalize_word_items(words)
        if not normalized:
            return []

        strong_punc = {"。", "！", "？", "!", "?", "；", ";"}
        # Treat list separator "、" as weaker than comma for subtitle boundary.
        comma_punc = {"，", ","}
        min_chars = max(1, int(self._config.word_split_min_chars))
        # Tune split behavior toward finer subtitle boundaries around punctuation.
        vad_gap_ms = max(800.0, float(self._config.word_vad_gap_s) * 1000.0)
        comma_pause_ms = max(300.0, float(self._config.word_split_comma_pause_s) * 1000.0)
        max_seg_ms = max(1000.0, float(self._config.word_max_segment_s) * 1000.0)
        min_seg_ms_for_comma = 500.0
        min_chars_for_comma = max(2, min_chars // 2)
        min_seg_ms_for_vad = 1600.0

        out: list[FiletransSegment] = []
        current: list[dict[str, Any]] = []

        def _flush() -> None:
            if not current:
                return
            start_ms = current[0]["begin"]
            end_ms = current[-1]["end"]
            if end_ms <= start_ms:
                current.clear()
                return
            text = self._compose_word_text(current)
            current.clear()
            if not text:
                return
            out.append(
                FiletransSegment(
                    start=float(start_ms) / 1000.0,
                    end=float(end_ms) / 1000.0,
                    text=text,
                )
            )

        for idx, item in enumerate(normalized):
            # Hard guardrail: one subtitle should not carry too many punctuation marks.
            # Flush before adding current token if it would exceed punctuation cap.
            if self._should_flush_before_append(current, item):
                _flush()
            current.append(item)

            seg_chars = sum(len(str(x["text"])) + len(str(x["punct"])) for x in current)
            seg_ms = current[-1]["end"] - current[0]["begin"]
            seg_punct_count = self._punct_count(current)
            punct = str(item["punct"] or "")
            next_item = normalized[idx + 1] if idx + 1 < len(normalized) else None
            gap_ms = (
                float(next_item["begin"] - item["end"]) if next_item is not None else 0.0
            )

            if self._should_split_segment(
                punct=punct,
                gap_ms=gap_ms,
                seg_chars=seg_chars,
                seg_ms=seg_ms,
                seg_punct_count=seg_punct_count,
                strong_punc=strong_punc,
                comma_punc=comma_punc,
                min_chars=min_chars,
                min_chars_for_comma=min_chars_for_comma,
                min_seg_ms_for_comma=min_seg_ms_for_comma,
                min_seg_ms_for_vad=min_seg_ms_for_vad,
                vad_gap_ms=vad_gap_ms,
                comma_pause_ms=comma_pause_ms,
                max_seg_ms=max_seg_ms,
            ):
                _flush()

        _flush()
        return self._merge_fragments(out)

    @staticmethod
    def _normalize_word_items(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in words:
            if not isinstance(item, dict):
                continue
            try:
                begin = float(item.get("begin_time"))
                end = float(item.get("end_time"))
            except Exception:
                continue
            text = str(item.get("text") or "")
            punctuation = str(item.get("punctuation") or "")
            if end <= begin:
                continue
            if not text and not punctuation:
                continue
            normalized.append(
                {
                    "begin": begin,
                    "end": end,
                    "text": text,
                    "punct": punctuation,
                }
            )
        return normalized

    @staticmethod
    def _punct_count(items: list[dict[str, Any]]) -> int:
        count = 0
        for item in items:
            punct = str(item.get("punct") or "")
            for ch in punct:
                if ch in SEGMENT_PUNCT_CHARS:
                    count += 1
        return count

    def _should_flush_before_append(
        self,
        current: list[dict[str, Any]],
        next_item: dict[str, Any],
    ) -> bool:
        if not current:
            return False
        next_punct = str(next_item.get("punct") or "")
        next_punct_count = sum(1 for ch in next_punct if ch in SEGMENT_PUNCT_CHARS)
        return self._punct_count(current) + next_punct_count > SEGMENT_PUNCT_LIMIT

    def _should_split_segment(
        self,
        *,
        punct: str,
        gap_ms: float,
        seg_chars: int,
        seg_ms: float,
        seg_punct_count: int,
        strong_punc: set[str],
        comma_punc: set[str],
        min_chars: int,
        min_chars_for_comma: int,
        min_seg_ms_for_comma: float,
        min_seg_ms_for_vad: float,
        vad_gap_ms: float,
        comma_pause_ms: float,
        max_seg_ms: float,
    ) -> bool:
        if self._should_split_on_strong_punctuation(punct, strong_punc):
            return True

        if self._should_split_on_comma(
            punct=punct,
            comma_punc=comma_punc,
            seg_ms=seg_ms,
            seg_chars=seg_chars,
            gap_ms=gap_ms,
            min_seg_ms_for_comma=min_seg_ms_for_comma,
            min_chars_for_comma=min_chars_for_comma,
            comma_pause_ms=comma_pause_ms,
        ):
            return True

        if self._should_split_on_vad_gap(
            gap_ms=gap_ms,
            seg_chars=seg_chars,
            seg_ms=seg_ms,
            min_chars=min_chars,
            min_seg_ms_for_vad=min_seg_ms_for_vad,
            vad_gap_ms=vad_gap_ms,
        ):
            return True

        if self._should_split_on_max_segment_guardrail(
            punct=punct,
            strong_punc=strong_punc,
            seg_ms=seg_ms,
            max_seg_ms=max_seg_ms,
        ):
            return True

        if self._should_split_on_punctuation_cap(
            punct=punct,
            comma_punc=comma_punc,
            strong_punc=strong_punc,
            seg_punct_count=seg_punct_count,
        ):
            return True

        return False

    @staticmethod
    def _should_split_on_strong_punctuation(
        punct: str,
        strong_punc: set[str],
    ) -> bool:
        return any(ch in strong_punc for ch in punct)

    def _should_split_on_comma(
        self,
        *,
        punct: str,
        comma_punc: set[str],
        seg_ms: float,
        seg_chars: int,
        gap_ms: float,
        min_seg_ms_for_comma: float,
        min_chars_for_comma: int,
        comma_pause_ms: float,
    ) -> bool:
        if not bool(self._config.word_split_on_comma):
            return False
        has_comma_punc = any(ch in comma_punc for ch in punct)
        if not has_comma_punc:
            return False
        return (
            seg_ms >= min_seg_ms_for_comma
            or seg_chars >= min_chars_for_comma
            or gap_ms >= comma_pause_ms
        )

    @staticmethod
    def _should_split_on_vad_gap(
        *,
        gap_ms: float,
        seg_chars: int,
        seg_ms: float,
        min_chars: int,
        min_seg_ms_for_vad: float,
        vad_gap_ms: float,
    ) -> bool:
        return gap_ms >= vad_gap_ms and seg_chars >= min_chars and seg_ms >= min_seg_ms_for_vad

    @staticmethod
    def _should_split_on_max_segment_guardrail(
        *,
        punct: str,
        strong_punc: set[str],
        seg_ms: float,
        max_seg_ms: float,
    ) -> bool:
        return seg_ms >= max_seg_ms and punct in strong_punc

    @staticmethod
    def _should_split_on_punctuation_cap(
        *,
        punct: str,
        comma_punc: set[str],
        strong_punc: set[str],
        seg_punct_count: int,
    ) -> bool:
        if seg_punct_count < SEGMENT_PUNCT_LIMIT:
            return False
        return punct in comma_punc.union(strong_punc)

    @staticmethod
    def _compose_word_text(items: list[dict[str, Any]]) -> str:
        output = ""
        for item in items:
            token = str(item.get("text") or "").strip()
            punct = str(item.get("punct") or "")
            if token:
                if output and _need_space_between(output[-1], token[0]):
                    output += " "
                output += token
            if punct:
                output += punct
        return output.strip()

    @staticmethod
    def _merge_fragments(segments: list[FiletransSegment]) -> list[FiletransSegment]:
        if not segments:
            return []
        return sorted(segments, key=lambda item: (item.start, item.end))

    @staticmethod
    def _cleanup_segments(segments: list[FiletransSegment]) -> list[FiletransSegment]:
        if not segments:
            return []

        # 1) Drop tiny overlapping artifacts by timing only.
        pruned: list[FiletransSegment] = []
        for idx, seg in enumerate(segments):
            duration = float(seg.end - seg.start)
            if idx + 1 < len(segments):
                next_start = float(segments[idx + 1].start)
            else:
                next_start = None
            if (
                duration <= 0.35
                and next_start is not None
                and float(seg.end) > float(next_start) + 0.02
                and abs(float(seg.start) - float(next_start)) <= 0.02
            ):
                continue
            pruned.append(seg)

        # 2) Make timeline monotonic and remove near-empty fragments.
        normalized: list[FiletransSegment] = []
        for seg in pruned:
            start = float(seg.start)
            end = float(seg.end)
            text = (seg.text or "").strip()
            if not text:
                continue
            if normalized and start < normalized[-1].end:
                # Keep continuity but avoid backwards overlap.
                start = float(normalized[-1].end)
            if end <= start + 0.05:
                continue
            normalized.append(FiletransSegment(start=start, end=end, text=text))
        return normalized

    def _resolve_language(self, lang: str | None) -> str | None:
        raw_lang = (lang or self._config.language or "").strip()
        if raw_lang:
            mapped = _map_lang_hint(raw_lang)
            return mapped or raw_lang
        legacy_hints = [item for item in self._config.language_hints if item]
        if len(legacy_hints) == 1:
            mapped = _map_lang_hint(legacy_hints[0])
            return mapped or legacy_hints[0]
        return None

    def _build_legacy_language_hints(self, lang: str | None) -> list[str]:
        hints = [item for item in self._config.language_hints if item]
        raw_lang = (lang or "").strip()
        if raw_lang:
            mapped = _map_lang_hint(raw_lang)
            if mapped and mapped not in hints:
                hints.insert(0, mapped)
        return hints

    def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
            "X-DashScope-Async": "enable",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        url = self._resolve(path)
        logging.info("[asr] dashscope http POST %s bytes=%s", url, len(body))
        return self._request_json(
            url=url,
            method="POST",
            data=body,
            headers=self._headers(extra_headers),
            stage="submit",
        )

    def _get_json(self, path: str) -> dict[str, Any]:
        url = self._resolve(path)
        logging.info("[asr] dashscope http GET %s", url)
        return self._request_json(
            url=url,
            method="GET",
            data=None,
            headers=self._headers(),
            stage="poll",
        )

    def _open_json_url(self, url: str, *, headers: dict[str, str]) -> dict[str, Any]:
        logging.info("[asr] dashscope open result url=%s", url)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise RuntimeError("DashScope transcription result URL is invalid.")
        return self._request_json(
            url=url,
            method="GET",
            data=None,
            headers=headers,
            stage="result_fetch",
        )

    def _request_json(
        self,
        *,
        url: str,
        method: str,
        data: bytes | None,
        headers: dict[str, str],
        stage: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, HTTP_REQUEST_MAX_ATTEMPTS + 1):
            req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = _read_error_text(exc)
                error = RuntimeError(f"DashScope {stage} failed: HTTP {exc.code}: {detail}")
                if attempt >= HTTP_REQUEST_MAX_ATTEMPTS or exc.code not in HTTP_RETRY_STATUS_CODES:
                    raise error from exc
                last_error = error
                _sleep_before_retry(stage, attempt, error)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                error = RuntimeError(f"DashScope {stage} failed: {exc}")
                if attempt >= HTTP_REQUEST_MAX_ATTEMPTS:
                    raise error from exc
                last_error = error
                _sleep_before_retry(stage, attempt, error)
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"DashScope {stage} failed without an error.")

    def _resolve(self, path: str) -> str:
        base = self._config.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path


def _read_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:
        body = ""
    return body.strip() or exc.reason or "unknown error"


def _sleep_before_retry(stage: str, attempt: int, error: Exception) -> None:
    delay = HTTP_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    logging.warning(
        "[asr] dashscope %s request failed attempt=%s/%s retry_in=%.1fs error=%s",
        stage,
        attempt,
        HTTP_REQUEST_MAX_ATTEMPTS,
        delay,
        error,
    )
    if delay > 0:
        time.sleep(delay)


def _normalize_status(status: str) -> str:
    if status == "SUCCEEDED":
        return "SUCCEEDED"
    if status in {"FAILED", "CANCELED", "CANCELLED"}:
        return "FAILED"
    return "RUNNING"


def _extract_transcription_url(output: dict[str, Any]) -> str | None:
    direct = _strip_non_empty_str(output.get("transcription_url"))
    if direct:
        return direct
    result = output.get("result")
    if isinstance(result, dict):
        nested = _strip_non_empty_str(result.get("transcription_url"))
        if nested:
            return nested
    results = output.get("results")
    if not isinstance(results, list):
        return None
    for item in results:
        if not isinstance(item, dict):
            continue
        value = _strip_non_empty_str(item.get("transcription_url"))
        if value:
            return value
    return None


def _candidate_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    sentences = payload.get("sentences")
    if isinstance(sentences, list):
        rows.extend(item for item in sentences if isinstance(item, dict))

    transcripts = payload.get("transcripts")
    if isinstance(transcripts, list):
        for tr in transcripts:
            if not isinstance(tr, dict):
                continue
            tr_sentences = tr.get("sentences")
            if isinstance(tr_sentences, list):
                rows.extend(item for item in tr_sentences if isinstance(item, dict))
            else:
                rows.append(tr)

    raw_segments = payload.get("segments")
    if isinstance(raw_segments, list):
        rows.extend(item for item in raw_segments if isinstance(item, dict))

    return rows


def _first_text(row: dict[str, Any]) -> str:
    for key in ("text", "transcript", "content"):
        value = _strip_non_empty_str(row.get(key))
        if value:
            return value
    return ""


def _read_time_s(row: dict[str, Any], keys: tuple[str, ...], *, ms: bool) -> float | None:
    for key in keys:
        if key not in row:
            continue
        raw = row.get(key)
        try:
            value = float(raw)
        except Exception:
            continue
        if ms:
            return value / 1000.0
        return value
    return None


def _map_lang_hint(lang: str) -> str:
    lowered = lang.strip().lower()
    mapping = {
        "chinese": "zh",
        "zh": "zh",
        "zh-cn": "zh",
        "mandarin": "zh",
        "english": "en",
        "en": "en",
        "en-us": "en",
        "cantonese": "yue",
        "yue": "yue",
    }
    return mapping.get(lowered, "")


def _need_space_between(left_char: str, right_char: str) -> bool:
    return (
        bool(left_char)
        and bool(right_char)
        and left_char.isascii()
        and right_char.isascii()
        and left_char.isalnum()
        and right_char.isalnum()
    )


def _strip_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
