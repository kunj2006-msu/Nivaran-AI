"""REST API endpoints for Voice & Audio Processing in Nivaran AI.

Provides:
- POST /api/voice/transcribe: Audio to text transcription via Groq Whisper.
- POST /api/voice/chat: Voice query processing with RAG pipeline, DB persistence, and TTS audio reply.
- POST /api/voice/tts: Text to speech MP3 audio streaming.
"""

import base64
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Response, HTTPException, status
from pydantic import BaseModel, Field

from src.services.voice_service import transcribe_audio, synthesize_speech
from src.services.chat_service import process_incoming_message, get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["Voice & Audio AI"])


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text content to synthesize into speech audio")
    lang: Optional[str] = Field("en", description="Language code (e.g., 'en', 'gu', 'hi')")


class TextVoiceChatRequest(BaseModel):
    text: str = Field(..., description="Transcribed query text")
    telegram_id: Optional[int] = Field(0, description="Optional customer or telegram user ID")
    user_name: Optional[str] = Field("Web Customer", description="Customer display name")
    email: Optional[str] = Field(None, description="Customer registered email")
    generate_audio: Optional[bool] = Field(True, description="Whether to include TTS audio in response")


@router.post("/transcribe", summary="Transcribe Audio File to Text")
async def transcribe_audio_endpoint(
    file: UploadFile = File(..., description="Audio file to transcribe (.ogg, .mp3, .wav, .m4a, .webm)"),
    language: Optional[str] = Form(None, description="Optional language hint (e.g., 'en', 'gu', 'hi')")
):
    """Transcribes an uploaded audio file using Groq Whisper API (whisper-large-v3)."""
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty audio file provided."
            )

        filename = file.filename or "recording.webm"
        transcript = transcribe_audio(audio_bytes, filename=filename, language=language)

        return {
            "status": "success",
            "filename": filename,
            "transcript": transcript,
            "bytes_received": len(audio_bytes)
        }
    except Exception as e:
        logger.error(f"❌ Error transcribing audio: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audio transcription failed: {str(e)}"
        )


@router.post("/chat", summary="Voice Chat Pipeline with RAG, Database Persistence & TTS")
async def voice_chat_endpoint(
    file: Optional[UploadFile] = File(None, description="Optional raw audio recording file"),
    text_query: Optional[str] = Form(None, description="Optional pre-transcribed text query"),
    telegram_id: Optional[int] = Form(0, description="Optional customer identifier"),
    user_name: Optional[str] = Form("Web Customer", description="Customer display name"),
    email: Optional[str] = Form(None, description="Customer email address"),
    generate_audio: Optional[bool] = Form(True, description="Generate spoken audio response")
):
    """Processes a voice or text query:
    1. Transcribes audio using Groq Whisper (if audio file provided).
    2. Logs the voice query into Supabase `chat_history` database table.
    3. Runs Nivaran AI RAG pipeline & escalation detection.
    4. Logs assistant response into Supabase database.
    5. Returns text response + Base64-encoded TTS audio for instant browser playback.
    """
    try:
        query_text = ""
        is_audio = False

        if file and file.filename:
            audio_bytes = await file.read()
            if audio_bytes and len(audio_bytes) > 0:
                filename = file.filename or "recording.webm"
                query_text = transcribe_audio(audio_bytes, filename=filename)
                is_audio = True

        if not query_text and text_query:
            query_text = text_query.strip()

        if not query_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No voice audio or text query provided."
            )

        logger.info(f"🎙️ Voice chat received query: '{query_text}' (User: {user_name}, ID: {telegram_id})")

        # Associate email if provided
        if email and telegram_id:
            get_or_create_user(telegram_id, user_name, email=email)

        # Process through RAG Pipeline & log explicitly as voice query in DB
        reply_text = process_incoming_message(
            telegram_id=telegram_id or 0,
            user_display_name=user_name or "Web Customer",
            message_text=query_text,
            is_voice=is_audio
        )

        audio_base64 = None
        if generate_audio and reply_text:
            try:
                tts_bytes = synthesize_speech(reply_text)
                audio_base64 = f"data:audio/mp3;base64,{base64.b64encode(tts_bytes).decode('utf-8')}"
            except Exception as tts_err:
                logger.warning(f"⚠️ TTS audio generation skipped: {tts_err}")

        return {
            "status": "success",
            "query": query_text,
            "response": reply_text,
            "is_voice": is_audio,
            "audio_base64": audio_base64
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing voice chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice chat processing failed: {str(e)}"
        )


@router.post("/tts", summary="Convert Text to Speech Audio Stream")
async def text_to_speech_endpoint(payload: TTSRequest):
    """Synthesizes text into an MP3 audio stream for playback."""
    try:
        audio_bytes = synthesize_speech(payload.text, lang=payload.lang or "en")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"❌ Error generating TTS: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS generation failed: {str(e)}"
        )
