
import asyncio
import os
from dotenv import load_dotenv
from google.genai import Client

async def test_gemini():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    
    print(f"Testing Gemini with model: {model}")
    print(f"API Key: {api_key[:5]}...{api_key[-5:]}")
    
    client = Client(api_key=api_key)
    
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents="Hello, identify yourself briefly."
        )
        print("\nResponse:")
        print(response.text)
        print("\n✅ Gemini API connection successful!")
    except Exception as e:
        print(f"\n❌ Error connecting to Gemini API: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
