"""LLM client supporting Qwen3.5-397b (Primary), Groq (Fallback), and Gemini (Backup)."""

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
    Unified LLM client with auto-failover:
    - Primary: Qwen3.5-397b (via opencode MCP or local)
    - Secondary: Groq (Llama-3.3-70b) - Free, fast
    - Tertiary: Gemini (Google AI Studio) - Backup
    
    Auto-failover logic:
    1. Try Qwen3.5-397b (if available via opencode/local)
    2. If offline/unavailable → Auto-switch to Groq
    3. If Groq fails → Fallback to Gemini
    """

    def __init__(self):
        self.primary_provider = "qwen"
        self.current_provider = self.primary_provider
        
        # Initialize all clients
        self.clients = {}
        self.models = {}
        
        # Qwen3.5-397b (Primary - OpenAI-compatible API)
        try:
            qwen_url = settings.qwen_base_url or "http://localhost:8000/v1"
            qwen_key = settings.qwen_api_key or "qwen"
            self.clients["qwen"] = AsyncOpenAI(
                api_key=qwen_key,
                base_url=qwen_url,
                timeout=120.0,
            )
            self.models["qwen"] = settings.qwen_model or "qwen3.5-397b"
            logger.info(f"Qwen client initialized: {self.models['qwen']}")
        except Exception as e:
            logger.warning(f"Qwen client init failed: {e}")
        
        # Groq (Secondary - Fast, Free)
        try:
            self.clients["groq"] = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                timeout=60.0,
            )
            self.models["groq"] = settings.groq_model
            logger.info(f"Groq client initialized: {self.models['groq']}")
        except Exception as e:
            logger.warning(f"Groq client init failed: {e}")
        
        # Gemini (Tertiary - Backup)
        try:
            self.clients["gemini"] = GeminiClient(api_key=settings.gemini_api_key)
            self.models["gemini"] = settings.gemini_model
            logger.info(f"Gemini client initialized: {self.models['gemini']}")
        except Exception as e:
            logger.warning(f"Gemini client init failed: {e}")
        
        # Set current provider
        if self.current_provider not in self.clients:
            self.current_provider = "groq" if "groq" in self.clients else "gemini"
        
        logger.info(f"LLM client initialized with failover: {self.current_provider}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,  # Increased for Qwen
    ) -> str:
        """
        Generate response with auto-failover.
        Tries providers in order: Qwen → Groq → Gemini
        """
        # Prepare messages
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            messages.extend(history)
            
        messages.append({"role": "user", "content": user_prompt})
        
        # Try each provider in order
        providers_to_try = ["qwen", "groq", "gemini"]
        last_error = None
        
        for provider in providers_to_try:
            if provider not in self.clients:
                continue
            
            try:
                logger.debug(f"Trying {provider}...")
                
                if provider == "gemini":
                    # Gemini-specific handling
                    full_prompt = system_prompt + "\n\n"
                    if history:
                        for msg in history:
                            role = "User" if msg["role"] == "user" else "Assistant"
                            full_prompt += f"{role}: {msg['content']}\n"
                    full_prompt += f"User: {user_prompt}"
                    
                    response = await self.clients["gemini"].aio.models.generate_content(
                        model=self.models["gemini"],
                        contents=full_prompt,
                        config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                        }
                    )
                    result = response.text
                    
                else:
                    # OpenAI-compatible (Qwen, Groq)
                    response = await self.clients[provider].chat.completions.create(
                        model=self.models[provider],
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    result = response.choices[0].message.content
                
                # Success - update current provider
                if provider != self.current_provider:
                    logger.info(f"Switched from {self.current_provider} to {provider}")
                    self.current_provider = provider
                
                return result
                
            except Exception as e:
                logger.warning(f"{provider} failed: {e}")
                last_error = e
                continue
        
        # All providers failed
        logger.error(f"All LLM providers failed. Last error: {last_error}")
        return (
            "⚠️ Maaf, semua AI service tidak tersedia saat ini. "
            "Silakan coba lagi nanti.\n\n"
            f"Last Error: {str(last_error)[:200] if last_error else 'Unknown'}"
        )

    async def check_health(self) -> bool:
        """Check if any LLM service is reachable."""
        for provider in ["qwen", "groq", "gemini"]:
            if provider not in self.clients:
                continue
            
            try:
                if provider == "gemini":
                    await self.clients["gemini"].aio.models.generate_content(
                        model=self.models["gemini"],
                        contents="ping",
                        config={"max_output_tokens": 5}
                    )
                else:
                    await self.clients[provider].chat.completions.create(
                        model=self.models[provider],
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=5,
                    )
                logger.info(f"Health check passed: {provider}")
                return True
            except Exception as e:
                logger.debug(f"{provider} health check failed: {e}")
        
        logger.warning("All LLM providers unreachable")
        return False
    
    def get_current_provider(self) -> str:
        """Get current active provider."""
        return self.current_provider
    
    def get_provider_status(self) -> dict:
        """Get status of all providers."""
        return {
            provider: {
                "available": provider in self.clients,
                "model": self.models.get(provider, "N/A"),
            }
            for provider in ["qwen", "groq", "gemini"]
        }


# Singleton
llm_client = LLMClient()
