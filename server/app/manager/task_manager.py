import asyncio
import logging

from app.llm.groq import GroqLLM
from app.tts.elevenlabs import ElevenLabsTTS
from app.transcriber.deepgram import DeepgramTranscriber
from app.io_handler.ws import WebsocketIOHandler
from app.lib.constants import DEFAULT_SYSTEM_PROMPT

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, agent_config, **kwargs):
        self.audio_queue = asyncio.Queue()
        self.transcriber_output_queue = asyncio.Queue()
        self.llm_output_queue = asyncio.Queue()
        self.synthesizer_output_queue = asyncio.Queue()
        
        self.kwargs: dict = kwargs
        self.agent_config: dict = agent_config
        
        # Auto end call if the call duration exceeds the maximum call duration. Default is 2 hours.
        self.max_call_duration_ms: int = agent_config.get("max_call_duration_ms", 7200000)
        
        self.websocket: WebSocket = kwargs.get("websocket", None)
        
        self.io_handler = None
        self.llm = None
        self.transcriber = None
        self.synthesizer = None
        
        self.io_task = None
        self.stt_task = None
        self.llm_task = None
        self.tts_task = None
        self.call_timeout_task = None
        self.tasks = []
        
        self.messages = [{
            "role": "system",
            "content": DEFAULT_SYSTEM_PROMPT
        }]
        
        self.call_status = {
            "response_id": 0,
            "is_callee_speaking": False,
            "is_agent_speaking": False,
            "is_call_ended": False
        }
        
    async def end_call(self):
        self.call_status["is_call_ended"] = True
        self.call_status["is_agent_speaking"] = False
        self.call_status["is_callee_speaking"] = False
        await self.websocket.close()
    
    # End the call if the call duration exceeds the maximum call duration
    async def end_call_on_timeout(self):
        await asyncio.sleep(self.max_call_duration_ms / 1000)
        await self.end_call()
        logger.info(f"Maxium call duration reached. Call ended after {self.max_call_duration_ms / 1000}s.")

    async def run(self):
        try:
            self.io_handler = WebsocketIOHandler(self.audio_queue, self.synthesizer_output_queue, websocket=self.websocket, messages=self.messages, call_status=self.call_status)
            self.transcriber = DeepgramTranscriber(self.audio_queue, self.transcriber_output_queue, call_status=self.call_status)
            self.llm = GroqLLM(self.transcriber_output_queue, self.llm_output_queue, messages=self.messages, call_status=self.call_status)
            self.synthesizer = ElevenLabsTTS(self.llm_output_queue, self.synthesizer_output_queue, call_status=self.call_status)
            
            await asyncio.gather(self.transcriber.establish_connection(), self.synthesizer.establish_connection())
            
            self.io_task = asyncio.create_task(self.io_handler.run())
            self.stt_task = asyncio.create_task(self.transcriber.transcribe())
            self.llm_task = asyncio.create_task(self.llm.run())
            self.tts_task = asyncio.create_task(self.synthesizer.synthesize())
            self.call_timeout_task = asyncio.create_task(self.end_call_on_timeout())

            self.tasks = [self.io_task, self.stt_task, self.llm_task, self.tts_task, self.call_timeout_task]
            await asyncio.gather(*self.tasks)
        except Exception as e:
            logger.error(f"TASK MANAGER ERROR: {e}", exc_info=True)
            
    async def cleanup(self):
        cleanup_tasks = []
        
        if self.llm:
            cleanup_tasks.append(self.llm.close_connection())
        
        if self.transcriber:
            cleanup_tasks.append(self.transcriber.close_connection())
            
        if self.synthesizer:
            cleanup_tasks.append(self.synthesizer.close_connection())
        
        if self.io_handler:
            cleanup_tasks.append(self.io_handler.close_connection())
        
        await asyncio.gather(*cleanup_tasks)
        
        for task in self.tasks:
            if task is not None:
                task.cancel()
        
        logger.info("Task manager cleanup complete.")
        