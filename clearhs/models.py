from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractedFields(BaseModel):
    """LLM이 문서 원문에서 구조화하여 채우는 필드. raw_text는 포함하지 않음."""

    product_name: str = Field(description="상품명")
    materials: List[str] = Field(default_factory=list, description="원재료/소재 목록")
    usage: Optional[str] = Field(default=None, description="용도")
    origin_country: Optional[str] = Field(default=None, description="원산지 국가")
    manufacturer: Optional[str] = Field(default=None, description="제조사")
    quantity: Optional[str] = Field(default=None, description="수량")
    weight: Optional[str] = Field(default=None, description="중량")
    # 260624 유림 추가
    unit_price: Optional[str] = Field(default=None, description="단가 (면세/가격검증 판단용)")
    currency: Optional[str] = Field(default=None, description="통화 단위 (KRW, USD 등)")
    intended_user: Optional[str] = Field(default=None, description="연구용/전시용/상업용 견본 등")



class ProductInfo(ExtractedFields):
    """ExtractedFields + raw_text. 파이프라인 전체에서 사용하는 최종 스키마."""

    raw_text: str = Field(description="업로드된 문서들의 원문 전체 텍스트 (LLM 컨텍스트/RAG용)")
    source_documents: List[str] = Field(
        default_factory=list,
        description="원문에 포함된 문서 종류 (invoice, packing_list, specification 등)",
    )


class CitedChunk(BaseModel):
    chunk_index: str
    similarity: float
    snippet: str


class ClassificationResult(BaseModel):
    hs_code: str
    hs_code_description: Optional[str] = None
    reasoning: str = Field(description="분류 근거 설명")
    cited_chunks: List[CitedChunk] = Field(default_factory=list)
    llm_self_eval: float = Field(ge=0, le=1, description="LLM이 스스로 평가한 분류 확신도 (0~1)")
    xai_confidence: Optional[float] = Field(
        default=None, description="최종 XAI 신뢰도 (검색유사도 40% + LLM자체평가 60%)"
    )


class FTAResult(BaseModel):
    eligible: bool
    applicable_agreements: List[str] = Field(default_factory=list)
    required_certificate_type: Optional[str] = None
    notes: Optional[str] = None
    # 0629 유림 추가 — PSR(품목별원산지결정기준) 실데이터 매칭 결과
    origin_criterion: Optional[str] = Field(
        default=None, description="분류된 HS코드에 해당하는 PSR 원산지결정기준 원문 (예: CTH, 완전생산기준 등)"
    )
    reasoning: Optional[str] = Field(default=None, description="판단 근거 설명")
    cited_chunks: List[CitedChunk] = Field(default_factory=list)
    llm_self_eval: float = Field(default=0.0, ge=0, le=1, description="매칭 확신도 (PSR 코드 정확매칭이면 높음)")


# 260624 유림 추가
class ExemptionResult(BaseModel):
    is_likely_exempt: bool
    exemption_category: Optional[str] = None   # "상업용 견본품/무상 샘플" 등
    exemption_basis: Optional[str] = None        # "관세법 제94조제3호"
    additional_required_documents: List[str] = Field(default_factory=list)
    reasoning: str
    cited_chunks: List[CitedChunk] = Field(default_factory=list)
    llm_self_eval: float = 0.0
    notes: Optional[str] = None


class DocumentCheckResult(BaseModel):
    required_documents: List[str]
    missing_documents: List[str]
    is_complete: bool
    # 260624 유림 추가 — 기본값 None 빠져있던 거 추가함 (없으면 documents.py에서
    # exemption 안 넘기는 기존 호출들이 다 에러남)
    exemption: Optional[ExemptionResult] = None