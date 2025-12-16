import asyncio
import logging

from fastapi import WebSocket
from app.lib.utils import add_message


logger = logging.getLogger(__name__)


class WebsocketIOHandler:
    def __init__(self, input_queue, output_queue, **kwargs):
        self.input_queue: asyncio.Queue = input_queue
        self.output_queue: asyncio.Queue = output_queue
        self.websocket: WebSocket = kwargs["websocket"]
        self.messages: list = kwargs["messages"]
        self.call_status: dict = kwargs["call_status"]
        
        self.sender_task = None
        self.receiver_task = None
        
        self.is_call_ended = False

    async def sender(self):
        try:
            while True:
                if self.is_call_ended:
                    break
                
                data = await self.websocket.receive_bytes()
                await self.input_queue.put(data)
        except Exception as e:
            logger.error(f"WS RECEIVER ERROR: {e}")
    
    async def receiver(self):
        while True:
            try:
                if self.is_call_ended:
                    break
                
                data = await self.output_queue.get()
                await self.websocket.send_bytes(data["audio"])
                add_message(self.messages, {"role": "assistant", "content": data["text"]})
            except Exception as e:
                logger.error(f"WS SENDER ERROR: {e}")
            
    async def run(self):
        try:
            self.sender_task = asyncio.create_task(self.sender())
            self.receiver_task = asyncio.create_task(self.receiver())
            
            await asyncio.gather(self.sender_task, self.receiver_task)
        except Exception as e:
            logger.error(f"WS HANDLER ERROR: {e}")
            
    async def close_connection(self):
        self.is_call_ended = True
        
        try:
            if self.sender_task:
                self.sender_task.cancel()
            if self.receiver_task:
                self.receiver_task.cancel()
            
            await self.websocket.close()
        except Exception as e:
            pass
        finally:
            self.sender_task = None
            self.receiver_task = None
            self.websocket = None
        
        logger.info("WebSocket connection closed")
    