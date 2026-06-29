import os
from typing import Optional
from fastapi import HTTPException, status
from google.cloud import speech
from google.cloud import translate_v2 as translate
from google.cloud import texttospeech

def transcribe_audio(audio_content: bytes, explicit_language: Optional[str] = None) -> dict:
    """
    Calls Google Cloud Speech-to-Text API to transcribe the provided audio content.
    """
    try:
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_content)
        
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code=explicit_language or "en-IN",
            alternative_language_codes=["hi-IN", "ta-IN", "te-IN", "mr-IN", "en-US"] if not explicit_language else [],
            enable_automatic_punctuation=True,
        )
        
        response = client.recognize(config=config, audio=audio)
        if not response.results:
            return {"transcribed_text": "", "confidence_score": 0.0, "detected_language_code": explicit_language or "unknown"}
        
        result = response.results[0]
        alternative = result.alternatives[0]
        detected_lang = getattr(result, "language_code", explicit_language or "unknown")
        
        return {
            "transcribed_text": alternative.transcript,
            "confidence_score": alternative.confidence,
            "detected_language_code": detected_lang
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech-to-Text API call failed: {str(e)}"
        )

def translate_text(text: str, target_language: str = "en", source_language: Optional[str] = None) -> dict:
    """
    Translates input text into the target language using Google Cloud Translation API.
    Returns a dict with:
      - translated_text: The translated string
      - detected_language: The ISO-639 language code detected for the source text
    """
    if not text.strip():
        return {"translated_text": "", "detected_language": source_language or "en"}
    try:
        client = translate.Client()
        result = client.translate(text, target_language=target_language, source_language=source_language)
        return {
            "translated_text": result.get("translatedText", ""),
            "detected_language": result.get("detectedSourceLanguage", source_language or target_language)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Translation API call failed: {str(e)}"
        )

def text_to_speech(text: str, language_code: str = "en-IN") -> bytes:
    """
    Synthesizes speech from the given text using Google Cloud Text-to-Speech.
    Returns raw audio bytes (MP3 format).
    """
    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Standardize language code format (e.g. 'hi' -> 'hi-IN')
        lang_mapping = {
            "hi": "hi-IN",
            "ta": "ta-IN",
            "te": "te-IN",
            "mr": "mr-IN",
            "en": "en-IN"
        }
        clean_lang = language_code.split("-")[0].lower()
        target_lang_code = lang_mapping.get(clean_lang, language_code)
        
        voice = texttospeech.VoiceSelectionParams(
            language_code=target_lang_code,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        return response.audio_content
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text-to-Speech API call failed: {str(e)}"
        )
