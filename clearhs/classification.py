import json
from typing import Dict, List, Tuple

from .clients import get_client
from .config import CONFIG
from .models import ClassificationResult, ProductInfo
from .rag import SEARCH_TOOL_SPEC, search_hs_knowledge

CLASSIFICATION_SYSTEM_PROMPT = """당신은 한국 관세청 품목분류(HS코드) 및 FTA 전문가입니다. \
주어진 상품정보를 바탕으로 가장 적절한 HS코드를 분류하세요. 반드시 search_hs_knowledge \
도구로 유사 분류사례나 기준을 먼저 검색하고, 검색된 내용 중 실제로 참고한 chunk_index만 \
cited_chunks에 포함하세요. llm_self_eval은 당신이 이 분류에 얼마나 확신하는지를 \
0~1 사이 값으로 스스로 평가한 것입니다."""


def classify_hs_code(
    product_info: ProductInfo, max_tool_calls: int = 3
) -> Tuple[ClassificationResult, List[Dict]]:
    """RAG 검색 도구를 활용해 HS코드를 분류한다.
    반환값: (분류 결과, 검색 로그) — 검색 로그는 XAI 신뢰도 계산에 사용."""
    messages = [
        {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(product_info.model_dump(exclude={"raw_text"}), ensure_ascii=False),
        },
    ]

    retrieval_log: List[Dict] = []
    client = get_client()

    for _ in range(max_tool_calls):
        response = client.chat.completions.create(
            model=CONFIG["OPENAI_MODEL"],
            messages=messages,
            tools=[SEARCH_TOOL_SPEC],
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            break

        messages.append(msg.model_dump(exclude_none=True))
        for tool_call in msg.tool_calls:
            args = json.loads(tool_call.function.arguments)
            hits = search_hs_knowledge(**args)
            retrieval_log.extend(hits)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(hits, ensure_ascii=False),
            })

    final = client.chat.completions.parse(
        model=CONFIG["OPENAI_MODEL"],
        messages=messages,
        response_format=ClassificationResult,
    )
    result = final.choices[0].message.parsed
    return result, retrieval_log
