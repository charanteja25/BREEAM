#!/usr/bin/env python3

import os
from dotenv import load_dotenv
import litellm

load_dotenv()

CHAT_MODEL = os.environ["LLM_PROVIDER_MODEL"]
EMBEDDING_MODEL = os.environ["EMBEDDING_MODEL"]

def judge(system_prompt: str, user_prompt: str) -> str:
    response = litellm.completion(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content

def embed(text: str) -> list[float]:
    response = litellm.embedding(model=EMBEDDING_MODEL, input=[text])
    return response.data[0]["embedding"]

if __name__ == "__main__":
    print("Testing chat model...")
    print(judge("You are a helpful assistant.", "Say hello in exactly 3 words."))
    print("\nTesting embedding model...")
    vec = embed("Transport assessment and travel plan")
    print(f"Got a {len(vec)}-dimension embedding vector.")

