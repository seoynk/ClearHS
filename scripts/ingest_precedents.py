"""분류사례(품목분류 결정사례) ChromaDB 적재 모듈.

scraping.py(FTA PSR 데이터)와는 완전히 분리된 모듈입니다.
PSR은 "원산지 인정 기준"이고, 분류사례는 "실제 HS코드 분류 판례"라서
RAG 검색에서 쓰이는 방식과 메타데이터 스키마가 달라야 합니다.

사용법:
    python -m scripts.ingest_precedents --input data/classification_precedents.xlsx

데이터 컬럼 (엑셀/CSV):
    참조번호, 시행일자, 시행기관, 결정세번, 품명, 물품설명, 결정사유, 이미지건수
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearhs.config import CONFIG
from clearhs.rag import _get_collection

# ── 청크 구성 ─────────────────────────────────────────────────────────────────
SOURCE_TYPE = "classification_precedent"

REQUIRED_COLUMNS = ["참조번호", "시행일자", "시행기관", "결정세번", "품명", "물품설명", "결정사유"]


def _stable_id(reference_no: str) -> str:
    """참조번호 기반 결정적 ID. 같은 참조번호로 재실행해도 같은 ID가 나와서
    upsert 시 중복이 아니라 덮어쓰기로 처리됨 (이전에 겪은 'Insert of existing
    embedding ID' 경고 문제를 원천적으로 방지)."""
    h = hashlib.sha1(f"precedent:{reference_no}".encode("utf-8")).hexdigest()[:16]
    return f"prec_{h}"


def _normalize_hs_code(raw: str) -> str:
    """'2309.90-2099' 같은 표기를 'XXXX.XX' (4+2단위)로 정규화.
    뒤 4자리(세부 세번)는 메타데이터에 별도 보관."""
    raw = str(raw).strip()
    digits = raw.replace(".", "").replace("-", "")
    if len(digits) >= 6:
        return f"{digits[:4]}.{digits[4:6]}"
    return raw


def build_chunk_text(row: pd.Series) -> str:
    """RAG 검색 대상이 되는 본문. 물품설명 + 결정사유를 합쳐서
    '이런 물건은 → 이런 이유로 → 이 코드' 패턴을 그대로 보존."""
    product_name = str(row["품명"]).strip()
    description  = str(row["물품설명"]).strip()
    reasoning    = str(row["결정사유"]).strip()
    return (
        f"[품명] {product_name}\n"
        f"[물품설명] {description}\n"
        f"[결정사유] {reasoning}"
    )


def build_metadata(row: pd.Series) -> Dict:
    code = _normalize_hs_code(row["결정세번"])
    return {
        "source_type":   SOURCE_TYPE,
        "code":          code,
        "raw_code":      str(row["결정세번"]).strip(),
        "product_name":  str(row["품명"]).strip(),
        "reference_no":  str(row["참조번호"]).strip(),
        "effective_date": str(row["시행일자"]).strip(),
        "authority":     str(row["시행기관"]).strip(),
        "agreement":     "",   # PSR과 스키마 호환을 위해 빈 문자열로 유지
    }


# ── 적재 + train/test 분할 ───────────────────────────────────────────────────
def load_dataframe(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {path.suffix}")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"필수 컬럼이 없습니다: {missing}\n"
            f"실제 컬럼: {list(df.columns)}\n"
            f"컬럼명이 다르면 --column-map으로 매핑해주세요 (예: '품목명:품명')."
        )

    before = len(df)
    df = df.dropna(subset=["결정세번", "물품설명", "결정사유"]).reset_index(drop=True)
    if len(df) < before:
        print(f"⚠️  필수 필드 결측으로 {before - len(df)}건 제외 (남은 건수: {len(df)})")
    return df


def split_train_test(df: pd.DataFrame, test_ratio: float, seed: int):
    """결정적 train/test 분할. seed 고정으로 재실행해도 같은 분할이 나옴.
    test셋은 ChromaDB에 절대 넣지 않고 별도 JSON으로 보관 — 정확도 평가용 holdout."""
    n = len(df)
    n_test = max(1, int(n * test_ratio)) if n > 0 else 0
    rng = random.Random(seed)
    indices = list(range(n))
    rng.shuffle(indices)
    test_idx = set(indices[:n_test])

    train_df = df.iloc[[i for i in range(n) if i not in test_idx]].reset_index(drop=True)
    test_df  = df.iloc[sorted(test_idx)].reset_index(drop=True)
    return train_df, test_df


def ingest(train_df: pd.DataFrame, batch_size: int = 64) -> int:
    collection = _get_collection()
    n = len(train_df)
    inserted = 0

    for start in range(0, n, batch_size):
        batch = train_df.iloc[start:start + batch_size]
        ids, docs, metas = [], [], []
        for _, row in batch.iterrows():
            ids.append(_stable_id(row["참조번호"]))
            docs.append(build_chunk_text(row))
            metas.append(build_metadata(row))

        # add() 대신 upsert() — 같은 id로 재실행해도 안전하게 덮어씀
        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        inserted += len(ids)
        print(f"  적재 중... {inserted}/{n}")

    return inserted


def save_holdout(test_df: pd.DataFrame, out_path: Path) -> None:
    """평가용 holdout 셋 저장. evaluate_classification.py에서 읽음.
    product_info에 필요한 최소 필드 + 정답 코드를 함께 저장."""
    records = []
    for _, row in test_df.iterrows():
        records.append({
            "reference_no":  str(row["참조번호"]).strip(),
            "product_name":  str(row["품명"]).strip(),
            "description":   str(row["물품설명"]).strip(),
            "true_hs_code":  _normalize_hs_code(row["결정세번"]),
            "raw_hs_code":   str(row["결정세번"]).strip(),
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"✅ holdout 테스트셋 저장: {out_path} ({len(records)}건)")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="분류사례 데이터를 ChromaDB에 적재합니다.")
    parser.add_argument("--input", required=True, help="분류사례 엑셀/CSV 경로")
    parser.add_argument("--test-ratio", type=float, default=0.15,
                        help="평가용으로 빼둘 비율 (기본 15%%, ChromaDB에 넣지 않음)")
    parser.add_argument("--seed", type=int, default=42, help="train/test 분할 시드")
    parser.add_argument("--holdout-out", default="data/precedent_holdout.json",
                        help="holdout 테스트셋 저장 경로")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 적재 없이 통계만 출력")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    print(f"📂 데이터 로드: {input_path}")
    df = load_dataframe(input_path)
    print(f"✅ {len(df)}건 로드 완료")

    train_df, test_df = split_train_test(df, args.test_ratio, args.seed)
    print(f"📊 분할 결과 — 학습(DB 적재): {len(train_df)}건 / 평가(holdout): {len(test_df)}건")

    if args.dry_run:
        print("\n[dry-run] 첫 청크 미리보기:")
        print(build_chunk_text(train_df.iloc[0]))
        print("\n[dry-run] 메타데이터 미리보기:")
        print(json.dumps(build_metadata(train_df.iloc[0]), ensure_ascii=False, indent=2))
        print("\n--dry-run 모드라 실제 적재/저장은 하지 않았습니다.")
        return

    print(f"\n💾 ChromaDB 적재 시작 (컬렉션: {CONFIG['COLLECTION_NAME']})")
    inserted = ingest(train_df)
    print(f"✅ {inserted}건 적재 완료")

    save_holdout(test_df, Path(args.holdout_out))


if __name__ == "__main__":
    main()