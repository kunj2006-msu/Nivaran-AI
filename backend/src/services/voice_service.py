"""Voice & Audio Service for Nivaran AI.

Provides:
1. Fast speech-to-text audio transcription using Groq Whisper models (whisper-large-v3 / whisper-large-v3-turbo).
2. Natural text-to-speech (TTS) audio synthesis using gTTS.
"""

import io
import re
import logging
from typing import Union, Optional
from groq import Groq
from gtts import gTTS
from src.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None


def get_groq_client() -> Groq:
    """Initializes and returns the Groq client instance."""
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def clean_text_for_speech(text: str) -> str:
    """Cleans markdown symbols, emojis, and formatting for natural TTS audio synthesis."""
    if not text:
        return ""
    
    # Remove markdown bold/italic asterisks & underscores
    cleaned = re.sub(r'[*_#`~]', '', text)
    # Remove markdown links [title](url) -> title
    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)
    # Remove HTML tags
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    # Normalize extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def transcribe_audio(
    audio_data: Union[bytes, io.BytesIO],
    filename: str = "audio.ogg",
    language: Optional[str] = None
) -> str:
    """Transcribes audio data to text using Groq Whisper API.

    Args:
        audio_data: Raw audio bytes or BytesIO stream (.ogg, .mp3, .wav, .m4a, .webm).
        filename: Audio filename with appropriate extension (e.g. 'voice.ogg' or 'query.webm').
        language: Optional ISO-639-1 language code hint (e.g. 'en', 'gu', 'hi').

    Returns:
        Transcribed plain text string.
    """
    if isinstance(audio_data, io.BytesIO):
        raw_bytes = audio_data.getvalue()
    elif isinstance(audio_data, bytes):
        raw_bytes = audio_data
    else:
        raise ValueError("audio_data must be bytes or io.BytesIO")

    if not raw_bytes or len(raw_bytes) < 100:
        logger.warning("⚠️ Empty or extremely small audio payload received for transcription.")
        return ""

    client = get_groq_client()
    whisper_models = [
        "whisper-large-v3",
        "whisper-large-v3-turbo",
        "distil-whisper-large-v3-en"
    ]

    last_error = None
    for model_name in whisper_models:
        try:
            logger.info(f"🎙️ Transcribing audio ({len(raw_bytes)} bytes) using Groq Whisper model '{model_name}'...")
            
            kwargs = {
                "file": (filename, raw_bytes),
                "model": model_name,
                "response_format": "text",
                "temperature": 0.0,
            }
            if language:
                kwargs["language"] = language

            transcript = client.audio.transcriptions.create(**kwargs)
            transcript_text = str(transcript).strip()
            
            if transcript_text:
                logger.info(f"✅ Voice transcription successful ({model_name}): '{transcript_text[:100]}...'")
                return transcript_text

        except Exception as e:
            logger.warning(f"⚠️ Groq Whisper transcription failed with model '{model_name}': {e}")
            last_error = e

    logger.error(f"❌ All Groq Whisper transcription attempts failed: {last_error}")
    raise RuntimeError(f"Audio transcription failed: {last_error}")


def synthesize_speech(text: str, lang: str = "en") -> bytes:
    """Synthesizes given text into MP3 audio stream bytes.

    Args:
        text: Plain text or markdown response to speak.
        lang: Language code for pronunciation (default 'en').

    Returns:
        Raw MP3 audio bytes.
    """
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        clean_text = "I have processed your request."

    try:
        logger.info(f"🔊 Synthesizing speech audio for text ({len(clean_text)} chars)...")
        tts = gTTS(text=clean_text, lang=lang, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        audio_bytes = fp.read()
        logger.info(f"✅ Speech synthesis complete ({len(audio_bytes)} MP3 bytes).")
        return audio_bytes
    except Exception as e:
        logger.error(f"❌ Text-to-Speech synthesis failed: {e}")
        raise RuntimeError(f"Speech synthesis error: {e}")
