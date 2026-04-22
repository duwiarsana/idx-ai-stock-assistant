
import asyncio
import sys
import os
from dotenv import load_dotenv
from google.genai import Client

async def list_models():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    client = Client(api_key=api_key)
    
    try:
        print("Available models:")
        models = await client.aio.models.list()
        for model in models:
            print(f"- {model.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    asyncio.run(list_models())
