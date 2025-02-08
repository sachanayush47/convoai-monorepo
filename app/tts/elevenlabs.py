import asyncio
import base64
import json
import logging
import websockets

from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY


class ElevenLabsTTS:
    def __init__(self, input_queue, output_queue, **kwargs):
        self.input_queue: asyncio.Queue = input_queue
        self.output_queue: asyncio.Queue = output_queue
        self.voice_id: str = kwargs.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
        self.model_id: str = kwargs.get("model_id", "eleven_flash_v2_5")
        self.inactivity_timeout: int = kwargs.get("inactivity_timeout", 180)
        self.elevenlabs_ws = None
        self.is_call_ended = False
    
    def get_xi_ws_url(self):
        ws = f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input?model_id={self.model_id}&inactivity_timeout={self.inactivity_timeout}"
        return ws
    
    async def establish_connection(self):
        try:
            self.elevenlabs_ws = await websockets.connect(self.get_xi_ws_url())
            bos_message = {
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8
                },
                "xi_api_key": ELEVENLABS_API_KEY
            }
            await self.elevenlabs_ws.send(json.dumps(bos_message))
            logger.info("Connected to ElevenLabs WebSocket")
        except Exception as e:
            logger.error(f"FAILED TO CONNECT WITH XI WS: {e}")
    
    async def sender(self):
        while True:
            if self.is_call_ended:
                break
            
            try:
                text: str = await self.input_queue.get()
                logger.info(f"Sending text: {text}")

                if text and text.strip() != "":
                    await self.elevenlabs_ws.send(json.dumps({"text": text}))
                    await self.elevenlabs_ws.send(json.dumps({"text": " ", "flush": True}))

            except Exception as e:
                logger.error(f"XI SENDER ERROR: {e}")
    
    async def receiver(self):
        while True:
            if self.is_call_ended:
                break
            
            try:
                message = await self.elevenlabs_ws.recv()
                data: dict = json.loads(message)
                if data.get("audio"):
                    logger.info(f"Received audio data: {len(data.get('audio'))} bytes")
                    await self.output_queue.put(base64.b64decode(data["audio"]))
                elif data.get('isFinal'):
                    logger.info("Received isFinal")
            
            except Exception as e:
                logger.error(f"XI RECEIVER ERROR: {e}")    
                
    async def synthesize(self):
        await asyncio.gather(self.sender(), self.receiver())
        
    async def close_connection(self):
        self.is_call_ended = True
        
        if self.elevenlabs_ws:
            try:
                await self.elevenlabs_ws.send(json.dumps({"text": ""}))
                await self.elevenlabs_ws.close()
            except Exception:
                pass
            
            self.elevenlabs_ws = None 
            logger.debug("XI WebSocket closed")
        else:
            logger.debug("XI WebSocket already closed")