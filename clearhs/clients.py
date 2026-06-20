from functools import lru_cache

from openai import OpenAI

from .config import CONFIG


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """OpenAI 클라이언트를 첫 호출 시점에만 생성한다.
    (OpenAI()는 api_key가 비어있으면 생성 시점에 바로 에러를 내기 때문에, .env 설정 전에도
    패키지 import 자체는 깨지지 않도록 실제로 호출하는 시점까지 생성을 미뤄둔다.)"""
    return OpenAI(api_key=CONFIG["OPENAI_API_KEY"])
