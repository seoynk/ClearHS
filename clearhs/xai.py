from typing import Dict, List

from .config import CONFIG
from .models import ClassificationResult


def calculate_xai_confidence(classification: ClassificationResult, retrieval_log: List[Dict]) -> float:
    """검색 유사도(인용된 chunk만) 40% + LLM 자체평가 60%로 최종 신뢰도를 계산."""
    cited_indices = {c.chunk_index for c in classification.cited_chunks}
    cited_similarities = [
        hit["similarity"] for hit in retrieval_log if hit["chunk_index"] in cited_indices
    ]
    retrieval_score = sum(cited_similarities) / len(cited_similarities) if cited_similarities else 0.0

    confidence = (
        CONFIG["RETRIEVAL_WEIGHT"] * retrieval_score
        + CONFIG["LLM_SELF_EVAL_WEIGHT"] * classification.llm_self_eval
    )
    return round(confidence, 4)
