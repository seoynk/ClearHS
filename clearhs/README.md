# ClearHS 파이프라인 (모듈화 버전)

검증 노트북(`ClearHS_pipeline_validation.ipynb`)에서 확인한 로직을 그대로 `.py` 모듈로 옮긴 패키지입니다.

## 설치 위치

이 `clearhs/` 폴더를 프로젝트 루트(예: `customs-rag/`)에 두세요. `chroma_db/`가 같은 위치(`customs-rag/chroma_db`)에 있다면 `.env`에서 `CHROMA_DB_PATH`를 비워둬도 자동으로 잡힙니다.

```
customs-rag/
├── clearhs/          <- 이 패키지
├── chroma_db/         <- 기존에 구축한 컬렉션
├── .env                <- .env.example 참고해서 작성
└── ...
```

## 모듈 구성

| 파일 | 역할 |
|---|---|
| `config.py` | 환경설정 (.env 로드, ChromaDB 경로 등) |
| `clients.py` | OpenAI 클라이언트 (lazy 생성) |
| `models.py` | Pydantic 스키마 (ExtractedFields, ProductInfo, ClassificationResult 등) |
| `pdf_extraction.py` | 1단계: PDF → Raw Text |
| `product_extraction.py` | 2단계: Raw Text → 구조화된 ProductInfo |
| `rag.py` | 3단계: ChromaDB + bge-m3 검색 도구 (`search_hs_knowledge`) |
| `classification.py` | 4단계: Tool calling 기반 HS코드 분류 (`classify_hs_code`) |
| `xai.py` | 5단계: XAI 신뢰도 계산 |
| `fta.py` | 6단계: FTA 적용 가능성 판단 (stub) |
| `documents.py` | 7단계: 필요서류 검증 |
| `pipeline.py` | 8단계: 전체 파이프라인 (`run_pipeline`) |
| `__main__.py` | CLI (`python -m clearhs invoice.pdf packing_list.pdf ...`) |

## 사용 예시

```python
from clearhs import run_pipeline

result = run_pipeline({
    "invoice": "invoice.pdf",
    "packing_list": "packing_list.pdf",
    "specification": "specification.pdf",
})
print(result["classification"]["hs_code"], result["classification"]["xai_confidence"])
```

또는 CLI로:

```bash
python -m clearhs invoice.pdf packing_list.pdf specification.pdf
```

## 다음 단계 (LangGraph)

- `classify_hs_code`의 tool-calling 루프 → `ToolNode` + 조건부 엣지
- `run_pipeline`의 각 단계 함수 → 각각 그래프 노드
- `xai_confidence`가 낮을 때 사람 확인 단계로 분기 → HITL 엣지
- `fta.py`, undervaluation risk detection → 실제 공공 API 연동 필요 (현재 stub)
