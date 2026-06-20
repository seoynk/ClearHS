from typing import Dict

import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    """pdfplumber로 PDF의 모든 페이지 텍스트를 추출."""
    texts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    full_text = "\n".join(texts)

    if len(full_text.strip()) < 20:
        print(f"⚠️ 추출된 텍스트가 거의 없습니다 ({pdf_path}). 스캔본일 가능성이 있어요. OCR이 필요할 수 있습니다.")

    return full_text


def build_combined_raw_text(doc_paths: Dict[str, str]) -> str:
    """{'invoice': path, 'packing_list': path, 'specification': path} 형태로 받아서
    문서 종류별 헤더를 붙여 하나의 텍스트로 합침."""
    sections = []
    for doc_type, path in doc_paths.items():
        text = extract_text_from_pdf(path)
        sections.append(f"===== {doc_type.upper()} =====\n{text.strip()}")
    return "\n\n".join(sections)
