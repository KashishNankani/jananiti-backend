"""
voice_processor.py
Transcribes citizen voice submissions using Groq's hosted whisper-large-v3 model.
IVRS is simulated (no real telephony) — if SARVAM_API_KEY is present we could route
through Sarvam AI's TTS/STT (https://www.sarvam.ai/apis) for better Indian-language
support, otherwise we fall back to Groq Whisper for transcription only.
"""

import os

from groq import Groq


def _get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not configured. Set it in your .env file.")
    return Groq(api_key=api_key)


def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Transcribe raw audio bytes using Groq Whisper large-v3. Returns transcript text."""
    client = _get_groq_client()
    transcription = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model="whisper-large-v3",
        response_format="json",
        temperature=0.0,
    )
    return transcription.text


def transcribe_ivrs_audio(audio_bytes: bytes, filename: str) -> str:
    """
    Simulated IVRS transcription path.
    Prefers Sarvam AI (SARVAM_API_KEY) for Indian-language STT if configured;
    falls back to Groq Whisper otherwise. No real telephony is involved —
    this just mirrors what an IVRS call's recorded segment would produce.
    """
    sarvam_key = os.getenv("SARVAM_API_KEY")
    if sarvam_key:
        try:
            import requests

            resp = requests.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": sarvam_key},
                files={"file": (filename, audio_bytes)},
                data={"model": "saarika:v2"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("transcript") or data.get("text")
            if text:
                return text
        except Exception:
            pass  # fall through to Groq Whisper

    return transcribe_audio(audio_bytes, filename)
