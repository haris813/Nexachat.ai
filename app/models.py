from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid4_str() -> str:
    return str(uuid.uuid4())


def _json_load(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    email = db.Column(db.String(255), nullable=True, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(100), nullable=False, default="Workspace user")
    is_guest = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "is_guest": self.is_guest,
            "created_at": self.created_at.isoformat(),
        }


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False, default="New conversation")
    system_prompt = db.Column(db.Text, nullable=False, default="")
    persona = db.Column(db.String(30), nullable=False, default="general")
    model = db.Column(db.String(80), nullable=False, default="gpt-5-mini")
    is_pinned = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    messages = db.relationship(
        "Message",
        backref="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Message.created_at",
    )

    def to_dict(self, include_messages: bool = False) -> dict:
        result = {
            "id": self.id,
            "title": self.title,
            "system_prompt": self.system_prompt,
            "persona": self.persona,
            "model": self.model,
            "is_pinned": self.is_pinned,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": len(self.messages),
        }
        if include_messages:
            result["messages"] = [message.to_dict() for message in self.messages]
        return result


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    provider = db.Column(db.String(30), nullable=True)
    model = db.Column(db.String(80), nullable=True)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    latency_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat(),
        }


class ConversationState(db.Model):
    __tablename__ = "conversation_states"
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    language = db.Column(db.String(20), nullable=False, default="auto")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class TaskPlan(db.Model):
    __tablename__ = "task_plans"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="awaiting_approval", index=True)
    steps_json = db.Column(db.Text, nullable=False, default="[]")
    required_tools_json = db.Column(db.Text, nullable=False, default="[]")
    attachment_ids_json = db.Column(db.Text, nullable=False, default="[]")
    expected_output = db.Column(db.String(255), nullable=False, default="Assistant response")
    confirmation_required = db.Column(db.Boolean, nullable=False, default=False)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def steps(self) -> list:
        return _json_load(self.steps_json, [])

    @property
    def required_tools(self) -> list:
        return _json_load(self.required_tools_json, [])

    @property
    def attachment_ids(self) -> list:
        return _json_load(self.attachment_ids_json, [])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "goal": self.goal,
            "intent": self.intent,
            "status": self.status,
            "steps": self.steps,
            "required_tools": self.required_tools,
            "attachment_ids": self.attachment_ids,
            "expected_output": self.expected_output,
            "confirmation_required": self.confirmation_required,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ToolRun(db.Model):
    __tablename__ = "tool_runs"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    plan_id = db.Column(
        db.String(36),
        db.ForeignKey("task_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="queued")
    input_json = db.Column(db.Text, nullable=False, default="{}")
    output_json = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    latency_ms = db.Column(db.Integer, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "input": _json_load(self.input_json, {}),
            "output": _json_load(self.output_json, None),
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "latency_ms": self.latency_ms,
        }


class UploadedFile(db.Model):
    __tablename__ = "uploaded_files"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    storage_path = db.Column(db.Text, nullable=False)
    mime_type = db.Column(db.String(150), nullable=False)
    extension = db.Column(db.String(20), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="ready")
    extracted_text = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.original_name,
            "mime_type": self.mime_type,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
            "metadata": _json_load(self.metadata_json, {}),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class Artifact(db.Model):
    __tablename__ = "artifacts"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    plan_id = db.Column(
        db.String(36),
        db.ForeignKey("task_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind = db.Column(db.String(30), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    storage_path = db.Column(db.Text, nullable=False)
    mime_type = db.Column(db.String(150), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="ready")
    metadata_json = db.Column(db.Text, nullable=False, default="{}")
    preview_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "plan_id": self.plan_id,
            "kind": self.kind,
            "name": self.display_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "metadata": _json_load(self.metadata_json, {}),
            "preview": _json_load(self.preview_json, {}),
            "download_url": f"/api/artifacts/{self.id}/download",
            "created_at": self.created_at.isoformat(),
        }


class ResearchSource(db.Model):
    __tablename__ = "research_sources"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    plan_id = db.Column(
        db.String(36),
        db.ForeignKey("task_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.Text, nullable=False)
    domain = db.Column(db.String(255), nullable=False)
    snippet = db.Column(db.Text, nullable=False, default="")
    retrieved_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "retrieved_at": self.retrieved_at.isoformat(),
        }


class Contact(db.Model):
    __tablename__ = "contacts"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    phone_ciphertext = db.Column(db.Text, nullable=False)
    phone_hash = db.Column(db.String(64), nullable=False)
    phone_last4 = db.Column(db.String(4), nullable=False)
    email_ciphertext = db.Column(db.Text, nullable=True)
    relationship = db.Column(db.String(80), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    preferred_channel = db.Column(db.String(30), nullable=False, default="whatsapp")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (db.UniqueConstraint("owner_id", "phone_hash", name="uq_contact_owner_phone"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone_masked": f"••••••{self.phone_last4}",
            "relationship": self.relationship,
            "notes": self.notes,
            "preferred_channel": self.preferred_channel,
            "created_at": self.created_at.isoformat(),
        }


class WhatsAppMessage(db.Model):
    __tablename__ = "whatsapp_messages"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    contact_id = db.Column(
        db.String(36),
        db.ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    message_type = db.Column(db.String(20), nullable=False, default="text")
    body_ciphertext = db.Column(db.Text, nullable=True)
    media_upload_id = db.Column(
        db.String(36),
        db.ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_masked = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending_confirmation", index=True)
    confirmation_hash = db.Column(db.String(64), nullable=False)
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    provider_message_id = db.Column(db.String(255), nullable=True, index=True)
    provider_response_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    delivered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)
    failed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self, include_body: bool = False, body: str | None = None) -> dict:
        result = {
            "id": self.id,
            "contact_id": self.contact_id,
            "message_type": self.message_type,
            "recipient_masked": self.recipient_masked,
            "status": self.status,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "provider_message_id": self.provider_message_id,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }
        if include_body:
            result["body"] = body
        return result


class UserPreference(db.Model):
    __tablename__ = "user_preferences"
    owner_id = db.Column(db.String(36), primary_key=True)
    language = db.Column(db.String(20), nullable=False, default="auto")
    document_style = db.Column(db.String(50), nullable=False, default="modern_light")
    presentation_theme = db.Column(db.String(50), nullable=False, default="modern_light")
    auto_speak = db.Column(db.Boolean, nullable=False, default=False)
    confirmation_mode = db.Column(db.String(30), nullable=False, default="always")
    memory_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "document_style": self.document_style,
            "presentation_theme": self.presentation_theme,
            "auto_speak": self.auto_speak,
            "confirmation_mode": self.confirmation_mode,
            "memory": _json_load(self.memory_json, {}),
        }


class UsageEvent(db.Model):
    __tablename__ = "usage_events"
    id = db.Column(db.String(36), primary_key=True, default=uuid4_str)
    owner_id = db.Column(db.String(36), nullable=False, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    tool_name = db.Column(db.String(80), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="success")
    latency_ms = db.Column(db.Integer, nullable=True)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    estimated_cost_usd = db.Column(db.Numeric(12, 6), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
