"""
chroma_sync.py

ChromaDB 컬렉션을 기기 간에 안전하게 옮기기 위한 export/rebuild 유틸리티.

배경
----
로컬 chroma_db/ 폴더 안의 hnsw 인덱스는 OS/아키텍처/chromadb 버전에 따라 다른 기기에서
못 읽는 경우가 있음 (Windows에서 만든 인덱스를 Mac에서 못 읽는 문제 등).
또한 GPU 없는 기기에서 전체 코퍼스를 처음부터 bge-m3로 다시 임베딩하면 몇 시간이 걸림.

해결책: "임베딩 계산"(느림, 모델 forward pass 필요)과 "로컬 인덱스 생성"(빠름, 벡터만
저장)을 분리한다.
- export: 이미 임베딩이 끝난 기기에서, 벡터+문서+메타데이터를 휴대 가능한 jsonl로 내보냄
- rebuild: 다른 기기에서 그 jsonl을 읽어, 임베딩 재계산 없이 새 로컬 컬렉션을 만듦
  (collection.add(embeddings=...)로 넣으면 임베딩 함수 forward pass 자체가 안 일어남)

사용법 (프로젝트 루트, clearhs 패키지를 import할 수 있는 위치에서 실행)
----
    # 임베딩이 이미 끝난 기기 (예: 숭 컴)에서
    python chroma_sync.py export --out customs_knowledge_v3.jsonl

    # 다른 기기 (예: 엶 컴)에서 — 위에서 만든 jsonl을 받아서
    python chroma_sync.py rebuild --in customs_knowledge_v3.jsonl

주의: jsonl 파일은 벡터(숫자) 포함이라 csv보다 크지만, 임베딩 자체를 다시 계산하는 것보다는
훨씬 가벼워요. git에는 올리지 말고 (현재 .gitignore가 *.csv, chroma_db/만 막고 있어서
이 jsonl은 안 막힘 — 필요하면 .gitignore에 *.jsonl도 추가) 드라이브/USB로 직접 전달하세요.
"""
import argparse
import json

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from clearhs.config import CONFIG


def _get_client():
    return chromadb.PersistentClient(path=CONFIG["CHROMA_DB_PATH"])


def export_collection(out_path: str, batch_size: int = 500) -> None:
    client = _get_client()
    collection = client.get_collection(CONFIG["COLLECTION_NAME"])
    total = collection.count()
    print(f"총 {total}개 문서를 '{out_path}'로 내보냅니다...")

    with open(out_path, "w", encoding="utf-8") as f:
        offset = 0
        while offset < total:
            batch = collection.get(
                include=["embeddings", "documents", "metadatas"],
                limit=batch_size,
                offset=offset,
            )
            for i in range(len(batch["ids"])):
                row = {
                    "id": batch["ids"][i],
                    "embedding": list(batch["embeddings"][i]),
                    "document": batch["documents"][i],
                    "metadata": batch["metadatas"][i],
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            offset += batch_size
            print(f"  {min(offset, total)}/{total}")
    print("완료! 이 파일을 다른 기기로 옮긴 뒤 'rebuild' 명령으로 불러오세요.")


def rebuild_collection(in_path: str, batch_size: int = 500) -> None:
    client = _get_client()
    # 모델 '로딩'은 빠름 (몇 초) — 느렸던 건 코퍼스 전체를 인코딩하는 forward pass였음.
    # 여기서는 이미 계산된 임베딩을 그대로 넣을 거라 forward pass가 발생하지 않음.
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=CONFIG["EMBEDDING_MODEL"])

    try:
        client.delete_collection(CONFIG["COLLECTION_NAME"])
        print(f"기존 '{CONFIG['COLLECTION_NAME']}' 컬렉션(깨졌던 것) 삭제함")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        CONFIG["COLLECTION_NAME"],
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    ids, docs, metas, embs = [], [], [], []
    with open(in_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ids.append(row["id"])
            docs.append(row["document"])
            metas.append(row["metadata"])
            embs.append(row["embedding"])

    print(f"총 {len(ids)}개 벡터를 임베딩 재계산 없이 추가합니다 (빠름)...")
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i : i + batch_size],
            embeddings=embs[i : i + batch_size],
            documents=docs[i : i + batch_size],
            metadatas=metas[i : i + batch_size],
        )
        print(f"  {min(i + batch_size, len(ids))}/{len(ids)}")
    print("완료! 임베딩 재계산 없이 이 기기에 로컬 인덱스를 새로 만들었습니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChromaDB 컬렉션 export/rebuild (기기간 이전용)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="현재 기기의 컬렉션을 jsonl로 내보내기")
    p_export.add_argument("--out", required=True)

    p_rebuild = sub.add_parser("rebuild", help="jsonl로부터 로컬 컬렉션 재생성 (임베딩 재계산 없음)")
    p_rebuild.add_argument("--in", dest="in_path", required=True)

    args = parser.parse_args()
    if args.command == "export":
        export_collection(args.out)
    elif args.command == "rebuild":
        rebuild_collection(args.in_path)
