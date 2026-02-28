"""
FastAPI application for the UROG Data Ingestion & AI Communication Platform.

Endpoints:
    GET  /health                     — Health check
    POST /api/webhook/ingest         — Receive JSON payloads into the data_inbox
    POST /api/admin/trigger-worker   — Process inbox → normalized tables
    POST /api/admin/generate-drafts  — Generate drafts for human review
    POST /api/admin/dispatch         — Send approved drafts & log results

Run with:
    uvicorn main:app --reload
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from dao import db
from ingest.worker import process_inbox
from generator.engine import ContentEngine
from src.dispatch import send_via_resend, send_via_meta

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UROG Automation Platform",
    version="1.0.0",
    description="Data Ingestion, AI Drafting, and Communication Dispatch",
)

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

    return results
