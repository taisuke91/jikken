"""
Flame / outrage score API (Gemini + JSON schema)
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
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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


class FlameScoreResponse(BaseModel):
    score: int = Field(..., ge=1, le=10)
    label: str = Field(...)
    raw_json: dict[str, Any] | None = None


LABELS_JA = [
    (1, "聖人モード"),
    (2, "ほぼ無害"),
    (3, "幾何数理工学の期末試験レベル"),
    (4, "ツッコミ待ち"),
    (5, "火種注意"),
    (6, "煽り気味"),
    (7, "かなり危険"),
    (8, "秒で炎上"),
    (9, "伝説の暴言"),
    (10, "規約抵触ギリギリ"),
]


def score_to_label(score: int) -> str:
    for s, label in LABELS_JA:
        if score <= s:
            return label
    return LABELS_JA[-1][1]


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


def send_score_to_mcu(score: int) -> bool:
    """Returns True if data was written to serial, False if skipped or failed."""
    ser = get_serial()
    if not ser:
        return False
    if SERIAL_SIMPLE:
        line = f"FLAME {score}\n"
        payload = line.encode("ascii")
    else:
        line = json.dumps({"type": "flame", "score": score}, ensure_ascii=False) + "\n"
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


# GeminiがJSONを返せなかった時に、テキストからスコアを抽出
def extract_score_from_text(text: str) -> int | None:
    m = re.search(r"(?<![0-9])([1-9]|10)(?![0-9])", text.strip())
    if m:
        return int(m.group(1))
    return None


# Geminiを使ってスコアを判定
def score_with_gemini(*, transcript: str | None, audio_bytes: bytes | None, mime_type: str) -> FlameScoreResponse:
    configure_genai()
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        safety_settings=_safety_unblock_all(),
    )

    user_parts: list[Any] = []
    if audio_bytes:
        user_parts.append("Score the speech in this audio. Return only the JSON schema.")
        user_parts.append({"mime_type": mime_type, "data": audio_bytes})
    if transcript:
        if audio_bytes:
            user_parts.append(
                "Optional transcript (prefer audio if they disagree):\n" + transcript.strip()
            )
        else:
            user_parts.append(
                "Score this utterance. Return only the JSON schema.\n\n" + transcript.strip()
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
        s = int(data["score"])
    except Exception:
        s_maybe = extract_score_from_text(raw_text)
        data = {"score": s_maybe} if s_maybe is not None else {}
        if s_maybe is None:
            raise HTTPException(
                status_code=502,
                detail=f"Bad model output: {raw_text[:500]}",
            )
        s = s_maybe

    s = max(1, min(10, s))
    return FlameScoreResponse(score=s, label=score_to_label(s), raw_json=data if isinstance(data, dict) else None)


BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIST = os.path.join(BASE_DIR, "..", "frontend", "dist")

app = FastAPI(title="Flame score API")

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
    }


class McuPushBody(BaseModel):
    score: int = Field(..., ge=1, le=10)


class McuPushResponse(BaseModel):
    ok: bool = True
    score: int
    label: str
    serial_write_ok: bool
    serial_configured: bool


class ScoreTextBody(BaseModel):
    transcript: str = Field(..., min_length=1)


@app.post("/api/mcu-push", response_model=McuPushResponse)
def mcu_push(body: McuPushBody):
    """Gemini を使わず、指定スコアだけをシリアル送信（配線・Arduino テスト用）。"""
    s = body.score
    written = send_score_to_mcu(s)
    return McuPushResponse(
        score=s,
        label=score_to_label(s),
        serial_write_ok=written,
        serial_configured=bool(SERIAL_PORT),
    )


@app.post("/api/score-text", response_model=FlameScoreResponse)
def score_text(body: ScoreTextBody):
    try:
        out = score_with_gemini(transcript=body.transcript, audio_bytes=None, mime_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("score_text failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    send_score_to_mcu(out.score)
    return out


@app.post("/api/score-audio", response_model=FlameScoreResponse)
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
        out = score_with_gemini(
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
    send_score_to_mcu(out.score)
    return out
