import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from .config import CONFIG
from .models import CitedChunk, ClassificationResult, FTAResult, ProductInfo

# 0629 유림 추가
# 국가별 적용 가능한 FTA 협정 + 그 협정의 PSR(품목별원산지결정기준) csv 매핑.
# PSR 데이터가 없는 국가는 psr_config_key=None으로 두면 협정명만 보여주고
# origin_criterion 조회는 스킵된다. (베트남 등 PSR 데이터 확보되면 여기에 csv만 추가)
FTA_AGREEMENTS_BY_COUNTRY = {
    "United States": {"agreements": ["한-미 FTA"], "psr_config_key": "PSR_US_CSV"},
    "China": {"agreements": ["한-중 FTA"], "psr_config_key": "PSR_CN_CSV"},
    "Vietnam": {"agreements": ["한-아세안 FTA", "한-베트남 FTA"], "psr_config_key": None},
}

# 0629 유림 추가 — LLM이 추출한 origin_country 표기가 제각각일 수 있어서 정규화
# (예: "USA", "U.S.", "미국" 등이 전부 "United States"로 매칭되게)
_COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.a": "United States",
    "u.s": "United States", "america": "United States", "미국": "United States",
    "china": "China", "중국": "China", "prc": "China", "p.r.c": "China",
    "vietnam": "Vietnam", "베트남": "Vietnam", "viet nam": "Vietnam",
}


def _normalize_country(name: Optional[str]) -> str:
    if not name:
        return ""
    key = name.strip().lower().rstrip(".")
    return _COUNTRY_ALIASES.get(key, name.strip())


def _digits_only(code: str) -> str:
    return re.sub(r"\D", "", code or "")


@lru_cache(maxsize=4)
def _load_psr_rows(csv_path: str) -> Tuple[Tuple[str, str], ...]:
    """PSR csv를 읽어 (code, content) 튜플로 캐싱한다. 파일 없으면 빈 튜플."""
    path = Path(csv_path)
    if not path.exists():
        return tuple()
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return tuple((row["code"], row["content"]) for row in reader)


def _parse_code_range(code: str) -> Optional[Tuple[int, int]]:
    """'0101-0106', '0902 – 0903' 같은 4단위 범위 표기를 (시작, 끝) 정수쌍으로 변환.
    범위 표기가 아니면 None."""
    normalized = code.replace("–", "-").replace("—", "-")
    m = re.match(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$", normalized)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _match_psr_rule(hs_code: str, psr_rows: Tuple[Tuple[str, str], ...]) -> Optional[Tuple[str, str]]:
    """분류된 hs_code에 해당하는 PSR 규정 1건을 찾는다.
    1순위: 6단위 소호 정확매칭 (예: '0901.12') — 더 구체적인 기준이라 우선
    2순위: 4단위 범위('0101-0106') 또는 단일('1101') 매칭"""
    digits = _digits_only(hs_code)
    if len(digits) < 4:
        return None
    heading4 = int(digits[:4])
    subheading6 = digits[:6] if len(digits) >= 6 else None

    if subheading6:
        for code, content in psr_rows:
            if "." in code and _digits_only(code) == subheading6:
                return code, content

    for code, content in psr_rows:
        rng = _parse_code_range(code)
        if rng is not None:
            if rng[0] <= heading4 <= rng[1]:
                return code, content
        elif "." not in code and _digits_only(code) == str(heading4):
            return code, content

    return None


def check_fta_eligibility(product_info: ProductInfo, classification: ClassificationResult) -> FTAResult:
    """원산지 국가에 적용 가능한 FTA협정을 찾고, 분류된 HS코드를 PSR(품목별원산지결정기준)
    실데이터에 코드매칭해서 원산지결정기준 원문을 같이 보여준다.

    RAG+LLM이 아니라 코드 패턴 매칭을 쓰는 이유: PSR 코드는 'HS코드 → 기준 텍스트'로
    1:1 매핑되는 구조화 데이터라서, 의미 기반 유사도 검색보다 정확매칭이 더 정확하고
    빠르고(추가 LLM 호출 없음) 결과가 항상 같다(재현 가능)."""
    normalized_country = _normalize_country(product_info.origin_country)
    country_info = FTA_AGREEMENTS_BY_COUNTRY.get(normalized_country)
    if not country_info:
        return FTAResult(
            eligible=False,
            notes=f"원산지 국가 '{product_info.origin_country or '미확인'}'에 대해 등록된 FTA 데이터가 없습니다.",
        )

    agreements = country_info["agreements"]
    psr_key = country_info.get("psr_config_key")

    origin_criterion: Optional[str] = None
    cited_chunks: List[CitedChunk] = []
    reasoning_parts = [f"원산지국({product_info.origin_country}) 기준 적용 가능 협정: {', '.join(agreements)}"]

    if psr_key and CONFIG.get(psr_key):
        psr_rows = _load_psr_rows(CONFIG[psr_key])
        match = _match_psr_rule(classification.hs_code, psr_rows)
        if match:
            matched_code, matched_content = match
            origin_criterion = matched_content.strip()
            preview = origin_criterion.replace("\n", " ")[:80]
            reasoning_parts.append(
                f"HS {classification.hs_code} → PSR 코드 '{matched_code}' 매칭, 원산지결정기준: {preview}..."
            )
            cited_chunks.append(
                CitedChunk(
                    chunk_index=f"psr_{matched_code}",
                    similarity=1.0,
                    snippet=origin_criterion[:200],
                )
            )
        else:
            reasoning_parts.append(f"HS {classification.hs_code}에 정확히 매칭되는 PSR 항목을 찾지 못함 (수동 확인 필요)")
    elif psr_key is None:
        reasoning_parts.append("이 협정은 아직 PSR 데이터가 연결되지 않아 원산지결정기준 자동조회는 지원되지 않음")

    return FTAResult(
        eligible=True,
        applicable_agreements=agreements,
        required_certificate_type="원산지증명서 (자율발급 또는 기관발급, 협정별 확인 필요)",
        origin_criterion=origin_criterion,
        reasoning=" / ".join(reasoning_parts),
        cited_chunks=cited_chunks,
        llm_self_eval=0.85 if origin_criterion else 0.4,
        notes=(
            "PSR 매칭은 HS코드 패턴 기반 1차 조회 결과이며 LLM 판단이 아닙니다. "
            "실제 협정관세율 적용 여부와 정확한 원산지 충족 여부는 관세사·세관 확인이 필요합니다."
        ),
    )