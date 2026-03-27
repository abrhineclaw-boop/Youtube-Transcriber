"""Abstract base repository defining the data access interface.

All database access goes through this interface so that swapping
SQLite for PostgreSQL is an implementation change, not a rewrite.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseRepository(ABC):
    """Abstract data access layer."""

    # --- Lifecycle ---
    @abstractmethod
    async def initialize(self) -> None:
        """Create tables and seed data if needed."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up connections."""
        ...

    # --- Profiles ---
    @abstractmethod
    async def get_profiles(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_profile(self, profile_id: int) -> Optional[dict]:
        ...

    @abstractmethod
    async def create_profile(self, name: str, description: str, analysis_hints: str = "") -> int:
        ...

    @abstractmethod
    async def delete_profile(self, profile_id: int) -> bool:
        """Delete a profile. Returns False if transcripts still reference it."""
        ...

    # --- Transcripts ---
    @abstractmethod
    async def create_transcript(self, video_url: str, profile_id: int) -> int:
        ...

    @abstractmethod
    async def get_transcript(self, transcript_id: int) -> Optional[dict]:
        ...

    @abstractmethod
    async def get_all_transcripts(self, channel: str | None = None, profile_id: int | None = None, tag: str | None = None, watch_later: bool | None = None, limit: int | None = None) -> list[dict]:
        ...

    @abstractmethod
    async def get_channels(self) -> list[dict]:
        """Return distinct channels with transcript counts."""
        ...

    @abstractmethod
    async def update_transcript(self, transcript_id: int, **kwargs) -> None:
        ...

    # --- Baseline Analysis ---
    @abstractmethod
    async def save_baseline_analysis(self, transcript_id: int, outline_json: str, summary: str) -> int:
        ...

    @abstractmethod
    async def get_baseline_analysis(self, transcript_id: int) -> Optional[dict]:
        ...

    # --- Analysis Results ---
    @abstractmethod
    async def save_analysis_result(self, transcript_id: int, analysis_type: str, result_json: str) -> int:
        ...

    @abstractmethod
    async def get_analysis_result(self, transcript_id: int, analysis_type: str) -> Optional[dict]:
        ...

    @abstractmethod
    async def get_analysis_results_for_transcript(self, transcript_id: int) -> list[dict]:
        ...

    # --- Channel Profiles ---
    @abstractmethod
    async def set_channel_profile(self, channel_name: str, profile_id: int) -> int:
        ...

    @abstractmethod
    async def get_channel_profile(self, channel_name: str) -> Optional[dict]:
        ...

    # --- Profile Grades ---
    @abstractmethod
    async def save_profile_grade(self, channel_profile_id: int, auto_selected_profile_id: int, user_grade: int) -> int:
        ...

    # --- Tags ---
    @abstractmethod
    async def get_tags_for_transcript(self, transcript_id: int) -> list[dict]:
        ...

    @abstractmethod
    async def add_tag_to_transcript(self, transcript_id: int, tag_name: str, source: str = "user") -> dict:
        ...

    @abstractmethod
    async def remove_tag_from_transcript(self, transcript_id: int, tag_id: int) -> None:
        ...

    @abstractmethod
    async def reject_auto_tag(self, transcript_id: int, tag_id: int) -> None:
        ...

    @abstractmethod
    async def confirm_auto_tag(self, transcript_id: int, tag_id: int) -> None:
        ...

    @abstractmethod
    async def get_confirmed_tags_for_channel(self, channel: str) -> list[str]:
        ...

    @abstractmethod
    async def get_all_tags(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_rejected_tags_for_channel(self, channel: str) -> list[str]:
        ...

    # --- URL Lookup ---
    @abstractmethod
    async def get_transcripts_by_urls(self, urls: list[str]) -> list[dict]:
        """Return existing transcripts matching the given URLs."""
        ...

    # --- Cross-Analysis ---
    @abstractmethod
    async def save_cross_analysis(self, analysis_type: str, transcript_ids: list[int], result_json: str) -> int:
        ...

    @abstractmethod
    async def get_cross_analysis(self, cross_analysis_id: int) -> Optional[dict]:
        ...

    @abstractmethod
    async def update_cross_analysis_result(self, cross_analysis_id: int, result_json: str) -> None:
        ...

    @abstractmethod
    async def get_all_cross_analyses(self, limit: int | None = None) -> list[dict]:
        ...
