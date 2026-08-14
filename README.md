# KSAP AI Desktop Support (Pipecat)

A voice + chat assistant: browser UI (mic or typed text) -> Deepgram (speech-to-text) -> LLM -> Deepgram Aura (text-to-speech) -> browser audio out.

There are two ways to run it:

- **`server.py`** (primary, deployable) — a branded web UI ("KSAP AI Desktop Support") with a live chat transcript, a text input box, and voice in/out over a plain WebSocket. Uses Deepgram for both STT and TTS, and Ollama Cloud for the LLM. This is the version deployed to Render — entirely free, no payment method needed anywhere, light enough to run on Render's 512MB free tier, and doesn't need UDP/WebRTC reachability that most PaaS hosts don't support.
- **`main.py`** (local-only alternative) — a plain console script using this PC's mic/speakers, a locally-running Ollama model, and local Kokoro TTS — no browser or cloud services involved.

## Setup (local)

1. Activate the virtual environment (already created in `venv/`):

   ```
   venv\Scripts\activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

   `main.py` additionally needs PyAudio (local mic/speaker) and Kokoro (`pip install "pipecat-ai[local,kokoro]"`) — both already installed in this project's `venv/`, but not in `requirements.txt` since `server.py`/Render doesn't need them (and PyAudio needs `portaudio` system headers on a fresh Linux box).

3. Copy `.env.example` to `.env` and fill in your keys:

   ```
   copy .env.example .env
   ```

   - `DEEPGRAM_API_KEY` — https://console.deepgram.com/ (free trial credits) — used by both `server.py` and `main.py`.
   - `OLLAMA_API_KEY` — https://ollama.com/settings/keys — used by `server.py` only, to call the `gemma4:31b-cloud` model via Ollama Cloud's OpenAI-compatible endpoint (`https://ollama.com/v1`).

4. For `main.py` only: make sure [Ollama](https://ollama.com) is installed and running locally, with a model pulled (`ollama pull gemma4:e4b`). `server.py` doesn't need local Ollama at all — it calls Ollama Cloud instead. Kokoro's model files (~350MB) auto-download to `~/.cache/pipecat/kokoro-onnx/` on first run of `main.py`.

## Run — web UI (recommended)

```
python server.py
```

Open **http://localhost:7860** in your browser. Click **Start** to connect your mic (grant permission when prompted), or just type a message and hit Send/Enter — both go through the same conversation. The bot's replies appear as chat bubbles and are also spoken aloud.

## Run — console only

```
python main.py
```

The agent speaks first (a short introduction), then listens via this PC's mic — just talk. Ctrl+C to stop.

## Deploying to Render

`server.py` is built to run 24/7 on Render, entirely on free tiers (no card required anywhere — Render's free web service tier doesn't need one, and neither does Ollama Cloud/Deepgram with just an API key):

- **LLM**: Ollama Cloud (`gemma4:31b-cloud`) instead of a local model — no GPU/big-RAM box needed.
- **TTS**: Deepgram Aura (cloud), not local Kokoro. Kokoro's ~325MB ONNX model, loaded on top of everything else, OOM-crashed the deployed instance on Render's free 512MB tier (confirmed via Render's logs: the process restarted a few seconds into every session, right when the TTS model was being loaded). Deepgram TTS reuses the same account/key as STT and needs no local model at all.
- **Voice transport**: a plain WebSocket (`FastAPIWebsocketTransport` server-side, `@pipecat-ai/websocket-transport` client-side), not WebRTC. We first tried self-hosted `SmallWebRTCTransport` — it worked fine in local testing (both peers on one machine), but on the real Render deployment, WebRTC connections hung forever at the ICE "checking" state. Adding a STUN server on both client and server didn't help either, which points to Render's container network blocking outbound UDP entirely — WebRTC fundamentally needs UDP for its media path, so no amount of ICE/STUN configuration can fix that. A WebSocket rides over the same plain TCP that the page's own HTTP load already uses successfully, so it sidesteps the problem entirely. (We also evaluated Daily's managed WebRTC, which handles NAT traversal via their own infrastructure — but Daily requires a payment method on file for their server-side SDK to join rooms programmatically even on the free tier, so it was ruled out to stay 100% free.)

Steps:

1. Push this project to a GitHub repo.
2. On Render, **New → Blueprint**, point it at the repo — it'll read `render.yaml` automatically (or create a Web Service manually with build command `pip install -r requirements.txt` and start command `python server.py`).
3. In the Render dashboard, set the two secret env vars (`render.yaml` marks them `sync: false`, meaning Render will prompt for them instead of storing values in the repo): `DEEPGRAM_API_KEY`, `OLLAMA_API_KEY`.
4. Deploy. Render assigns a public HTTPS URL and injects `PORT` automatically — `server.py` already reads it (`os.environ.get("PORT", 7860)`).

## Swapping providers

Each stage is a separate service object — swap any one out independently:

- STT: `pipecat.services.deepgram.stt.DeepgramSTTService` -> any other `pipecat.services.*.stt` class (e.g. `assemblyai`, `whisper`)
- LLM: `server.py` uses `pipecat.services.openai.llm.OpenAILLMService` pointed at Ollama Cloud's OpenAI-compatible endpoint; `main.py` uses `pipecat.services.ollama.llm.OLLamaLLMService` against a local Ollama. Either can swap to `pipecat.services.anthropic.llm.AnthropicLLMService`, etc.
- TTS: `server.py` uses `pipecat.services.deepgram.tts.DeepgramTTSService` (`DEEPGRAM_TTS_VOICE` in `.env` picks the Aura voice, default `aura-2-helena-en`); `main.py` uses local `pipecat.services.kokoro.tts.KokoroTTSService` (`KOKORO_VOICE` picks the voice, e.g. `af_heart`, `am_adam`, `bf_emma`). Only reintroduce Kokoro (or another local TTS) in `server.py` if deploying to a host with more than ~512MB RAM.
- Transport: `server.py` uses `pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport`; swap for `pipecat.transports.daily.transport.DailyTransport` for more full-featured WebRTC (screen share, video, etc.), at the cost of needing a Daily account with a payment method on file. `pipecat.transports.smallwebrtc.transport.SmallWebRTCTransport` is self-hosted WebRTC with no external service, but needs a host with real UDP reachability (unlike most PaaS platforms) to actually work for remote users.

`static/index.html` uses the official `@pipecat-ai/client-js` + `@pipecat-ai/websocket-transport` JS SDKs (loaded via CDN) for the browser side — mic/speaker capture, live transcripts (`RTVIEvent.UserTranscript` / `BotOutput`), and typed input (`sendText`) all go through Pipecat's RTVI protocol.
