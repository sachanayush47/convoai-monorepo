import asyncio
import aiohttp
import json
import logging
import websockets

from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)

DEEPGRAM_API_KEY = settings.DEEPGRAM_API_KEY


class DeepgramTranscriber:
    def __init__(self, input_queue, output_queue, **kwargs):
        self.input_queue: asyncio.Queue = input_queue
        self.output_queue: asyncio.Queue = output_queue
        self.deepgram_ws = None
        self.sentence: str = ""
        
        self.sender_task = None
        self.receiver_task = None
        
        self.is_call_ended: bool = False
     
    def get_deepgram_ws_url(self):
        # dg_params = {
        #     'model': "nova-2",
        #     'filler_words': 'true',
        #     'language': "en-US",
        #     'vad_events' :'true'
        # }
        
        # dg_params['encoding'] = "linear16"
        # dg_params['sample_rate'] = 16000
        # dg_params['channels'] = "1"
        # dg_params['interim_results'] = 'true'
        # dg_params['utterance_end_ms'] = 1000
        # dg_params['endpointing'] = 400

        ws = "wss://api.deepgram.com/v1/listen"  
        return ws

    async def establish_connection(self):
        try:
            self.deepgram_ws = await websockets.connect(
                self.get_deepgram_ws_url(),
                extra_headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}"
                }
            )
            logger.info("Connected to Deepgram WebSocket")
        except Exception as e:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.get_deepgram_ws_url(), headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}) as resp:
                    response_body = await resp.text()
                    logger.error(f"WebSocket connection rejected. Status: {resp.status}, Response: {response_body}")
        
            logger.error(f"Error connecting to Deepgram WebSocket: {e}", exc_info=True)

    async def sender(self):
        while True:
            try:
                audio = await self.input_queue.get()
                await self.deepgram_ws.send(audio)
            except Exception as e:
                logger.error(f"DEEPGRAM SENDER ERROR: {e}")
    
    async def receiver(self):
        async for message in self.deepgram_ws:
            data: dict = json.loads(message)
            
            try:
                transcript: str = data["channel"]["alternatives"][0]["transcript"]
                
                if transcript and transcript.strip() != "":
                    self.sentence += transcript
                
                if data["speech_final"]:
                    if self.sentence.strip() != "":
                        await self.output_queue.put(self.sentence)
                    
                    self.sentence = ""
            except Exception as e:
                logger.error(f"DEEPGRAM RECEIVER ERROR: {e}")
            
    async def transcribe(self):
        self.sender_task = asyncio.create_task(self.sender())
        self.receiver_task = asyncio.create_task(self.receiver())
        await asyncio.gather(self.sender_task, self.receiver_task)
    
    async def close_connection(self):
        self.is_call_ended = True
        
        if self.deepgram_ws:
            try:
                await self.deepgram_ws.send('{"type": "CloseStream"}')
                await self.deepgram_ws.close()
            except Exception:
                pass
            
            logger.info("Deepgram WebSocket closed")
        else:
            logger.info("Deepgram WebSocket already closed")
        
        try:
            if self.sender_task:
                self.sender_task.cancel()
            if self.receiver_task:
                self.receiver_task.cancel()
        except Exception:
            pass
        
        self.sender_task = None
        self.receiver_task = None
        self.deepgram_ws = None