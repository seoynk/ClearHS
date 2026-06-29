"""ClearHS 파이프라인 Streamlit 테스트 UI
실행: streamlit run app.py  (프로젝트 루트에서)
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Set
from clearhs.xai import normalize_similarity

import streamlit as st

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClearHS – HS 코드 분류",
    page_icon="🛃",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Apple HIG 스타일 ──────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                 "Helvetica Neue", Arial, sans-serif;
}
.stApp { background: #f5f5f7; }

/* 카드 */
.ac {
    background: #fff;
    border-radius: 18px;
    padding: 22px 24px;
    margin-bottom: 14px;
    box-shadow: 0 2px 14px rgba(0,0,0,0.07);
}

/* 섹션 라벨 */
.section-label {
    font-size: 11px; font-weight: 600; letter-spacing: 1px;
    color: #6e6e73; text-transform: uppercase; margin-bottom: 12px;
}

/* HS 코드 */
.hs-num {
    font-size: 3.2rem; font-weight: 700; letter-spacing: 1px;
    color: #0071e3; line-height: 1;
}
.hs-desc { font-size: 13px; color: #6e6e73; margin-top: 6px; line-height: 1.5; }

/* 상품정보 그리드 */
.info-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-top: 4px; }
.info-cell { background: #f5f5f7; border-radius: 12px; padding: 12px 14px; }
.info-cell .lbl { font-size: 11px; color: #6e6e73; margin-bottom: 4px; }
.info-cell .val { font-size: 15px; font-weight: 600; color: #1d1d1f; }

/* 인용 배지 */
.cited-badge {
    background: #34c759; color: #fff; font-size: 10px; font-weight: 600;
    padding: 2px 8px; border-radius: 20px; margin-left: 7px; vertical-align: middle;
}

/* 태그 */
.tag { display: inline-block; border-radius: 20px; font-size: 11px;
       font-weight: 500; padding: 3px 10px; margin: 2px; }
.tag-blue   { background: #e8f1fd; color: #0071e3; }
.tag-green  { background: #e8f8ee; color: #1a7f3c; }
.tag-orange { background: #fff4e5; color: #a85900; }
.tag-gray   { background: #f0f0f2; color: #555; }

/* 청크 카드 */
.chunk-cited { border: 2px solid #34c759; background: #f0fdf4;
               border-radius: 14px; padding: 16px; margin-bottom: 10px; }
.chunk-other { border: 1.5px solid #e5e5ea; background: #fafafa;
               border-radius: 14px; padding: 16px; margin-bottom: 10px; opacity: 0.65; }
.sim-bar-bg  { background: #e5e5ea; border-radius: 4px; height: 5px;
               overflow: hidden; margin: 8px 0; }
.chunk-text  { font-size: 12px; color: #4a4a55; line-height: 1.65;
               font-family: monospace; white-space: pre-wrap; margin-top: 8px; }

/* Streamlit 요소 보정 */
div[data-testid="stExpander"] {
    background: #fff; border-radius: 14px;
    border: 1.5px solid #e5e5ea !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05);
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 유틸 / 시각화 헬퍼
# ═══════════════════════════════════════════════════════════════════════════════

# 0630 서연 추가 — PDF 원문 청크의 줄바꿈과 중복 줄을 정리하여
# 화면에서 읽기 쉽게 표시하기 위한 후처리 (DB 데이터는 변경하지 않음)
def pretty_chunk(text: str) -> str:
    """RAG 검색 결과 텍스트 정리."""

    # CRLF → LF
    text = text.replace("\r\n", "\n")

    # 빈 줄 정리
    text = re.sub(r"\n{2,}", "\n", text)

    # 같은 줄이 연속되면 하나 제거
    lines, prev = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line or line == prev:
            continue
        lines.append(line)
        prev = line
    text = "\n".join(lines)

    # 문장이 중간에서 끊긴 경우 이어붙이기
    text = re.sub(r"(?<=[가-힣A-Za-z0-9)])\n(?=[가-힣A-Za-z(])", " ", text)
    return text.strip()


def render_confidence_card(conf: float, retrieval_score: float, llm_self_eval: float,
                            ret_w: float = 0.4, llm_w: float = 0.6) -> str:
    """XAI 신뢰도 — 큰 수치 pill + 분해 바."""
    if conf >= 0.75:
        color, bg, label = "#34c759", "#f0fdf4", "높음"
    elif conf >= 0.5:
        color, bg, label = "#ff9f0a", "#fff8ed", "보통"
    else:
        color, bg, label = "#ff3b30", "#fff1f0", "낮음"

    rc, lc = ret_w * retrieval_score, llm_w * llm_self_eval

    def bar(emoji, name, score, weight, contrib, bar_color):
        return f"""
<div style="margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px">
    <span style="font-size:13px;color:#1d1d1f;font-weight:500">{emoji}&nbsp;{name}</span>
    <span style="font-size:12px;font-weight:700;color:{bar_color};font-variant-numeric:tabular-nums">
      {weight:.0%} × {score:.3f} = {contrib:.3f}
    </span>
  </div>
  <div style="background:#f0f0f2;border-radius:6px;height:8px;overflow:hidden">
    <div style="background:{bar_color};width:{contrib*100:.1f}%;height:100%;border-radius:6px;
                min-width:{2 if contrib>0 else 0}px"></div>
  </div>
</div>"""

    if conf >= 0.75:
        alert_bg, alert_tc, alert_msg = "#e8f8ee", "#1a7f3c", "✅ 높은 신뢰도로 분류되었습니다."
    elif conf >= 0.5:
        alert_bg, alert_tc, alert_msg = "#fff8ed", "#a85900", "ℹ️ 추가 검토를 권장합니다."
    else:
        alert_bg, alert_tc, alert_msg = "#fff1f0", "#c0392b", "⚠️ 신뢰도가 낮습니다. 직접 검토해주세요."

    return f"""
<div class="ac" style="margin-bottom:0">
  <div class="section-label">XAI 신뢰도</div>
  <div style="text-align:center;padding:18px 0 22px">
    <div style="display:inline-flex;flex-direction:column;align-items:center;
                background:{bg};border-radius:24px;padding:16px 38px">
      <span style="font-size:50px;font-weight:700;color:{color};line-height:1;
                   letter-spacing:-1px;font-variant-numeric:tabular-nums">{conf:.0%}</span>
      <span style="font-size:13px;color:{color};margin-top:5px;font-weight:500">{label}</span>
    </div>
  </div>
  <div style="background:#f0f0f2;border-radius:8px;height:10px;overflow:hidden;margin-bottom:22px">
    <div style="background:linear-gradient(90deg,{color}cc,{color});
                width:{conf*100:.1f}%;height:100%;border-radius:8px"></div>
  </div>
  <div class="section-label">신뢰도 산정 근거</div>
  {bar("🔍","검색 근거 점수", retrieval_score, ret_w, rc, "#0071e3")}
  {bar("🤖","AI 자체 확신도",   llm_self_eval,  llm_w, lc, "#5856d6")}
  <div style="border-top:1px solid #f0f0f2;padding-top:12px;margin-top:4px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <span style="font-size:13px;color:#6e6e73">합계</span>
      <span style="font-size:20px;font-weight:700;color:#1d1d1f;
                   font-variant-numeric:tabular-nums">{conf:.1%}</span>
    </div>
    <div style="background:{alert_bg};border-radius:10px;padding:10px 14px;
                font-size:13px;color:{alert_tc}">{alert_msg}</div>
  </div>
</div>"""


def render_candidate_codes(retrieval_log: List[Dict], final_hs: str) -> str:
    """RAG 검색 결과를 HS 코드 후보 카드로 표시 — '그래서 뭐?' 문제 해결."""
    code_map: Dict[str, Dict] = {}
    for h in retrieval_log:
        code = h["metadata"].get("code", "")
        if not code:
            continue
        if code not in code_map or h["similarity"] > code_map[code]["similarity"]:
            code_map[code] = h

    if not code_map:
        return '<p style="color:#aeaeb2;font-size:13px;text-align:center;padding:16px">후보 코드 없음</p>'

    sorted_codes = sorted(code_map.values(), key=lambda x: -x["similarity"])
    final_prefix = final_hs[:4]
    cards = []

    for h in sorted_codes:
        code = h["metadata"].get("code", "")
        sim  = h["similarity"]

        if sim >= 0.7:   strength, sc = "강한 후보", "#34c759"
        elif sim >= 0.5: strength, sc = "유력 후보", "#ff9f0a"
        else:            strength, sc = "참고 후보", "#aeaeb2"

        is_match   = code[:4] == final_prefix
        match_html = (
            f'<span style="background:#e8f8ee;color:#1a7f3c;font-size:10px;font-weight:600;'
            f'padding:2px 9px;border-radius:10px;margin-left:8px">✓ 최종 선택</span>'
            if is_match else
            f'<span style="background:#f5f5f7;color:#aeaeb2;font-size:10px;'
            f'padding:2px 9px;border-radius:10px;margin-left:8px">미선택</span>'
        )
        border = "#34c759" if is_match else "#e5e5ea"
        bg     = "#f0fdf4" if is_match else "#fafafa"

        preview = pretty_chunk(h.get("text",""))[:160]
        if len(h.get("text","")) > 160: preview += "…"

        cards.append(f"""
<div style="border:1.5px solid {border};background:{bg};border-radius:12px;
            padding:14px 16px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">
    <div>
      <span style="font-size:20px;font-weight:700;color:#1d1d1f;
                   font-family:monospace;letter-spacing:1px">HS {code}</span>
      {match_html}
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:{sc};font-weight:600">{strength}</div>
      <div style="font-size:14px;font-weight:700;color:{sc};font-variant-numeric:tabular-nums">
        {sim:.1%}
      </div>
    </div>
  </div>
  <div style="background:#f0f0f2;border-radius:4px;height:5px;overflow:hidden;margin-bottom:8px">
    <div style="background:{sc};width:{sim*100:.1f}%;height:100%;border-radius:4px"></div>
  </div>
  <div style="font-size:12px;color:#6e6e73;line-height:1.55;font-family:monospace">{preview}</div>
</div>""")

    return "\n".join(cards)


# 0630 서연 수정 — AI가 실제 인용한 청크와 단순 검색 결과를 분리하여 표시
# (최종 판단 근거와 참고용 검색 결과를 구분하여 가독성 개선)
def render_chunk_cards(retrieval_log: List[Dict], cited_idx: Set[str]) -> str:
    """상세 청크 카드."""
    # 0630 서연 추가 — 실제 인용된 검색 결과를 먼저, 나머지를 뒤에 정렬
    cited  = sorted([h for h in retrieval_log if h["chunk_index"] in cited_idx],  key=lambda x: -x["similarity"])
    others = sorted([h for h in retrieval_log if h["chunk_index"] not in cited_idx], key=lambda x: -x["similarity"])
    cards  = []

    for hit in cited + others:
        is_cited = hit["chunk_index"] in cited_idx
        sim      = hit.get("similarity", 0)
        meta     = hit.get("metadata", {})
        # 0630 서연 추가 — 화면이 너무 길어지지 않도록 미리보기만 표시
        preview  = pretty_chunk(hit.get("text",""))[:280]
        if len(hit.get("text","")) > 280: preview += "…"
        preview  = preview.replace("<","&lt;").replace(">","&gt;")

        cls   = "chunk-cited" if is_cited else "chunk-other"
        badge = '<span class="cited-badge">인용</span>' if is_cited else ""
        if sim >= 0.7:   sc, strength = "#34c759", "강한"
        elif sim >= 0.5: sc, strength = "#ff9f0a", "유력"
        else:            sc, strength = "#aeaeb2", "참고"

        tags = ""
        if meta.get("agreement"):
            tags += f'<span class="tag tag-blue">{meta["agreement"]}</span>'
        if meta.get("code"):
            tags += f'<span class="tag tag-gray">HS {meta["code"]}</span>'
        if meta.get("source_type"):
            tags += f'<span class="tag tag-orange">{meta["source_type"].upper()}</span>'

        cards.append(f"""
<div class="{cls}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span style="font-family:monospace;font-size:12px;color:#6e6e73">
      청크 #{hit["chunk_index"]}{badge}
    </span>
    <div style="text-align:right">
      <div style="font-size:10px;color:{sc}">{strength} 후보</div>
      <div style="font-size:13px;font-weight:700;color:{sc};font-variant-numeric:tabular-nums">
        {sim:.1%}
      </div>
    </div>
  </div>
  <div class="sim-bar-bg">
    <div style="background:{sc};width:{sim*100:.1f}%;height:100%;border-radius:4px"></div>
  </div>
  <div style="margin-bottom:6px">{tags}</div>
  <div class="chunk-text">{preview}</div>
</div>""")

    return "\n".join(cards) or '<p style="color:#aeaeb2;font-size:13px">검색 결과 없음</p>'


# ═══════════════════════════════════════════════════════════════════════════════
# 사이드바
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
<div style="padding:6px 0 14px">
  <div style="font-size:22px;font-weight:700;color:#1d1d1f;letter-spacing:-0.5px">🛃 ClearHS</div>
  <div style="font-size:12px;color:#6e6e73;margin-top:2px">HS 코드 자동 분류 시스템</div>
</div>""", unsafe_allow_html=True)

    # 0628 유림 추가 — API 키/ChromaDB 없이 화면·연결만 먼저 확인하는 모드
    test_mode = st.checkbox(
        "🧪 테스트 모드",
        value=False,
        help="API 키를 아직 못 받았거나 ChromaDB가 준비 안 됐을 때, UI와 파이프라인 연결이 "
             "제대로 되는지 더미 데이터로 먼저 확인할 수 있어요. PDF 추출(1단계)·FTA(4단계)·"
             "서류검증(5단계 로직)은 그대로 실제 코드로 돌아가고, LLM이 필요한 "
             "상품정보추출(2단계)·HS분류(3단계)·면세판단(5단계)만 더미값으로 대체돼요.",
    )

    with st.expander("⚙️ API / DB 설정", expanded=not test_mode):
        st.markdown('<div style="font-size:12px;font-weight:600;color:#1d1d1f;margin-bottom:6px">문서 추출 (Upstage)</div>', unsafe_allow_html=True)
        upstage_api_key = st.text_input(
            "Upstage API Key", value=os.getenv("UPSTAGE_API_KEY",""),
            type="password", placeholder="up-...", disabled=test_mode, label_visibility="collapsed")
        upstage_model = st.selectbox(
            "Upstage 모델", ["solar-pro2","solar-mini"],
            index=0, disabled=test_mode)

        # 0628 서연 추가 - 모델 두 개 사용하기 위해 분리
        st.markdown('<div style="font-size:12px;font-weight:600;color:#1d1d1f;margin:10px 0 6px">HS 분류 (OpenAI)</div>', unsafe_allow_html=True)
        openai_api_key = st.text_input(
            "OpenAI API Key", value=os.getenv("OPENAI_API_KEY",""),
            type="password", placeholder="sk-...", disabled=test_mode, label_visibility="collapsed")
        openai_model = st.selectbox(
            "OpenAI 모델", ["gpt-5.4", "gpt-4.1", "gpt-5.4-mini"],
            index=0, disabled=test_mode)

        st.divider()
        chroma_path = st.text_input(
            "ChromaDB 경로",
            value=os.getenv("CHROMA_DB_PATH", str(Path(__file__).parent / "chroma_db")),
            disabled=test_mode)
        collection_name = st.text_input(
            "컬렉션",
            value=os.getenv("COLLECTION_NAME","customs_knowledge_v3"),
            disabled=test_mode)

    st.markdown("---")
    st.markdown('<div style="font-size:13px;font-weight:600;color:#1d1d1f;margin-bottom:8px">📄 문서 업로드</div>', unsafe_allow_html=True)
    st.caption("인보이스는 필수. 나머지는 선택.")
    invoice_file = st.file_uploader("인보이스 (Invoice) *", type=["pdf"], key="invoice")
    packing_file = st.file_uploader("패킹리스트 (Packing List)",  type=["pdf"], key="packing")
    spec_file    = st.file_uploader("명세서 (Specification)",      type=["pdf"], key="spec")

    st.markdown("---")
    run_btn = st.button("🚀 분류 실행",
                        use_container_width=True, type="primary",
                        disabled=invoice_file is None)
    if not invoice_file:
        st.caption("인보이스를 업로드하면 버튼이 활성화됩니다.")


# ═══════════════════════════════════════════════════════════════════════════════
# 초기 화면
# ═══════════════════════════════════════════════════════════════════════════════
if not run_btn:
    st.markdown("""
<div style="max-width:620px;margin:80px auto;text-align:center">
  <div style="font-size:52px;margin-bottom:14px">🛃</div>
  <div style="font-size:28px;font-weight:700;color:#1d1d1f;letter-spacing:-0.5px;line-height:1.3">
    무역 서류를 업로드하면<br>HS 코드를 자동으로 분류합니다
  </div>
  <div style="font-size:15px;color:#6e6e73;margin-top:14px;line-height:1.8">
    인보이스 · 패킹리스트 · 명세서<br>
    → 상품 정보 추출 → RAG 기반 HS 코드 분류<br>
    → XAI 신뢰도 + FTA 적용 + 면세 판단 + 서류 체크
  </div>
</div>""", unsafe_allow_html=True)
    st.stop()


# ── 실행: clearhs import 후 CONFIG를 직접 덮어써서 설정 주입 ─────────────────
# 0626 유림 수정
# clearhs.config.CONFIG는 모듈이 "처음 import될 때" 한 번만 만들어지는 딕셔너리라서,
# os.environ만 바꾸는 방식은 Streamlit 두 번째 실행부터는 반영이 안 될 수 있다.
# (clearhs.config는 서버 프로세스 안에서 한 번만 import되고, 그 다음부터는 재실행돼도
#  import 자체가 다시 일어나지 않기 때문 — get_client.cache_clear()는 클라이언트
#  객체만 새로 만들 뿐, CONFIG 안의 값 자체는 안 바꿔준다.)
# 그래서 다른 모듈들이 들고 있는 "같은 CONFIG 딕셔너리 객체"를 직접 덮어쓴다.
try:
    from clearhs.pdf_extraction     import build_combined_raw_text
    from clearhs.product_extraction import extract_product_info
    from clearhs.classification     import classify_hs_code
    from clearhs.xai                import calculate_xai_confidence
    from clearhs.fta                import check_fta_eligibility
    from clearhs.documents          import check_duty_exemption, verify_required_documents  # 0626 유림 추가
    from clearhs.clients            import get_openai_client, get_upstage_client
    from clearhs.rag                import _get_collection
    from clearhs.models             import ProductInfo, ClassificationResult, FTAResult, ExemptionResult, CitedChunk  # 0628 유림 추가
    import clearhs.config as _cfg
except ImportError as e:
    st.error(f"`clearhs` 패키지를 찾을 수 없어요. `app.py`가 프로젝트 루트에 있는지 확인해주세요.\n\n`{e}`")
    st.stop()

# 0626 유림 수정 — os.environ 대신 CONFIG를 직접 덮어씀 + OPENAI_BASE_URL 추가
# 0628 서연 추가 - 모델 두 개 사용하기 위해 분리
if not test_mode:
    # Upstage 설정
    _cfg.CONFIG["UPSTAGE_API_KEY"]  = upstage_api_key
    _cfg.CONFIG["UPSTAGE_MODEL"]    = upstage_model

    # OpenAI 설정
    _cfg.CONFIG["OPENAI_API_KEY"]   = openai_api_key
    _cfg.CONFIG["OPENAI_MODEL"]     = openai_model

    _cfg.CONFIG["CHROMA_DB_PATH"]   = chroma_path
    _cfg.CONFIG["COLLECTION_NAME"]  = collection_name

    # 캐시 초기화
    get_openai_client.cache_clear()
    get_upstage_client.cache_clear()
    _get_collection.cache_clear()


# 0628 유림 추가 — 테스트 모드용 더미 함수들 (실제 API/ChromaDB 호출 없음, models.py 그대로 사용)
def _mock_extract(raw: str, docs: list) -> "ProductInfo":
    return ProductInfo(
        product_name="(테스트) 블루투스 이어폰",
        materials=["plastic","lithium battery"],
        usage="개인용 음향기기", origin_country="China",
        manufacturer="Dummy Co., Ltd.",
        quantity="100 EA", weight="2.5 kg",
        unit_price="15.00", currency="USD",
        intended_user="일반 소비자용",
        raw_text=raw, source_documents=docs,
    )

def _mock_classify(pi: "ProductInfo"):
    cls = ClassificationResult(
        hs_code="8518.30",
        hs_code_description="헤드폰·이어폰 및 이와 결합된 마이크로폰",
        reasoning="(테스트 더미) 음향 변환기기로 분류 — HS 8518.30 해당",
        cited_chunks=[CitedChunk(chunk_index="law_001", similarity=0.82, snippet="(더미 인용)")],
        llm_self_eval=0.78,
    )
    log = [{"chunk_index":"law_001","text":"(더미 검색 결과)","metadata":{"code":"8518.30","agreement":"KOREA_CHINA_FTA","source_type":"psr"},"similarity":0.82}]
    return cls, log

def _mock_exemption(pi: "ProductInfo") -> "ExemptionResult":
    return ExemptionResult(
        is_likely_exempt=False,
        reasoning="(테스트 더미) 실제 면세 판단이 아닙니다.",
        notes="API 키 연결 전 UI 확인용 더미 데이터입니다.",
    )


# ── 업로드 파일 임시 저장 ────────────────────────────────────────────────────
tmp_dir = tempfile.mkdtemp()
def _save(f) -> str:
    p = os.path.join(tmp_dir, f.name)
    with open(p,"wb") as fh: fh.write(f.getbuffer())
    return p

doc_paths: dict = {}
if invoice_file: doc_paths["invoice"]       = _save(invoice_file)
if packing_file: doc_paths["packing_list"]  = _save(packing_file)
if spec_file:    doc_paths["specification"] = _save(spec_file)


# ═══════════════════════════════════════════════════════════════════════════════
# 파이프라인 실행 + 결과 렌더링
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("## 📊 분류 결과")
if test_mode:
    st.warning("🧪 테스트 모드입니다 — 2·3·5단계(상품정보추출·HS분류·면세판단)는 전부 더미 데이터예요. "
               "실제 분류/판단 결과가 아니라 화면과 데이터 연결만 확인하는 용도예요.")


# ─ 1단계: PDF 추출 ────────────────────────────────────────────────────────────
with st.status("📄 1단계: PDF 텍스트 추출 중...", expanded=False) as s1:
    try:
        raw = build_combined_raw_text(doc_paths)
        s1.update(label=f"✅ 1단계 완료 — {len(raw):,}자 추출", state="complete")
    except Exception as e:
        s1.update(label="❌ 1단계 실패", state="error", expanded=True)
        st.error(str(e)); st.stop()

with st.expander("추출된 원문 보기"):
    st.text_area("", value=raw, height=180, label_visibility="collapsed")


# ─ 2단계: 상품정보 구조화 ────────────────────────────────────────────────────
with st.status("🔍 2단계: 상품 정보 구조화 중 (LLM)...", expanded=False) as s2:
    try:
        # 0628 유림 수정 — 테스트 모드 분기
        pi = _mock_extract(raw, list(doc_paths.keys())) if test_mode \
             else extract_product_info(raw, source_documents=list(doc_paths.keys()))
        s2.update(label=f"✅ 2단계 완료 — {pi.product_name}", state="complete")
    except Exception as e:
        s2.update(label="❌ 2단계 실패", state="error", expanded=True)
        st.error(str(e)); st.stop()

# 상품정보 카드
usage_row = f'<div style="margin-top:10px;font-size:13px;color:#6e6e73">용도: {pi.usage}</div>' if pi.usage else ""
mat_row   = f'<div style="margin-top:8px">' + "".join(f'<span class="tag tag-gray">{m}</span>' for m in pi.materials) + '</div>' if pi.materials else ""
st.markdown(f"""
<div class="ac">
  <div class="section-label">추출된 상품 정보</div>
  <div class="info-grid">
    <div class="info-cell"><div class="lbl">상품명</div><div class="val">{pi.product_name}</div></div>
    <div class="info-cell"><div class="lbl">제조사</div><div class="val">{pi.manufacturer or "—"}</div></div>
    <div class="info-cell"><div class="lbl">원산지</div><div class="val">{pi.origin_country or "—"}</div></div>
    <div class="info-cell"><div class="lbl">수량</div><div class="val">{pi.quantity or "—"}</div></div>
    <div class="info-cell"><div class="lbl">중량</div><div class="val">{pi.weight or "—"}</div></div>
    <div class="info-cell"><div class="lbl">단가</div><div class="val">{(pi.unit_price or "—") + (" " + (pi.currency or "") if pi.unit_price else "")}</div></div>
  </div>
  {usage_row}{mat_row}
</div>""", unsafe_allow_html=True)


# ─ 3단계: HS 코드 분류 (RAG Tool Calling) ─────────────────────────────────────
with st.status("🤖 3단계: HS 코드 분류 중 (RAG + Tool Calling)...", expanded=False) as s3:
    try:
        # 0628 유림 수정 — 테스트 모드 분기
        if test_mode:
            cls, retrieval_log = _mock_classify(pi)
        else:
            cls, retrieval_log = classify_hs_code(pi)
        cls.xai_confidence = calculate_xai_confidence(cls, retrieval_log)
        s3.update(label=f"✅ 3단계 완료 — HS {cls.hs_code}", state="complete")
    except Exception as e:
        s3.update(label="❌ 3단계 실패", state="error", expanded=True)
        st.error(str(e)); st.stop()

# 0630 서연 수정 — XAI와 동일한 방식으로 검색 유사도를 계산
# (평균 대신 실제 인용된 청크 중 가장 높은 유사도를 사용하고 동일한 정규화를 적용)
cited_idx = {c.chunk_index for c in cls.cited_chunks}

cited_sims = [
    h["similarity"]
    for h in retrieval_log
    if h["chunk_index"] in cited_idx
]

ret_score = max(cited_sims) if cited_sims else 0.0
ret_score = normalize_similarity(ret_score)

conf = cls.xai_confidence or 0.0

# HS 분류 레이아웃: 좌(HS+근거) / 우(신뢰도 카드)
col_left, col_right = st.columns([5, 4], gap="medium")

# 0630 서연 추가 — reasoning의 줄바꿈과 제목을 HTML 형태로 변환
reasoning_html = (
    cls.reasoning
    .replace("\n", "<br>")
    .replace("[후보 제외 이유]", "<b>❌ 후보 제외 이유</b>")
    .replace("[후보 비교]", "<br><br><b>📚 후보 비교</b>")
    .replace("[최종 판단]", "<br><br><b>✅ 최종 판단</b>")
)

with col_left:
    desc_html = f'<div class="hs-desc">{cls.hs_code_description}</div>' if cls.hs_code_description else ""
    st.markdown(f"""
<div class="ac" style="height:100%">
  <div class="section-label">HS 코드 분류 결과</div>
  <div class="hs-num">{cls.hs_code}</div>
  {desc_html}
  <div style="margin-top:18px">
    <div class="section-label">분류 근거</div>
    <div style="font-size:14px;color:#1d1d1f;line-height:1.75;background:#f5f5f7;
                border-radius:10px;padding:14px 16px">{reasoning_html}</div>
  </div>
</div>""", unsafe_allow_html=True)

with col_right:
    ret_w = _cfg.CONFIG.get("RETRIEVAL_WEIGHT", 0.4)
    llm_w = _cfg.CONFIG.get("LLM_SELF_EVAL_WEIGHT", 0.6)
    st.markdown(
        render_confidence_card(conf, ret_score, cls.llm_self_eval, ret_w, llm_w),
        unsafe_allow_html=True,
    )

# RAG 후보 코드 카드 (항상 노출)
if retrieval_log:
    st.markdown(f"""
<div class="ac">
  <div class="section-label">RAG 후보 코드 — 유사도 높은 순</div>
  <div style="font-size:12px;color:#6e6e73;margin-bottom:12px">
    DB에서 찾은 유사 사례입니다. LLM은 이 코드들을 출발점으로 최종 분류를 결정했어요.
  </div>
  {render_candidate_codes(retrieval_log, cls.hs_code)}
</div>""", unsafe_allow_html=True)

    # 0630 서연 추가 — 실제 인용된 검색 결과 / 인용되지 않은 후보를 구분해서 표시
    n_cited = len(cited_idx & {h["chunk_index"] for h in retrieval_log})
    with st.expander(f"🔍 상세 청크 보기 — {n_cited}건 인용 / {len(retrieval_log)}건 검색"):
        st.markdown(render_chunk_cards(retrieval_log, cited_idx), unsafe_allow_html=True)


# ─ 4단계: FTA 적용 판단 ───────────────────────────────────────────────────────
with st.status("🤝 4단계: FTA 적용 가능성 판단 중...", expanded=False) as s4:
    try:
        fta = check_fta_eligibility(pi, cls)
        s4.update(label=f"✅ 4단계 완료 — {'FTA 적용 가능' if fta.eligible else 'FTA 해당 없음'}", state="complete")
    except Exception as e:
        s4.update(label="❌ 4단계 실패", state="error", expanded=True)
        st.error(str(e)); st.stop()

fta_color = "#e8f8ee" if fta.eligible else "#fff4e5"
fta_tc    = "#1a7f3c"  if fta.eligible else "#a85900"
fta_icon  = "✅" if fta.eligible else "⚠️"
agreements_str = " · ".join(fta.applicable_agreements) if fta.applicable_agreements else "해당 없음"
cert_str  = fta.required_certificate_type or "—"

# 0629 유림 추가 — PSR(원산지결정기준) 실데이터 매칭 결과 화면에 표시
st.markdown(f"""
<div class="ac">
  <div class="section-label">FTA 적용 가능성</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
    <div style="flex:1;min-width:180px;background:{fta_color};border-radius:12px;padding:14px 16px">
      <div style="font-size:11px;color:{fta_tc};font-weight:600;margin-bottom:5px">적용 협정</div>
      <div style="font-size:16px;font-weight:700;color:{fta_tc}">{fta_icon} {agreements_str}</div>
    </div>
    <div style="flex:1;min-width:180px;background:#f5f5f7;border-radius:12px;padding:14px 16px">
      <div style="font-size:11px;color:#6e6e73;font-weight:600;margin-bottom:5px">필요 서류</div>
      <div style="font-size:14px;font-weight:600;color:#1d1d1f">{cert_str}</div>
    </div>
  </div>
  {f'<div style="background:#fffbe6;border-radius:10px;padding:12px 14px;font-size:13px;color:#1d1d1f"><b>원산지결정기준 (PSR)</b><br>{fta.origin_criterion}</div>' if getattr(fta,"origin_criterion",None) else '<div style="font-size:13px;color:#aeaeb2">ℹ️ 이 HS코드에 대한 PSR 데이터를 찾지 못했어요 — 수동 확인이 필요해요.</div>'}
  {f'<div style="font-size:12px;color:#aeaeb2;margin-top:8px">{fta.notes}</div>' if fta.notes else ""}
</div>""", unsafe_allow_html=True)

# 0629 유림 추가 — 판단 근거 펼쳐보기
if getattr(fta, "reasoning", None):
    with st.expander("🔍 FTA 판단 근거 자세히 보기"):
        st.write(fta.reasoning)
        if getattr(fta,"cited_chunks",None):
            for c in fta.cited_chunks:
                st.caption(f"`{c.chunk_index}` — {c.snippet[:150]}")


# ─ 5단계: 면세 판단 + 서류 검증 ─────────────────────────────────────────────────
# 0626 유림 수정 (check_duty_exemption 호출 추가, verify_required_documents에 결과 전달)
with st.status("📋 5단계: 면세 대상 여부 판단 + 필요 서류 검증 중...", expanded=False) as s5:
    try:
        # 0628 유림 수정 — 테스트 모드 분기
        exemption = _mock_exemption(pi) if test_mode else check_duty_exemption(pi)
        doc_check = verify_required_documents(pi, fta, exemption)
        lbl = "서류 완비" if doc_check.is_complete else f"누락 {len(doc_check.missing_documents)}건"
        s5.update(label=f"✅ 5단계 완료 — {lbl}", state="complete")
    except Exception as e:
        s5.update(label="❌ 5단계 실패", state="error", expanded=True)
        st.error(str(e)); st.stop()

# 0626 유림 추가 — 면세 가능성 UI
if getattr(exemption, "is_likely_exempt", False):
    cat  = getattr(exemption,"exemption_category","")
    basis= getattr(exemption,"exemption_basis","")
    add_docs = getattr(exemption,"additional_required_documents",[])
    ex_html = f"""
<div style="background:#e8f8ee;border-radius:12px;padding:14px 16px;margin-bottom:10px">
  <div style="font-size:14px;font-weight:700;color:#1a7f3c;margin-bottom:6px">
    ✅ 면세 대상 가능성 있음{f" — {cat}" if cat else ""}
  </div>
  <div style="font-size:13px;color:#1d1d1f">{exemption.reasoning}</div>
  {f'<div style="font-size:12px;color:#1a7f3c;margin-top:6px">근거: {basis}</div>' if basis else ""}
  {f'<div style="font-size:12px;color:#1a7f3c;margin-top:4px">추가 서류: {", ".join(add_docs)}</div>' if add_docs else ""}
</div>"""
else:
    ex_html = '<div style="background:#f5f5f7;border-radius:12px;padding:14px 16px;font-size:13px;color:#6e6e73">면세/감면 대상에 해당하지 않는 것으로 판단됨</div>'

# 서류 체크 카드
def doc_card(name, missing):
    icon  = "❌" if missing else "✅"
    bg    = "#fff1f0" if missing else "#e8f8ee"
    tc    = "#c0392b" if missing else "#1a7f3c"
    label = "미업로드" if missing else "업로드됨"
    return (f'<div style="flex:1;min-width:140px;background:{bg};border-radius:12px;'
            f'padding:14px 16px"><div style="font-size:11px;color:{tc};font-weight:600;'
            f'margin-bottom:4px">{icon} {label}</div>'
            f'<div style="font-size:14px;font-weight:600;color:#1d1d1f">'
            f'{name.replace("_"," ").title()}</div></div>')

doc_cards = "".join(doc_card(d, d in doc_check.missing_documents) for d in doc_check.required_documents)
complete_html = "" if doc_check.is_complete else \
    f'<div style="margin-top:10px;font-size:13px;color:#c0392b">누락 서류: {", ".join(doc_check.missing_documents)}</div>'

notes_html = f'<div style="font-size:12px;color:#aeaeb2;margin-top:6px">{exemption.notes}</div>' \
             if getattr(exemption,"notes",None) else ""

st.markdown(f"""
<div class="ac">
  <div class="section-label">면세/감면 대상 여부</div>
  {ex_html}
  {notes_html}
  <div class="section-label" style="margin-top:16px">필요 서류 체크리스트</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap">{doc_cards}</div>
  {complete_html}
</div>""", unsafe_allow_html=True)

if doc_check.is_complete:
    st.success("필요 서류가 모두 업로드되었습니다.")


# ─ 결과 JSON 다운로드 ─────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
final_result = {
    "product_info":    pi.model_dump(),
    "classification":  cls.model_dump(),
    "fta_result":      fta.model_dump(),
    "document_check":  doc_check.model_dump(),
}
st.download_button(
    label="⬇️ 전체 결과 JSON 다운로드",
    data=json.dumps(final_result, ensure_ascii=False, indent=2),
    file_name=f"clearhs_{pi.product_name[:30].replace(' ','_')}.json",
    mime="application/json",
    use_container_width=True,
)