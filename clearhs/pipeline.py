from typing import Dict

from .classification import classify_hs_code
from .documents import verify_required_documents
from .fta import check_fta_eligibility
from .pdf_extraction import build_combined_raw_text
from .product_extraction import extract_product_info
from .xai import calculate_xai_confidence


def run_pipeline(doc_paths: Dict[str, str]) -> Dict:
    """doc_paths 예: {'invoice': '...', 'packing_list': '...', 'specification': '...'}"""
    combined_raw_text = build_combined_raw_text(doc_paths)
    product_info = extract_product_info(combined_raw_text, source_documents=list(doc_paths.keys()))

    classification, retrieval_log = classify_hs_code(product_info)
    classification.xai_confidence = calculate_xai_confidence(classification, retrieval_log)

    fta_result = check_fta_eligibility(product_info, classification)
    doc_check = verify_required_documents(product_info, fta_result)

    return {
        "product_info": product_info.model_dump(),
        "classification": classification.model_dump(),
        "fta_result": fta_result.model_dump(),
        "document_check": doc_check.model_dump(),
    }
