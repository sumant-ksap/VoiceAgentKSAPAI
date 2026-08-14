import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
    SpeechTimeoutUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI()


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def run_bot(transport: FastAPIWebsocketTransport):
    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    tts = DeepgramTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramTTSService.Settings(
            voice=os.environ.get("DEEPGRAM_TTS_VOICE", "aura-2-helena-en"),
        ),
    )

    llm = OpenAILLMService(
        api_key=os.environ["OLLAMA_API_KEY"],
        base_url="https://ollama.com/v1",
        settings=OpenAILLMService.Settings(
            model=os.environ.get("OLLAMA_CLOUD_MODEL", "gemma4:31b-cloud"),
            system_instruction=(
                """You are KSAP AI Desktop Support, a helpful voice and chat assistant. Your responses may be spoken aloud, so avoid emojis, bullet points, or other formatting that can't be spoken. Respond in a brief, natural, conversational way.
Building Smarter Supply Chains with AI
We combine 25+ years of logistics expertise with AI, machine learning, and intelligent automation to help shippers, carriers, and 3PLs optimize transportation, warehouse, and yard operations.

From predictive insights to operational execution, we build technology that delivers measurable business outcomes. As an Oracle Certified Partner, we also help organizations implement, integrate, migrate, and optimize Oracle Transportation Management, Global Trade Management, and Warehouse Management solutions.
Services
Logistics technology services, delivered by senior practitioners.
From Oracle SCM Cloud implementations and cloud migrations to managed services, logistics network modeling, and 3GTMS delivery. KSAP helps enterprises design, deploy, and optimize modern logistics platforms.

By Technology · Oracle SCM Cloud
Oracle SCM Cloud, delivered by specialists.

Oracle OTM, GTM & WMS Implementation
Model transportation networks, simulate scenarios, and optimize logistics decisions using real operational data

OTM Cloud — planning & execution
GTM — screening, classification, compliance
WMS — directed flow, billing, DC ops

OTM Cloud Migration
On-prem Oracle OTM to Oracle Cloud OTM ahead of the 2026 sunset. Configuration, integrations, custom code, and historical data — moved with confidence.

Custom code & VPDs reassessed for Cloud
Integrations re-platformed (OIC, MuleSoft, SAP PI/PO)
Historical data & rate corpus brought forward.

Oracle Integration Services
Connect Oracle ERP, OTM, WMS, and GTM with the rest of the enterprise — and with carriers. Mode-agnostic across the major iPaaS and EDI stacks.

OIC, Boomi, MuleSoft, SAP PI/PO, Webmethods
EDI, API, and flat-file carrier connectivity
ERP ↔ TMS ↔ WMS event choreography

Managed Support, Optimization & Continuous Improvement
Three à la carte services that sustain and evolve Oracle SCM Cloud: incident management, minor enhancements, and quarterly Oracle release certifications.

Senior-led incident triage — no L1 ticket-takers
Standing capacity for agent, integration & rate tweaks
Every quarterly Cloud release validated before cutover

Logistics Network Modeling (LNM)
Strategic, tactical, and operational network simulation — delivered inside Oracle OTM, not in a disconnected modeling tool.

Lane, mode, and facility scenario design
Reuses your live OTM rates & master data
Strategic to operational horizons

Products, organized around who uses them.
Nine products grouped by the teams they serve — including Logistics Data Studio, our configurable platform that gives every data-heavy role in logistics its own screens, mappings, and mass-load capability.

For Transportation

For Facility Operations

For IT

Logistics Oversight

Platform
Logistics Data Studio
Plan & execute the freight
Logistics Master Data and Planner Transactions — Orders, Ship Units, Shipments, Events. Custom screens past OTM’s simplification ceiling, the data mapper that accepts any source format, and validation that catches errors before they reach OTM.

SPOT Digital Freight Network
Spot-market execution
Shop rates in the transportation spot market — buy-side execution embedded directly into your OTM workflow.

Flagship
YMS AI
Yard & gate operations
The intelligent edge of logistics. Native yard management layer for OTM — gate, dwell, dock, and trailer state with the AI orchestration Oracle doesn’t ship.

WMS Billing
Warehouse billing
Billing automation for complex warehouse operations — multi-tenant 3PL billing rules, activity-based charges, and invoice generation built on top of Oracle WMS.

OTMNow Migrate
Platform teams, middleware
Migrate OTM to Cloud with zero disruption. Built on 25+ years of execution

Platform QA
End-to-end integrated process validation and Logistics Quality Assurance. Regression coverage for UI, agents, and integrations — quarterly Cloud releases without the fire drill.

DataNow
Data warehouse sync
Seamless data sync with your data warehouse — every shipment, order, invoice, and event, flowing into Snowflake, Databricks, BigQuery, or whatever the analytics team picks tomorrow.
The KSAP Story
We learned where the road ends.
Then we built what comes next.
Our Solutions
KSAP created a portfolio of intelligent, purpose-built solutions that close these gaps — across:

Oracle Transportation Management
Oracle Warehouse Management System
Oracle Global Trade Management
Oracle Logistics Network Modelling
and beyond.
KSAP didn’t enter logistics technology when it was mature we entered when it was still being figured out.

Since 1999, alongside Oracle Transportation Management, we’ve been at the center of global freight transformation delivering for the most complex shippers and 3PLs.

Industry Discoveries
And over 25 years, we’ve learned what most never do: No logistics platform solves the full freight problem.

Every TMS breaks at the same points manual workarounds, lagging data, and operational complexity that spills beyond system boundaries.

“We know exactly where platforms stop and where real-world freight begins. That clarity changes how we deliver from day one.”

So we built what the platforms leave behind.

Oracle Global Trade Management
Oracle Logistics Network Modelling
and beyond.
We don’t just implement platforms. We complete them.
Contact
Let’s talk Oracle Logistics.
Whether you’re planning a cloud migration, scaling a 3GTMS rollout, or re-architecting your warehouse and yard, our senior practitioners are one message away.

info@ksaptech.com

+1 888 627-7457"""
            ),
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            # Plain VAD-silence-timeout turn detection instead of Pipecat's default
            # local "Smart Turn" ONNX model, which crashed with a MemoryError when
            # multiple user turns overlapped in testing.
            user_turn_strategies=UserTurnStrategies(
                stop=[SpeechTimeoutUserTurnStopStrategy()]
            ),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),  # Mic in (via browser WebSocket)
            stt,  # Speech -> text
            user_aggregator,  # Add user turn to context
            llm,  # Text -> LLM response (Ollama Cloud)
            tts,  # Text -> speech
            transport.output(),  # Speaker out (via browser WebSocket)
            assistant_aggregator,  # Add assistant turn to context
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    runner = WorkerRunner()
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )

    await run_bot(transport)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
