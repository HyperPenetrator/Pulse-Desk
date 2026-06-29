import base64
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from comms_client import translate_text, text_to_speech

router = APIRouter(prefix="/webhook", tags=["webhook"])

def triage_symptoms_stub(text_en: str) -> Dict[str, str]:
    """
    Lightweight triage/dispatch logic stub.
    Checks for emergency keywords and returns severity and advice.
    """
    text_lower = text_en.lower()
    emergency_keywords = ["chest pain", "bleeding", "accident", "emergency", "breathing", "unconscious", "heart attack", "stroke"]
    
    is_emergency = any(kw in text_lower for kw in emergency_keywords)
    
    if is_emergency:
        return {
            "severity": "emergency",
            "advice": "An ambulance is being dispatched to your location. Please stay calm."
        }
    else:
        return {
            "severity": "non-emergency",
            "advice": "Your symptoms have been logged as non-urgent. A healthcare assistant will contact you shortly."
        }

@router.post("/dialogflow")
async def dialogflow_webhook(request: Dict[str, Any], db: Session = Depends(get_db)):
    """
    FastAPI route at /webhook/dialogflow that receives Dialogflow CX fulfillment requests,
    translates if needed, runs triage logic, translates the response back,
    and conditionally generates Text-to-Speech for voice channel.
    """
    try:
        # 1. Parse Dialogflow CX request payload
        text_query = request.get("text")
        # If text is not provided, check alternate fields or queryResult
        if not text_query:
            text_query = request.get("transcript", "")
            
        language_code = request.get("languageCode", "en")
        
        # Check session info / parameters
        session_info = request.get("sessionInfo", {})
        parameters = session_info.get("parameters", {})
        
        # Determine channel (voice vs SMS/WhatsApp)
        channel = parameters.get("channel", "sms")
        if request.get("payload", {}).get("telephony") is not None:
            channel = "voice"
            
        # 2. Translation to English if needed
        detected_lang = language_code.split("-")[0].lower()
        if detected_lang != "en" and text_query:
            translation_res = translate_text(text_query, target_language="en")
            english_query = translation_res["translated_text"]
            original_lang = translation_res["detected_language"]
        else:
            english_query = text_query
            original_lang = detected_lang

        # 3. Call Triage/Dispatch logic stub
        triage_result = triage_symptoms_stub(english_query)
        severity = triage_result["severity"]
        advice_en = triage_result["advice"]

        # 4. Translate response back to user's language
        if original_lang != "en" and original_lang != "unknown":
            response_translation = translate_text(advice_en, target_language=original_lang)
            final_response_text = response_translation["translated_text"]
        else:
            final_response_text = advice_en

        # 5. Conditionally apply Text-to-Speech for voice channel
        audio_base64 = None
        if channel == "voice":
            audio_bytes = text_to_speech(final_response_text, language_code=language_code)
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # 6. Formulate Dialogflow CX response
        messages = [
            {
                "text": {
                    "text": [final_response_text]
                }
            }
        ]
        
        # Prepare custom payload if audio is generated
        payload = {}
        if audio_base64:
            payload["audio_base64"] = audio_base64
            # Add custom payload to messages
            messages.append({
                "payload": {
                    "audio_base64": audio_base64
                }
            })

        # Update session parameters
        updated_parameters = dict(parameters)
        updated_parameters["triage_severity"] = severity
        updated_parameters["detected_language"] = original_lang

        response_payload = {
            "fulfillmentResponse": {
                "messages": messages
            },
            "sessionInfo": {
                "parameters": updated_parameters
            }
        }
        
        return response_payload

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook execution failed: {str(e)}"
        )
