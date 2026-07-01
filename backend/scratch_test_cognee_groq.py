import asyncio
import cognee

async def test():
    cognee.config.set_llm_provider("openai")
    cognee.config.set_llm_endpoint("https://api.groq.com/openai/v1")
    cognee.config.set_llm_model("groq/llama-3.3-70b-versatile")
    
    cognee.config.set_embedding_provider("fastembed")
    cognee.config.set_embedding_model("BAAI/bge-small-en-v1.5")
    cognee.config.set_embedding_dimensions(384)
    
    # Load API key from settings or config
    import sys
    sys.path.insert(0, ".")
    from core.config import settings
    cognee.config.set_llm_api_key(settings.GROQ_API_KEY)
    
    # Bypass connection test for embedding since it's local
    import os
    os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true"
    
    print("Testing remember/recall with OpenAI provider + Groq endpoint...")
    try:
        await cognee.remember("Alice likes dynamic programming.", dataset_name="test_alice")
        print("Remember succeeded!")
        res = await cognee.recall("What does Alice like?", datasets=["test_alice"])
        print("Recall succeeded! Result:", res)
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    asyncio.run(test())
