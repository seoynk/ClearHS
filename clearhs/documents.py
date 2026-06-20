from .models import DocumentCheckResult, FTAResult, ProductInfo

BASE_REQUIRED_DOCUMENTS = ["invoice", "packing_list"]


def verify_required_documents(product_info: ProductInfo, fta_result: FTAResult) -> DocumentCheckResult:
    required = list(BASE_REQUIRED_DOCUMENTS)
    if fta_result.eligible:
        required.append("certificate_of_origin")

    missing = [doc for doc in required if doc not in product_info.source_documents]
    return DocumentCheckResult(
        required_documents=required,
        missing_documents=missing,
        is_complete=len(missing) == 0,
    )
