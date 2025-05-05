"""
Vector storage using ChromaDB (local, persistent) + OpenAI Embeddings
"""

import os
from typing import List, Dict, Any

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.schema import Document
from langchain.vectorstores import Chroma

from config.settings import (
    OPENAI_API_KEY,
    EMBEDDINGS_MODEL,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    VECTOR_DIR
)
from retrieval.chunking import adaptive_text_splitter


class VectorStore:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=OPENAI_API_KEY,
            model=EMBEDDINGS_MODEL
        )
        self.vectorstore = None

    def _get_chroma(self):
        if not self.vectorstore:
            self.vectorstore = Chroma(
                persist_directory=VECTOR_DIR,
                embedding_function=self.embeddings
            )
        return self.vectorstore

    async def index_transcript(self, transcript_data: Dict[str, Any], video_id: str) -> None:
        transcript_text = transcript_data.get("transcript", "")
        chunks = adaptive_text_splitter(
            transcript_text,
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=DEFAULT_CHUNK_OVERLAP
        )

        # Create LangChain Document objects with metadata
        docs = [
            Document(page_content=chunk, metadata={"video_id": video_id, "chunk_id": i})
            for i, chunk in enumerate(chunks)
        ]

        # Store in Chroma and persist
        chroma = self._get_chroma()
        chroma.add_documents(docs)
        chroma.persist()

    async def hybrid_search(self, video_id: str, query: str, k: int = 4, vector_weight: float = 0.7) -> List[Dict[str, Any]]:
        chroma = self._get_chroma()

        # Perform vector similarity search with video_id filter
        results = chroma.similarity_search(
            query=query,
            k=k,
            filter={"video_id": video_id}
        )

        return [{"content": doc.page_content} for doc in results]
