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
    api_key = st.text_input(
        "Upstage API Key",
        value=os.getenv("UPSTAGE_API_KEY", ""),
        type="password",
        placeholder="...",
    )
    chroma_path = st.text_input(
        "ChromaDB 경로",
        value=os.getenv("CHROMA_DB_PATH", str(Path(__file__).parent / "chroma_db")),
        placeholder="./chroma_db",
    )
    collection_name = st.text_input(
        "컬렉션 이름",
        value=os.getenv("COLLECTION_NAME", "customs_knowledge_v3"),
    )
    model_name = st.selectbox(
    "모델",
    ["solar-mini"],
    index=0,
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


# ── 실행: 설정을 환경변수로 주입 후 파이프라인 호출 ──────────────────────────
os.environ["OPENAI_API_KEY"]  = api_key
os.environ["CHROMA_DB_PATH"]  = chroma_path
os.environ["COLLECTION_NAME"] = collection_name
os.environ["OPENAI_MODEL"]    = model_name

# clearhs를 import하기 전에 환경변수를 세팅해야 하므로 run 시점에 import
try:
    from clearhs.pdf_extraction    import build_combined_raw_text
    from clearhs.product_extraction import extract_product_info
    from clearhs.classification    import classify_hs_code
    from clearhs.xai               import calculate_xai_confidence
    from clearhs.fta               import check_fta_eligibility
    from clearhs.documents         import verify_required_documents
    # lru_cache 된 클라이언트/컬렉션을 환경변수 변경 후 재생성하기 위해 캐시 초기화
    from clearhs.clients import get_client
    from clearhs.rag     import _get_collection
    get_client.cache_clear()
    _get_collection.cache_clear()
except ImportError as e:
    st.error(f"clearhs 패키지를 찾을 수 없어요. `app.py`가 프로젝트 루트에 있는지 확인해주세요.\n\n`{e}`")
    st.stop()

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


# ─ 5단계: 서류 검증 ───────────────────────────────────────────────────────────
with st.status("📋 5단계: 필요 서류 검증 중...", expanded=False) as s5:
    try:
        doc_check = verify_required_documents(product_info, fta_result)
        label = "✅ 서류 완비" if doc_check.is_complete else f"⚠️ 누락 서류 {len(doc_check.missing_documents)}건"
        s5.update(label=f"5단계 완료 — {label}", state="complete")
    except Exception as e:
        s5.update(label="❌ 5단계 실패", state="error", expanded=True)
        st.error(str(e))
        st.stop()

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
