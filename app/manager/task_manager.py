import asyncio
import logging

from app.llm.groq import GroqLLM
from app.tts.elevenlabs import ElevenLabsTTS
from app.transcriber.deepgram import DeepgramTranscriber


logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, agent_config, **kwargs):
        self.response_id = 0
        
        self.audio_queue = asyncio.Queue()
        self.stt_output_queue = asyncio.Queue()
        self.llm_output_queue = asyncio.Queue()
        self.tts_output_queue = asyncio.Queue()
        
        self.kwargs: dict = kwargs
        self.agent_config: dict = agent_config
        
        self.websocket = kwargs.get("websocket", None)
        
        self.audio_task = None
        self.stt_task = None
        self.llm_task = None
        self.tts_task = None
        self.stream_task = None
        
        self.messages = [{
            "role": "system",
            "content": "Strictly, ouput in less than 5 words."
        }]
        
        self.is_callee_speaking = False
        self.is_agent_speaking = False
        self.is_call_ended = False
    
    async def get_audio_bytes(self):
        try:
            while True:
                data = await self.websocket.receive_bytes()
                await self.audio_queue.put(data)
        except Exception as e:
            logger.error(f"Error receiving audio data: {e}", exc_info=True)
    
    def add_message(self, message):
        if message is None:
            return
        
        last_message = self.messages[-1]
        
        if message["role"] == last_message["role"]:
            last_message["content"] += f" {message['content']}"
        else:
            self.messages.append(message)

    async def generate_agent_response(self, llm: GroqLLM):
        while True:
            try:
                text = await self.stt_output_queue.get()
                logger.info(f"Received STT text: {text}")
                # self.add_message({"role": "user", "content": text})
                await llm.generate_text([{"role": "user", "content": text}])
            except Exception as e:
                logger.error(f"Error receiving STT text: {e}", exc_info=True)
                
    async def stream(self):
        while True:
            try:
                audio_data = await self.tts_output_queue.get()
                await self.websocket.send_bytes(audio_data)
            except Exception as e:
                logger.error(f"Error sending audio data: {e}", exc_info=True)
    
    async def run(self):
        try:
            llm = GroqLLM(self.llm_output_queue)
            dg_transcriber = DeepgramTranscriber(self.audio_queue, self.stt_output_queue)
            tts = ElevenLabsTTS(self.llm_output_queue, self.tts_output_queue)
            
            await dg_transcriber.establish_connection()
            await tts.establish_connection()
            
            self.audio_task = asyncio.create_task(self.get_audio_bytes())
            self.stt_task = asyncio.create_task(dg_transcriber.transcribe())
            self.llm_task = asyncio.create_task(self.generate_agent_response(llm))
            self.tts_task = asyncio.create_task(tts.synthesize())
            self.stream_task = asyncio.create_task(self.stream())
            
            await asyncio.gather(self.audio_task, self.stt_task, self.llm_task, self.tts_task, self.stream_task)
        except Exception as e:
            logger.error(f"Error running task manager: {e}", exc_info=True)
            
    def cleanup(self):
        self.llm_task.cancel()
        self.audio_task.cancel()
        self.stt_task.cancel()
        self.tts_task.cancel()