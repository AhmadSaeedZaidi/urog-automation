"""
Orchestrator — ties the DAO, Ingest, and Generator libraries into a
cohesive end-to-end pipeline.

Public API:
    run_pipeline(csv_path, source_name)   — ingest CSV + process inbox
    generate_drafts(template_name, role)  — fetch audience, generate drafts
    dispatch_drafts(drafts, db_instance)  — send approved drafts & log results
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dao import db as default_db
from ingest import ingest_csv, process_inbox
from generator.engine import ContentEngine

from src.dispatch import send_via_resend, send_via_meta


# ---------------------------------------------------------------------------
# 1. Pipeline Run
# ---------------------------------------------------------------------------


def run_pipeline(
    csv_path: str,
    source_name: Optional[str] = None,
    db: Any = None,
) -> dict:
    """
    Full ingestion pipeline:
      1. Load a CSV into the data_inbox (Bronze layer).
      2. Process the inbox → upsert into the people table (Silver layer).

    Returns a summary dict.
    """
    db = db or default_db

    # Step 1 — Ingest
    inbox_id = ingest_csv(csv_path, source_name)

    # Step 2 — Process inbox
    process_inbox()

    return {"inbox_id": inbox_id, "status": "pipeline_complete"}


# ---------------------------------------------------------------------------
# 2. Drafting Phase  (Human-in-the-loop)
# ---------------------------------------------------------------------------


def generate_drafts(
    template_name: str,
    role: Optional[str] = None,
    limit: int = 50,
    context_override: str = "",
    db: Any = None,
) -> List[Dict[str, Any]]:
    """
    1. Fetch a segment of users (optionally filtered by role).
    2. Fetch the named template.
    3. Run the ContentEngine for each user.
    4. Return a list of draft dicts for human review.

    Each draft:
        {
            "recipient_id": <uuid>,
            "recipient_email": <str>,
            "recipient_phone": <str | None>,
            "template_id": <uuid>,
            "template_name": <str>,
            "platform": <str>,
            "content": <str>,
            "status": "draft",
        }
    """
    db = db or default_db
    engine = ContentEngine()

    people = db.get_people(role=role, limit=limit)
    if not people:
        print("[Orchestrator] No people found for the given filter.")
        return []

    drafts: List[Dict[str, Any]] = []

    for person in people:
        user_data = {
            "email": person["email"],
            "full_name": person.get("full_name"),
            "phone": person.get("phone"),
            "profile_data": person.get("profile_data", {}),
        }

        result = engine.generate_message(
            template_name, user_data, context_override=context_override
        )

        if result.get("status") == "success":
            drafts.append(
                {
                    "recipient_id": person["id"],
                    "recipient_email": person["email"],
                    "recipient_phone": person.get("phone"),
                    "template_id": result["template_id"],
                    "template_name": template_name,
                    "platform": db.get_template(template_name).get("platform", "email"),
                    "content": result["content"],
                    "status": "draft",
                }
            )
        else:
            print(
                f"[Orchestrator] Skipping {person['email']}: "
                f"{result.get('error', 'unknown error')}"
            )

    print(f"[Orchestrator] Generated {len(drafts)} draft(s) for review.")
    return drafts


# ---------------------------------------------------------------------------
# 3. Dispatch Loop  (Post approval)
# ---------------------------------------------------------------------------


def dispatch_drafts(
    drafts: List[Dict[str, Any]],
    db: Any = None,
) -> List[Dict[str, Any]]:
    """
    Iterate through *approved* drafts, dispatch via the appropriate channel,
    and log the outcome in ``sent_logs``.

    Returns the list of drafts annotated with 'sent' or 'failed' status.
    """
    db = db or default_db
    results: List[Dict[str, Any]] = []

    for draft in drafts:
        platform = draft.get("platform", "email")
        success = False
        error_msg: Optional[str] = None

        try:
            if platform == "email":
                success = send_via_resend(draft["recipient_email"], draft["content"])
            elif platform == "whatsapp":
                phone = draft.get("recipient_phone")
                if not phone:
                    raise ValueError("No phone number for WhatsApp dispatch.")
                success = send_via_meta(phone, draft["content"])
            else:
                raise ValueError(f"Unsupported platform: {platform}")
        except Exception as exc:
            error_msg = str(exc)

        status = "sent" if success else "failed"

        # Log to DB
        db.log_sent_message(
            recipient_id=draft["recipient_id"],
            template_id=draft["template_id"],
            platform=platform,
            compiled_msg=draft["content"],
            status=status,
            error=error_msg,
        )

        draft["status"] = status
        results.append(draft)

    sent = sum(1 for r in results if r["status"] == "sent")
    failed = len(results) - sent
    print(f"[Dispatch] Complete — {sent} sent, {failed} failed.")
    return results
