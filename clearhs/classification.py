import json
from typing import Dict, List, Tuple

from .clients import get_openai_client
from .config import CONFIG
from .models import ClassificationResult, ProductInfo
from .rag import search_hs_knowledge

# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────
CLASSIFICATION_SYSTEM_PROMPT = """당신은 한국 관세청 품목분류(HS코드) 전문가입니다.

## 분류 절차 (반드시 이 순서대로 수행하세요)

### STEP 1: 후보 코드 목록 확인
[검색된 유사 사례] 섹션에서 등장하는 모든 HS 코드와 유사도를 확인하세요.
유사도가 높을수록 해당 상품과 관련성이 높습니다.

### STEP 2: 후보 코드 평가
각 후보 코드가 [상품정보]의 품목명·재질·용도와 맞는지 평가하세요.
- 유사도 0.7 이상: 강력한 후보 — 이 코드를 선택하지 않으려면 명확한 반증이 필요합니다.
- 유사도 0.5~0.7: 유력한 후보 — 품목 설명이 상품과 일치하면 우선 검토하세요.
- 유사도 0.5 미만: 참고만 하고 독립적으로 판단하세요.

### STEP 3: 최종 코드 선택
- 후보 코드 중에서 선택하는 경우: 해당 코드가 왜 적합한지 설명하세요.
- 후보 코드를 벗어나는 경우: 선택하지 않은 핵심 후보(최대 3개)에 대해서만 제외 이유를 설명하세요.

### STEP 4: 자기평가
- cited_chunks: 실제 참고한 청크 index만 포함 (참고하지 않은 청크는 제외)
- llm_self_eval: 검색 증거와 분류 근거의 일치도 (0~1)
  * 검색 후보 코드를 그대로 채택 + 품목설명 일치 → 0.9~1.0
  * 후보 코드 채택 + 일부 불일치 → 0.6~0.8
  * 후보 코드 없이 독자 판단 → 0.3~0.5
  * 핵심 정보(재질/용도) 부재로 불확실 → 0.3 이하

## reasoning 작성 규칙

reasoning은 반드시 아래 형식을 따르세요.
STEP 1, STEP 2 등의 표현은 reasoning에 출력하지 마세요.

[후보 제외 이유]
- 최종 판단과 직접 비교한 핵심 후보(최대 3개)에 대해서만 제외 이유를 작성하세요.
- 관련성이 낮은 후보는 나열하지 마세요.

[후보 비교]
- 최종 HS코드와 가장 유사했던 후보 2~3개를 비교하세요.
- 각 후보는 한 줄씩 아래 형식으로 작성하세요.
  • HS코드 : 일치하는 점 / 제외한 이유

[최종 판단]
- 상품의 핵심 특징(재질, 용도, 형태)을 근거로 최종 HS코드를 선택한 이유를 2~3문장으로 작성하세요.
- 추가 확인이 필요한 정보가 있으면 마지막 줄에 "확인 필요: ..." 형식으로 작성하세요.

## 주의사항
- 검색된 사례는 FTA 원산지 규정(PSR) 데이터입니다.
- 각 청크에 포함된 HS 코드를 분류 후보로만 활용하세요.
- 원산지결정기준(세번변경기준, 부가가치기준 등)은 HS 분류 근거로 사용하지 마세요.
- 상품정보에 없는 사실은 추측하지 마세요.
- reasoning은 간결하고 읽기 쉽게 작성하며, 동일한 내용을 반복하지 마세요.
"""

# ── 결정적 쿼리 생성 ──────────────────────────────────────────────────────────
def _build_queries(product_info: ProductInfo) -> List[str]:
    queries = []

    parts = [product_info.product_name]
    if product_info.materials:
        parts.append(" ".join(product_info.materials[:3]))
    queries.append(" ".join(parts))

    if product_info.usage:
        queries.append(f"{product_info.product_name} {product_info.usage} HS코드")
    else:
        queries.append(f"{product_info.product_name} HS코드 품목분류")

    if product_info.origin_country:
        queries.append(
            f"{product_info.product_name} {product_info.origin_country} 원산지기준"
        )
    return queries


def _deduplicate(hits: List[Dict]) -> List[Dict]:
    seen, result = set(), []
    for h in hits:
        if h["chunk_index"] not in seen:
            seen.add(h["chunk_index"])
            result.append(h)
    return result


# ── RAG 후보 코드 요약 (컨텍스트 주입용) ────────────────────────────────────
def _build_candidate_summary(retrieval_log: List[Dict]) -> str:
    """유사도 순 정렬 후, 코드·설명·유사도를 구조화해서 LLM에 전달.
    LLM이 후보 코드를 먼저 인지하게 만드는 것이 핵심."""
    sorted_hits = sorted(retrieval_log, key=lambda x: -x["similarity"])
    lines = ["[검색된 유사 사례 — 유사도 높은 순]"]
    for h in sorted_hits:
        code = h["metadata"].get("code", "—")
        sim  = h["similarity"]
        sig  = "★★★" if sim >= 0.7 else ("★★" if sim >= 0.5 else "★")
        lines.append(
            f"\n[{h['chunk_index']}] {sig} 유사도 {sim:.4f}  →  HS {code}\n{h['text']}"
        )
    return "\n".join(lines)


# ── 메인 분류 함수 ────────────────────────────────────────────────────────────
def classify_hs_code(
    product_info: ProductInfo,
    n_results_per_query: int = 5,
) -> Tuple[ClassificationResult, List[Dict]]:
    queries      = _build_queries(product_info)
    raw_hits: List[Dict] = []
    for q in queries:
        raw_hits.extend(search_hs_knowledge(q, n_results=n_results_per_query))
    retrieval_log = _deduplicate(raw_hits)

    candidate_summary = _build_candidate_summary(retrieval_log)

    user_content = (
        f"[상품정보]\n"
        f"{json.dumps(product_info.model_dump(exclude={'raw_text'}), ensure_ascii=False, indent=2)}"
        f"\n\n{candidate_summary}"
    )

    response = get_openai_client().chat.completions.parse(
        model=CONFIG["OPENAI_MODEL"],
        temperature=0,
        messages=[
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        response_format=ClassificationResult,
    )
    result = response.choices[0].message.parsed
    return result, retrieval_log