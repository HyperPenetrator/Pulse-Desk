# Context: Multilingual Voice-to-Text (STT) API

## 1. Overview & Purpose
In rural and semi-urban Primary Health Centres (PHCs) and Community Health Centres (CHCs), healthcare workers, administrators, and doctors face severe time constraints. Expecting them to manually type complex inventory updates, patient counts, or attendance logs into a digital dashboard introduces operational friction and data entry delays.

The **Voice-to-Text API** serves as the primary data-ingestion gateway for non-technical or heavily burdened field staff. By leveraging Automatic Speech Recognition (ASR), users can update the platform using natural verbal commands in their native languages (e.g., Hindi, Tamil, Telugu, Marathi, etc.), which are then transcribed and processed into structured system inputs.

---

## 2. Key Objectives & Scope
* **Multilingual Support:** Accurately transcribe regional languages and dialects, including "Hinglish" or mixed-language phrases commonly used in medical contexts (e.g., "Paracetamol stock khatam ho gaya hai").
* **Low-Latency Processing:** Deliver near-real-time transcriptions so users receive immediate visual confirmation of their voice inputs.
* **Noise Resilience:** Filter out ambient background noise common in crowded public health facilities.
* **Seamless Integration:** Output clean, normalized text strings that downstream Natural Language Processing (NLP) or Named Entity Recognition (NER) models can easily parse for intent (e.g., extracting medicine names, quantities, or bed statuses).

---

## 3. Core Functional Requirements

### A. Audio Ingestion
* Accepts audio payloads in standard compressed formats (`.mp3`, `.wav`, `.ogg`, `.m4a`) to minimize mobile data consumption in low-bandwidth environments.
* Supports both streaming (real-time chunking) and batch (file upload) audio processing.

### B. Language Detection & Transcription
* **Auto-Language Detection:** Ideally detects the spoken regional language automatically, or accepts an explicit `language_code` parameter from the frontend toggle.
* **Medical/Operational Vocabulary:** Must recognize specialized terms like medicine names (e.g., "Amoxicillin", "ORS"), health terms, and administrative jargon (e.g., "OPD footfall", "ICU beds").

### C. Output Format
* Returns a structured JSON payload containing:
    * The raw transcribed text.
    * A confidence score (0.0 to 1.0).
    * The detected language code.

---

## 4. Technical Architecture & Potential Stack
The API acts as a wrapper around advanced ASR models optimized for regional Indian/multilingual contexts.

* **Potential Engine Options:**
    * *Open Source / Self-Hosted:* **OpenAI Whisper** (fine-tuned on regional datasets) or **Bhashini API** (Government of India's AI translation tool engine, ideal for PHC/CHC contexts).
    * *Cloud Providers:* Google Cloud Speech-to-Text, Azure Speech Service, or AWS Transcribe.
* **Backend Framework:** FastAPI / Node.js (Express) to handle asynchronous audio stream processing cleanly.

---

## 5. Sample API Schema

### Endpoint: `POST /api/v1/voice/transcribe`

**Headers:**
```http
Content-Type: multipart/form-data
Authorization: Bearer <token>