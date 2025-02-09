import asyncio
import logging
import string

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.lib.utils import add_message


settings = get_settings()
logger = logging.getLogger(__name__)


class GroqLLM:
    SPLITTERS = (".", ",", "?", "!", ";", ":", "—", "-")
    PUNCTUATION = set(string.punctuation)
    END_MARKER = "\0"  # Null byte as end marker

    def __init__(self, input_queue, output_queue, messages):
        if settings.OPENAI_BASE_URL:
            self.client = AsyncOpenAI(base_url=settings.OPENAI_BASE_URL, api_key=settings.OPENAI_API_KEY)
        else:
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        self.input_queue: asyncio.Queue = input_queue
        self.output_queue: asyncio.Queue = output_queue
        self.sentence: str = ""
        self.messages: list = messages

    def add_to_queue(self, text: str):
        if text == GroqLLM.END_MARKER:
            # If there's any remaining sentence, queue it.
            if self.sentence:
                self.output_queue.put_nowait(self.sentence.strip())
                self.sentence = ""
            
            return
        
        stripped_text = text.strip()
        self.sentence += text
        
        if stripped_text.endswith(GroqLLM.SPLITTERS):
            self.output_queue.put_nowait(self.sentence)
            self.sentence = ""
            
    async def generate_text(self):
        logger.info(f"Generating text for messages: {self.messages}")
        
        response = await self.client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=self.messages,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices:
                content = chunk.choices[0].delta.content
                if content and content.strip() != "":
                    self.add_to_queue(content)
                    
        # Add null byte to indicate end of response
        self.add_to_queue(GroqLLM.END_MARKER)
        
    async def run(self):
        while True:
            try:
                text = await self.input_queue.get()
                logger.info(f"Transcribe user message: {text}")
                add_message(self.messages, {"role": "user", "content": text})
                await self.generate_text()
            except Exception as e:
                logger.error(f"GROQ LLM RUNNER ERROR: {e}", exc_info=True)
        