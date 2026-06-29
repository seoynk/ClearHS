from functools import lru_cache
from openai import OpenAI

from .config import CONFIG


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """OpenAI API"""
    return OpenAI(
        api_key=CONFIG["OPENAI_API_KEY"],
    )


@lru_cache(maxsize=1)
def get_upstage_client() -> OpenAI:
    """Upstage API"""
    return OpenAI(
        api_key=CONFIG["UPSTAGE_API_KEY"],
        base_url="https://api.upstage.ai/v1",
    )