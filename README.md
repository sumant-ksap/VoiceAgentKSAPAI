# KSAP AI Desktop Support (Pipecat)

A voice + chat assistant: browser UI (mic or typed text) -> Deepgram (speech-to-text) -> LLM -> Kokoro (local text-to-speech) -> browser audio out.

There are two ways to run it:

- **`server.py`** (primary, deployable) — a branded web UI ("KSAP AI Desktop Support") with a live chat transcript, a text input box, and voice in/out over a self-hosted WebRTC transport. Uses Deepgram (STT), Ollama Cloud (LLM), and local Kokoro (TTS). This is the version deployed to Render — entirely free, no payment method needed anywhere.
- **`main.py`** (local-only alternative) — a plain console script using this PC's mic/speakers and a locally-running Ollama model directly, no browser or cloud LLM involved.

## Setup (local)

1. Activate the virtual environment (already created in `venv/`):

   ```
   venv\Scripts\activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

   `main.py` additionally needs PyAudio for local mic/speaker access (`pip install "pipecat-ai[local]"`) — already installed in this project's `venv/`, but not in `requirements.txt` since Render doesn't need it (and installing PyAudio on a fresh Linux box needs `portaudio` system headers).

3. Copy `.env.example` to `.env` and fill in your keys:

   ```
   copy .env.example .env
   ```

   - `DEEPGRAM_API_KEY` — https://console.deepgram.com/ (free trial credits) — used by both `server.py` and `main.py`.
   - `OLLAMA_API_KEY` — https://ollama.com/settings/keys — used by `server.py` only, to call the `gemma4:31b-cloud` model via Ollama Cloud's OpenAI-compatible endpoint (`https://ollama.com/v1`).

4. For `main.py` only: make sure [Ollama](https://ollama.com) is installed and running locally, with a model pulled (`ollama pull gemma4:e4b`). `server.py` doesn't need local Ollama at all — it calls Ollama Cloud instead.

   Kokoro's model files (~350MB) auto-download to `~/.cache/pipecat/kokoro-onnx/` on first run, for either script.

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

`server.py` is built to run 24/7 on Render, entirely on free tiers (no card required anywhere — Render's free web service tier doesn't need one, and neither does Ollama Cloud with just an API key):

- **LLM**: Ollama Cloud (`gemma4:31b-cloud`) instead of a local model — no GPU/big-RAM box needed.
- **Voice transport**: `SmallWebRTCTransport`, self-hosted, no external service. We evaluated Daily's managed WebRTC as a more NAT/firewall-reliable alternative, but Daily requires a payment method on file for their server-side SDK to join rooms programmatically even on the free tier — ruled out to keep this 100% free. Practical effect: voice should work fine on most home/office networks (a public STUN server is configured in `static/index.html`), but may fail without a TURN relay on restrictive corporate networks. Text chat always works regardless.
- **TTS**: Kokoro still runs locally in the same process (CPU-only, no extra service needed) — its model files download once, pre-warmed at server startup so the download doesn't block real user connections.

Steps:

1. Push this project to a GitHub repo.
2. On Render, **New → Blueprint**, point it at the repo — it'll read `render.yaml` automatically (or create a Web Service manually with build command `pip install -r requirements.txt` and start command `python server.py`).
3. In the Render dashboard, set the two secret env vars (`render.yaml` marks them `sync: false`, meaning Render will prompt for them instead of storing values in the repo): `DEEPGRAM_API_KEY`, `OLLAMA_API_KEY`.
4. Deploy. Render assigns a public HTTPS URL and injects `PORT` automatically — `server.py` already reads it (`os.environ.get("PORT", 7860)`).

## Swapping providers

Each stage is a separate service object — swap any one out independently:

- STT: `pipecat.services.deepgram.stt.DeepgramSTTService` -> any other `pipecat.services.*.stt` class (e.g. `assemblyai`, `whisper`)
- LLM: `server.py` uses `pipecat.services.openai.llm.OpenAILLMService` pointed at Ollama Cloud's OpenAI-compatible endpoint; `main.py` uses `pipecat.services.ollama.llm.OLLamaLLMService` against a local Ollama. Either can swap to `pipecat.services.anthropic.llm.AnthropicLLMService`, etc.
- TTS: `pipecat.services.kokoro.tts.KokoroTTSService` -> `pipecat.services.elevenlabs.tts.ElevenLabsTTSService`, `pipecat.services.cartesia.tts.CartesiaTTSService`, etc. (`KOKORO_VOICE` in `.env` picks the voice — see `kokoro_onnx`'s voice list, e.g. `af_heart`, `am_adam`, `bf_emma`)
- Transport: `server.py` uses `pipecat.transports.smallwebrtc.transport.SmallWebRTCTransport`; swap for `pipecat.transports.daily.transport.DailyTransport` for more reliable NAT traversal, at the cost of needing a Daily account with a payment method on file.

`static/index.html` uses the official `@pipecat-ai/client-js` + `@pipecat-ai/small-webrtc-transport` JS SDKs (loaded via CDN) for the browser side — mic/speaker capture, live transcripts (`RTVIEvent.UserTranscript` / `BotOutput`), and typed input (`sendText`) all go through Pipecat's RTVI protocol.
