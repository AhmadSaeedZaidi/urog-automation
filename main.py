"""
FastAPI application for the UROG Data Ingestion & AI Communication Platform.

Endpoints:
    GET  /health                       — Health check
    POST /api/webhook/ingest           — Receive JSON payloads into the data_inbox
    POST /api/admin/trigger-worker     — Process inbox → normalized tables
    POST /api/admin/generate-drafts    — Generate drafts for human review
    POST /api/admin/dispatch           — Send approved drafts & log results
    POST /api/admin/upload-file        — Upload a .csv / .xlsx file
    POST /api/admin/ingest-gsheets     — Ingest rows from a Google Spreadsheet
    POST /api/admin/create-opportunity — Create opportunity + linked Google Sheet

Run with:
    uvicorn main:app --reload
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dao import db
from forms import WorkspaceMaker
from ingest.loader import GoogleSheetsLoader, LoaderFactory
from ingest.worker import process_inbox
from generator.engine import ContentEngine
from src.dispatch import send_via_resend, send_via_meta
from src.discord_logger import send_audit_message

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UROG Automation Platform",
    version="1.0.0",
    description="Data Ingestion, AI Drafting, and Communication Dispatch",
)

# Allow the local frontend to reach the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files (index.html, apiClient.js)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class IngestPayload(BaseModel):
    source_name: str = Field(
        ..., description="Human-readable label for the data source"
    )
    source_type: str = Field(
        "webhook", description="e.g. google_form, csv, webhook, manual_entry"
    )
    data: Dict[str, Any] | List[Dict[str, Any]] = Field(
        ..., description="The raw payload to store in the inbox"
    )


class TriggerWorkerResponse(BaseModel):
    status: str
    message: str


class DraftRequest(BaseModel):
    template_name: str = Field(..., description="Name of the template to use")
    role: Optional[str] = Field(None, description="Filter audience by role")
    limit: int = Field(50, ge=1, le=500, description="Max people to draft for")
    context_override: str = Field("", description="Extra context for the AI")


class DraftItem(BaseModel):
    recipient_id: str
    recipient_email: str
    recipient_phone: Optional[str] = None
    template_id: str
    template_name: str
    platform: str
    content: str
    status: str = "draft"


class DispatchRequest(BaseModel):
    drafts: List[DraftItem]


class DispatchResult(BaseModel):
    recipient_email: str
    platform: str
    status: str
    error: Optional[str] = None


class OpportunityRequest(BaseModel):
    title: str = Field(..., description="Opportunity title")
    professor_email: str = Field(
        ..., description="Email of the professor (must exist in the people table)"
    )
    description: Optional[str] = Field(None, description="Opportunity description")
    type: str = Field("research", description="e.g. research, internship, event")
    sheet_headers: List[str] = Field(
        default_factory=lambda: ["Name", "Email", "Status"],
        description="Column headers for the linked Google Sheet",
    )


class OpportunityResponse(BaseModel):
    opportunity_id: str
    title: str
    spreadsheet_id: str
    spreadsheet_url: str


class IngestGSheetsRequest(BaseModel):
    spreadsheet_id: str = Field(..., description="Google Spreadsheet ID to ingest")
    source_name: Optional[str] = Field(
        None, description="Human-readable label (defaults to gsheet-<id>)"
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check():
    """Simple status check."""
    return {"status": "ok", "service": "urog-automation"}


# ---------------------------------------------------------------------------
# POST /api/webhook/ingest
# ---------------------------------------------------------------------------


@app.post("/api/webhook/ingest", status_code=201)
def webhook_ingest(payload: IngestPayload):
    """
    Receive a JSON payload (e.g. from n8n or a web form) and push it
    directly into the DAO ``data_inbox``.
    """
    try:
        inbox_id = db.ingest_raw(
            source_name=payload.source_name,
            source_type=payload.source_type,
            payload=payload.data,
        )
        return {"status": "accepted", "inbox_id": str(inbox_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /api/admin/trigger-worker
# ---------------------------------------------------------------------------


@app.post("/api/admin/trigger-worker", response_model=TriggerWorkerResponse)
def trigger_worker(background_tasks: BackgroundTasks):
    """
    Kick off the ingestion worker that moves data from the inbox
    to the normalized Silver-layer tables.

    The work runs as a FastAPI background task so the response returns
    immediately.
    """
    background_tasks.add_task(_run_worker)
    return TriggerWorkerResponse(
        status="accepted",
        message="Worker triggered — processing inbox in the background.",
    )


def _run_worker():
    """Wrapper so process_inbox exceptions are caught cleanly."""
    try:
        process_inbox()
    except Exception as exc:
        print(f"[Worker] Error: {exc}")


# ---------------------------------------------------------------------------
# POST /api/admin/generate-drafts
# ---------------------------------------------------------------------------


@app.post("/api/admin/generate-drafts", response_model=List[DraftItem])
def generate_drafts_endpoint(req: DraftRequest):
    """
    Fetch a segment of users, run the generator against the named template,
    and return drafts for human review.
    """
    engine = ContentEngine()

    people = db.get_people(role=req.role, limit=req.limit)
    if not people:
        return []

    drafts: List[DraftItem] = []

    for person in people:
        user_data = {
            "email": person["email"],
            "full_name": person.get("full_name"),
            "phone": person.get("phone"),
            "profile_data": person.get("profile_data", {}),
        }

        result = engine.generate_message(
            req.template_name, user_data, context_override=req.context_override
        )

        if result.get("status") == "success":
            template_record = db.get_template(req.template_name)
            drafts.append(
                DraftItem(
                    recipient_id=str(person["id"]),
                    recipient_email=person["email"],
                    recipient_phone=person.get("phone"),
                    template_id=str(result["template_id"]),
                    template_name=req.template_name,
                    platform=template_record.get("platform", "email")
                    if template_record
                    else "email",
                    content=result["content"],
                    status="draft",
                )
            )
        else:
            # Add this so you can actually see the Gemini error!
            print(f"FAILED for {person['email']}: {result.get('error')}")

    return drafts


# ---------------------------------------------------------------------------
# POST /api/admin/dispatch
# ---------------------------------------------------------------------------


@app.post("/api/admin/dispatch", response_model=List[DispatchResult])
def dispatch_endpoint(req: DispatchRequest):
    """
    Accept a list of approved drafts and send them via the appropriate
    channel, logging every result to ``sent_logs``.
    """
    results: List[DispatchResult] = []

    for draft in req.drafts:
        success = False
        error_msg: Optional[str] = None

        try:
            if draft.platform == "email":
                success = send_via_resend(draft.recipient_email, draft.content)
            elif draft.platform == "whatsapp":
                if not draft.recipient_phone:
                    raise ValueError("No phone number for WhatsApp dispatch.")
                success = send_via_meta(draft.recipient_phone, draft.content)
            else:
                raise ValueError(f"Unsupported platform: {draft.platform}")
        except Exception as exc:
            error_msg = str(exc)

        status = "sent" if success else "failed"

        # Log to DB
        try:
            db.log_sent_message(
                recipient_id=draft.recipient_id,
                template_id=draft.template_id,
                platform=draft.platform,
                compiled_msg=draft.content,
                status=status,
                error=error_msg,
            )
        except Exception as log_exc:
            print(f"[Dispatch] Failed to log message: {log_exc}")

        results.append(
            DispatchResult(
                recipient_email=draft.recipient_email,
                platform=draft.platform,
                status=status,
                error=error_msg,
            )
        )

    sent = sum(1 for r in results if r.status == "sent")
    failed = sum(1 for r in results if r.status == "failed")
    send_audit_message(
        "Dispatch Complete",
        f"Sent: {sent} | Failed: {failed} | Total: {len(results)}",
    )

    return results


# ---------------------------------------------------------------------------
# POST /api/admin/upload-file
# ---------------------------------------------------------------------------

# Map MIME / extension to LoaderFactory keys
_EXTENSION_MAP: Dict[str, str] = {
    ".csv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
}


@app.post("/api/admin/upload-file", status_code=201)
async def upload_file(file: UploadFile, source_name: Optional[str] = None):
    """
    Accept a physical ``.csv`` or ``.xlsx`` file upload, route it through
    the ``LoaderFactory``, and push the data into the DAO inbox.

    The temp file is cleaned up after processing.
    """
    # Determine file type from the filename extension
    filename = file.filename or ""
    _, ext = os.path.splitext(filename.lower())

    loader_type = _EXTENSION_MAP.get(ext)
    if not loader_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Accepted: .csv, .xlsx, .xls",
        )

    # Save to a temp file so the loader can read it from disk
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        contents = await file.read()
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(contents)

        loader = LoaderFactory.get_loader(loader_type)
        inbox_id = loader.load(tmp_path, source_name=source_name or filename)

        return {
            "status": "accepted",
            "inbox_id": str(inbox_id),
            "filename": filename,
            "loader_type": loader_type,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# POST /api/admin/ingest-gsheets
# ---------------------------------------------------------------------------


@app.post("/api/admin/ingest-gsheets", status_code=201)
def ingest_gsheets_endpoint(req: IngestGSheetsRequest):
    """
    Ingest data from a Google Spreadsheet (via the service-account bot)
    and push the rows into the DAO inbox.
    """
    try:
        loader = GoogleSheetsLoader()
        inbox_id = loader.load(
            req.spreadsheet_id,
            source_name=req.source_name,
        )
        if inbox_id is None:
            raise HTTPException(
                status_code=400,
                detail="Spreadsheet is empty or has no data rows.",
            )
        return {
            "status": "accepted",
            "inbox_id": str(inbox_id),
            "spreadsheet_id": req.spreadsheet_id,
        }
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /api/admin/create-opportunity
# ---------------------------------------------------------------------------


@app.post(
    "/api/admin/create-opportunity",
    response_model=OpportunityResponse,
    status_code=201,
)
def create_opportunity_endpoint(req: OpportunityRequest):
    """
    Create a new opportunity **and** a linked Google Sheet in one call.

    1. Look up the professor in the ``people`` table by email.
    2. ``WorkspaceMaker.create_opportunity_sheet()`` → creates the sheet
       and shares it with the professor.
    3. ``db.create_opportunity()`` → stores the sheet metadata in ``form_config``.
    4. Returns the opportunity ID + Google Sheet URL.
    """
    # 1. Resolve professor → owner_id
    professor = db.get_person_by_email(req.professor_email)
    if not professor:
        raise HTTPException(
            status_code=404,
            detail=f"Professor not found: {req.professor_email}",
        )
    owner_id = str(professor["id"])

    # 2. Create & share the Google Sheet
    maker = WorkspaceMaker()
    try:
        sheet_info = maker.create_opportunity_sheet(
            title=f"UROG — {req.title}",
            professor_email=req.professor_email,
            sheet_headers=req.sheet_headers,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create Google Sheet: {exc}",
        )

    form_config = {
        "spreadsheet_id": sheet_info["spreadsheet_id"],
        "spreadsheet_url": sheet_info["url"],
    }

    # 3. Persist the opportunity
    try:
        opp_id = db.create_opportunity(
            title=req.title,
            owner_id=owner_id,
            description=req.description,
            type=req.type,
            form_config=form_config,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    send_audit_message(
        "Opportunity Created",
        f"**{req.title}** for {req.professor_email}\nSheet: {sheet_info['url']}",
    )

    return OpportunityResponse(
        opportunity_id=str(opp_id),
        title=req.title,
        spreadsheet_id=sheet_info["spreadsheet_id"],
        spreadsheet_url=sheet_info["url"],
    )
