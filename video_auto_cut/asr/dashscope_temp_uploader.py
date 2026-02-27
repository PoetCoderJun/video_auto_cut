"""Upload audio to DashScope temporary OSS and get oss:// URL for ASR.

Uses Aliyun Bailian free temporary storage (48h validity). Only DashScope API key needed.
See: https://help.aliyun.com/zh/model-studio/get-temporary-file-url
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_upload_policy_for_frontend(
    *,
    api_key: str,
    base_url: str,
    model_name: str,
    file_name: str,
) -> dict[str, Any]:
    """Get DashScope getPolicy credentials for frontend POST form upload.

    Returns dict with: upload_host, policy, OSSAccessKeyId, signature, key, oss_url,
    and optional x_oss_object_acl, x_oss_forbid_overwrite.
    Frontend uses these to POST multipart form to upload_host.
    """
    policy_data = _get_upload_policy(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model_name=model_name,
    )
    upload_dir = (policy_data.get("upload_dir") or "").strip().strip("/")
    key = f"{upload_dir}/{file_name}" if upload_dir else file_name
    oss_url = f"oss://{key}"
    out: dict[str, Any] = {
        "upload_host": policy_data["upload_host"].rstrip("/"),
        "policy": policy_data["policy"],
        "OSSAccessKeyId": policy_data["oss_access_key_id"],
        "signature": policy_data["signature"],
        "key": key,
        "oss_url": oss_url,
    }
    if policy_data.get("x_oss_object_acl") is not None:
        out["x_oss_object_acl"] = str(policy_data["x_oss_object_acl"])
    if policy_data.get("x_oss_forbid_overwrite") is not None:
        out["x_oss_forbid_overwrite"] = str(policy_data["x_oss_forbid_overwrite"])
    return out


def upload_to_dashscope_temp(
    *,
    api_key: str,
    base_url: str,
    model_name: str,
    file_path: Path,
) -> str:
    """Upload local file to DashScope temporary OSS, return oss:// URL.

    Args:
        api_key: DashScope API key.
        base_url: DashScope base URL (e.g. https://dashscope.aliyuncs.com).
        model_name: ASR model name (e.g. qwen3-asr-flash-filetrans).
        file_path: Local audio file path.

    Returns:
        oss:// URL for use in ASR submit (requires X-DashScope-OssResourceResolve: enable).
    """
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"audio file not found: {path}")

    policy_data = _get_upload_policy(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model_name=model_name,
    )
    oss_url = _upload_file_to_temp_oss(policy_data, path)
    logger.info("[asr] dashscope temp upload done: %s", oss_url)
    return oss_url


def _get_upload_policy(
    *,
    api_key: str,
    base_url: str,
    model_name: str,
) -> dict[str, Any]:
    url = f"{base_url}/api/v1/uploads?action=getPolicy&model={model_name}"
    req = urllib.request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(
            f"DashScope getPolicy failed: HTTP {exc.code}: {body.strip()[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DashScope getPolicy failed: {exc}") from exc

    data_obj = data.get("data")
    if not isinstance(data_obj, dict):
        raise RuntimeError(f"Unexpected getPolicy response: {data}")

    required = ("upload_host", "upload_dir", "oss_access_key_id", "signature", "policy")
    for key in required:
        if key not in data_obj:
            raise RuntimeError(f"getPolicy missing field: {key}")

    return data_obj


def _upload_file_to_temp_oss(policy_data: dict[str, Any], file_path: Path) -> str:
    upload_host = policy_data["upload_host"].rstrip("/")
    upload_dir = (policy_data.get("upload_dir") or "").strip().strip("/")
    file_name = file_path.name
    key = f"{upload_dir}/{file_name}" if upload_dir else file_name

    with open(file_path, "rb") as f:
        file_content = f.read()

    boundary = "----FormBoundary" + "x" * 16
    body_parts: list[bytes] = []

    def _append_field(name: str, value: str) -> None:
        body_parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )

    _append_field("OSSAccessKeyId", policy_data["oss_access_key_id"])
    _append_field("Signature", policy_data["signature"])
    _append_field("policy", policy_data["policy"])
    _append_field("key", key)
    _append_field("success_action_status", "200")
    if policy_data.get("x_oss_object_acl") is not None:
        _append_field("x-oss-object-acl", str(policy_data["x_oss_object_acl"]))
    if policy_data.get("x_oss_forbid_overwrite") is not None:
        _append_field("x-oss-forbid-overwrite", str(policy_data["x_oss_forbid_overwrite"]))

    body_parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    body_parts.append(file_content)
    body_parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(body_parts)

    req = urllib.request.Request(
        url=upload_host,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Temp OSS upload failed: HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(
            f"Temp OSS upload failed: HTTP {exc.code}: {body.strip()[:300]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Temp OSS upload failed: {exc}") from exc

    return f"oss://{key}"
