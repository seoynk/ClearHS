from typing import List

from .clients import get_client
from .config import CONFIG
from .models import ExtractedFields, ProductInfo

EXTRACTION_SYSTEM_PROMPT = """당신은 무역 서류(인보이스, 패킹리스트, 거래명세서 등)에서 \
상품 정보를 정확하게 추출하는 전문가입니다. 여러 문서가 섞여 있을 수 있으니 \
서로 보완되는 정보는 종합하고, 문서 간에 값이 다르면 더 구체적이고 신뢰도 높은 \
문서(거래명세서 > 인보이스 > 패킹리스트 순)를 우선하세요. 문서에 없는 정보는 \
null 또는 빈 값으로 두고 추측해서 채우지 마세요."""


def extract_product_info(combined_raw_text: str, source_documents: List[str]) -> ProductInfo:
    """raw_text에서 구조화된 필드를 뽑아내고, raw_text/source_documents를 붙여 ProductInfo로 반환."""
    response = get_client().chat.completions.parse(
        model=CONFIG["OPENAI_MODEL"],
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": combined_raw_text},
        ],
        response_format=ExtractedFields,
    )
    fields = response.choices[0].message.parsed
    return ProductInfo(
        **fields.model_dump(),
        raw_text=combined_raw_text,
        source_documents=source_documents,
    )
