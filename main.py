import wave
import asyncio
import time
import os
import uuid
import shutil
import websockets
import json
import requests
import subprocess
import logging
import sys
import base64

from openai import AsyncOpenAI

from io import BytesIO
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs


DEEPGRAM_API_KEY = "1ce92a4b66b3fc90938dc0569bdf4712bb533d28"
ELEVENLABS_API_KEY = "sk_f49ef9623b21de8e0afcf02dc9b831d68b00f89112dc8a83"
VOICE_ID = '21m00Tcm4TlvDq8ikWAM'

def is_installed(lib_name):
    return shutil.which(lib_name) is not None

async def text_chunker(chunks):
    """Split text into chunks, ensuring to not break sentences."""
    splitters = (".", ",", "?", "!", ";", ":", "—", "-", "(", ")", "[", "]", "}", " ")
    buffer = ""
    async for text in chunks:
        if buffer.endswith(splitters):
            yield buffer + " "
            buffer = text
        elif text.startswith(splitters):
            yield buffer + text[0] + " "
            buffer = text[1:]
        else:
            buffer += text
    if buffer:
        yield buffer + " "


class LLMHandler:
    def __init__(self):
        self.openai = AsyncOpenAI(base_url="https://api.groq.com/openai/v1")

    async def generate_text(self, messages):
        response = await self.openai.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=messages,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices:
                yield chunk.choices[0].delta.content
                

async def stream(audio_stream):
    """Stream audio data using mpv player."""
    
    if not is_installed("mpv"):
        raise ValueError(
            "mpv not found, necessary to stream audio. "
            "Install instructions: https://mpv.io/installation/"
        )
        
    mpv_process = subprocess.Popen(
        ["mpv", "--no-cache", "--no-terminal", "--", "fd://0"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    
    print("Started streaming audio")
    async for chunk in audio_stream:
        if chunk:
            mpv_process.stdin.write(chunk)
            mpv_process.stdin.flush()
    if mpv_process.stdin:
        mpv_process.stdin.close()
    mpv_process.wait()


class TextToSpeechHandler:
    def __init__(self, voice_id: str = "21m00Tcm4TlvDq8ikWAM", model_id: str = "eleven_flash_v2_5"):
        self.voice_id = voice_id
        self.model_id = model_id
        self.xi = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        self.xi_websocket: websockets.WebSocketClientProtocol | None = None
        self.logger = logging.getLogger(__name__)
    
    
    async def setup(self, voice_settings: VoiceSettings = None) -> None:
        if voice_settings is None:
            voice_settings = VoiceSettings()
        
        WEBSOCKET_URI = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input".format(voice_id=self.voice_id)
        
        try:
            self.xi_websocket = await websockets.connect(WEBSOCKET_URI)
            await self._send_initial_config(voice_settings)
            self.logger.info("Successfully established websocket connection")
        except Exception as e:
            self.logger.error(f"Failed to setup websocket connection: {str(e)}")


    async def _send_initial_config(self, voice_settings: VoiceSettings) -> None:
        config = {
            "text": " ",
            "voice_settings": {
                "stability": voice_settings.stability,
                "similarity_boost": voice_settings.similarity_boost
            },
            "xi_api_key": ELEVENLABS_API_KEY,
        }
        await self._send_message(config)

    
    async def _send_message(self, message: dict) -> None:
        if not self.xi_websocket:
            raise Exception("Websocket connection not established")
        
        try:
            await self.xi_websocket.send(json.dumps(message))
        except Exception as e:
            self.logger.error(f"Failed to send message: {str(e)}")
            raise Exception(f"Message sending failed: {str(e)}") from e


    async def close(self) -> None:
        if self.xi_websocket:
            try:
                await self._send_message({"text": ""})
                await self.xi_websocket.close()
                self.logger.info("Successfully closed websocket connection")
            except Exception as e:
                self.logger.error(f"Error during connection closure: {str(e)}")
            finally:
                self.xi_websocket = None


    async def text_to_speech_input_streaming(
        self,
        input_queue: asyncio.Queue, 
        output_queue: asyncio.Queue
    ) -> None:
        
        if not self.xi_websocket:
            raise Exception("Websocket connection not established")
        
        try:
            while True:
                text = await input_queue.get()
                if not text:
                    # Handle empty input gracefully
                    continue
                    
                await self._send_message({"text": text})
                
                async for audio_chunk in self._process_audio_stream():
                    await output_queue.put(audio_chunk)
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.error("Websocket connection closed unexpectedly")
            await self.close()
            raise Exception("Connection closed unexpectedly")
        except Exception as e:
            self.logger.error(f"Streaming error: {str(e)}")
            raise Exception(f"Streaming failed: {str(e)}") from e


    async def _process_audio_stream(self):
        if not os.path.exists("output.mp3"):
            x = open("output.mp3", "wb")
        else:
            x = open("output.mp3", "ab")
        
        while True:
            message = await self.xi_websocket.recv()
            data = json.loads(message)
            
            if data.get("audio"):
                x.write(base64.b64decode(data["audio"]))
                yield base64.b64decode(data["audio"])
            elif data.get("isFinal"):
                break
            
async def main():
    logging.basicConfig(level=logging.INFO)
    
    llm = LLMHandler()
    tts = TextToSpeechHandler()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ]
    
    input_queue = asyncio.Queue()
    output_queue = asyncio.Queue()
    
    try:
        await tts.setup()
        
        async def get_text():
            async for content in llm.generate_text(messages):
                await input_queue.put_nowait(content)
        
        asyncio.create_task(get_text())
        asyncio.create_task(tts.text_to_speech_input_streaming(input_queue, output_queue))
        # asyncio.create_task(stream(output_queue))
            
        
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await tts.close()
        
if __name__ == '__main__':
    asyncio.run(main())



# class ConversationManager:
#     def __init__(self):
#         self.llm = LLMHandler()
#         self.tts = TextToSpeechHandler()
        
#         # Queues for different data flows
#         self.audio_queue = asyncio.Queue()  # Raw audio input/output
#         self.tts_queue = asyncio.Queue()    # Text to be converted to speech
#         self.llm_queue = asyncio.Queue()    # LLM responses
#         self.stt_queue = asyncio.Queue()    # Speech-to-text results
        
#         self.logger = logging.getLogger(__name__)
#         self._running = False
#         self.conversation_history: list[Message] = []

#     def _initialize_conversation(self) -> list[dict[str, str]]:
#         """Initialize conversation with system prompt."""
#         return [
#             {"role": "system", "content": "You are a helpful assistant."},
#             *[{"role": msg.role, "content": msg.content} 
#               for msg in self.conversation_history]
#         ]

#     async def _process_llm_responses(self):
#         """Process LLM responses and forward to TTS."""
#         try:
#             while self._running:
#                 content = await self.llm_queue.get()
#                 if content:
#                     # Store in conversation history
#                     self.conversation_history.append(
#                         Message(role="assistant", content=content)
#                     )
#                     # Forward to TTS
#                     await self.tts_queue.put(content)
#         except Exception as e:
#             self.logger.error(f"Error processing LLM responses: {str(e)}")
#             raise

#     async def _process_tts_output(self):
#         """Process TTS output and send to audio queue."""
#         try:
#             while self._running:
#                 audio_data = await self.audio_queue.get()
#                 if audio_data:
#                     # Handle audio output (implement audio playback here)
#                     pass
#         except Exception as e:
#             self.logger.error(f"Error processing TTS output: {str(e)}")
#             raise

#     async def _handle_user_input(self, user_input: str):
#         """Process user input and send to LLM."""
#         self.conversation_history.append(
#             Message(role="user", content=user_input)
#         )
#         messages = self._initialize_conversation()
        
#         async for content in self.llm.generate_text(messages):
#             await self.llm_queue.put(content)

#     async def run(self, initial_prompt: Optional[str] = None):
#         """Run the conversation manager with all components."""
#         self._running = True
        
#         try:
#             # Initialize components
#             await self.tts.setup()
            
#             # Start processing tasks
#             tasks = [
#                 asyncio.create_task(self._process_llm_responses()),
#                 asyncio.create_task(self._process_tts_output()),
#                 asyncio.create_task(self.tts.text_to_speech_input_streaming(
#                     self.tts_queue, self.audio_queue
#                 ))
#             ]
            
#             # Handle initial prompt if provided
#             if initial_prompt:
#                 await self._handle_user_input(initial_prompt)
            
#             # Wait for all tasks to complete
#             await asyncio.gather(*tasks)
            
#         except Exception as e:
#             self.logger.error(f"Error in conversation manager: {str(e)}")
#             raise
#         finally:
#             self._running = False
#             await self.cleanup()

#     async def cleanup(self):
#         """Clean up resources."""
#         try:
#             await self.tts.close()
#         except Exception as e:
#             self.logger.error(f"Error during cleanup: {str(e)}")

# # Example usage
# async def main():
#     logging.basicConfig(level=logging.INFO)
    
#     manager = ConversationManager()
    
#     try:
#         await manager.run(initial_prompt="What is the capital of France?")
#     except KeyboardInterrupt:
#         print("\nShutting down gracefully...")
#     finally:
#         await manager.cleanup()

# if __name__ == "__main__":
#     asyncio.run(main())            
        

    


# async def main():
#     llm = LLMHandler()
#     messages = [
#         {"role": "system", "content": "You are a helpful assistant."},
#         {"role": "user", "content": "What is the capital of France?"},
#     ]
    
#     save_file_path = f"{uuid.uuid4()}.mp3"

#     async for content in llm.generate_text(messages):
#         stt = TextToSpeechHandler()
#         await stt.text_to_speech_input_streaming(content)
        
        

    

# if __name__ == '__main__':
#     asyncio.run(main())