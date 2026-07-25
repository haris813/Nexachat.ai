from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
from datetime import UTC, datetime
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    send_file,
    session,
    stream_with_context,
)
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import (
    Artifact,
    Contact,
    Conversation,
    ConversationState,
    Message,
    ResearchSource,
    TaskPlan,
    ToolRun,
    UploadedFile,
    UsageEvent,
    User,
    UserPreference,
    WhatsAppMessage,
)
from ..services.ai import AIService
from ..services.artifacts import ArtifactService
from ..services.files import FileValidationError, UploadService, extract_file
from ..services.orchestrator import Orchestrator, Planner
from ..services.security import SecretBox, SecurityError, normalize_phone, safe_display_name
from ..services.tools import TOOL_DEFINITIONS
from ..services.whatsapp import WhatsAppService, apply_status_webhook, verify_meta_signature

workspace_bp = Blueprint("workspace", __name__)
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@workspace_bp.before_request
def verify_workspace_request():
    if request.endpoint in {"workspace.whatsapp_webhook"}:
        return None
    if current_app.config.get("AUTH_REQUIRED"):
        user = db.session.get(User, session.get("user_id"))
        if (not user or user.is_guest) and not (request.endpoint or "").startswith("workspace.auth_"):
            return jsonify({"error": "Authentication is required"}), 401
    if request.method in UNSAFE_METHODS:
        expected = str(session.get("csrf_token") or "")
        provided = str(request.headers.get("X-CSRF-Token") or "")
        if not expected or not provided or not hmac.compare_digest(expected, provided):
            return jsonify({"error": "Invalid or missing CSRF token"}), 403
    return None


def _owner_id() -> str:
    return str(session["user_id"])


def _owned(model, identifier):
    return model.query.filter_by(id=identifier, owner_id=_owner_id()).first_or_404()


def _json_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@workspace_bp.get("/tools")
def list_tools():
    return jsonify([item.to_dict() for item in TOOL_DEFINITIONS])


@workspace_bp.post("/plans")
@limiter.limit("30 per minute")
def create_plan():
    payload = request.get_json(silent=True) or {}
    goal = " ".join(str(payload.get("goal") or "").split()).strip()
    if not goal:
        return jsonify({"error": "Task goal cannot be empty"}), 400
    if len(goal) > current_app.config["MAX_INPUT_CHARS"]:
        return jsonify({"error": "Task goal is too long"}), 413
    try:
        conversation_id = int(payload.get("conversation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "A conversation is required"}), 400
    conversation = Conversation.query.filter_by(id=conversation_id, owner_id=_owner_id()).first_or_404()
    attachment_ids = [str(item) for item in payload.get("attachment_ids") or []][:10]
    plan = Planner.create(
        owner_id=_owner_id(),
        conversation_id=conversation.id,
        goal=goal,
        attachment_ids=attachment_ids,
    )
    if plan is None:
        return jsonify({"mode": "chat"}), 200
    if conversation.title == "New conversation":
        conversation.title = goal[:54] + ("…" if len(goal) > 54 else "")
    conversation.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"mode": "plan", "plan": plan.to_dict()}), 201


@workspace_bp.get("/plans")
def list_plans():
    plans = (
        TaskPlan.query.filter_by(owner_id=_owner_id()).order_by(desc(TaskPlan.created_at)).limit(100).all()
    )
    return jsonify([plan.to_dict() for plan in plans])


@workspace_bp.get("/plans/<plan_id>")
def get_plan(plan_id: str):
    plan = _owned(TaskPlan, plan_id)
    runs = ToolRun.query.filter_by(plan_id=plan.id, owner_id=_owner_id()).order_by(ToolRun.started_at).all()
    sources = ResearchSource.query.filter_by(plan_id=plan.id, owner_id=_owner_id()).all()
    return jsonify(
        {
            **plan.to_dict(),
            "tool_runs": [item.to_dict() for item in runs],
            "sources": [item.to_dict() for item in sources],
        }
    )


@workspace_bp.post("/plans/<plan_id>/execute")
@limiter.limit("20 per minute")
def execute_plan(plan_id: str):
    plan = _owned(TaskPlan, plan_id)

    @stream_with_context
    def generate():
        for event in Orchestrator(_owner_id()).execute(plan):
            yield _json_event(event["event"], event["data"])

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"},
    )


@workspace_bp.post("/plans/<plan_id>/cancel")
def cancel_plan(plan_id: str):
    plan = _owned(TaskPlan, plan_id)
    if plan.status != "awaiting_approval":
        return jsonify({"error": "Only plans awaiting approval can be cancelled"}), 409
    plan.status = "cancelled"
    plan.completed_at = datetime.now(UTC)
    db.session.commit()
    return jsonify(plan.to_dict())


@workspace_bp.post("/uploads")
@limiter.limit("20 per hour")
def upload_file():
    incoming = request.files.get("file")
    if incoming is None:
        return jsonify({"error": "Choose a file to upload"}), 400
    try:
        upload = UploadService.save(_owner_id(), incoming)
        db.session.add(UsageEvent(owner_id=_owner_id(), event_type="upload", status="success"))
        db.session.commit()
        return jsonify(upload.to_dict()), 201
    except FileValidationError as error:
        return jsonify({"error": str(error)}), 400


@workspace_bp.get("/uploads")
def list_uploads():
    records = (
        UploadedFile.query.filter_by(owner_id=_owner_id())
        .order_by(desc(UploadedFile.created_at))
        .limit(100)
        .all()
    )
    return jsonify([item.to_dict() for item in records])


@workspace_bp.delete("/uploads/<upload_id>")
def delete_upload(upload_id: str):
    from ..services.storage import get_upload_storage

    upload = _owned(UploadedFile, upload_id)
    if WhatsAppMessage.query.filter_by(media_upload_id=upload.id).first():
        return jsonify({"error": "This upload is referenced by a WhatsApp audit record"}), 409
    storage = get_upload_storage()
    storage.delete(upload.storage_path)
    db.session.delete(upload)
    db.session.commit()
    return "", 204


@workspace_bp.post("/uploads/<upload_id>/transcribe")
@limiter.limit("10 per hour")
def transcribe_upload(upload_id: str):
    upload = _owned(UploadedFile, upload_id)
    if not upload.mime_type.startswith("audio/"):
        return jsonify({"error": "Only audio uploads can be transcribed"}), 400
    transcript = AIService().transcribe(Path(upload.storage_path))
    upload.extracted_text = transcript
    metadata = json.loads(upload.metadata_json or "{}")
    metadata["transcribed_at"] = datetime.now(UTC).isoformat()
    upload.metadata_json = json.dumps(metadata)
    db.session.commit()
    return jsonify({"upload": upload.to_dict(), "transcript": transcript, "requires_review": True})


@workspace_bp.post("/speech")
@limiter.limit("20 per hour")
def synthesize_speech():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    if not text or len(text) > 4096:
        return jsonify({"error": "Speech text must contain 1–4,096 characters"}), 400
    service = ArtifactService(_owner_id())
    ai = AIService()
    artifact = service.create_audio(
        "spoken-response",
        text,
        lambda path: ai.synthesize_speech(text, path),
    )
    return jsonify(artifact.to_dict()), 201


@workspace_bp.get("/artifacts")
def list_artifacts():
    kind = str(request.args.get("kind") or "").strip()
    query = Artifact.query.filter_by(owner_id=_owner_id(), deleted_at=None)
    if kind:
        query = query.filter_by(kind=kind)
    records = query.order_by(desc(Artifact.created_at)).limit(200).all()
    return jsonify([item.to_dict() for item in records])


@workspace_bp.get("/artifacts/<artifact_id>/download")
def download_artifact(artifact_id: str):
    from ..services.storage import get_artifact_storage

    artifact = _owned(Artifact, artifact_id)
    if artifact.deleted_at:
        return jsonify({"error": "Artifact has been deleted"}), 404
    storage = get_artifact_storage()
    presigned = storage.presigned_url(artifact.storage_path)
    if presigned:
        from flask import redirect

        return redirect(presigned)
    path = Path(artifact.storage_path).resolve()
    root = Path(current_app.config["ARTIFACT_DIR"]).resolve()
    if root not in path.parents or not path.is_file():
        return jsonify({"error": "Artifact file is unavailable"}), 404
    return send_file(
        path,
        mimetype=artifact.mime_type,
        as_attachment=True,
        download_name=artifact.display_name,
        conditional=True,
        etag=True,
    )


@workspace_bp.patch("/artifacts/<artifact_id>")
def rename_artifact(artifact_id: str):
    artifact = _owned(Artifact, artifact_id)
    payload = request.get_json(silent=True) or {}
    requested = safe_display_name(str(payload.get("name") or ""))
    if not requested:
        return jsonify({"error": "Artifact name cannot be empty"}), 400
    suffix = Path(artifact.display_name).suffix
    artifact.display_name = requested if requested.lower().endswith(suffix.lower()) else requested + suffix
    db.session.commit()
    return jsonify(artifact.to_dict())


@workspace_bp.delete("/artifacts/<artifact_id>")
def delete_artifact(artifact_id: str):
    from ..services.storage import get_artifact_storage

    artifact = _owned(Artifact, artifact_id)
    if artifact.deleted_at:
        return "", 204
    storage = get_artifact_storage()
    storage.delete(artifact.storage_path)
    artifact.deleted_at = datetime.now(UTC)
    artifact.status = "deleted"
    db.session.commit()
    return "", 204


@workspace_bp.post("/artifacts/<artifact_id>/convert")
@limiter.limit("20 per hour")
def convert_artifact(artifact_id: str):
    artifact = _owned(Artifact, artifact_id)
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("format") or "").lower()
    if target not in {"pdf", "word", "powerpoint", "excel"}:
        return jsonify({"error": "Supported conversion targets: pdf, word, powerpoint, excel"}), 400
    extension = Path(artifact.storage_path).suffix.lower()
    text, metadata = extract_file(Path(artifact.storage_path), extension)
    title = Path(artifact.display_name).stem
    service = ArtifactService(_owner_id(), artifact.conversation_id)
    sources = []
    if artifact.plan_id:
        sources = [
            item.to_dict()
            for item in ResearchSource.query.filter_by(plan_id=artifact.plan_id, owner_id=_owner_id()).all()
        ]
    sections = [
        {"heading": "Converted content", "body": text[:60000] or json.dumps(metadata, ensure_ascii=False)}
    ]
    if target == "pdf":
        created = service.create_pdf(title, sections, sources=sources)
    elif target == "word":
        created = service.create_word(title, sections, sources=sources)
    elif target == "powerpoint":
        paragraphs = [item for item in text.splitlines() if item.strip()]
        slides = [
            {"title": f"Section {index + 1}", "bullets": paragraphs[index : index + 4], "takeaway": ""}
            for index in range(0, min(len(paragraphs), 28), 4)
        ] or [{"title": "Converted content", "bullets": ["No readable text was found."], "takeaway": ""}]
        created = service.create_powerpoint(title, slides[:7], sources=sources)
    else:
        rows = [
            {"Line": index + 1, "Content": value}
            for index, value in enumerate(text.splitlines())
            if value.strip()
        ]
        created = service.create_excel(
            title, rows or [{"Content": "No readable text was found."}], sources=sources
        )
    return jsonify(created.to_dict()), 201


@workspace_bp.post("/conversations/<int:conversation_id>/artifact-export")
def export_conversation_artifact(conversation_id: int):
    conversation = Conversation.query.filter_by(id=conversation_id, owner_id=_owner_id()).first_or_404()
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("format") or "markdown").lower()
    service = ArtifactService(_owner_id(), conversation.id)
    markdown = f"# {conversation.title}\n\n" + "\n\n---\n\n".join(
        f"## {'You' if item.role == 'user' else 'NexaChat'}\n\n{item.content}"
        for item in conversation.messages
    )
    if target == "markdown":
        artifact = service.create_conversation_export(conversation.title, markdown)
    else:
        sections = [
            {
                "heading": "Conversation",
                "body": [
                    f"{'You' if item.role == 'user' else 'NexaChat'}: {item.content}"
                    for item in conversation.messages
                ],
            }
        ]
        if target == "pdf":
            artifact = service.create_pdf(conversation.title, sections)
        elif target == "word":
            artifact = service.create_word(conversation.title, sections, template="meeting_summary")
        elif target == "powerpoint":
            slides = [
                {"title": "Conversation summary", "bullets": section["body"][:6], "takeaway": ""}
                for section in sections
            ]
            artifact = service.create_powerpoint(conversation.title, slides)
        else:
            return jsonify({"error": "Supported export formats: markdown, pdf, word, powerpoint"}), 400
    return jsonify(artifact.to_dict()), 201


def _contact_payload(contact: Contact, *, reveal: bool = False) -> dict:
    result = contact.to_dict()
    if reveal:
        box = SecretBox()
        result["phone"] = box.decrypt(contact.phone_ciphertext)
        result["email"] = box.decrypt(contact.email_ciphertext)
    return result


@workspace_bp.get("/contacts")
def list_contacts():
    search = str(request.args.get("q") or "").strip()
    query = Contact.query.filter_by(owner_id=_owner_id())
    if search:
        query = query.filter(Contact.name.ilike(f"%{search}%"))
    return jsonify([_contact_payload(item) for item in query.order_by(Contact.name).limit(200).all()])


@workspace_bp.post("/contacts")
def create_contact():
    payload = request.get_json(silent=True) or {}
    try:
        name = safe_display_name(str(payload.get("name") or ""), "")
        if not name:
            raise ValueError("Contact name is required")
        phone = normalize_phone(str(payload.get("phone") or ""))
        box = SecretBox()
        contact = Contact(
            owner_id=_owner_id(),
            name=name,
            phone_ciphertext=box.encrypt(phone),
            phone_hash=box.digest(phone),
            phone_last4=phone[-4:],
            email_ciphertext=box.encrypt(str(payload.get("email") or "").strip() or None),
            relationship=safe_display_name(str(payload.get("relationship") or ""), "") or None,
            notes=str(payload.get("notes") or "").strip()[:2000] or None,
            preferred_channel=str(payload.get("preferred_channel") or "whatsapp")[:30],
        )
        db.session.add(contact)
        db.session.commit()
        return jsonify(_contact_payload(contact)), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A contact with this phone number already exists"}), 409
    except (SecurityError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@workspace_bp.get("/contacts/<contact_id>")
def get_contact(contact_id: str):
    return jsonify(_contact_payload(_owned(Contact, contact_id), reveal=True))


@workspace_bp.patch("/contacts/<contact_id>")
def update_contact(contact_id: str):
    contact = _owned(Contact, contact_id)
    payload = request.get_json(silent=True) or {}
    box = SecretBox()
    try:
        if "name" in payload:
            contact.name = safe_display_name(str(payload["name"]), "")
            if not contact.name:
                raise ValueError("Contact name is required")
        if "phone" in payload:
            phone = normalize_phone(str(payload["phone"]))
            contact.phone_ciphertext = box.encrypt(phone)
            contact.phone_hash = box.digest(phone)
            contact.phone_last4 = phone[-4:]
        if "email" in payload:
            contact.email_ciphertext = box.encrypt(str(payload["email"]).strip() or None)
        if "relationship" in payload:
            contact.relationship = safe_display_name(str(payload["relationship"]), "") or None
        if "notes" in payload:
            contact.notes = str(payload["notes"]).strip()[:2000] or None
        if "preferred_channel" in payload:
            contact.preferred_channel = str(payload["preferred_channel"])[:30]
        db.session.commit()
        return jsonify(_contact_payload(contact))
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A contact with this phone number already exists"}), 409
    except (SecurityError, ValueError) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400


@workspace_bp.delete("/contacts/<contact_id>")
def delete_contact(contact_id: str):
    contact = _owned(Contact, contact_id)
    if WhatsAppMessage.query.filter_by(contact_id=contact.id).first():
        return jsonify({"error": "Contact has WhatsApp audit history and cannot be deleted"}), 409
    db.session.delete(contact)
    db.session.commit()
    return "", 204


@workspace_bp.post("/contacts/import")
def import_contacts():
    incoming = request.files.get("file")
    if not incoming:
        return jsonify({"error": "Choose a CSV contact file"}), 400
    try:
        text = incoming.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error):
        return jsonify({"error": "Contact import must be a valid UTF-8 CSV"}), 400
    created, skipped = 0, []
    box = SecretBox()
    for index, row in enumerate(rows[:1000], start=2):
        try:
            phone = normalize_phone(row.get("phone") or row.get("phone_number") or "")
            contact = Contact(
                owner_id=_owner_id(),
                name=safe_display_name(row.get("name") or "", ""),
                phone_ciphertext=box.encrypt(phone),
                phone_hash=box.digest(phone),
                phone_last4=phone[-4:],
                email_ciphertext=box.encrypt((row.get("email") or "").strip() or None),
                relationship=(row.get("relationship") or row.get("label") or "")[:80] or None,
                notes=(row.get("notes") or "")[:2000] or None,
                preferred_channel=(row.get("preferred_channel") or "whatsapp")[:30],
            )
            if not contact.name:
                raise ValueError("missing name")
            with db.session.begin_nested():
                db.session.add(contact)
                db.session.flush()
            created += 1
        except Exception as error:
            skipped.append({"row": index, "reason": str(error)[:120]})
    db.session.commit()
    return jsonify({"created": created, "skipped": skipped[:50]})


@workspace_bp.post("/whatsapp/prepare")
def prepare_whatsapp():
    payload = request.get_json(silent=True) or {}
    contact = _owned(Contact, str(payload.get("contact_id") or ""))
    service = WhatsAppService(_owner_id())
    message_type = str(payload.get("message_type") or "text")
    if message_type == "audio":
        upload = _owned(UploadedFile, str(payload.get("upload_id") or ""))
        record, token = service.prepare_audio(contact, upload)
        body = None
    else:
        body = str(payload.get("body") or "").strip()
        record, token = service.prepare_text(contact, body)
    return jsonify(
        {
            **record.to_dict(include_body=True, body=body),
            "contact_name": contact.name,
            "confirmation_token": token,
            "mode": current_app.config["WHATSAPP_MODE"],
        }
    ), 201


@workspace_bp.post("/whatsapp/<message_id>/confirm-send")
@limiter.limit("10 per minute")
def confirm_whatsapp(message_id: str):
    record = _owned(WhatsAppMessage, message_id)
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("confirmation_token") or "")
    try:
        updated = WhatsAppService(_owner_id()).confirm_and_send(record, token)
        return jsonify(updated.to_dict())
    except (SecurityError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@workspace_bp.get("/whatsapp/messages")
def list_whatsapp_messages():
    records = (
        WhatsAppMessage.query.filter_by(owner_id=_owner_id())
        .order_by(desc(WhatsAppMessage.created_at))
        .limit(100)
        .all()
    )
    return jsonify([item.to_dict() for item in records])


@workspace_bp.route("/whatsapp/webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        expected = current_app.config["META_WHATSAPP_WEBHOOK_VERIFY_TOKEN"]
        if mode == "subscribe" and expected and hmac.compare_digest(str(token or ""), expected):
            return str(challenge or ""), 200
        return "Verification failed", 403
    raw_body = request.get_data(cache=True)
    if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"error": "Invalid webhook signature"}), 401
    updated = apply_status_webhook(request.get_json(silent=True) or {})
    return jsonify({"received": True, "updated": updated})


@workspace_bp.get("/preferences")
def get_preferences():
    preferences = db.session.get(UserPreference, _owner_id())
    if not preferences:
        preferences = UserPreference(owner_id=_owner_id())
        db.session.add(preferences)
        db.session.commit()
    return jsonify(preferences.to_dict())


@workspace_bp.patch("/preferences")
def update_preferences():
    preferences = db.session.get(UserPreference, _owner_id()) or UserPreference(owner_id=_owner_id())
    payload = request.get_json(silent=True) or {}
    if "language" in payload:
        language = str(payload["language"])
        if language not in {"auto", "en", "hi", "hinglish"}:
            return jsonify({"error": "Unsupported language preference"}), 400
        preferences.language = language
    if "document_style" in payload:
        preferences.document_style = str(payload["document_style"])[:50]
    if "presentation_theme" in payload:
        preferences.presentation_theme = str(payload["presentation_theme"])[:50]
    if "auto_speak" in payload:
        preferences.auto_speak = bool(payload["auto_speak"])
    if "memory" in payload:
        memory = payload["memory"]
        if not isinstance(memory, dict) or len(json.dumps(memory)) > 8000:
            return jsonify({"error": "Memory must be a small JSON object"}), 400
        preferences.memory_json = json.dumps(memory, ensure_ascii=False)
    db.session.add(preferences)
    db.session.commit()
    return jsonify(preferences.to_dict())


@workspace_bp.delete("/preferences/memory")
def clear_memory():
    preferences = db.session.get(UserPreference, _owner_id())
    if preferences:
        preferences.memory_json = "{}"
        db.session.commit()
    return "", 204


@workspace_bp.post("/conversations/<int:conversation_id>/archive")
def archive_conversation(conversation_id: int):
    Conversation.query.filter_by(id=conversation_id, owner_id=_owner_id()).first_or_404()
    state = db.session.get(ConversationState, conversation_id)
    if not state:
        state = ConversationState(conversation_id=conversation_id, owner_id=_owner_id())
        db.session.add(state)
    state.is_archived = True
    db.session.commit()
    return jsonify({"conversation_id": conversation_id, "is_archived": True})


@workspace_bp.post("/conversations/<int:conversation_id>/unarchive")
def unarchive_conversation(conversation_id: int):
    Conversation.query.filter_by(id=conversation_id, owner_id=_owner_id()).first_or_404()
    state = db.session.get(ConversationState, conversation_id)
    if state:
        state.is_archived = False
        db.session.commit()
    return jsonify({"conversation_id": conversation_id, "is_archived": False})


@workspace_bp.get("/analytics")
def workspace_analytics():
    owner = _owner_id()
    conversation_ids = [row.id for row in Conversation.query.filter_by(owner_id=owner).all()]
    plans = TaskPlan.query.filter_by(owner_id=owner).all()
    runs = ToolRun.query.filter_by(owner_id=owner).all()
    events = UsageEvent.query.filter_by(owner_id=owner).all()
    by_tool: dict[str, int] = {}
    for run in runs:
        by_tool[run.tool_name] = by_tool.get(run.tool_name, 0) + 1
    latencies = [run.latency_ms for run in runs if run.latency_ms is not None]
    messages = (
        Message.query.filter(Message.conversation_id.in_(conversation_ids)).all() if conversation_ids else []
    )
    return jsonify(
        {
            "conversations": len(conversation_ids),
            "messages": len(messages),
            "artifacts": Artifact.query.filter_by(owner_id=owner, deleted_at=None).count(),
            "uploads": UploadedFile.query.filter_by(owner_id=owner).count(),
            "contacts": Contact.query.filter_by(owner_id=owner).count(),
            "tool_calls": len(runs),
            "web_searches": by_tool.get("web_search", 0),
            "successful_tasks": sum(plan.status == "completed" for plan in plans),
            "failed_tasks": sum(plan.status == "failed" for plan in plans),
            "pending_confirmations": sum(plan.status == "awaiting_confirmation" for plan in plans),
            "average_tool_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
            "most_used_tools": sorted(by_tool.items(), key=lambda item: item[1], reverse=True)[:8],
            "estimated_ai_cost_usd": float(sum((event.estimated_cost_usd or 0) for event in events)),
        }
    )


@workspace_bp.post("/auth/register")
def auth_register():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().casefold()
    password = str(payload.get("password") or "")
    name = safe_display_name(str(payload.get("display_name") or ""), "NexaChat user")
    if "@" not in email or len(email) > 255:
        return jsonify({"error": "Enter a valid email address"}), 400
    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters"}), 400
    if User.query.filter(func.lower(User.email) == email).first():
        return jsonify({"error": "An account with this email already exists"}), 409
    user = User(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        display_name=name,
        is_guest=False,
    )
    db.session.add(user)
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    session["csrf_token"] = hashlib.sha256(f"{user.id}:{datetime.now(UTC).isoformat()}".encode()).hexdigest()
    return jsonify({"user": user.to_dict(), "csrf_token": session["csrf_token"]}), 201


@workspace_bp.post("/auth/login")
def auth_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().casefold()
    password = str(payload.get("password") or "")
    user = User.query.filter(func.lower(User.email) == email).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401
    session.clear()
    session["user_id"] = user.id
    session["csrf_token"] = hashlib.sha256(f"{user.id}:{datetime.now(UTC).isoformat()}".encode()).hexdigest()
    return jsonify({"user": user.to_dict(), "csrf_token": session["csrf_token"]})


@workspace_bp.post("/auth/logout")
def auth_logout():
    session.clear()
    return "", 204


@workspace_bp.get("/auth/me")
def auth_me():
    user = db.session.get(User, _owner_id())
    return jsonify(user.to_dict() if user else None)
