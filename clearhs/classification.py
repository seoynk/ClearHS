import json
from typing import Dict, List, Tuple

from .clients import get_openai_client
from .config import CONFIG
from .models import ClassificationResult, ProductInfo
from .rag import search_hs_knowledge

ST_PRECEDENT = "classification_precedent"

# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────
# 분류사례/PSR 데이터 모두 "관련 분류 정보"로 통일해서 제공.
# 소스 타입을 LLM에 명시하지 않아 reasoning 출력에 드러나지 않음.
# 내부적으로는 분류사례를 컨텍스트 앞쪽에 배치해 우선 참조하게 함.
CLASSIFICATION_SYSTEM_PROMPT = """당신은 한국 관세청 품목분류(HS코드) 전문가입니다.

## 분류 절차

### STEP 1: 후보 코드 검토
[관련 분류 정보] 섹션에서 HS 코드 후보와 유사도를 확인하세요.
유사도가 높을수록 해당 상품과 관련성이 높습니다.

- 유사도 0.6 이상: 강력한 후보 — 물품 설명이 일치하면 우선 채택
- 유사도 0.4~0.6: 유력한 후보 — 상품 특성과 대조 후 채택 여부 결정
- 유사도 0.4 미만: 참고용 — 독립적으로 판단하되 코드 범위 힌트로만 활용

### STEP 2: 최종 코드 선택
상품의 품목명·재질·용도·기능을 기준으로 가장 적합한 HS 코드를 선택하세요.
후보 코드와 다른 코드를 선택할 경우, reasoning에 그 이유를 명확히 설명하세요.

### STEP 3: 자기평가 (llm_self_eval)
- 0.9~1.0: 유사 사례와 물품 설명이 명확히 일치
- 0.7~0.9: 유사 사례를 참고했으나 일부 불일치
- 0.5~0.7: 유사 사례가 부족하거나 간접적으로 참고
- 0.3~0.5: 사례 없이 품목 특성만으로 판단
- 0.3 이하: 핵심 정보(재질/용도) 부재로 불확실

## 주의사항
- 상품정보에 없는 사실을 추측해 분류하지 마세요.
- 불확실한 정보는 reasoning에서 "확인 필요"로 명시하세요.
- cited_chunks는 실제로 참고한 항목만 포함하세요."""


# ── 쿼리 생성 ────────────────────────────────────────────────────────────────
def _build_queries(product_info: ProductInfo) -> List[str]:
    queries = []

    parts = [product_info.product_name]
    if product_info.materials:
        parts.append(" ".join(product_info.materials[:3]))
    queries.append(" ".join(parts))

    if product_info.usage:
        queries.append(f"{product_info.product_name} {product_info.usage}")
    else:
        queries.append(f"{product_info.product_name} 품목분류 결정")

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


# ── 컨텍스트 구성 ─────────────────────────────────────────────────────────────
# 분류사례를 앞에, PSR을 뒤에 배치 (소스 타입 태그는 LLM에 노출하지 않음)
def _build_candidate_summary(retrieval_log: List[Dict]) -> str:
    precedents = sorted(
        [h for h in retrieval_log if h["metadata"].get("source_type") == ST_PRECEDENT],
        key=lambda x: -x["similarity"],
    )
    others = sorted(
        [h for h in retrieval_log if h["metadata"].get("source_type") != ST_PRECEDENT],
        key=lambda x: -x["similarity"],
    )

    lines = ["[관련 분류 정보 — 유사도 높은 순]"]
    for h in precedents + others:
        code = h["metadata"].get("code", "—")
        sim  = h["similarity"]
        sig  = "★★★" if sim >= 0.7 else ("★★" if sim >= 0.5 else "★")
        lines.append(
            f"\n[{h['chunk_index']}] {sig} 유사도 {sim:.4f} | HS {code}\n{h['text']}"
        )
    return "\n".join(lines)


# ── 메인 분류 함수 ────────────────────────────────────────────────────────────
def classify_hs_code(
    product_info: ProductInfo,
    n_results_per_query: int = 5,
) -> Tuple[ClassificationResult, List[Dict]]:
    queries = _build_queries(product_info)
    raw_hits: List[Dict] = []
    for q in queries:
        raw_hits.extend(search_hs_knowledge(q, n_results=n_results_per_query))
    retrieval_log = _deduplicate(raw_hits)

    user_content = (
        f"[상품정보]\n"
        f"{json.dumps(product_info.model_dump(exclude={'raw_text'}), ensure_ascii=False, indent=2)}"
        f"\n\n{_build_candidate_summary(retrieval_log)}"
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
    return response.choices[0].message.parsed, retrieval_log