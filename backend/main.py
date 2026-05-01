"""
Flame / outrage state API (Gemini returns score ∈ {-1..3}; score=-1 resets state to 0, else current+score clamped to {0..3} for MCU).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from typing_extensions import TypedDict

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.generativeai.types import HarmBlockThreshold, HarmCategory
from pydantic import BaseModel, Field

from prompts import SYSTEM_INSTRUCTION

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SERIAL_PORT = os.getenv("SERIAL_PORT", "").strip()
SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", "115200"))
SERIAL_SIMPLE = os.getenv("SERIAL_SIMPLE", "").lower() in ("1", "true", "yes")


class FlameScoreDict(TypedDict):
    score: int


class FlameStateResponse(BaseModel):
    """score: LLM judgment this turn; state after apply (score==-1 ⇒ 0; else clamp(current+score))."""

    score: int = Field(..., ge=-1, le=3)
    state: int = Field(..., ge=0, le=3)
    label: str = Field(...)
    raw_json: dict[str, Any] | None = None


LABELS_JA = [
    (0, "平常"),
    (1, "ちょい刺激"),
    (2, "かなりヤバい"),
    (3, "限界寸前"),
]


def state_to_label(state: int) -> str:
    for s, label in LABELS_JA:
        if state <= s:
            return label
    return LABELS_JA[-1][1]


# Running accumulator for serial / UI (resets only on process restart).
_mcu_state: int = 0


def get_mcu_state() -> int:
    return _mcu_state


def apply_llm_score_to_state(current: int, llm_score: int) -> int:
    """LLM score: -1 forces state to 0; nonnegative scores add then clamp to 0..3."""
    if llm_score == -1:
        return 0
    return max(0, min(3, current + llm_score))


def _safety_unblock_all():
    return {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }


_serial = None


def get_serial():
    global _serial
    if not SERIAL_PORT:
        return None
    if _serial is not None and _serial.is_open:
        return _serial
    try:
        import serial
        _serial = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.2)
        logger.info("Serial opened %s @ %s", SERIAL_PORT, SERIAL_BAUD)
        return _serial
    except Exception as e:
        logger.warning("Serial open failed: %s", e)
        return None


def send_state_to_mcu(state: int) -> bool:
    """Send accumulated level 0–3 to MCU. Returns True if written."""
    state = max(0, min(3, state))
    ser = get_serial()
    if not ser:
        return False
    if SERIAL_SIMPLE:
        line = f"FLAME {state}\n"
        payload = line.encode("ascii")
    else:
        line = json.dumps({"type": "flame", "state": state}, ensure_ascii=False) + "\n"
        payload = line.encode("utf-8")
    try:
        ser.write(payload)
        ser.flush()
        return True
    except Exception as e:
        logger.warning("Serial write failed: %s", e)
        return False


def configure_genai() -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set (see .env.example)")
    genai.configure(api_key=GEMINI_API_KEY)


def extract_score_from_text(text: str) -> int | None:
    """Recover score ∈ {-1..3} from malformed model text."""
    t = text.strip()
    if re.search(r"(?<![\d-])-1(?!\d)", t):
        return -1
    m = re.search(r"(?<!\d)([0-3])(?!\d)", t)
    if m:
        return int(m.group(1))
    return None


def parse_score_with_gemini(*, transcript: str | None, audio_bytes: bytes | None, mime_type: str) -> tuple[int, dict[str, Any]]:
    configure_genai()
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        safety_settings=_safety_unblock_all(),
    )

    user_parts: list[Any] = []
    if audio_bytes:
        user_parts.append("Classify this audio into score (-1..3). Return only the JSON schema.")
        user_parts.append({"mime_type": mime_type, "data": audio_bytes})
    if transcript:
        if audio_bytes:
            user_parts.append(
                "Optional transcript (prefer audio if they disagree):\n" + transcript.strip()
            )
        else:
            user_parts.append(
                "Classify this utterance into score (-1..3). Return only the JSON schema.\n\n"
                + transcript.strip()
            )

    if not user_parts:
        raise ValueError("audio or transcript required")

    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=FlameScoreDict,
        temperature=0.2,
    )

    ab_len = len(audio_bytes) if audio_bytes else 0
    try:
        response = model.generate_content(user_parts, generation_config=generation_config)
    except Exception as e:
        logger.warning(
            "Gemini generate_content failed: %s (model=%s mime=%r audio_len=%d has_transcript=%s)",
            e,
            GEMINI_MODEL,
            mime_type,
            ab_len,
            bool(transcript and transcript.strip()),
        )
        raise

    raw_text = (response.text or "").strip()
    try:
        data = json.loads(raw_text)
        d = int(data["score"])
    except Exception:
        d_maybe = extract_score_from_text(raw_text)
        data = {"score": d_maybe} if d_maybe is not None else {}
        if d_maybe is None:
            raise HTTPException(
                status_code=502,
                detail=f"Bad model output: {raw_text[:500]}",
            )
        d = d_maybe

    d = max(-1, min(3, d))
    return d, data if isinstance(data, dict) else {"score": d}


BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIST = os.path.join(BASE_DIR, "..", "frontend", "dist")

app = FastAPI(title="Flame state API")


@app.middleware("http")
async def disable_asset_cache_for_dev(request: Request, call_next):
    """Avoid stale CSS/JS when iterating on frontend/dist (Safari caches aggressively)."""
    response = await call_next(request)
    path = request.url.path
    ext = path.rsplit(".", 1)[-1] if "." in path.split("/")[-1] else ""
    if path.startswith("/assets/") and ext in ("css", "js"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif path == "/" or path == "/index.html":
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST), name="assets")


@app.get("/")
def index():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="frontend/dist/index.html not found")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model": GEMINI_MODEL,
        "serial_configured": bool(SERIAL_PORT),
        "serial_simple": SERIAL_SIMPLE,
        "accumulator_state": get_mcu_state(),
    }


class McuPushBody(BaseModel):
    state: int = Field(..., ge=0, le=3)


class McuPushResponse(BaseModel):
    ok: bool = True
    state: int
    label: str
    serial_write_ok: bool
    serial_configured: bool


class ScoreTextBody(BaseModel):
    transcript: str = Field(..., min_length=1)


def apply_turn(llm_score: int, raw_json: dict[str, Any] | None) -> FlameStateResponse:
    """Apply LLM score (-1 ⇒ reset to 0; else accumulate), push resulting state to MCU."""
    global _mcu_state
    _mcu_state = apply_llm_score_to_state(_mcu_state, llm_score)
    send_state_to_mcu(_mcu_state)
    return FlameStateResponse(
        score=llm_score,
        state=_mcu_state,
        label=state_to_label(_mcu_state),
        raw_json=raw_json,
    )


@app.post("/api/mcu-push", response_model=McuPushResponse)
def mcu_push(body: McuPushBody):
    """Gemini なし。指定の状態 0–3 を蓄積変数にセットしてシリアル送信（配線テスト用）。"""
    global _mcu_state
    _mcu_state = max(0, min(3, body.state))
    written = send_state_to_mcu(_mcu_state)
    return McuPushResponse(
        state=_mcu_state,
        label=state_to_label(_mcu_state),
        serial_write_ok=written,
        serial_configured=bool(SERIAL_PORT),
    )


@app.post("/api/score-text", response_model=FlameStateResponse)
def score_text(body: ScoreTextBody):
    try:
        llm_score, raw = parse_score_with_gemini(
            transcript=body.transcript, audio_bytes=None, mime_type="text/plain"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("score_text failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return apply_turn(llm_score, raw)


@app.post("/api/score-audio", response_model=FlameStateResponse)
async def score_audio(
    file: UploadFile = File(...),
    transcript: str | None = Form(None),
):
    mime = file.content_type or "audio/webm"
    try:
        audio_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"read failed: {e}") from e
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="empty file")

    logger.info(
        "score_audio: received file=%r size=%d bytes mime=%r transcript_chars=%d gemini_key_set=%s",
        file.filename,
        len(audio_bytes),
        mime,
        len(transcript) if transcript else 0,
        bool(GEMINI_API_KEY),
    )

    try:
        llm_score, raw = parse_score_with_gemini(
            transcript=transcript,
            audio_bytes=audio_bytes,
            mime_type=mime,
        )
    except HTTPException as e:
        logger.warning("score_audio: HTTP %s: %s", e.status_code, e.detail)
        raise
    except Exception as e:
        logger.exception("score_audio failed (size=%d mime=%r)", len(audio_bytes), mime)
        raise HTTPException(status_code=500, detail=str(e)) from e
    return apply_turn(llm_score, raw)
