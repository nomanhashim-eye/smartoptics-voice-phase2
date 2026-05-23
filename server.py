"""
SmartOptics Voice Test Harness — Phase 2 (Cloud / Azure Streaming)
==================================================================

A small FastAPI app that:
  1. Serves the test-harness web page.
  2. Accepts a WebSocket connection from the browser carrying raw PCM
     audio frames (16 kHz, 16-bit, mono).
  3. Bridges that audio stream to Azure Cognitive Services Speech
     in continuous-recognition mode.
  4. Streams interim and final transcripts back to the browser.

Audio is never written to disk. The Azure session is configured to
discard audio after transcription (per §22.4 of the SmartOptics
Voice Input Service spec).

Environment variables required:
    AZURE_SPEECH_KEY     — Speech resource key (KEY 1 or KEY 2)
    AZURE_SPEECH_REGION  — e.g. "uksouth"

Optional:
    PORT                 — defaults to 8000 (Render sets this)
"""

import os
import sys
import asyncio
import json
import logging
import threading
from queue import Queue, Empty
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import azure.cognitiveservices.speech as speechsdk
except ImportError as e:
    print(f"Missing dependency: {e.name}", file=sys.stderr)
    print("Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

AZURE_KEY = os.environ.get("AZURE_SPEECH_KEY", "").strip()
AZURE_REGION = os.environ.get("AZURE_SPEECH_REGION", "uksouth").strip().lower()
HERE = Path(__file__).parent.resolve()

# Optical / clinical phrase list used by Azure as a recognition bias.
# This is the Azure equivalent of Whisper's initial_prompt.
OPTICAL_PHRASES = [
    # Prescription terminology
    "sphere", "cylinder", "axis", "prism", "add", "near vision", "distance vision",
    "visual acuity", "Snellen", "LogMAR", "PD", "pupillary distance",
    # Pathology and anatomy
    "presbyopia", "myopia", "hyperopia", "astigmatism", "amblyopia",
    "blepharitis", "conjunctivitis", "glaucoma", "cataract",
    "macular degeneration", "diabetic retinopathy", "dry eye",
    "intraocular pressure", "fundus", "retina", "cornea", "lens",
    "pupil", "iris", "optic disc", "tonometry", "ophthalmoscopy",
    # NHS / GOS terminology
    "GOS", "GOS one", "GOS three", "GOS six", "NHS", "HC2", "HC3",
    "voucher", "domiciliary",
    # Brand names — these are where vanilla STT typically fails
    "Acuvue", "Acuvue Oasys", "Varilux", "Varilux X", "Crizal",
    "Crizal Sapphire", "Hoya", "Hoya Hilux", "Essilor", "Eyezen",
    "Zeiss", "Drivesafe", "DuraVision", "varifocal", "bifocal",
    "single vision", "hydraluxe",
]

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("voice-phase2")


# ----------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------

app = FastAPI(title="SmartOptics Voice Test (Phase 2)")


@app.get("/")
async def root():
    return FileResponse(HERE / "index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "region": AZURE_REGION,
        "key_configured": bool(AZURE_KEY),
        "phrase_count": len(OPTICAL_PHRASES),
    }


# ----------------------------------------------------------------------
# WebSocket: /ws — bridges browser <-> Azure Speech streaming
# ----------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_transcribe(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket connected")

    if not AZURE_KEY:
        await ws.send_json({"type": "error", "message": "AZURE_SPEECH_KEY not configured on server"})
        await ws.close()
        return

    # ------------------------------------------------------------------
    # Per-connection state
    # ------------------------------------------------------------------
    loop = asyncio.get_event_loop()
    use_phrases = True  # Toggleable via client config message

    # ------------------------------------------------------------------
    # Wait for the client's "start" message which carries config
    # ------------------------------------------------------------------
    try:
        raw_config = await ws.receive_text()
        config = json.loads(raw_config)
        if config.get("type") != "start":
            await ws.send_json({"type": "error", "message": "first message must be {type: 'start'}"})
            await ws.close()
            return
        use_phrases = bool(config.get("use_phrases", True))
        log.info(f"Session start, use_phrases={use_phrases}")
    except Exception as e:
        await ws.send_json({"type": "error", "message": f"bad start frame: {e}"})
        await ws.close()
        return

    # ------------------------------------------------------------------
    # Azure Speech SDK setup
    #
    # We use PushAudioInputStream — the browser sends raw PCM frames
    # which we push into the SDK. The SDK manages the connection to
    # Azure on a background thread and fires recognizing/recognized
    # callbacks as transcripts arrive.
    # ------------------------------------------------------------------
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = "en-GB"
    # Disable Microsoft's audio logging server-side (per §22.4):
    speech_config.set_property(
        speechsdk.PropertyId.Speech_LogFilename, ""
    )
    speech_config.set_service_property(
        name="audiologging",
        value="false",
        channel=speechsdk.ServicePropertyChannel.UriQueryParameter,
    )
    # Request profanity is masked (less of an issue clinically, but tidy):
    speech_config.set_profanity(speechsdk.ProfanityOption.Masked)

    # 16 kHz, 16-bit, mono — the browser side must emit the same.
    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=16000, bits_per_sample=16, channels=1
    )
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config, audio_config=audio_config
    )

    # Apply phrase-list biasing if requested
    if use_phrases:
        phrase_list = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
        for phrase in OPTICAL_PHRASES:
            phrase_list.addPhrase(phrase)

    # ------------------------------------------------------------------
    # Bridge: Azure callbacks fire on background threads. We can't await
    # WebSocket sends from those threads — we hand them off to the event
    # loop via run_coroutine_threadsafe.
    # ------------------------------------------------------------------
    def send_safely(payload: dict):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
        except RuntimeError:
            pass  # connection closed

    def on_recognizing(evt):
        text = evt.result.text or ""
        if text:
            send_safely({"type": "interim", "text": text})

    def on_recognized(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text or ""
            if text:
                send_safely({"type": "final", "text": text})
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            log.info("No speech could be recognized")

    def on_canceled(evt):
        reason = evt.reason
        details = getattr(evt, "error_details", "") or ""
        log.warning(f"Azure cancelled: reason={reason} details={details}")
        send_safely({"type": "error", "message": f"Azure cancelled: {details or reason}"})

    def on_session_stopped(evt):
        log.info("Azure session stopped")
        send_safely({"type": "session_stopped"})

    recognizer.recognizing.connect(on_recognizing)
    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(on_session_stopped)

    # ------------------------------------------------------------------
    # Begin continuous recognition. This call is non-blocking.
    # ------------------------------------------------------------------
    recognizer.start_continuous_recognition_async().get()
    await ws.send_json({"type": "ready"})
    log.info("Azure recognizer running")

    # ------------------------------------------------------------------
    # Pump audio from the WebSocket into the push stream until the
    # client tells us to stop or the connection drops.
    # ------------------------------------------------------------------
    total_bytes = 0
    try:
        while True:
            msg = await ws.receive()
            # FastAPI websocket receive() returns either {"bytes": ...} or {"text": ...}
            if msg.get("type") == "websocket.disconnect":
                log.info("client disconnected")
                break
            if "bytes" in msg and msg["bytes"]:
                chunk = msg["bytes"]
                total_bytes += len(chunk)
                push_stream.write(chunk)
            elif "text" in msg and msg["text"]:
                try:
                    payload = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "stop":
                    log.info("client requested stop")
                    break
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.exception("error in audio pump")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # ------------------------------------------------------------------
        # Tear down. Order matters: close the push stream first (signals
        # end-of-stream to the SDK), then stop recognition, then close ws.
        # ------------------------------------------------------------------
        try:
            push_stream.close()
        except Exception:
            pass
        try:
            recognizer.stop_continuous_recognition_async().get()
        except Exception:
            pass
        log.info(f"session ended, total audio bytes: {total_bytes}")
        try:
            await ws.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Local dev entrypoint
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
