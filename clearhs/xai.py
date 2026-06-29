from typing import Dict, List

from .config import CONFIG
from .models import ClassificationResult


# 0630 서연 추가 — ChromaDB cosine similarity를 신뢰도 계산에 적합하도록 보정
# (0.6 전후도 실제 검색에서는 충분히 높은 유사도이므로 구간별로 정규화)
def normalize_similarity(sim: float) -> float:
    if sim >= 0.80:
        return 1.00
    elif sim >= 0.70:
        return 0.95
    elif sim >= 0.60:
        return 0.90
    elif sim >= 0.50:
        return 0.80
    elif sim >= 0.40:
        return 0.65
    return sim


def calculate_xai_confidence(
    classification: ClassificationResult,
    retrieval_log: List[Dict],
) -> float:
    """
    XAI 신뢰도 계산

    - 검색 근거: 실제 인용된 청크 중 가장 높은 유사도
    - LLM 자체평가: 모델의 분류 확신도
    """

    cited_indices = {
        c.chunk_index
        for c in classification.cited_chunks
    }

    cited_similarities = [
        hit["similarity"]
        for hit in retrieval_log
        if hit["chunk_index"] in cited_indices
    ]

    # 0630 서연 수정 — 평균이 아닌 가장 높은 검색 유사도를 대표값으로 사용
    retrieval_score = (
        max(cited_similarities)
        if cited_similarities
        else 0.0
    )

    # 0630 서연 추가 — 검색 유사도 정규화
    retrieval_score = normalize_similarity(retrieval_score)

    confidence = (
        CONFIG["RETRIEVAL_WEIGHT"] * retrieval_score
        + CONFIG["LLM_SELF_EVAL_WEIGHT"] * classification.llm_self_eval
    )

    return round(min(confidence, 1.0), 4)