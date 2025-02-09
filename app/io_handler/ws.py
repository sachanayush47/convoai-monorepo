import asyncio
import logging

from fastapi import WebSocket
from app.lib.utils import add_message


logger = logging.getLogger(__name__)


class WebsocketIOHandler:
    def __init__(self, input_queue, output_queue, ws, messages):
        self.input_queue: asyncio.Queue = input_queue
        self.output_queue: asyncio.Queue = output_queue
        self.websocket: WebSocket = ws
        self.messages: list = messages

    async def sender(self):
        try:
            while True:
                data = await self.websocket.receive_bytes()
                await self.input_queue.put(data)
        except Exception as e:
            logger.error(f"WS RECEIVER ERROR: {e}")
    
    async def receiver(self):
        while True:
            try:
                data = await self.output_queue.get()
                await self.websocket.send_bytes(data["audio"])
                add_message(self.messages, {"role": "assistant", "content": data["text"]})
            except Exception as e:
                logger.error(f"WS SENDER ERROR: {e}")
                
    async def run(self):
        try:
            await asyncio.gather(self.sender(), self.receiver())
        except Exception as e:
            logger.error(f"WS HANDLER ERROR: {e}")
    