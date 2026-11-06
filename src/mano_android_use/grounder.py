"""GUI Grounder: gui-plus + glm-4.6v-flash via OpenAI-compatible chat.completions."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mano.action_codec import parse_tool_call
from mano.errors import ManoError, ManoNetworkError
from mano.gui_plus_client import GuiVLM, endpoint_from_base
from mano.media import image_data_url
# Production-supported model ids (configurable).

SUPPORTED_MODELS = (
    "gui-plus",
    "gui-plus-2026-02-26",
    "glm-4.6v-flash",
    "glm-4.6v-flashx",
)

DEFAULT_MODEL = "gui-plus-2026-02-26"
DEFAULT_DASHSCOPE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_ZHIPU = "https://open.bigmodel.cn/api/paas/v4"

SYSTEM_GUI_PLUS = (
    "You are a mobile GUI agent. Look at the screenshot and return exactly one "
    "<tool_call>{\"name\":\"mobile_use\",\"arguments\":{...}}</tool_call> JSON. "
    "click arguments must look like {\"action\":\"click\",\"coordinate\":[x,y]} "
    "with normalized coordinates in 0..1000."
)

SYSTEM_GLM = (
    "You are a mobile GUI grounding model. Given a screenshot and an instruction, "
    "output ONE JSON object and nothing else — no markdown, no commentary, no trailing commas.\n"
    "Allowed shapes:\n"
    '{"action":"click","coordinate":[x,y]}  // x,y normalized 0..1000\n'
    '{"action":"click","bbox":[xmin,ymin,xmax,ymax]}  // normalized 0..1000\n'
    '{"action":"type","text":"..."}\n'
    '{"action":"swipe","coordinate":[x1,y1],"coordinate2":[x2,y2]}\n'
    '{"action":"system_button","button":"BACK"}\n'
    '{"action":"terminate","status":"success"}'
)


@dataclass
class GrounderResult:
    ok: bool
    model: str
    action: dict[str, Any] | None
    raw: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "action": self.action,
            "raw": self.raw[:2000],
            "error": self.error,
        }


def resolve_endpoint(model: str) -> tuple[str, str]:
    """Return (base_url, api_key) for the model family.

    Both providers can live in ``.env`` at once:
    - DashScope / gui-plus: ``DASHSCOPE_API_KEY`` (or ``MAU_DASHSCOPE_API_KEY``)
    - Zhipu / glm-*: ``ZHIPU_API_KEY`` (or ``MAU_ZHIPU_API_KEY`` / ``BIGMODEL_API_KEY``)
    Optional override: ``MAU_GROUNDER_API_KEY`` + ``MAU_GROUNDER_BASE_URL`` apply only when
    they match the selected family (or when family-specific keys are absent).
    """
    model = model.strip()
    generic_key = os.getenv("MAU_GROUNDER_API_KEY", "").strip()
    generic_base = os.getenv("MAU_GROUNDER_BASE_URL", "").strip()

    if model.startswith("glm-"):
        key = (
            os.getenv("MAU_ZHIPU_API_KEY", "").strip()
            or os.getenv("ZHIPU_API_KEY", "").strip()
            or os.getenv("BIGMODEL_API_KEY", "").strip()
            or generic_key
        )
        base = (
            os.getenv("MAU_ZHIPU_BASE_URL", "").strip()
            or (
                generic_base
                if "bigmodel" in generic_base or "zhipu" in generic_base
                else ""
            )
            or DEFAULT_ZHIPU
        )
        return base, key

    key = (
        os.getenv("MAU_DASHSCOPE_API_KEY", "").strip()
        or os.getenv("DASHSCOPE_API_KEY", "").strip()
        or os.getenv("MANO_API_KEY", "").strip()
        or generic_key
    )
    base = (
        os.getenv("MAU_DASHSCOPE_BASE_URL", "").strip()
        or os.getenv("MANO_BASE_URL", "").strip()
        or (
            generic_base
            if "dashscope" in generic_base or "aliyun" in generic_base or "maas.aliyun" in generic_base
            else ""
        )
        or DEFAULT_DASHSCOPE
    )
    return base, key


class Grounder:
    """Thin multi-backend wrapper; normalizes actions to mano action dicts."""

    def __init__(self, model: str | None = None) -> None:
        self.model = (model or os.getenv("MAU_GROUNDER_MODEL") or os.getenv("MANO_MODEL") or DEFAULT_MODEL).strip()
        base, key = resolve_endpoint(self.model)
        if not key:
            raise ManoError(
                "No grounder API key: set MAU_GROUNDER_API_KEY (or MANO_API_KEY / "
                "DASHSCOPE_API_KEY / ZHIPU_API_KEY)"
            )
        # Reuse mano GuiVLM transport; override fields for multi-provider.
        os.environ.setdefault("MANO_API_KEY", key)
        self._client = GuiVLM()
        self._client.api_key = key
        self._client.model = self.model
        self._client.endpoint = endpoint_from_base(base)

    def propose(self, image: Path, instruction: str) -> GrounderResult:
        image = Path(image)
        if not image.is_file():
            return GrounderResult(False, self.model, None, "", f"missing image: {image}")
        try:
            if self.model.startswith("gui-plus"):
                raw, action = self._propose_gui_plus(image, instruction)
                return GrounderResult(True, self.model, action, raw)
            raw, action = self._propose_glm_style(image, instruction)
            return GrounderResult(True, self.model, action, raw)
        except ManoError as exc:
            return GrounderResult(False, self.model, None, "", str(exc)[:800])

    def _propose_gui_plus(self, image: Path, instruction: str) -> tuple[str, dict[str, Any]]:
        """Like mano.runner.propose_action but parse via normalize_action.

        gui-plus sometimes omits the opening ``<tool_call>`` tag while still
        returning valid mobile_use JSON + ``</tool_call>``. Large MuMu
        screenshots are downscaled to reduce truncated completions.
        """
        prepared = _prepare_image_for_vlm(image)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_GUI_PLUS},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": image_data_url(prepared)}},
                ],
            },
        ]
        last_err: Exception | None = None
        text = ""
        for attempt in range(3):
            try:
                response = self._client.complete(messages, max_tokens=900)
            except ManoError as exc:
                last_err = exc
                if attempt < 2 and isinstance(exc, ManoNetworkError):
                    self._client.retries += 1
                    time.sleep(2**attempt)
                    continue
                raise
            text = self._client.content(response)
            try:
                return text, normalize_action(text)
            except ManoError as exc:
                last_err = exc
                if attempt == 2:
                    break
                messages.extend(
                    [
                        {"role": "assistant", "content": text},
                        {
                            "role": "user",
                            "content": (
                                f"Parse error: {str(exc)[:500]}. "
                                "Return exactly one corrected "
                                '<tool_call>{"name":"mobile_use","arguments":{...}}</tool_call>.'
                            ),
                        },
                    ]
                )
                self._client.retries += 1
        raise ManoError(f"VLM returned an unparseable action 3 times in a row: {last_err}")

    def _propose_glm_style(self, image: Path, instruction: str) -> tuple[str, dict[str, Any]]:
        # Zhipu free VL often rejects Aliyun-only fields / very large PNG payloads
        # (Broken pipe). Downscale + lean OpenAI-compatible body.
        prepared = _prepare_image_for_vlm(image)
        data_url = image_data_url(prepared) if prepared.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else (
            "data:image/png;base64," + base64.b64encode(prepared.read_bytes()).decode("ascii")
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_GLM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": instruction},
                ],
            },
        ]
        last_err: Exception | None = None
        text = ""
        for _ in range(3):
            response = self._zhipu_complete(messages, max_tokens=700)
            text = GuiVLM.content(response)
            try:
                return text, normalize_action(text)
            except ManoError as exc:
                last_err = exc
                messages.extend(
                    [
                        {"role": "assistant", "content": text},
                        {
                            "role": "user",
                            "content": (
                                f"Parse error: {exc}. Return one corrected JSON action only."
                            ),
                        },
                    ]
                )
                self._client.retries += 1
        raise ManoError(f"grounder unparseable: {last_err}; last={text[:500]}")

    def _zhipu_complete(self, messages: list[dict[str, Any]], max_tokens: int = 700) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.01,
            "max_tokens": max_tokens,
            "stream": False,
            # Official GLM-4.6V docs use thinking; disable for faster/cheaper grounding.
            "thinking": {"type": "disabled"},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._client.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self._client.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_http: urllib.error.HTTPError | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                last_http = exc
                # 429 / 平台“访问量过大”：退避重试（免费 flash 常见）。
                if exc.code == 429 and attempt < 3:
                    self._client.retries += 1
                    time.sleep(2 ** attempt * 3)  # 3s, 6s, 12s
                    # Rebuild request (body already on request.full_url/data)
                    request = urllib.request.Request(
                        self._client.endpoint,
                        data=body,
                        headers={
                            "Authorization": f"Bearer {self._client.api_key}",
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    continue
                raise ManoError(f"Zhipu HTTP {exc.code}: {err_body[:1200]}") from exc
            except urllib.error.URLError as exc:
                raise ManoNetworkError(f"network error calling Zhipu VLM: {exc}") from exc
        else:
            raise ManoError(f"Zhipu HTTP {getattr(last_http, 'code', '?')}: retries exhausted")
        self._client.call_count += 1
        usage = result.get("usage") or {}
        self._client.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self._client.completion_tokens += int(usage.get("completion_tokens") or 0)
        return result


def _prepare_image_for_vlm(image: Path, *, max_edge: int = 1280) -> Path:
    """Downscale large screenshots to reduce payload / truncated-completion failures."""
    image = Path(image)
    if image.stat().st_size < 900_000:
        return image
    sips = shutil.which("sips")
    if not sips:
        return image
    tmp = Path(tempfile.mkdtemp(prefix="mau-vlm-")) / f"resized{image.suffix or '.png'}"
    try:
        subprocess.run(
            [sips, "-Z", str(max_edge), str(image), "--out", str(tmp)],
            check=True,
            capture_output=True,
        )
        if tmp.is_file() and tmp.stat().st_size > 0:
            return tmp
    except (subprocess.CalledProcessError, OSError):
        return image
    return image


# Back-compat alias for older imports/tests.
_prepare_image_for_zhipu = _prepare_image_for_vlm


_JSON_RE = re.compile(r"\{.*\}", re.S)
_BBOX_RE = re.compile(
    r"\[\[\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]\]"
)


def _loads_action_json(raw: str) -> dict[str, Any]:
    """Parse model JSON; tolerate trailing commas and truncated closers."""
    cleaned = raw.strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(cleaned)
        if repaired is None:
            raise
        return json.loads(repaired)


def _repair_truncated_json(raw: str) -> str | None:
    """Close missing ``]`` / ``}`` when the model cuts mid-object.

    Example: ``{"action":"click","coordinate": [387, 909]`` → append ``]}``.
    """
    s = raw.rstrip()
    if not s.startswith("{"):
        # Keep only from the first object start if present.
        idx = s.find("{")
        if idx < 0:
            return None
        s = s[idx:]
    open_braces = s.count("{") - s.count("}")
    open_brackets = s.count("[") - s.count("]")
    if open_braces < 0 or open_brackets < 0:
        return None
    if open_braces == 0 and open_brackets == 0:
        return None
    candidate = s + ("]" * open_brackets) + ("}" * open_braces)
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return candidate


def _iter_json_objects(text: str) -> list[str]:
    """Yield top-level `{...}` slices (supports one level of nesting)."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[i : j + 1])
                    i = j + 1
                    break
        else:
            break
    return out


def normalize_action(text: str) -> dict[str, Any]:
    """Normalize gui-plus tool_call or GLM JSON / bbox into mano action dict."""
    text = text.strip()
    # Models sometimes emit JSON + closing tag without the opening <tool_call>.
    if "</tool_call>" in text and "<tool_call>" not in text:
        text = "<tool_call>" + text
    # Prefer mano tool_call if present.
    if "<tool_call>" in text:
        try:
            return parse_tool_call(text)
        except ManoError:
            # Fall through: strip tags and parse JSON envelope.
            text = re.sub(r"</?tool_call>", "", text).strip()

    # Fenced json
    if "```" in text:
        text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()

    # Nested envelopes e.g. {"name":"mobile_use","arguments":{"action":...}}
    for candidate in _iter_json_objects(text):
        if "action" not in candidate and "arguments" not in candidate:
            continue
        try:
            obj = _loads_action_json(candidate)
        except json.JSONDecodeError:
            continue
        try:
            return _from_obj(obj)
        except ManoError:
            continue

    # Truncated object without a closing brace (not yielded by _iter_json_objects).
    if "{" in text and "action" in text:
        try:
            obj = _loads_action_json(text[text.find("{") :])
            return _from_obj(obj)
        except (json.JSONDecodeError, ManoError):
            pass

    match = _JSON_RE.search(text)
    if match:
        try:
            obj = _loads_action_json(match.group(0))
        except json.JSONDecodeError as exc:
            raise ManoError(f"invalid action JSON: {exc}") from exc
        return _from_obj(obj)

    # Last-resort: pull a click coordinate even from a chopped string.
    coord = re.search(
        r'"action"\s*:\s*"click".*?"coordinate"\s*:\s*\[\s*([0-9.]+)\s*,\s*([0-9.]+)',
        text,
        re.S,
    )
    if coord:
        return {
            "action": "click",
            "coordinate": [float(coord.group(1)), float(coord.group(2))],
        }

    bbox = _BBOX_RE.search(text)
    if bbox:
        xmin, ymin, xmax, ymax = (float(bbox.group(i)) for i in range(1, 5))
        # Heuristic: values in 0..1 → scale to 0..1000; else assume already 0..1000 or pixels later.
        if max(xmin, ymin, xmax, ymax) <= 1.0:
            xmin, ymin, xmax, ymax = (v * 1000 for v in (xmin, ymin, xmax, ymax))
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        return {"action": "click", "coordinate": [cx, cy]}

    raise ManoError(f"no action JSON in grounder output: {text[:500]}")


def _from_obj(obj: dict[str, Any]) -> dict[str, Any]:
    if "arguments" in obj and isinstance(obj["arguments"], dict):
        obj = obj["arguments"]
    if "name" in obj and obj.get("name") == "mobile_use" and isinstance(obj.get("arguments"), dict):
        obj = obj["arguments"]

    action = dict(obj)
    if "bbox" in action and "coordinate" not in action:
        bbox = action.pop("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            raise ManoError(f"bad bbox: {bbox!r}")
        xmin, ymin, xmax, ymax = map(float, bbox)
        if max(xmin, ymin, xmax, ymax) <= 1.0:
            xmin, ymin, xmax, ymax = (v * 1000 for v in (xmin, ymin, xmax, ymax))
        action["action"] = action.get("action") or "click"
        action["coordinate"] = [(xmin + xmax) / 2, (ymin + ymax) / 2]
    if "action" not in action:
        raise ManoError(f"action missing in {action!r}")
    return action


def pixel_from_normalized(action: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    """Convert normalized 0..1000 coords to pixel ints for DeviceSession.tap/swipe."""
    from mano.action_codec import int_coord

    out = dict(action)
    kind = out.get("action")
    if kind == "click" and "coordinate" in out:
        x, y = int_coord(out["coordinate"], width, height)
        out["pixel"] = [x, y]
    if kind == "swipe" and "coordinate" in out:
        # gui-plus sometimes emits end point as coordinate2, sometimes as offset.
        end = out.get("coordinate2") or out.get("offset")
        if end is not None:
            x1, y1 = int_coord(out["coordinate"], width, height)
            x2, y2 = int_coord(end, width, height)
            out["pixel"] = [x1, y1]
            out["pixel2"] = [x2, y2]
    return out
