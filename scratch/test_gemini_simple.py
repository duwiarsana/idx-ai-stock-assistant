
import sys
import os
from dotenv import load_dotenv

print("Script started")
load_dotenv()

try:
    from google import genai
    print("Import successful")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

api_key = os.getenv("GEMINI_API_KEY")
print(f"API Key: {api_key[:5]}...{api_key[-5:]}")

client = genai.Client(api_key=api_key)
print("Client created")

try:
    print("Generating content...")
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Say 'OK'"
    )
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Generation failed: {e}")
