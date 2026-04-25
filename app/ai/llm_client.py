"""LLM client supporting Gemini (Google), DeepSeek API, and Ollama (local)."""

import logging
from typing import Optional

import httpx
from openai import AsyncOpenAI
from google.genai import Client as GeminiClient

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMClient:
    """
    Unified LLM client that supports:
    - Gemini (Google AI Studio)
    - DeepSeek API (OpenAI-compatible)
    - Ollama local inference (OpenAI-compatible API)
    """

    def __init__(self):
        self.provider = settings.llm_provider

        if self.provider == "gemini":
            self.client = GeminiClient(api_key=settings.gemini_api_key)
            self.model = settings.gemini_model
        elif self.provider == "deepseek":
            self.client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                timeout=60.0,
            )
            self.model = settings.deepseek_model
        elif self.provider == "ollama":
            # Ollama exposes an OpenAI-compatible API
            self.client = AsyncOpenAI(
                api_key="ollama",  # Ollama doesn't need a real key
                base_url=f"{settings.ollama_base_url}/v1",
                timeout=120.0,
            )
            self.model = settings.ollama_model
        elif self.provider == "groq":
            self.client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                timeout=60.0,
            )
            self.model = settings.groq_model
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info(f"LLM client initialized: provider={self.provider}, model={self.model}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """
        Generate a response from the LLM with optional conversation history.
        """
        # Prepare messages
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            # Map history roles to LLM roles if needed (usually already 'user'/'assistant')
            messages.extend(history)
            
        messages.append({"role": "user", "content": user_prompt})

        try:
            if self.provider == "gemini":
                # For Gemini, we combine messages into one prompt or use chat session
                # Simplest is combining for now
                full_prompt = system_prompt + "\n\n"
                if history:
                    for msg in history:
                        role = "User" if msg["role"] == "user" else "Assistant"
                        full_prompt += f"{role}: {msg['content']}\n"
                full_prompt += f"User: {user_prompt}"
                
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=full_prompt,
                    config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }
                )
                return response.text
            else:
                # OpenAI-compatible clients (Groq, DeepSeek, Ollama)
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            # Return a graceful fallback
            return (
                "⚠️ Maaf, saya tidak dapat menganalisis saat ini. "
                "Silakan coba lagi dalam beberapa saat.\n\n"
                f"Error: {str(e)[:100]}"
            )

    async def check_health(self) -> bool:
        """Check if the LLM service is reachable."""
        try:
            if self.provider == "gemini":
                await self.client.aio.models.generate_content(
                    model=self.model,
                    contents="ping",
                    config={"max_output_tokens": 5}
                )
            else:
                await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                )
            return True
        except Exception as e:
            logger.warning(f"LLM health check failed ({self.provider}): {e}")
            return False


# Singleton
llm_client = LLMClient()
