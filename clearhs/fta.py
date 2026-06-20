from .models import ClassificationResult, FTAResult, ProductInfo

# TODO: 실제 FTA 협정관세 데이터 / 관세청 FTA 포털 공공 API로 교체
FTA_AGREEMENTS_BY_COUNTRY = {
    "Vietnam": ["한-아세안 FTA", "한-베트남 FTA"],
    "China": ["한-중 FTA"],
    "United States": ["한-미 FTA"],
    # ...
}


def check_fta_eligibility(product_info: ProductInfo, classification: ClassificationResult) -> FTAResult:
    agreements = FTA_AGREEMENTS_BY_COUNTRY.get(product_info.origin_country or "", [])
    eligible = len(agreements) > 0
    return FTAResult(
        eligible=eligible,
        applicable_agreements=agreements,
        required_certificate_type=(
            "원산지증명서 (자율발급 또는 기관발급, 협정별 확인 필요)" if eligible else None
        ),
        notes="실제 협정관세율/품목 적용 여부는 관세청 FTA 포털/공공 API로 추가 검증 필요",
    )
