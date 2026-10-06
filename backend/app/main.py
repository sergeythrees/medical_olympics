from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import repository, schemas
from app.config import settings
from app.db import get_session
from app.extraction import ExtractionFailed, LLMNotConfigured, extract_case, make_llm

app = FastAPI(title="Clinical Cases API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

DB = Annotated[Session, Depends(get_session)]


@app.exception_handler(repository.NotFound)
def _not_found(_: Request, e: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(e)}, status_code=status.HTTP_404_NOT_FOUND)


@app.exception_handler(repository.Conflict)
def _conflict(_: Request, e: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(e)}, status_code=status.HTTP_409_CONFLICT)


@app.exception_handler(repository.InvalidAnswer)
def _invalid_answer(_: Request, e: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(e)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


@app.get("/health", tags=["ops"])
def health(session: DB) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/cases", status_code=status.HTTP_201_CREATED, tags=["cases"])
def create_case(body: schemas.CaseIn, session: DB) -> schemas.CasePublic:
    case = repository.create_case(session, body)
    return repository.get_case(session, case.id)


@app.get("/cases", tags=["cases"])
def list_cases(session: DB) -> list[schemas.CaseSummary]:
    return repository.list_cases(session)


@app.get("/cases/{case_id}", tags=["cases"])
def get_case(case_id: int, session: DB) -> schemas.CasePublic:
    """The case as a participant sees it: no points, no explanations."""
    return repository.get_case(session, case_id)


@app.post("/cases/{case_id}/submissions", status_code=status.HTTP_201_CREATED, tags=["scoring"])
def submit_answers(case_id: int, body: schemas.SubmissionIn, session: DB) -> schemas.SubmissionResult:
    return repository.submit(session, case_id, body)


@app.get("/submissions/{submission_id}", tags=["scoring"])
def get_submission(submission_id: int, session: DB) -> schemas.SubmissionResult:
    return repository.get_result(session, submission_id)


@app.get("/cases/{case_id}/leaderboard", tags=["scoring"])
def leaderboard(case_id: int, session: DB) -> list[schemas.LeaderboardEntry]:
    return repository.leaderboard(session, case_id)


@app.post("/extract", tags=["llm"])
async def extract(body: schemas.ExtractIn) -> schemas.CaseIn:
    """Structure a raw clinical text with an LLM. Returns a draft for the author to review
    and then POST to /cases; nothing is saved here."""
    try:
        llm = make_llm(settings)
        result = await run_in_threadpool(extract_case, body.text, llm)
    except LLMNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except ExtractionFailed as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM provider error: {e}") from e
    return result.case
