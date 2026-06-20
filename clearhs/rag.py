from functools import lru_cache
from typing import Dict, List

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from .config import CONFIG

SEARCH_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "search_hs_knowledge",
        "description": "HS코드 분류를 위해 관세청 품목분류 사례, 분류기준, 관련 법령 등을 ChromaDB에서 검색합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 질의 (제품명, 재질, 용도 등)"},
                "n_results": {"type": "integer", "description": "검색 결과 개수", "default": 5},
            },
            "required": ["query"],
        },
    },
}


@lru_cache(maxsize=1)
def _get_collection():
    """ChromaDB 컬렉션을 첫 호출 시점에만 연결한다.
    (모듈을 import만 해도 바로 DB에 연결되면, 키/경로가 아직 안 갖춰진 환경에서 import 자체가
    실패할 수 있어서 — 실제로 검색을 호출하는 시점까지 연결을 미뤄둔다.)"""
    chroma_client = chromadb.PersistentClient(path=CONFIG["CHROMA_DB_PATH"])
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=CONFIG["EMBEDDING_MODEL"])
    return chroma_client.get_collection(
        name=CONFIG["COLLECTION_NAME"],
        embedding_function=embedding_fn,
    )


def search_hs_knowledge(query: str, n_results: int = 5) -> List[Dict]:
    """ChromaDB에서 관세 분류사례/기준 등을 검색해 (청크, 유사도) 리스트로 반환."""
    collection = _get_collection()
    results = collection.query(query_texts=[query], n_results=n_results)
    hits = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        hits.append({
            "chunk_index": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "similarity": round(1 - distance, 4),  # cosine distance -> similarity
        })
    return hits
