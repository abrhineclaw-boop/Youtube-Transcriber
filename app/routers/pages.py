"""Page routes serving HTML templates."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("pages/home.html", {"request": request})


@router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request):
    return templates.TemplateResponse("pages/library.html", {"request": request})


@router.get("/transcript/{transcript_id}", response_class=HTMLResponse)
async def transcript_detail_page(request: Request, transcript_id: int):
    return templates.TemplateResponse(
        "pages/transcript.html",
        {"request": request, "transcript_id": transcript_id},
    )


@router.get("/transcript/{transcript_id}/analysis/{analysis_type}", response_class=HTMLResponse)
async def analysis_view_page(request: Request, transcript_id: int, analysis_type: str):
    return templates.TemplateResponse(
        "pages/analysis.html",
        {
            "request": request,
            "transcript_id": transcript_id,
            "analysis_type": analysis_type,
        },
    )


@router.get("/cross-analyses", response_class=HTMLResponse)
async def cross_analyses_library_page(request: Request):
    return templates.TemplateResponse("pages/cross_analyses.html", {"request": request})


@router.get("/cross-analysis/{cross_analysis_id}", response_class=HTMLResponse)
async def cross_analysis_page(request: Request, cross_analysis_id: int):
    return templates.TemplateResponse(
        "pages/cross_analysis.html",
        {"request": request, "cross_analysis_id": cross_analysis_id},
    )
