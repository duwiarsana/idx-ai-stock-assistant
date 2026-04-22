
from app.config import get_settings
from dotenv import load_dotenv

load_dotenv()
settings = get_settings()
print(f"LLM_PROVIDER: {settings.llm_provider}")
print(f"GROQ_API_KEY: {settings.groq_api_key[:5]}...")
print(f"GEMINI_API_KEY: {settings.gemini_api_key[:5]}...")
