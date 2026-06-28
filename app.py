"""ClearHS 파이프라인 Streamlit 테스트 UI
실행: streamlit run app.py  (프로젝트 루트에서)
"""

import json
import os
import tempfile
from pathlib import Path

import streamlit as st

# ── 페이지 기본 설정 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClearHS – HS 코드 분류",
    page_icon="🛃",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 최소한의 전역 스타일 ──────────────────────────────────────────────────────
st.markdown("""
<style>
/* 섹션 카드 */
.result-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1rem;
}
/* HS 코드 큰 표시 */
.hs-badge {
    font-size: 2.2rem;
    font-weight: 700;
    color: #1e40af;
    letter-spacing: 2px;
}
/* 신뢰도 색상 */
.conf-high  { color: #16a34a; font-weight: 700; }
.conf-mid   { color: #d97706; font-weight: 700; }
.conf-low   { color: #dc2626; font-weight: 700; }
/* 서류 상태 */
.doc-ok   { color: #16a34a; }
.doc-miss { color: #dc2626; }
</style>
""", unsafe_allow_html=True)


# ── 사이드바: 설정 + 파일 업로드 ─────────────────────────────────────────────
with st.sidebar:
    st.title("🛃 ClearHS")
    st.caption("관세 HS 코드 자동 분류 · 테스트 UI")
    st.divider()

    # --- 환경 설정 ---
    st.subheader("⚙️ 환경 설정")

    # 0628 유림 추가 — API 키/ChromaDB 없이 화면·연결만 먼저 확인하는 모드
    test_mode = st.checkbox(
        "🧪 테스트 모드 (API 키 / ChromaDB 없이 더미 데이터로 확인)",
        value=False,
        help="API 키를 아직 못 받았거나 ChromaDB가 준비 안 됐을 때, UI와 파이프라인 연결이 "
             "제대로 되는지 더미 데이터로 먼저 확인할 수 있어요. PDF 추출(1단계)·FTA(4단계)·"
             "서류검증(5단계 로직)은 그대로 실제 코드로 돌아가고, LLM이 필요한 "
             "상품정보추출(2단계)·HS분류(3단계)·면세판단(5단계)만 더미값으로 대체돼요.",
    )

    api_key = st.text_input(
        "Upstage API Key",
        value=os.getenv("UPSTAGE_API_KEY", ""),
        type="password",
        placeholder="...",
        disabled=test_mode,
    )
    chroma_path = st.text_input(
        "ChromaDB 경로",
        value=os.getenv("CHROMA_DB_PATH", str(Path(__file__).parent / "chroma_db")),
        placeholder="./chroma_db",
        disabled=test_mode,
    )
    collection_name = st.text_input(
        "컬렉션 이름",
        value=os.getenv("COLLECTION_NAME", "customs_knowledge_v3"),
        disabled=test_mode,
    )
    model_name = st.selectbox(
        "모델",
        ["solar-pro2", "solar-mini"],
        index=0,
        help="구조화된 출력(response_format)은 solar-pro2에서만 지원돼요. "
             "solar-mini는 분류/추출/면세판단 단계에서 에러가 날 수 있어요.",
        disabled=test_mode,
    )
    st.divider()

    # --- 파일 업로드 ---
    st.subheader("📄 문서 업로드")
    st.caption("인보이스는 필수. 나머지는 선택.")

    invoice_file     = st.file_uploader("인보이스 (Invoice) *", type=["pdf"], key="invoice")
    packing_file     = st.file_uploader("패킹리스트 (Packing List)", type=["pdf"], key="packing")
    spec_file        = st.file_uploader("명세서 (Specification)", type=["pdf"], key="spec")

    st.divider()
    run_btn = st.button(
        "🚀 분류 실행",
        use_container_width=True,
        type="primary",
        disabled=invoice_file is None,
    )
    if invoice_file is None:
        st.caption("인보이스를 업로드하면 버튼이 활성화됩니다.")


# ── 메인: 초기 안내 ───────────────────────────────────────────────────────────
if not run_btn:
    st.markdown("## 시작하려면 왼쪽에서 파일을 업로드하고 **분류 실행**을 눌러주세요.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**1단계** PDF → 텍스트 추출\npdfplumber")
    with col2:
        st.info("**2단계** 구조화 추출 + 분류\nGPT + RAG (ChromaDB)")
    with col3:
        st.info("**3단계** XAI · FTA · 서류검증\n신뢰도 · 협정 · 서류 체크")
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
    from clearhs.pdf_extraction    import build_combined_raw_text
    from clearhs.product_extraction import extract_product_info
    from clearhs.classification    import classify_hs_code
    from clearhs.xai               import calculate_xai_confidence
    from clearhs.fta               import check_fta_eligibility
    from clearhs.documents         import check_duty_exemption, verify_required_documents  # 0626 유림 추가
    from clearhs.clients import get_client
    from clearhs.rag     import _get_collection
    from clearhs.models  import ProductInfo, ClassificationResult, FTAResult, ExemptionResult, CitedChunk  # 0628 유림 추가
    import clearhs.config as _cfg
except ImportError as e:
    st.error(f"clearhs 패키지를 찾을 수 없어요. `app.py`가 프로젝트 루트에 있는지 확인해주세요.\n\n`{e}`")
    st.stop()

# 0628 유림 추가 — 테스트 모드용 더미 함수들 (실제 API/ChromaDB 호출 없음, models.py 그대로 사용)
def _mock_extract_product_info(raw_text: str, source_documents: list) -> ProductInfo:
    return ProductInfo(
        product_name="(테스트 모드) 블루투스 이어폰",
        materials=["plastic", "lithium battery"],
        usage="개인용 음향기기",
        origin_country="China",
        manufacturer="Dummy Co., Ltd.",
        quantity="100 EA",
        weight="2.5 kg",
        unit_price="15.00",
        currency="USD",
        intended_user="일반 소비자용",
        raw_text=raw_text,
        source_documents=source_documents,
    )

def _mock_classify_hs_code(product_info: ProductInfo):
    classification = ClassificationResult(
        hs_code="8518.30",
        hs_code_description="헤드폰·이어폰 및 이와 결합된 마이크로폰",
        reasoning="(테스트 모드 더미) 음향 변환기기로 분류되어 HS 8518.30에 해당함",
        cited_chunks=[CitedChunk(chunk_index="law_001", similarity=0.82, snippet="(더미 인용 텍스트)")],
        llm_self_eval=0.78,
    )
    retrieval_log = [
        {"chunk_index": "law_001", "text": "(더미 검색 결과 텍스트)", "metadata": {}, "similarity": 0.82},
    ]
    return classification, retrieval_log

def _mock_check_duty_exemption(product_info: ProductInfo) -> ExemptionResult:
    return ExemptionResult(
        is_likely_exempt=False,
        reasoning="(테스트 모드 더미) 실제 면세 판단이 아닙니다.",
        notes="API 키 연결 전 UI 확인용 더미 데이터입니다.",
    )

# 0626 유림 수정 — os.environ 대신 CONFIG를 직접 덮어씀 + OPENAI_BASE_URL 추가
if not test_mode:
    _cfg.CONFIG["OPENAI_API_KEY"]  = api_key
    _cfg.CONFIG["OPENAI_BASE_URL"] = "https://api.upstage.ai/v1"  # Upstage Solar 엔드포인트
    _cfg.CONFIG["OPENAI_MODEL"]    = model_name
    _cfg.CONFIG["CHROMA_DB_PATH"]  = chroma_path
    _cfg.CONFIG["COLLECTION_NAME"] = collection_name

    # lru_cache 된 클라이언트/컬렉션을 새 설정으로 재생성하기 위해 캐시 초기화
    get_client.cache_clear()
    _get_collection.cache_clear()

# 업로드 파일을 임시 파일로 저장
tmp_dir = tempfile.mkdtemp()

def save_tmp(uploaded) -> str:
    path = os.path.join(tmp_dir, uploaded.name)
    with open(path, "wb") as f:
        f.write(uploaded.getbuffer())
    return path

doc_paths: dict[str, str] = {}
if invoice_file: doc_paths["invoice"]      = save_tmp(invoice_file)
if packing_file: doc_paths["packing_list"] = save_tmp(packing_file)
if spec_file:    doc_paths["specification"] = save_tmp(spec_file)


# ── 단계별 실행 + 결과 렌더링 ────────────────────────────────────────────────
st.markdown("## 📊 분류 결과")

if test_mode:
    st.warning("🧪 테스트 모드입니다 — 2·3·5단계(상품정보추출·HS분류·면세판단)는 전부 더미 데이터예요. "
               "실제 분류/판단 결과가 아니라 화면과 데이터 연결만 확인하는 용도예요.")

result = {}

# ─ 1단계: PDF 추출 ────────────────────────────────────────────────────────────
with st.status("📄 1단계: PDF 텍스트 추출 중...", expanded=False) as s1:
    try:
        combined_raw_text = build_combined_raw_text(doc_paths)
        char_count = len(combined_raw_text)
        s1.update(label=f"✅ 1단계 완료 — {char_count:,}자 추출", state="complete", expanded=False)
    except Exception as e:
        s1.update(label="❌ 1단계 실패", state="error", expanded=True)
        st.error(str(e))
        st.stop()

with st.expander("추출된 원문 보기"):
    st.text_area("raw_text", value=combined_raw_text, height=200, label_visibility="collapsed")


# ─ 2단계: 상품정보 구조화 추출 ────────────────────────────────────────────────
with st.status("🔍 2단계: 상품 정보 구조화 중 (LLM)...", expanded=False) as s2:
    try:
        # 0628 유림 수정 — 테스트 모드 분기
        if test_mode:
            product_info = _mock_extract_product_info(combined_raw_text, list(doc_paths.keys()))
        else:
            product_info = extract_product_info(combined_raw_text, source_documents=list(doc_paths.keys()))
        s2.update(label=f"✅ 2단계 완료 — {product_info.product_name}", state="complete")
    except Exception as e:
        s2.update(label="❌ 2단계 실패", state="error", expanded=True)
        st.error(str(e))
        st.stop()

st.markdown("### 📦 추출된 상품 정보")
cols = st.columns(2)
fields = {
    "상품명": product_info.product_name,
    "제조사": product_info.manufacturer or "—",
    "원산지": product_info.origin_country or "—",
    "용도":   product_info.usage or "—",
    "수량":   product_info.quantity or "—",
    "중량":   product_info.weight or "—",
}
for i, (label, val) in enumerate(fields.items()):
    cols[i % 2].metric(label, val)

if product_info.materials:
    st.markdown("**소재·재질**")
    st.markdown("  ".join(f"`{m}`" for m in product_info.materials))


# ─ 3단계: HS 코드 분류 (RAG Tool Calling) ─────────────────────────────────────
with st.status("🤖 3단계: HS 코드 분류 중 (RAG + Tool Calling)...", expanded=False) as s3:
    try:
        # 0628 유림 수정 — 테스트 모드 분기
        if test_mode:
            classification, retrieval_log = _mock_classify_hs_code(product_info)
        else:
            classification, retrieval_log = classify_hs_code(product_info)
        classification.xai_confidence = calculate_xai_confidence(classification, retrieval_log)
        s3.update(label=f"✅ 3단계 완료 — HS {classification.hs_code}", state="complete")
    except Exception as e:
        s3.update(label="❌ 3단계 실패", state="error", expanded=True)
        st.error(str(e))
        st.stop()

st.markdown("### 🏷️ HS 코드 분류")
c1, c2, c3 = st.columns([2, 2, 2])

conf = classification.xai_confidence or 0
conf_class = "conf-high" if conf >= 0.75 else ("conf-mid" if conf >= 0.5 else "conf-low")
conf_label = "높음 ✅" if conf >= 0.75 else ("보통 ⚠️" if conf >= 0.5 else "낮음 ❌")

with c1:
    st.markdown(f'<div class="hs-badge">{classification.hs_code}</div>', unsafe_allow_html=True)
    if classification.hs_code_description:
        st.caption(classification.hs_code_description)

with c2:
    st.markdown(f"**XAI 신뢰도**")
    st.progress(conf)
    st.markdown(f'<span class="{conf_class}">{conf:.1%} — {conf_label}</span>', unsafe_allow_html=True)
    st.caption(f"검색유사도 40% + LLM자체평가 {classification.llm_self_eval:.1%} × 60%")

with c3:
    st.markdown("**분류 근거**")
    st.write(classification.reasoning)

if retrieval_log:
    with st.expander(f"📚 RAG 검색 결과 ({len(retrieval_log)}건)"):
        for hit in retrieval_log:
            sim = hit.get("similarity", 0)
            bar = "█" * int(sim * 10) + "░" * (10 - int(sim * 10))
            st.markdown(f"**`{hit['chunk_index']}`** [{bar}] {sim:.4f}")
            meta = hit.get("metadata", {})
            if meta.get("agreement"):
                st.caption(f"협정: {meta['agreement']}  |  코드: {meta.get('code','—')}")
            st.text(hit["text"][:300] + ("..." if len(hit["text"]) > 300 else ""))
            st.divider()

if classification.cited_chunks:
    with st.expander(f"🔗 인용된 청크 ({len(classification.cited_chunks)}건)"):
        for chunk in classification.cited_chunks:
            st.markdown(f"- **`{chunk.chunk_index}`** 유사도 `{chunk.similarity:.4f}` — {chunk.snippet}")


# ─ 4단계: FTA 적용 판단 ───────────────────────────────────────────────────────
with st.status("🤝 4단계: FTA 적용 가능성 판단 중...", expanded=False) as s4:
    try:
        fta_result = check_fta_eligibility(product_info, classification)
        s4.update(label=f"✅ 4단계 완료 — {'FTA 적용 가능' if fta_result.eligible else 'FTA 해당 없음'}", state="complete")
    except Exception as e:
        s4.update(label="❌ 4단계 실패", state="error", expanded=True)
        st.error(str(e))
        st.stop()

st.markdown("### 🤝 FTA 적용 가능성")
if fta_result.eligible:
    st.success(f"FTA 적용 가능 — {', '.join(fta_result.applicable_agreements)}")
    if fta_result.required_certificate_type:
        st.markdown(f"**필요 서류:** {fta_result.required_certificate_type}")
else:
    st.warning("해당 원산지에 적용 가능한 FTA 협정 없음 (현재 stub 기준)")
if fta_result.notes:
    st.caption(f"⚠️ {fta_result.notes}")


# ─ 5단계: 면세 판단 + 서류 검증 ─────────────────────────────────────────────────
# 0626 유림 수정 (check_duty_exemption 호출 추가, verify_required_documents에 결과 전달)
with st.status("📋 5단계: 면세 대상 여부 판단 + 필요 서류 검증 중...", expanded=False) as s5:
    try:
        # 0628 유림 수정 — 테스트 모드 분기
        if test_mode:
            exemption_result = _mock_check_duty_exemption(product_info)
        else:
            exemption_result = check_duty_exemption(product_info)
        doc_check = verify_required_documents(product_info, fta_result, exemption_result)
        label = "✅ 서류 완비" if doc_check.is_complete else f"⚠️ 누락 서류 {len(doc_check.missing_documents)}건"
        s5.update(label=f"5단계 완료 — {label}", state="complete")
    except Exception as e:
        s5.update(label="❌ 5단계 실패", state="error", expanded=True)
        st.error(str(e))
        st.stop()

# 0626 유림 추가 — 면세 가능성 UI
st.markdown("### 💰 면세/감면 대상 여부")
if exemption_result.is_likely_exempt:
    st.success(
        f"면세 대상일 가능성 있음 — {exemption_result.exemption_category or ''} "
        f"({exemption_result.exemption_basis or '근거 조항 미확정'})"
    )
    st.markdown(f"**판단 근거:** {exemption_result.reasoning}")
    if exemption_result.additional_required_documents:
        st.markdown(f"**추가로 필요한 서류:** {', '.join(exemption_result.additional_required_documents)}")
else:
    st.info("면세/감면 대상에 해당하지 않는 것으로 판단됨")
if exemption_result.notes:
    st.caption(f"⚠️ {exemption_result.notes}")

st.markdown("### 📋 필요 서류 검증")
doc_cols = st.columns(len(doc_check.required_documents))
for i, doc in enumerate(doc_check.required_documents):
    missing = doc in doc_check.missing_documents
    icon = "❌" if missing else "✅"
    status_txt = "미업로드" if missing else "업로드됨"
    doc_cols[i].metric(doc.replace("_", " ").title(), f"{icon} {status_txt}")

if doc_check.is_complete:
    st.success("필요 서류가 모두 업로드되었습니다.")
else:
    st.error(f"누락 서류: {', '.join(doc_check.missing_documents)}")


# ─ 결과 JSON 다운로드 ─────────────────────────────────────────────────────────
st.divider()
final_result = {
    "product_info":    product_info.model_dump(),
    "classification":  classification.model_dump(),
    "fta_result":      fta_result.model_dump(),
    "document_check":  doc_check.model_dump(),
}
st.download_button(
    label="⬇️ 전체 결과 JSON 다운로드",
    data=json.dumps(final_result, ensure_ascii=False, indent=2),
    file_name=f"clearhs_{product_info.product_name[:30].replace(' ','_')}.json",
    mime="application/json",
    use_container_width=True,
)