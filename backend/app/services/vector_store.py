"""
向量库封装 - ChromaDB

提供 add / similarity_search / delete_by_file 等操作，
搜索时返回 chunk 文本 + 完整 metadata。
"""
import os
import uuid
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from app.config import get_settings

settings = get_settings()

_chroma_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None
_embedding_fn = None


def _get_chroma_dir() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    chroma_dir = os.path.join(base, "chroma_data")
    os.makedirs(chroma_dir, exist_ok=True)
    return chroma_dir


def _get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
    return _embedding_fn


def _get_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        chroma_dir = _get_chroma_dir()
        _chroma_client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = _get_client()
        ef = _get_embedding_fn()
        _collection = client.get_or_create_collection(
            name="documents",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_chunks(chunks: list) -> int:
    """
    批量添加 chunk 到向量库。
    返回添加的 chunk 数量。
    """
    collection = get_collection()

    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        chunk_id = str(uuid.uuid4())
        ids.append(chunk_id)
        documents.append(chunk.text)

        # Chroma metadata 只接受 str/int/float/bool
        meta = dict(chunk.metadata)
        meta["headers"] = "|".join(meta.get("headers", []))
        metadatas.append(meta)

    if not ids:
        return 0

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )
    return len(ids)


def similarity_search(query: str, top_k: int = 5) -> List[dict]:
    """
    相似度搜索。返回 [{id, text, metadata, distance}, ...]
    metadata 中的 headers 字段会被还原为 list。
    """
    collection = get_collection()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    output = []
    if not results["ids"] or not results["ids"][0]:
        return output

    for i, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        if "headers" in meta and isinstance(meta["headers"], str):
            meta["headers"] = meta["headers"].split("|") if meta["headers"] else []
        output.append({
            "id": doc_id,
            "text": results["documents"][0][i],
            "metadata": meta,
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })

    return output


def delete_by_file(file_path: str) -> int:
    """删除指定文件的所有 chunk。"""
    collection = get_collection()
    results = collection.get(where={"file_path": file_path})
    if results["ids"]:
        collection.delete(ids=results["ids"])
        return len(results["ids"])
    return 0


def clear_collection() -> None:
    """清空整个 collection。"""
    client = _get_client()
    try:
        client.delete_collection("documents")
    except Exception:
        pass
    global _collection
    _collection = None


def search(search_query: str, top_k: int = 3) -> List[dict]:
    """便捷搜索函数（供验证脚本使用）。"""
    return similarity_search(search_query, top_k=top_k)
