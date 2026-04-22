
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_gemini_connection():
    print("Testing Gemini Connection via LLMClient...")
    
    # We need to set up environment first because the client is a singleton 
    # that reads settings on import. But since we are running as a script, 
    # let's try to initialize it manually or hope it reads .env correctly.
    
    try:
        from app.ai.llm_client import LLMClient
        client = LLMClient()
        
        print(f"Provider: {client.provider}")
        print(f"Model: {client.model}")
        
        # Test 1: Health Check
        print("\nRunning health check...")
        is_healthy = await client.check_health()
        if is_healthy:
            print("✅ Health check passed!")
        else:
            print("❌ Health check failed!")
            # Let's try a direct generation to see the error
            print("\nAttempting direct generation to see error...")
            await client.generate("system", "ping")
            return

        # Test 2: Text Generation
        print("\nTesting text generation...")
        system_prompt = "You are a helpful stock assistant."
        user_prompt = "Identify yourself and say 'Sistem siap dijalankan!'"
        
        response = await client.generate(system_prompt, user_prompt)
        print(f"\nResponse from Gemini:\n{response}")
        
        if "Sistem siap dijalankan!" in response or len(response) > 10:
            print("\n✅ AI Integration SUCCESSFUL!")
        else:
            print("\n⚠️ AI Integration might have issues (response too short).")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gemini_connection())
