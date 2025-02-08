import asyncio
from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()


class GroqLLM:
    def __init__(self, output_queue):
        if settings.OPENAI_BASE_URL:
            self.client = AsyncOpenAI(base_url=settings.OPENAI_BASE_URL, api_key=settings.OPENAI_API_KEY)
        else:
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        self.output_queue: asyncio.Queue = output_queue
        self.sentence: str = ""

    def add_to_queue(self, text: str):
        splitters = (".", ",", "?", "!", ";", ":", "—", "-")
        
        if text.strip().endswith(splitters):
            self.sentence += text
            self.output_queue.put_nowait(self.sentence)
            self.sentence = ""
        else:
            self.sentence += text + " "
    
    async def generate_text(self, messages):
        
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
    