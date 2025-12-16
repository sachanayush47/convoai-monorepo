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
        
        self.sender_task = None
        self.receiver_task = None
        
        self.is_call_ended = False
        
                                            # All are in seconds
        self.max_buffer_time = 3            # Configurable buffer limit
        self.current_buffer_time = 0.0      # Tracks client's estimated buffer
        self.last_update_time = None        # For time tracking
        
        self.sender_task = None
        self.receiver_task = None
        self.is_call_ended = False

    async def receiver(self):
        self.output_queue
        
        try:
            while True:
                if self.is_call_ended:
                    break
                
                data = await self.websocket.receive_bytes()
                await self.input_queue.put(data)
        except Exception as e:
            logger.error(f"WS RECEIVER ERROR: {e}")
    
    async def sender(self):
        loop = asyncio.get_event_loop()
        self.last_update_time = loop.time()
        
        while True:
            try:
                if self.is_call_ended:
                    break
                
                data = await self.output_queue.get()
                data_duration = data["duration_ms"] / 1000
                
                # Update buffer time based on elapsed time
                current_time = loop.time()
                elapsed = current_time - self.last_update_time
                self.current_buffer_time = max(self.current_buffer_time - elapsed, 0.0)
                
                # Buffer control logic
                if self.current_buffer_time + data_duration > self.max_buffer_time:
                    # Calculate needed sleep time to maintain buffer limit
                    excess = (self.current_buffer_time + data_duration) - self.max_buffer_time
                    await asyncio.sleep(excess + (self.max_buffer_time / 2))
                    
                    # Update buffer time after sleeping
                    current_time_after_sleep = loop.time()
                    elapsed_sleep = current_time_after_sleep - current_time
                    self.current_buffer_time = max(self.current_buffer_time - elapsed_sleep, 0.0)
                
                await self.websocket.send_bytes(data["audio"])
                add_message(self.messages, {"role": "assistant", "content": data["text"]})
                
                # Update buffer tracking
                self.current_buffer_time += data_duration
                self.last_update_time = loop.time()

            except asyncio.CancelledError:
                raise
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
    