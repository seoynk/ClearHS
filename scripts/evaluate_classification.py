"""분류사례 holdout셋으로 HS 코드 분류 정확도를 측정합니다.

사용법:
    python -m scripts.evaluate_classification \
        --holdout data/precedent_holdout.json \
        --output  output/eval_results.json \
        --limit   20          # 테스트용: 일부만 실행 (생략 시 전체)
        --verbose             # 건별 결과 출력
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clearhs.classification import classify_hs_code
from clearhs.models import ProductInfo


# ── 더미 ProductInfo 생성 ─────────────────────────────────────────────────────
def build_product_info(record: dict) -> ProductInfo:
    """holdout 레코드 → ProductInfo.
    실제 인보이스 없이 품명+물품설명만으로 평가하므로,
    파이프라인 전체가 아닌 분류 단계만 측정합니다."""
    return ProductInfo(
        product_name=record["product_name"],
        materials=[],
        usage=record.get("description", ""),
        origin_country=None,
        manufacturer=None,
        quantity=None,
        weight=None,
        raw_text=record.get("description", ""),
        source_documents=[],
    )


# ── 일치율 계산 ───────────────────────────────────────────────────────────────
def match_4digit(pred: str, true: str) -> bool:
    """4단위(류·호) 일치 — 가장 넓은 기준."""
    return pred.replace(".", "")[:4] == true.replace(".", "")[:4]

def match_6digit(pred: str, true: str) -> bool:
    """6단위(소호) 일치 — 실무 통관 기준."""
    return pred.replace(".", "")[:6] == true.replace(".", "")[:6]


# ── 메인 평가 루프 ────────────────────────────────────────────────────────────
def evaluate(holdout_path: Path, limit: Optional[int], verbose: bool) -> dict:
    records = json.loads(holdout_path.read_text(encoding="utf-8"))
    if limit:
        records = records[:limit]

    total   = len(records)
    results = []
    ok_4, ok_6 = 0, 0

    print(f"\n📊 평가 시작 — {total}건\n{'─'*52}")

    for i, rec in enumerate(records, 1):
        ref    = rec["reference_no"]
        true_hs = rec["true_hs_code"]

        try:
            pi  = build_product_info(rec)
            cls, log = classify_hs_code(pi)
            pred_hs  = cls.hs_code
            conf     = cls.xai_confidence or 0.0
            hit4     = match_4digit(pred_hs, true_hs)
            hit6     = match_6digit(pred_hs, true_hs)
            ok_4    += int(hit4)
            ok_6    += int(hit6)
            status   = "✅" if hit6 else ("🟡" if hit4 else "❌")
            error    = None
        except Exception as e:
            pred_hs = "ERROR"
            conf = hit4 = hit6 = 0
            status = "💥"
            error = str(e)

        result = {
            "reference_no": ref,
            "product_name": rec["product_name"],
            "true_hs":  true_hs,
            "pred_hs":  pred_hs,
            "match_4":  bool(hit4),
            "match_6":  bool(hit6),
            "confidence": round(conf, 4),
            "error": error,
        }
        results.append(result)

        if verbose or not hit6:
            print(f"[{i:3}/{total}] {status}  정답:{true_hs}  예측:{pred_hs}  "
                  f"신뢰도:{conf:.0%}  {rec['product_name'][:40]}")
        elif i % 10 == 0:
            print(f"[{i:3}/{total}] 진행 중... (4단위 {ok_4}/{i} = {ok_4/i:.0%})")

        time.sleep(0.3)  # API 레이트 리밋 여유

    # ── 요약 ─────────────────────────────────────────────────────────────────
    acc4 = ok_4 / total if total else 0
    acc6 = ok_6 / total if total else 0

    # 오답 패턴: 4단위도 틀린 케이스
    wrong = [r for r in results if not r["match_4"]]
    error_cases = [r for r in results if r["error"]]

    print(f"\n{'═'*52}")
    print(f"  4단위 일치율 (류·호):  {ok_4}/{total} = {acc4:.1%}")
    print(f"  6단위 일치율 (소호):   {ok_6}/{total} = {acc6:.1%}")
    print(f"  오류 건수:             {len(error_cases)}건")
    if wrong:
        print(f"\n  ❌ 4단위 불일치 {len(wrong)}건 (상위 5개):")
        for r in wrong[:5]:
            print(f"     정답 {r['true_hs']} → 예측 {r['pred_hs']}  {r['product_name'][:35]}")
    print(f"{'═'*52}\n")

    return {
        "summary": {
            "total": total,
            "acc_4digit": round(acc4, 4),
            "acc_6digit": round(acc6, 4),
            "error_count": len(error_cases),
        },
        "results": results,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", default="data/precedent_holdout.json")
    parser.add_argument("--output",  default="output/eval_results.json")
    parser.add_argument("--limit",   type=int, default=None,
                        help="평가할 최대 건수 (생략 시 전체 96건)")
    parser.add_argument("--verbose", action="store_true",
                        help="건별 결과를 모두 출력")
    args = parser.parse_args()

    holdout_path = Path(args.holdout)
    if not holdout_path.exists():
        print(f"❌ holdout 파일을 찾을 수 없어요: {holdout_path}")
        sys.exit(1)

    report = evaluate(holdout_path, args.limit, args.verbose)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 결과 저장: {out}")


if __name__ == "__main__":
    main()
