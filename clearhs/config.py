import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# clearhs/config.py 기준 부모 폴더(프로젝트 루트)를 계산해서 chroma_db 기본 경로를 잡는다.
# -> 어떤 cwd에서 스크립트를 실행하든 항상 같은 chroma_db를 보게 됨 (노트북에서 겪었던
#    "../chroma_db"가 실행 위치에 따라 다른 폴더를 가리키는 문제를 구조적으로 없앤다).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CHROMA_PATH = str(_PROJECT_ROOT / "chroma_db")

CONFIG = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
    "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "solar-mini"),
    "CHROMA_DB_PATH": os.getenv("CHROMA_DB_PATH") or _DEFAULT_CHROMA_PATH,
    "COLLECTION_NAME": os.getenv("COLLECTION_NAME", "customs_knowledge_v3"),
    "EMBEDDING_MODEL": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    "RETRIEVAL_WEIGHT": float(os.getenv("RETRIEVAL_WEIGHT", "0.4")),
    "LLM_SELF_EVAL_WEIGHT": float(os.getenv("LLM_SELF_EVAL_WEIGHT", "0.6")),
}
