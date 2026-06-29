"""ClearHS – HS 코드 분류 시스템
실행: streamlit run app.py  (프로젝트 루트에서)
"""

import html as _html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Set

import streamlit as st

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClearHS",
    page_icon="CH",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS (변수 시스템 + 컴포넌트) ─────────────────────────────────────────────
st.markdown("""
<style>
:root {
  --bg:          #f6f7f9;
  --panel:       #ffffff;
  --soft:        #f1f4f8;
  --text:        #17202a;
  --muted:       #667085;
  --line:        #d8dee8;
  --blue:        #2563eb;
  --green:       #16803c;
  --amber:       #a45b00;
  --red:         #b42318;
  --green-bg:    #edf8f1;
  --amber-bg:    #fff6e8;
  --red-bg:      #fff0ed;
}

html, body, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
               "Helvetica Neue", Arial, sans-serif;
}
.stApp          { background: var(--bg); }
.block-container { padding-top: 24px; padding-bottom: 48px; max-width: 1160px; }

/* 헤더 툴바 숨김 */
div[data-testid="stToolbar"],
div[data-testid="stDecoration"] { visibility: hidden; height: 0; }

/* 패널 */
.panel {
  background: var(--panel);
  border: 1px solid rgba(23,32,42,.08);
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 4px 20px rgba(22,34,51,.06);
  margin-bottom: 14px;
}

/* 키커 / 타이틀 */
.kicker {
  color: var(--muted); font-size: 11px; font-weight: 700;
  letter-spacing: .5px; text-transform: uppercase; margin-bottom: 6px;
}
.panel-title {
  color: var(--text); font-size: 17px; font-weight: 700; margin-bottom: 4px;
}
.panel-copy { color: var(--muted); font-size: 13px; line-height: 1.65; }

/* 요약 그리드 */
.summary-grid {
  display: grid;
  grid-template-columns: 1.3fr 0.9fr 0.9fr 0.9fr;
  gap: 12px;
  margin-bottom: 18px;
}
.metric-card {
  background: var(--panel);
  border: 1px solid rgba(23,32,42,.08);
  border-radius: 10px;
  padding: 16px 18px;
  box-shadow: 0 2px 10px rgba(22,34,51,.05);
}
.metric-label { color: var(--muted); font-size: 11px; font-weight: 700; margin-bottom: 8px; }
.metric-value { font-size: 24px; font-weight: 760; font-variant-numeric: tabular-nums; color: var(--text); line-height: 1.1; }
.metric-note  { color: var(--muted); font-size: 12px; margin-top: 6px; line-height: 1.4; }

/* HS 코드 */
.hs-hero { font-size: 52px; font-weight: 780; color: var(--blue);
           font-variant-numeric: tabular-nums; line-height: 1; margin: 10px 0 8px; }

/* 신뢰도 pill */
.conf-pill {
  border-radius: 10px; padding: 16px; text-align: center; margin: 10px 0 12px;
}
.conf-number { font-size: 44px; font-weight: 780; font-variant-numeric: tabular-nums; line-height: 1; }
.conf-label  { font-size: 13px; font-weight: 700; margin-top: 5px; }

/* 공통 바 */
.bar-bg   { height: 8px; background: #e3e8ef; border-radius: 999px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999px; }

/* 분류 근거 박스 */
.reason-box {
  background: var(--soft); border-radius: 8px;
  padding: 14px 16px; font-size: 14px; color: var(--text);
  line-height: 1.75; margin-top: 12px;
}

/* 상품 정보 그리드 */
.info-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-top: 12px; }
.info-cell { background: var(--soft); border-radius: 8px; padding: 12px 14px; }
.info-lbl  { color: var(--muted); font-size: 11px; font-weight: 700; margin-bottom: 5px; }
.info-val  { color: var(--text); font-size: 14px; font-weight: 650; overflow-wrap: anywhere; }

/* 태그 */
.tag { display:inline-flex; align-items:center; background:#eef2f7; color:#344054;
       border-radius:999px; padding:4px 9px; margin:3px 3px 0 0;
       font-size:12px; font-weight:620; }

/* 후보 코드 카드 */
.candidate { border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:8px; }
.candidate-selected { border-color:rgba(22,128,60,.5); background:var(--green-bg); }
.cand-code { font-family:ui-monospace,monospace; font-size:18px; font-weight:760; color:var(--text); }
.cand-meta { color:var(--muted); font-size:12px; line-height:1.5; margin-top:6px; }

/* 청크 카드 */
.chunk         { border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:8px; }
.chunk-cited   { border-color:rgba(22,128,60,.5); background:var(--green-bg); }
.chunk-text    { color:#344054; font-family:ui-monospace,monospace; font-size:12px;
                 line-height:1.65; white-space:pre-wrap; margin-top:8px; }

/* 상태 박스 */
.status-box       { background:var(--soft); border-radius:8px; padding:14px; }
.status-box-green { background:var(--green-bg); }
.status-box-amber { background:var(--amber-bg); }
.status-box-red   { background:var(--red-bg); }
.status-grid      { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }

/* Streamlit 오버라이드 */
div[data-testid="stFileUploader"] {
  background: #fff; border:1px dashed #b7c2d0; border-radius:8px; padding:8px 12px 2px;
}
div[data-testid="stExpander"] {
  border:1px solid rgba(23,32,42,.10); border-radius:8px; background:#fff;
}
.stButton>button, .stDownloadButton>button {
  border-radius:8px; min-height:44px; font-weight:700;
}

@media(max-width:900px) {
  .summary-grid, .info-grid, .status-grid { grid-template-columns:1fr; }
  .hs-hero { font-size:38px; }
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 유틸 헬퍼
# ═══════════════════════════════════════════════════════════════════════════════

def esc(v) -> str:
    return "-" if (v is None or v == "") else _html.escape(str(v))

def pct(v: float) -> str:
    return f"{max(0., min(1., v)):.0%}"

def pretty_chunk(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    lines, prev = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line or line == prev: continue
        lines.append(line); prev = line
    text = "\n".join(lines)
    return re.sub(r"(?<=[가-힣A-Za-z0-9)])\n(?=[가-힣A-Za-z(])", " ", text).strip()

def confidence_tone(conf: float):
    if conf >= 0.75: return "#16803c", "#edf8f1", "높음",   "신뢰도 높음"
    if conf >= 0.5:  return "#a45b00", "#fff6e8", "보통",   "검토 권장"
    return               "#b42318", "#fff0ed", "낮음",   "수동 검토 필요"


# ═══════════════════════════════════════════════════════════════════════════════
# 시각화 컴포넌트
# ═══════════════════════════════════════════════════════════════════════════════

def render_confidence_card(conf: float, retrieval_score: float, llm_self_eval: float,
                            ret_w: float = 0.4, llm_w: float = 0.6) -> str:
    color, bg, label, message = confidence_tone(conf)
    rc = ret_w * retrieval_score
    lc = llm_w * llm_self_eval

    def factor(title, score, weight, contrib, bar_color):
        return f"""
<div style="margin-top:12px">
  <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px">
    <span style="color:var(--text)">{esc(title)}</span>
    <strong style="color:{bar_color};font-variant-numeric:tabular-nums">
      {weight:.0%} × {score:.3f} = {contrib:.3f}
    </strong>
  </div>
  <div class="bar-bg">
    <div class="bar-fill" style="width:{min(contrib*100,100):.1f}%;background:{bar_color}"></div>
  </div>
</div>"""

    return f"""
<div class="panel" style="padding:18px">
  <div class="kicker">XAI confidence</div>
  <div class="panel-title">분류 신뢰도</div>
  <div class="conf-pill" style="background:{bg}">
    <div class="conf-number" style="color:{color}">{pct(conf)}</div>
    <div class="conf-label" style="color:{color}">{label}</div>
  </div>
  <div class="bar-bg">
    <div class="bar-fill" style="width:{min(conf*100,100):.1f}%;background:{color}"></div>
  </div>
  {factor("🔍 검색 근거 점수", retrieval_score, ret_w, rc, "#2563eb")}
  {factor("🤖 AI 자체 확신도", llm_self_eval,  llm_w, lc, "#6d5bd0")}
  <div class="status-box{'status-box-green' if conf>=0.75 else ' status-box-amber' if conf>=0.5 else ' status-box-red'}"
       style="margin-top:14px;font-size:13px;font-weight:700;color:{color}">
    {message}
  </div>
</div>"""


def render_candidate_codes(retrieval_log: List[Dict], final_hs: str,
                            max_show: int = 3) -> str:
    """HS 후보 코드 카드 — 최대 max_show개만 표시."""
    code_map: Dict[str, Dict] = {}
    for h in retrieval_log:
        code = h.get("metadata", {}).get("code", "")
        if not code: continue
        if code not in code_map or h.get("similarity",0) > code_map[code].get("similarity",0):
            code_map[code] = h

    if not code_map:
        return '<div class="panel-copy">후보 코드가 없습니다.</div>'

    final_prefix = (final_hs or "")[:4]
    sorted_hits  = sorted(code_map.values(), key=lambda x: -x.get("similarity",0))
    cards = []

    for h in sorted_hits[:max_show]:          # ← 상위 3개만
        code     = h.get("metadata",{}).get("code","")
        sim      = h.get("similarity", 0)
        selected = code[:4] == final_prefix
        strength = "강한 후보" if sim>=0.7 else ("유력 후보" if sim>=0.5 else "참고 후보")
        sc_color = "#16803c" if sim>=0.7 else ("#a45b00" if sim>=0.5 else "#667085")
        preview  = pretty_chunk(h.get("text",""))[:200]
        if len(h.get("text","")) > 200: preview += "..."

        cards.append(f"""
<div class="candidate {'candidate-selected' if selected else ''}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div class="cand-code">HS {esc(code)}</div>
      <div class="cand-meta">{'✓ 최종 선택과 같은 4단위' if selected else '미선택'}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:{sc_color};font-weight:700">{strength}</div>
      <div style="font-size:15px;font-weight:760;color:{sc_color};font-variant-numeric:tabular-nums">{sim:.1%}</div>
    </div>
  </div>
  <div class="bar-bg" style="margin-bottom:8px">
    <div class="bar-fill" style="width:{min(sim*100,100):.1f}%;background:{sc_color}"></div>
  </div>
  <div class="cand-meta">{esc(preview)}</div>
</div>""")

    hidden = len(sorted_hits) - max_show
    if hidden > 0:
        cards.append(f'<div class="panel-copy" style="text-align:center;padding:8px 0">외 {hidden}개 후보 (상세 청크 탭 참고)</div>')

    return "\n".join(cards)


def render_chunk_cards(retrieval_log: List[Dict], cited_idx: Set[str]) -> str:
    cited  = sorted([h for h in retrieval_log if h.get("chunk_index") in cited_idx],  key=lambda x: -x.get("similarity",0))
    others = sorted([h for h in retrieval_log if h.get("chunk_index") not in cited_idx], key=lambda x: -x.get("similarity",0))
    cards  = []

    for hit in cited + others:
        is_cited = hit.get("chunk_index") in cited_idx
        sim      = hit.get("similarity", 0)
        meta     = hit.get("metadata", {})
        preview  = pretty_chunk(hit.get("text",""))[:360]
        if len(hit.get("text","")) > 360: preview += "..."
        sc = "#16803c" if sim>=0.7 else ("#a45b00" if sim>=0.5 else "#667085")

        tags = "".join([
            f'<span class="tag">{esc(meta["agreement"])}</span>' if meta.get("agreement") else "",
            f'<span class="tag">HS {esc(meta["code"])}</span>'   if meta.get("code")      else "",
            f'<span class="tag">{esc(str(meta.get("source_type","")).upper())}</span>' if meta.get("source_type") else "",
        ])

        cards.append(f"""
<div class="chunk {'chunk-cited' if is_cited else ''}">
  <div style="display:flex;justify-content:space-between;margin-bottom:6px">
    <div>
      <span style="font-family:ui-monospace,monospace;font-size:13px;font-weight:700">
        청크 #{esc(hit.get('chunk_index'))}
      </span>
      {'<span class="tag" style="background:#dcfce7;color:#16803c;margin-left:6px">인용됨</span>' if is_cited else ''}
    </div>
    <div style="font-weight:760;color:{sc};font-variant-numeric:tabular-nums">{sim:.1%}</div>
  </div>
  <div style="margin-bottom:6px">{tags}</div>
  <div class="chunk-text">{esc(preview)}</div>
</div>""")

    return "\n".join(cards) or '<div class="panel-copy">검색 결과가 없습니다.</div>'


def render_info_cell(label, value) -> str:
    return f'<div class="info-cell"><div class="info-lbl">{esc(label)}</div><div class="info-val">{esc(value)}</div></div>'


# ═══════════════════════════════════════════════════════════════════════════════
# 헤더 + 파일 업로드 (사이드바 없음)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="margin-bottom:20px">
  <div style="font-size:28px;font-weight:760;color:var(--text);letter-spacing:-.5px">ClearHS</div>
  <div style="color:var(--muted);font-size:14px;margin-top:3px">
    무역 서류를 업로드하면 상품 정보를 추출하고 HS 코드, FTA 가능성, 필요 서류를 한 화면에서 검토합니다.
  </div>
</div>
""", unsafe_allow_html=True)

up1, up2, up3 = st.columns(3)
with up1: invoice_file = st.file_uploader("📄 인보이스 *", type=["pdf"], key="invoice")
with up2: packing_file = st.file_uploader("📦 패킹리스트", type=["pdf"], key="packing")
with up3: spec_file    = st.file_uploader("📋 명세서",     type=["pdf"], key="spec")

with st.expander("⚙️ 고급 설정", expanded=False):
    test_mode = st.toggle(
        "🧪 테스트 모드",
        value=False,
        help="API 키/ChromaDB 없이 더미 데이터로 UI 확인. LLM이 필요한 2·3·5단계만 더미값으로 대체됩니다.",
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("**문서 추출 (Upstage)**")
        upstage_api_key = st.text_input("Upstage API Key", value=os.getenv("UPSTAGE_API_KEY",""),
                                         type="password", placeholder="up-...", disabled=test_mode)
        upstage_model   = st.selectbox("모델", ["solar-pro2","solar-mini"], disabled=test_mode)
    with sc2:
        st.markdown("**HS 분류 (OpenAI)**")
        openai_api_key  = st.text_input("OpenAI API Key", value=os.getenv("OPENAI_API_KEY",""),
                                         type="password", placeholder="sk-...", disabled=test_mode)
        openai_model    = st.selectbox("모델", ["gpt-4.1-mini","gpt-4.1","gpt-4o-mini","gpt-4o"], disabled=test_mode)
    dc1, dc2 = st.columns(2)
    with dc1:
        chroma_path     = st.text_input("ChromaDB 경로",
                                         value=os.getenv("CHROMA_DB_PATH", str(Path(__file__).parent/"chroma_db")),
                                         disabled=test_mode)
    with dc2:
        collection_name = st.text_input("컬렉션",
                                         value=os.getenv("COLLECTION_NAME","customs_knowledge_v3"),
                                         disabled=test_mode)

run_btn = st.button("분류 실행 →", use_container_width=True, type="primary",
                    disabled=invoice_file is None)

if invoice_file is None:
    st.info("인보이스를 업로드하면 분류를 실행할 수 있습니다.")

if not run_btn:
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# clearhs 모듈 import + CONFIG 주입
# ═══════════════════════════════════════════════════════════════════════════════
try:
    from clearhs.pdf_extraction     import build_combined_raw_text
    from clearhs.product_extraction import extract_product_info
    from clearhs.classification     import classify_hs_code
    from clearhs.xai                import calculate_xai_confidence, normalize_similarity
    from clearhs.fta                import check_fta_eligibility
    from clearhs.documents          import check_duty_exemption, verify_required_documents
    from clearhs.clients            import get_openai_client, get_upstage_client
    from clearhs.rag                import _get_collection
    from clearhs.models             import ProductInfo, ClassificationResult, ExemptionResult, CitedChunk
    import clearhs.config as _cfg
except ImportError as e:
    st.error(f"`clearhs` 패키지를 찾을 수 없어요. app.py가 프로젝트 루트에 있는지 확인해주세요.\n\n{e}")
    st.stop()

if not test_mode:
    _cfg.CONFIG["UPSTAGE_API_KEY"]  = upstage_api_key
    _cfg.CONFIG["UPSTAGE_MODEL"]    = upstage_model
    _cfg.CONFIG["OPENAI_API_KEY"]   = openai_api_key
    _cfg.CONFIG["OPENAI_MODEL"]     = openai_model
    _cfg.CONFIG["CHROMA_DB_PATH"]   = chroma_path
    _cfg.CONFIG["COLLECTION_NAME"]  = collection_name
    get_openai_client.cache_clear()
    get_upstage_client.cache_clear()
    _get_collection.cache_clear()


# ── 테스트 모드 더미 함수 ────────────────────────────────────────────────────
def _mock_extract(raw, docs):
    return ProductInfo(product_name="(테스트) 블루투스 이어폰", materials=["plastic","lithium battery"],
                       usage="개인용 음향기기", origin_country="China", manufacturer="Dummy Co., Ltd.",
                       quantity="100 EA", weight="2.5 kg", unit_price="15.00", currency="USD",
                       intended_user="일반 소비자용", raw_text=raw, source_documents=docs)

def _mock_classify(pi):
    cls = ClassificationResult(hs_code="8518.30", hs_code_description="헤드폰, 이어폰 및 마이크로폰과 결합된 음향기기",
        reasoning="(테스트 더미) 음향 변환기기 → HS 8518.30",
        cited_chunks=[CitedChunk(chunk_index="law_001", similarity=0.82, snippet="(더미 인용)")],
        llm_self_eval=0.78)
    log = [{"chunk_index":"law_001","text":"(더미 검색 결과) 헤드폰·이어폰 → HS 8518.30",
            "metadata":{"code":"8518.30","agreement":"KOREA_CHINA_FTA","source_type":"psr"},"similarity":0.82}]
    return cls, log

def _mock_exemption(pi):
    return ExemptionResult(is_likely_exempt=False, reasoning="(테스트 더미) 실제 면세 판단이 아닙니다.",
                           notes="API 키 연결 전 UI 확인용 더미 데이터입니다.")


# ── 파일 저장 ────────────────────────────────────────────────────────────────
tmp_dir = tempfile.mkdtemp()
def _save(f):
    p = os.path.join(tmp_dir, f.name)
    with open(p,"wb") as fh: fh.write(f.getbuffer())
    return p

doc_paths = {}
if invoice_file: doc_paths["invoice"]       = _save(invoice_file)
if packing_file: doc_paths["packing_list"]  = _save(packing_file)
if spec_file:    doc_paths["specification"] = _save(spec_file)


# ═══════════════════════════════════════════════════════════════════════════════
# 파이프라인 실행 (단일 st.status 블록)
# ═══════════════════════════════════════════════════════════════════════════════
if test_mode:
    st.warning("🧪 테스트 모드 — 2·3·5단계(상품정보·HS분류·면세판단)는 더미 데이터입니다.")

with st.status("서류를 읽고 분류를 준비하는 중입니다.", expanded=True) as status:
    try:
        raw          = build_combined_raw_text(doc_paths)
        status.update(label=f"원문 추출 완료: {len(raw):,}자", state="running")

        pi = _mock_extract(raw, list(doc_paths.keys())) if test_mode \
             else extract_product_info(raw, source_documents=list(doc_paths.keys()))
        status.update(label=f"상품 정보 추출 완료: {pi.product_name}", state="running")

        cls, retrieval_log = _mock_classify(pi) if test_mode else classify_hs_code(pi)
        cls.xai_confidence = calculate_xai_confidence(cls, retrieval_log)
        status.update(label=f"HS 코드 분류 완료: {cls.hs_code}", state="running")

        fta      = check_fta_eligibility(pi, cls)
        status.update(label="FTA 적용 가능성 확인 완료", state="running")

        exemption = _mock_exemption(pi) if test_mode else check_duty_exemption(pi)
        doc_check = verify_required_documents(pi, fta, exemption)
        status.update(label="검토가 완료되었습니다.", state="complete", expanded=False)
    except Exception as e:
        status.update(label="처리 중 오류가 발생했습니다.", state="error", expanded=True)
        st.error(str(e)); st.stop()


# ── 공통 계산값 ──────────────────────────────────────────────────────────────
cited_idx   = {c.chunk_index for c in cls.cited_chunks}
cited_sims  = [h.get("similarity",0) for h in retrieval_log if h.get("chunk_index") in cited_idx]
ret_score   = normalize_similarity(max(cited_sims) if cited_sims else 0.0)
conf        = cls.xai_confidence or 0.0
conf_color, _, _, conf_msg = confidence_tone(conf)
fta_ok      = bool(getattr(fta,"eligible", False))
missing_docs = list(getattr(doc_check,"missing_documents",[]) or [])
doc_ok      = bool(getattr(doc_check,"is_complete", False))
ret_w       = _cfg.CONFIG.get("RETRIEVAL_WEIGHT", 0.4)
llm_w       = _cfg.CONFIG.get("LLM_SELF_EVAL_WEIGHT", 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# 요약 그리드 (4 메트릭) — 스크롤 없이 한눈에
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="summary-grid">
  <div class="metric-card" style="border-left:3px solid var(--blue)">
    <div class="metric-label">최종 HS 코드</div>
    <div class="metric-value" style="color:var(--blue)">{esc(cls.hs_code)}</div>
    <div class="metric-note">{esc(cls.hs_code_description)}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">신뢰도</div>
    <div class="metric-value" style="color:{conf_color}">{pct(conf)}</div>
    <div class="metric-note">{esc(conf_msg)}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">FTA</div>
    <div class="metric-value" style="color:{'var(--green)' if fta_ok else 'var(--amber)'}">
      {'가능' if fta_ok else '확인 필요'}
    </div>
    <div class="metric-note">{esc(' · '.join(getattr(fta,'applicable_agreements',[]) or []) or '해당 협정 없음')}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">필요 서류</div>
    <div class="metric-value" style="color:{'var(--green)' if doc_ok else 'var(--red)'}">
      {'완비' if doc_ok else f'{len(missing_docs)}건 누락'}
    </div>
    <div class="metric-note">{esc(', '.join(missing_docs) if missing_docs else '업로드된 서류 기준 충족')}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── HS 분류 결과 (2단) ────────────────────────────────────────────────────────
st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
col_left, col_right = st.columns([1.3, 0.8], gap="medium")

# reasoning 마크업 변환 (0630 서연 방식 유지)
reasoning_html = (
    cls.reasoning
    .replace("\n","<br>")
    .replace("[후보 제외 이유]", "<b>❌ 후보 제외 이유</b>")
    .replace("[후보 비교]",     "<br><br><b>📚 후보 비교</b>")
    .replace("[최종 판단]",     "<br><br><b>✅ 최종 판단</b>")
)

with col_left:
    st.markdown(f"""
<div class="panel">
  <div class="kicker">Classification</div>
  <div class="panel-title">HS 코드 분류 결과</div>
  <div class="hs-hero">{esc(cls.hs_code)}</div>
  <div class="panel-copy">{esc(cls.hs_code_description)}</div>
  <div class="reason-box">{reasoning_html}</div>
</div>""", unsafe_allow_html=True)

with col_right:
    st.markdown(render_confidence_card(conf, ret_score, cls.llm_self_eval, ret_w, llm_w),
                unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 탭 구조 (스크롤 대신 탭으로 정보 분리)
# ═══════════════════════════════════════════════════════════════════════════════
tab_product, tab_evidence, tab_documents, tab_raw = st.tabs(
    ["📦 상품 정보", "🔍 분류 근거", "🤝 FTA / 서류", "📄 원문 / JSON"]
)

# ─ 상품 정보 탭 ──────────────────────────────────────────────────────────────
with tab_product:
    price = "-"
    if getattr(pi,"unit_price",None):
        price = f"{pi.unit_price} {getattr(pi,'currency','') or ''}".strip()

    mat_tags = "".join(f'<span class="tag">{esc(m)}</span>' for m in (pi.materials or []))

    st.markdown(f"""
<div class="panel">
  <div class="kicker">Extracted product</div>
  <div class="panel-title">추출된 상품 정보</div>
  <div class="info-grid">
    {render_info_cell("상품명",  pi.product_name)}
    {render_info_cell("제조사",  pi.manufacturer)}
    {render_info_cell("원산지",  pi.origin_country)}
    {render_info_cell("수량",    pi.quantity)}
    {render_info_cell("중량",    pi.weight)}
    {render_info_cell("단가",    price)}
  </div>
  <div style="margin-top:14px">
    <div class="info-lbl">용도</div>
    <div class="panel-copy">{esc(pi.usage)}</div>
  </div>
  <div style="margin-top:12px">
    <div class="info-lbl">재질/구성</div>
    <div>{mat_tags or '<span class="panel-copy">추출된 재질 정보 없음</span>'}</div>
  </div>
</div>""", unsafe_allow_html=True)

# ─ 분류 근거 탭 ──────────────────────────────────────────────────────────────
with tab_evidence:
    st.markdown(f"""
<div class="panel">
  <div class="kicker">RAG candidates</div>
  <div class="panel-title">검색 후보 코드 <span style="font-size:13px;font-weight:400;color:var(--muted)">(상위 3개)</span></div>
  <div class="panel-copy" style="margin-bottom:14px">
    DB에서 찾은 유사 사례입니다. 최종 선택과 같은 4단위 분류는 녹색으로 표시됩니다.
  </div>
  {render_candidate_codes(retrieval_log, cls.hs_code, max_show=3)}
</div>""", unsafe_allow_html=True)

    n_cited = len(cited_idx & {h.get("chunk_index") for h in retrieval_log})
    with st.expander(f"상세 청크 — {n_cited}건 인용 / {len(retrieval_log)}건 검색"):
        st.markdown(render_chunk_cards(retrieval_log, cited_idx), unsafe_allow_html=True)

# ─ FTA / 서류 탭 ─────────────────────────────────────────────────────────────
with tab_documents:
    agreements   = " · ".join(getattr(fta,"applicable_agreements",[]) or []) or "해당 없음"
    cert_type    = getattr(fta,"required_certificate_type",None) or "-"
    origin_crit  = getattr(fta,"origin_criterion",None)
    fta_reasoning= getattr(fta,"reasoning",None)
    exempt       = bool(getattr(exemption,"is_likely_exempt",False))
    ex_text      = getattr(exemption,"reasoning",None) or ("면세 대상 가능성 있음" if exempt else "면세/감면 대상에 해당하지 않음")

    doc_boxes = "".join(f"""
<div class="status-box {'status-box-red' if d in missing_docs else 'status-box-green'}">
  <div class="info-lbl">{'미업로드' if d in missing_docs else '업로드됨'}</div>
  <div class="info-val">{esc(str(d).replace('_',' ').title())}</div>
</div>""" for d in (doc_check.required_documents or []))

    st.markdown(f"""
<div class="panel">
  <div class="kicker">FTA & documents</div>
  <div class="panel-title">FTA 적용 가능성</div>
  <div class="status-grid" style="margin:12px 0">
    <div class="status-box {'status-box-green' if fta_ok else 'status-box-amber'}">
      <div class="info-lbl">적용 협정</div>
      <div class="info-val">{esc(agreements)}</div>
    </div>
    <div class="status-box">
      <div class="info-lbl">필요 증명서</div>
      <div class="info-val">{esc(cert_type)}</div>
    </div>
  </div>
  <div class="status-box" style="margin-bottom:18px">
    <div class="info-lbl">원산지결정기준 (PSR)</div>
    <div class="panel-copy">{esc(origin_crit) if origin_crit else 'PSR 데이터를 찾지 못했습니다. 수동 확인이 필요합니다.'}</div>
  </div>

  <div class="panel-title">면세/감면 대상 여부</div>
  <div class="status-box {'status-box-green' if exempt else ''}" style="margin:10px 0 18px">
    <div class="panel-copy">{esc(ex_text)}</div>
  </div>

  <div class="panel-title">필요 서류 체크리스트</div>
  <div class="status-grid" style="margin-top:10px">{doc_boxes}</div>
</div>""", unsafe_allow_html=True)

    if fta_reasoning:
        with st.expander("FTA 판단 근거 자세히 보기"):
            st.write(fta_reasoning)
            for c in (getattr(fta,"cited_chunks",[]) or []):
                st.caption(f"`{c.chunk_index}` — {c.snippet[:150]}")

# ─ 원문 / JSON 탭 ────────────────────────────────────────────────────────────
with tab_raw:
    with st.expander("추출된 원문", expanded=False):
        st.text_area("", value=raw, height=220, label_visibility="collapsed")

    final_result = {
        "product_info":   pi.model_dump(),
        "classification": cls.model_dump(),
        "fta_result":     fta.model_dump(),
        "document_check": doc_check.model_dump(),
    }
    st.download_button(
        label="⬇️ 전체 결과 JSON 다운로드",
        data=json.dumps(final_result, ensure_ascii=False, indent=2),
        file_name=f"clearhs_{str(pi.product_name)[:30].replace(' ','_')}.json",
        mime="application/json",
        use_container_width=True,
    )