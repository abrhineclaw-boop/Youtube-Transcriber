from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# --- Profiles ---
class ProfileCreate(BaseModel):
    name: str
    description: str
    analysis_hints: str = ""


class Profile(ProfileCreate):
    id: int
    created_at: datetime


# --- Transcripts ---
class TranscriptCreate(BaseModel):
    video_url: str
    profile_id: int


class Transcript(BaseModel):
    id: int
    video_url: str
    title: str
    channel: str
    duration_seconds: int
    transcript_json: str  # JSON with timestamps
    profile_id: int
    status: str  # pending, downloading, transcribing, analyzing, ready, error
    error_message: Optional[str] = None
    created_at: datetime


class TranscriptListItem(BaseModel):
    id: int
    video_url: str
    title: str
    channel: str
    duration_seconds: int
    profile_id: int
    profile_name: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    has_baseline: bool
    completed_analyses: list[str]


# --- Baseline Analysis ---
class BaselineAnalysis(BaseModel):
    id: int
    transcript_id: int
    outline_json: str  # JSON: list of {title, start_time, end_time}
    summary: str
    created_at: datetime


# --- Analysis Results ---
class AnalysisResult(BaseModel):
    id: int
    transcript_id: int
    analysis_type: str
    result_json: str
    created_at: datetime


# --- Channel Profiles ---
class ChannelProfile(BaseModel):
    id: int
    channel_name: str
    profile_id: int
    created_at: datetime


# --- Profile Grades ---
class ProfileGrade(BaseModel):
    id: int
    channel_profile_id: int
    auto_selected_profile_id: int
    user_grade: int  # 1-5
    created_at: datetime


# --- API Request/Response ---
class SubmitURLRequest(BaseModel):
    video_url: str
    profile_id: int


class SubmitURLResponse(BaseModel):
    transcript_id: int
    status: str
    message: str


class SubmitBatchRequest(BaseModel):
    video_urls: list[str]
    profile_id: int


class SubmitBatchResponse(BaseModel):
    transcript_ids: list[int]
    message: str


class RunAnalysisRequest(BaseModel):
    analysis_type: str


class RunPackageRequest(BaseModel):
    package: str


class SectionDeepDiveRequest(BaseModel):
    section_index: int


class CrossAnalysisRequest(BaseModel):
    transcript_ids: list[int]
    instructions: str


class PlaylistImportRequest(BaseModel):
    playlist_url: str
    profile_id: int
    max_videos: int = 50


class PlaylistImportResponse(BaseModel):
    playlist_title: str
    total_in_playlist: int
    queued_count: int
    skipped_duplicates: int
    transcript_ids: list[int]
    message: str


class PlaylistPreviewRequest(BaseModel):
    playlist_url: str
    max_videos: int = 50


class PlaylistPreviewResponse(BaseModel):
    playlist_title: str
    total_in_playlist: int
    video_count: int
    urls: list[str]
    duplicates: dict


class JobStatus(BaseModel):
    transcript_id: int
    status: str
    error_message: Optional[str] = None
