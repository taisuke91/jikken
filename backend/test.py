
from __future__ import annotations

import json
import logging
import os
import re
import typing
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERIAL_PORT = "COM4"
SERIAL_BAUD = 115200
SERIAL_SIMPLE = True

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
        ser.close()
        return True
    except Exception as e:
        logger.warning("Serial write failed: %s", e)
        return False