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
        
        self.io_task = None
        self.stt_task = None
        self.llm_task = None
        self.tts_task = None
        self.tasks = []
        
        self.messages = [{
            "role": "system",
            "content": DEFAULT_SYSTEM_PROMPT
        }]
        
        self.is_callee_speaking = False
        self.is_agent_speaking = False
        self.is_call_ended = False
                
    async def run(self):
        try:
            llm = GroqLLM(self.transcriber_output_queue, self.llm_output_queue, self.messages)
            transcriber = DeepgramTranscriber(self.audio_queue, self.transcriber_output_queue)
            synthesizer = ElevenLabsTTS(self.llm_output_queue, self.synthesizer_output_queue)
            io_handler = WebsocketIOHandler(self.audio_queue, self.synthesizer_output_queue, self.websocket, self.messages)
            
            await asyncio.gather(transcriber.establish_connection(), synthesizer.establish_connection())
            
            self.io_task = asyncio.create_task(io_handler.run())
            self.stt_task = asyncio.create_task(transcriber.transcribe())
            self.llm_task = asyncio.create_task(llm.run())
            self.tts_task = asyncio.create_task(synthesizer.synthesize())
            
            self.tasks = [self.io_task, self.stt_task, self.llm_task, self.tts_task]
            await asyncio.gather(*self.tasks)
        except Exception as e:
            logger.error(f"TASK MANAGER ERROR: {e}", exc_info=True)
            
    def cleanup(self):
        pass
        # self.llm_task.cancel()
        # self.io_task.cancel()
        # self.stt_task.cancel()
        # self.tts_task.cancel()