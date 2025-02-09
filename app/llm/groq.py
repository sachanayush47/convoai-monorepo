import asyncio
import logging
import string

from openai import AsyncOpenAI

from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)


class GroqLLM:
    SPLITTERS = (".", ",", "?", "!", ";", ":", "—", "-")
    PUNCTUATION = set(string.punctuation)
    END_MARKER = "\0"  # Null byte as end marker

    def __init__(self, output_queue):
        if settings.OPENAI_BASE_URL:
            self.client = AsyncOpenAI(base_url=settings.OPENAI_BASE_URL, api_key=settings.OPENAI_API_KEY)
        else:
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        self.output_queue: asyncio.Queue = output_queue
        self.sentence: str = ""

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
            
    async def generate_text(self, messages):
        logger.debug(f"Generating text for messages: {messages}")
        
        response = await self.client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=messages,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices:
                content = chunk.choices[0].delta.content
                if content and content.strip() != "":
                    self.add_to_queue(content)
                    
        # Add null byte to indicate end of response
        self.add_to_queue(GroqLLM.END_MARKER)