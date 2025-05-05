import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List, Union

from services.youtube import YouTubeService
from transcription.service import TranscriptionService
from retrieval.vector_store import VectorStore
from llm.provider import LLMProvider
from cache.manager import CacheManager


class ProcessingEngine:
    def __init__(self):
        self.youtube_service = YouTubeService()
        self.transcription = TranscriptionService()
        self.vector_store = VectorStore()
        self.llm_provider = LLMProvider()
        self.cache_manager = CacheManager()

    async def process_video(self, video_url: str, options: Dict[str, Any]) -> str:
        video_id = self.youtube_service.extract_video_id(video_url)

        if self.cache_manager.has_processed_video(video_id):
            return video_id

        audio_path = await self.youtube_service.download_audio(video_url, options)
        transcript_data = await self.transcription.transcribe(audio_path, video_id, options)
        await self.vector_store.index_transcript(transcript_data, video_id)
        self.cache_manager.mark_video_processed(video_id)

        return video_id

    async def query_video(
        self,
        video_id: str,
        query: str,
        stream: bool = True,
        options: Dict[str, Any] = {}
    ) -> Union[str, AsyncGenerator[Dict[str, Any], None], Dict[str, Any]]:
        # Cache lookup
        cached_response = self.cache_manager.get_cached_response(video_id, query)
        if cached_response:
            if stream:
                async def yield_cached():
                    yield {
                        "token": cached_response,
                        "is_complete": True,
                        "processed_response": cached_response
                    }
                return yield_cached()
            else:
                return {
                    "response": cached_response,
                    "hallucination": None,
                    "relevance": None
                }

        # Determine hybrid search weight
        search_method = options.get("search_method", "hybrid")
        if search_method == "vector":
            vector_weight = 1.0
        elif search_method == "keyword":
            vector_weight = 0.0
        else:
            vector_weight = 0.7

        context_data = await self.vector_store.hybrid_search(video_id, query, vector_weight=vector_weight)
        context_text = "\n\n".join([item["content"] for item in context_data])

        if stream:
            async def process_stream():
                full_response = ""
                async for chunk in self.llm_provider.stream_response(query, context_data, video_id=video_id):
                    if not chunk["is_complete"]:
                        full_response += chunk["token"]
                        yield chunk
                    else:
                        processed_response = chunk.get("processed_response", full_response)
                        self.cache_manager.cache_response(video_id, query, processed_response)
                        yield {
                            "token": "",
                            "is_complete": True,
                            "processed_response": processed_response
                        }

            return process_stream()

        else:
            result = await self.llm_provider.generate(query, context_data, video_id=video_id)
            processed_response = result["response"]
            self.cache_manager.cache_response(video_id, query, processed_response)

            return {
                "response": processed_response
            }

    async def summarize_video(self, video_id: str, length: str = "medium") -> str:
        # Check if summary is cached
        cache_key = f"summarize {length}"
        cached_summary = self.cache_manager.get_cached_response(video_id, cache_key)
        if cached_summary:
            return cached_summary

        # ✅ Load full chunks directly from Chroma using filtering
        chroma = self.vector_store._get_chroma()
        docs = chroma.similarity_search("summary_seed", k=1000, filter={"video_id": video_id})
        full_content = "\n\n".join([doc.page_content for doc in docs])

        if not full_content.strip():
            print("[WARNING] Transcript is empty, skipping summarization.")
            return ""

        # Generate and cache summary
        summary = await self.llm_provider.summarize(full_content, length)
        self.cache_manager.cache_response(video_id, cache_key, summary)

        return summary
