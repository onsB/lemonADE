import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def build_llm() -> ChatOpenAI:
    """Chat model served by LM Studio, configured from .env."""
    return ChatOpenAI(
        base_url=os.environ["LMSTUDIO_BASE_URL"],
        api_key=os.environ["LMSTUDIO_API_KEY"],
        model=os.environ["LLM_MODEL"],
        temperature=0,
        timeout=300,
    )
