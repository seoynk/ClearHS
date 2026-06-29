# 0626 유림 수정 (면세 판단 로직 추가로 import 확장)
import json
from typing import Optional

from .clients import get_openai_client
from .config import CONFIG
from .models import DocumentCheckResult, ExemptionResult, FTAResult, ProductInfo
from .rag import search_hs_knowledge

BASE_REQUIRED_DOCUMENTS = ["invoice", "packing_list"]

# 0626 유림 추가
# 관세법 제88~99조 면세/감면 조항 중, 스타트업·일반 무역에서 가장 자주 부딪히는 유형만
# 추려서 LLM에게 참고 가이드로 제공한다. (시행규칙상 첨부서류는 법 본문에는 없어서
# RAG 검색만으로는 안 나오는 부분 — 실무 가이드를 시스템 프롬프트에 보강해 둠.)
# TODO: 관세청 공공API/시행규칙 데이터 확보되면 이 부분도 RAG로 대체
EXEMPTION_REFERENCE_GUIDE = """\
[참고: 관세법상 주요 면세·감면 조항 — 스타트업/일반 무역 빈출 유형]
- 관세법 제94조제3호 (상업용견본품 또는 광고용품의 면세)
  · 무상으로 제공되는 샘플/견본품, 상업적 가치가 없거나 견본임이 표시된 물품
  · 추가서류: 무상사유서, 관세감면신청서
- 관세법 제94조제4호 (소액물품 등의 면세)
  · 소액(통상 미화 250달러 이하 수준, 시행규칙 기준 변동 가능) 무상 물품
  · 추가서류: 별도 신청서 없이 수입신고 시 면세 처리 가능(케이스에 따라 다름)
- 관세법 제90조 (학술연구용품의 감면)
  · 국가기관/학교/공공연구기관 또는 기업부설연구소의 연구개발용 물품
  · 추가서류: 관세감면신청서, 기업부설연구소 인정서(해당 시), 연구계획서(해당 시)
- 관세법 제93조제2호 (박람회 등 행사용 물품의 면세)
  · 박람회·국제경기대회 등 행사 참가자가 수입하는 물품
  · 추가서류: 행사 참가 확인서, 관세감면신청서
위 유형에 명확히 해당하지 않으면 is_likely_exempt=False로 판단하세요. 확신이 낮으면 \
False로 두고 notes에 불확실성을 명시하세요. 실제 적용 여부는 세관 심사 대상이며, \
이 판단은 1차 참고용임을 notes에 반드시 포함하세요."""

# 0626 유림 추가
EXEMPTION_SYSTEM_PROMPT = f"""당신은 한국 관세법상 관세 면세·감면 대상 여부를 1차로 \
선별하는 전문가입니다. 주어진 상품정보와 search_hs_knowledge로 검색된 관세법 조항을 \
근거로, 이 물품이 면세/감면 대상에 해당할 가능성이 있는지 판단하세요. 실제로 참고한 \
조항 chunk만 cited_chunks에 포함하고, 근거 없이 추측하지 마세요.

{EXEMPTION_REFERENCE_GUIDE}"""


# 0626 유림 추가
def _build_exemption_query(product_info: ProductInfo) -> str:
    parts = [
        product_info.product_name,
        product_info.usage or "",
        product_info.intended_user or "",
        "무상 샘플 견본품 소액물품 학술연구용품 박람회 면세 감면",
    ]
    return " ".join(p for p in parts if p)


# 0626 유림 추가
def check_duty_exemption(product_info: ProductInfo, n_results: int = 6) -> ExemptionResult:
    """관세법 면세/감면 조항(제88~99조 등)을 RAG로 검색해, 해당 상품이 면세 대상일
    가능성이 있는지 LLM으로 1차 판단한다. classify_hs_code와 동일한 RAG+구조화출력 패턴."""
    query = _build_exemption_query(product_info)
    hits = search_hs_knowledge(query, n_results=n_results)

    client = get_openai_client()
    messages = [
        {"role": "system", "content": EXEMPTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "product_info": product_info.model_dump(exclude={"raw_text"}),
                    "retrieved_law_chunks": hits,
                },
                ensure_ascii=False,
            ),
        },
    ]

    response = client.chat.completions.parse(
        model=CONFIG["OPENAI_MODEL"],
        messages=messages,
        response_format=ExemptionResult,
    )
    return response.choices[0].message.parsed


# 0626 유림 수정 (exemption_result 파라미터 추가 + 면세서류 반영 로직 추가)
def verify_required_documents(
    product_info: ProductInfo,
    fta_result: FTAResult,
    exemption_result: Optional[ExemptionResult] = None,
) -> DocumentCheckResult:
    required = list(BASE_REQUIRED_DOCUMENTS)
    if fta_result.eligible:
        required.append("certificate_of_origin")
    # 0626 유림 추가
    if exemption_result and exemption_result.is_likely_exempt:
        for doc in exemption_result.additional_required_documents:
            if doc not in required:
                required.append(doc)

    missing = [doc for doc in required if doc not in product_info.source_documents]
    return DocumentCheckResult(
        required_documents=required,
        missing_documents=missing,
        is_complete=len(missing) == 0,
        exemption=exemption_result,  # 0626 유림 추가
    )