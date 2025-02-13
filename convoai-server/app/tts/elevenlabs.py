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
        self.call_status = kwargs["call_status"]
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
        """
        EXAMPLE RESPONSE:
        {
            "audio": "Y3VyaW91cyBtaW5kcyB0aGluayBhbGlrZSA6KQ==",
            "isFinal": false,
            "normalizedAlignment": {
                "charStartTimesMs": [0, 3, 7, 9, 11, 12, 13, 15, 17, 19, 21],
                "charDurationsMs": [3, 4, 2, 2, 1, 1, 2, 2, 2, 2, 3],
                "chars": ["H", "e", "l", "l", "o", " ", "w", "o", "r", "l", "d"]
            },
            "alignment": {
                "charStartTimesMs": [0, 3, 7, 9, 11, 12, 13, 15, 17, 19, 21],
                "charDurationsMs": [3, 4, 2, 2, 1, 1, 2, 2, 2, 2, 3],
                "chars": ["H", "e", "l", "l", "o", " ", "w", "o", "r", "l", "d"]
            }
        }
        """
        
        while True:
            if self.is_call_ended:
                break
            
            try:
                message = await self.elevenlabs_ws.recv()
                data: dict = json.loads(message)
                if data.get("audio"):
                    logger.info(f"Received audio data: {len(data.get('audio'))} bytes")
                    await self.output_queue.put({
                        "audio": base64.b64decode(data.get("audio")),
                        "text": "".join(data.get("alignment", {}).get("chars", [])),
                        "duration_ms": sum(data.get("alignment", {}).get("charDurationsMs", [])),
                    })
                if data.get('isFinal'):
                    logger.info("Received isFinal")
            
            except Exception as e:
                logger.error(f"XI RECEIVER ERROR: {e}")    
                
    async def synthesize(self):
        self.sender_task = asyncio.create_task(self.sender())
        self.receiver_task = asyncio.create_task(self.receiver())
        await asyncio.gather(self.sender_task, self.receiver_task)
        
    async def close_connection(self):
        self.is_call_ended = True
        
        if self.elevenlabs_ws:
            try:
                await self.elevenlabs_ws.send(json.dumps({"text": ""}))
                await self.elevenlabs_ws.close()
            except Exception:
                pass
            
            self.elevenlabs_ws = None 
            logger.info("XI WebSocket closed")
        else:
            logger.info("XI WebSocket already closed")
        
        try:
            if self.sender_task:
                self.sender_task.cancel()
            if self.receiver_task:
                self.receiver_task.cancel()
        except Exception:
            pass
            
        self.sender_task = None
        self.receiver_task = None
        self.elevenlabs_ws = None