import pytest
from fastapi.testclient import TestClient
import comms_client
import webhook
from main import app

client = TestClient(app)

# Helper to verify standard structure of Dialogflow CX response
def verify_cx_response_structure(data: dict):
    assert "fulfillmentResponse" in data
    assert "messages" in data["fulfillmentResponse"]
    assert len(data["fulfillmentResponse"]["messages"]) > 0
    assert "text" in data["fulfillmentResponse"]["messages"][0]
    assert "text" in data["fulfillmentResponse"]["messages"][0]["text"]
    assert len(data["fulfillmentResponse"]["messages"][0]["text"]["text"]) > 0
    assert "sessionInfo" in data
    assert "parameters" in data["sessionInfo"]

def test_webhook_hindi_voice_emergency(monkeypatch):
    """
    Tests the Dialogflow CX webhook with a voice channel request in Hindi
    that contains an emergency symptom (chest pain).
    """
    # Mock Translation for: "Mujhe bohot tej chhati me dard ho raha hai" -> "I have very severe chest pain"
    # and the emergency response: "An ambulance is being dispatched..." -> "Aapki location par ambulance bheji ja rahi hai. Kripya shant rahein."
    def mock_translate_text(text: str, target_language: str = "en", source_language=None) -> dict:
        if "chhati me dard" in text.lower():
            return {"translated_text": "I have very severe chest pain", "detected_language": "hi"}
        elif "ambulance is being dispatched" in text.lower():
            return {"translated_text": "Aapki location par ambulance bheji ja rahi hai. Kripya shant rahein.", "detected_language": "en"}
        return {"translated_text": text, "detected_language": "hi"}

    # Mock Text-to-Speech returning dummy bytes
    def mock_text_to_speech(text: str, language_code: str = "en-IN") -> bytes:
        assert text == "Aapki location par ambulance bheji ja rahi hai. Kripya shant rahein."
        assert language_code == "hi-IN"
        return b"mocked_hindi_tts_audio_bytes"

    monkeypatch.setattr(comms_client, "translate_text", mock_translate_text)
    monkeypatch.setattr(comms_client, "text_to_speech", mock_text_to_speech)

    payload = {
        "detectIntentResponseId": "12345",
        "text": "Mujhe bohot tej chhati me dard ho raha hai",
        "languageCode": "hi-IN",
        "sessionInfo": {
            "session": "projects/test/agents/test/sessions/111",
            "parameters": {
                "channel": "voice"
            }
        }
    }

    response = client.post("/webhook/dialogflow", json=payload)
    assert response.status_code == 200
    data = response.json()
    verify_cx_response_structure(data)

    # Verify translated response text
    messages = data["fulfillmentResponse"]["messages"]
    assert messages[0]["text"]["text"][0] == "Aapki location par ambulance bheji ja rahi hai. Kripya shant rahein."

    # Verify custom payload message contains the base64 audio since it is voice channel
    assert len(messages) == 2
    assert "payload" in messages[1]
    assert "audio_base64" in messages[1]["payload"]
    assert len(messages[1]["payload"]["audio_base64"]) > 0

    # Verify session parameters updated
    params = data["sessionInfo"]["parameters"]
    assert params["triage_severity"] == "emergency"
    assert params["detected_language"] == "hi"

def test_webhook_tamil_sms_non_emergency(monkeypatch):
    """
    Tests the Dialogflow CX webhook with a non-voice channel (SMS) request in Tamil
    that contains a non-emergency symptom (mild fever).
    """
    # Mock Translation for: "எனக்கு லேசான காய்ச்சல் உள்ளது" -> "I have a mild fever"
    # and response: "Your symptoms have been logged as non-urgent..." -> "உங்கள் அறிகுறிகள் அவசரமற்றதாக பதிவு செய்யப்பட்டுள்ளன."
    def mock_translate_text(text: str, target_language: str = "en", source_language=None) -> dict:
        if "காய்ச்சல்" in text:
            return {"translated_text": "I have a mild fever", "detected_language": "ta"}
        elif "symptoms have been logged" in text:
            return {"translated_text": "உங்கள் அறிகுறிகள் அவசரமற்றதாக பதிவு செய்யப்பட்டுள்ளன.", "detected_language": "en"}
        return {"translated_text": text, "detected_language": "ta"}

    monkeypatch.setattr(comms_client, "translate_text", mock_translate_text)

    payload = {
        "detectIntentResponseId": "67890",
        "text": "எனக்கு லேசான காய்ச்சல் உள்ளது",
        "languageCode": "ta-IN",
        "sessionInfo": {
            "session": "projects/test/agents/test/sessions/222",
            "parameters": {
                "channel": "sms"
            }
        }
    }

    response = client.post("/webhook/dialogflow", json=payload)
    assert response.status_code == 200
    data = response.json()
    verify_cx_response_structure(data)

    # Verify translated response text
    messages = data["fulfillmentResponse"]["messages"]
    assert messages[0]["text"]["text"][0] == "உங்கள் அறிகுறிகள் அவசரமற்றதாக பதிவு செய்யப்பட்டுள்ளன."

    # Verify no TTS audio returned because it is SMS channel
    assert len(messages) == 1

    # Verify session parameters updated
    params = data["sessionInfo"]["parameters"]
    assert params["triage_severity"] == "non-emergency"
    assert params["detected_language"] == "ta"
