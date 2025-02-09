import asyncio
import logging

from app.llm.groq import GroqLLM
from app.tts.elevenlabs import ElevenLabsTTS
from app.transcriber.deepgram import DeepgramTranscriber
from app.io_handler.ws import WebsocketIOHandler
from app.lib.constants import DEFAULT_SYSTEM_PROMPT


logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, agent_config, **kwargs):
        self.response_id = 0
        
        self.audio_queue = asyncio.Queue()
        self.transcriber_output_queue = asyncio.Queue()
        self.llm_output_queue = asyncio.Queue()
        self.synthesizer_output_queue = asyncio.Queue()
        
        self.kwargs: dict = kwargs
        self.agent_config: dict = agent_config
        
        self.websocket = kwargs.get("websocket", None)
        
        self.io_handler = None
        self.llm = None
        self.transcriber = None
        self.synthesizer = None
        
        self.io_task = None
        self.stt_task = None
        self.llm_task = None
        self.tts_task = None
        self.tasks = []
        
        self.messages = [{
            "role": "system",
            "content": DEFAULT_SYSTEM_PROMPT
        }]
        
        
        self.call_status = {
            "is_callee_speaking": False,
            "is_agent_speaking": False,
            "is_call_ended": False
        }
                
    async def run(self):
        try:
            self.llm = GroqLLM(self.transcriber_output_queue, self.llm_output_queue, self.messages)
            self.transcriber = DeepgramTranscriber(self.audio_queue, self.transcriber_output_queue)
            self.synthesizer = ElevenLabsTTS(self.llm_output_queue, self.synthesizer_output_queue)
            self.io_handler = WebsocketIOHandler(self.audio_queue, self.synthesizer_output_queue, self.websocket, self.messages)
            
            await asyncio.gather(self.transcriber.establish_connection(), self.synthesizer.establish_connection())
            
            self.io_task = asyncio.create_task(self.io_handler.run())
            self.stt_task = asyncio.create_task(self.transcriber.transcribe())
            self.llm_task = asyncio.create_task(self.llm.run())
            self.tts_task = asyncio.create_task(self.synthesizer.synthesize())

            self.tasks = [self.io_task, self.stt_task, self.llm_task, self.tts_task]
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
        