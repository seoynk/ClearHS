"""ClearHS: PDF 추출 -> 구조화 -> RAG 검색 -> HS코드 분류+XAI -> FTA 판단 -> 서류검증 파이프라인."""

from .classification import classify_hs_code
from .documents import verify_required_documents
from .fta import check_fta_eligibility
from .models import (
    ClassificationResult,
    DocumentCheckResult,
    ExtractedFields,
    FTAResult,
    ProductInfo,
)
from .pdf_extraction import build_combined_raw_text, extract_text_from_pdf
from .pipeline import run_pipeline
from .product_extraction import extract_product_info
from .rag import search_hs_knowledge
from .xai import calculate_xai_confidence

__all__ = [
    "run_pipeline",
    "classify_hs_code",
    "extract_text_from_pdf",
    "build_combined_raw_text",
    "extract_product_info",
    "search_hs_knowledge",
    "calculate_xai_confidence",
    "check_fta_eligibility",
    "verify_required_documents",
    "ExtractedFields",
    "ProductInfo",
    "ClassificationResult",
    "FTAResult",
    "DocumentCheckResult",
]
