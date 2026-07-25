from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import requests
from flask import current_app

from ..extensions import db
from ..models import Contact, UploadedFile, WhatsAppMessage
from .security import SecretBox, SecurityError, mask_phone


class WhatsAppError(RuntimeError):
    pass


class WhatsAppService:
    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id
        self.box = SecretBox()

    def prepare_text(self, contact: Contact, body: str) -> tuple[WhatsAppMessage, str]:
        normalized = " ".join(body.split()).strip()
        if not normalized:
            raise ValueError("WhatsApp message cannot be empty")
        if len(normalized) > 4096:
            raise ValueError("WhatsApp text messages are limited to 4,096 characters")
        phone = self._contact_phone(contact)
        token = secrets.token_urlsafe(32)
        record = WhatsAppMessage(
            owner_id=self.owner_id,
            contact_id=contact.id,
            message_type="text",
            body_ciphertext=self.box.encrypt(normalized),
            recipient_masked=mask_phone(phone),
            status="pending_confirmation",
            confirmation_hash=self.box.digest(token),
        )
        db.session.add(record)
        db.session.commit()
        return record, token

    def prepare_audio(self, contact: Contact, upload: UploadedFile) -> tuple[WhatsAppMessage, str]:
        if not upload.mime_type.startswith("audio/"):
            raise ValueError("Only validated audio uploads can be sent as voice messages")
        phone = self._contact_phone(contact)
        token = secrets.token_urlsafe(32)
        record = WhatsAppMessage(
            owner_id=self.owner_id,
            contact_id=contact.id,
            message_type="audio",
            media_upload_id=upload.id,
            recipient_masked=mask_phone(phone),
            status="pending_confirmation",
            confirmation_hash=self.box.digest(token),
        )
        db.session.add(record)
        db.session.commit()
        return record, token

    def confirm_and_send(self, record: WhatsAppMessage, confirmation_token: str) -> WhatsAppMessage:
        if record.owner_id != self.owner_id:
            raise WhatsAppError("Message confirmation does not belong to this user")
        if record.status != "pending_confirmation" or record.confirmed_at is not None:
            raise WhatsAppError("This message is no longer awaiting confirmation")
        supplied_hash = self.box.digest(confirmation_token)
        if not hmac.compare_digest(record.confirmation_hash, supplied_hash):
            raise SecurityError("Confirmation token is invalid")

        record.confirmed_at = datetime.now(UTC)
        record.status = "confirmed"
        db.session.commit()

        try:
            response = self._send_provider_message(record)
            record.provider_message_id = response.get("message_id")
            record.provider_response_json = json.dumps(response.get("safe_response", {}), ensure_ascii=False)
            record.status = "sent"
            record.sent_at = datetime.now(UTC)
            db.session.commit()
            return record
        except Exception as error:
            record.status = "failed"
            record.failed_at = datetime.now(UTC)
            record.provider_response_json = json.dumps({"error_type": type(error).__name__})
            db.session.commit()
            raise

    def _send_provider_message(self, record: WhatsAppMessage) -> dict[str, Any]:
        if record.confirmed_at is None or record.status != "confirmed":
            raise WhatsAppError("Provider send blocked: no confirmed action record exists")
        contact = db.session.get(Contact, record.contact_id)
        if not contact or contact.owner_id != self.owner_id:
            raise WhatsAppError("Recipient contact is unavailable")
        phone = self._contact_phone(contact)
        if current_app.config["WHATSAPP_MODE"] == "mock":
            return {
                "message_id": f"mock-{secrets.token_hex(10)}",
                "safe_response": {"mode": "mock", "accepted": True, "recipient": mask_phone(phone)},
            }
        return self._send_meta(record, phone)

    def _send_meta(self, record: WhatsAppMessage, phone: str) -> dict[str, Any]:
        token = current_app.config["META_WHATSAPP_ACCESS_TOKEN"]
        phone_number_id = current_app.config["META_WHATSAPP_PHONE_NUMBER_ID"]
        if not token or not phone_number_id:
            raise WhatsAppError("Meta WhatsApp credentials are incomplete")
        version = current_app.config["META_GRAPH_API_VERSION"]
        base = f"https://graph.facebook.com/{version}/{phone_number_id}"
        headers = {"Authorization": f"Bearer {token}"}
        if record.message_type == "text":
            body = self.box.decrypt(record.body_ciphertext) or ""
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone.lstrip("+"),
                "type": "text",
                "text": {"preview_url": False, "body": body},
            }
        elif record.message_type == "audio":
            upload = db.session.get(UploadedFile, record.media_upload_id)
            if not upload or upload.owner_id != self.owner_id:
                raise WhatsAppError("Audio upload is unavailable")
            media_id = self._upload_media(base, headers, upload)
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone.lstrip("+"),
                "type": "audio",
                "audio": {"id": media_id},
            }
        else:
            raise WhatsAppError("Unsupported WhatsApp message type")
        response = requests.post(
            f"{base}/messages",
            headers={**headers, "Content-Type": "application/json"},
            json=cast(Any, payload),
            timeout=(5, 30),
        )
        response.raise_for_status()
        body = response.json()
        message_id = str((body.get("messages") or [{}])[0].get("id") or "")
        if not message_id:
            raise WhatsAppError("Meta accepted the request without returning a message ID")
        return {
            "message_id": message_id,
            "safe_response": {
                "messaging_product": body.get("messaging_product"),
                "contact_count": len(body.get("contacts") or []),
                "message_id": message_id,
            },
        }

    @staticmethod
    def _upload_media(base: str, headers: dict[str, str], upload: UploadedFile) -> str:
        path = Path(upload.storage_path)
        with path.open("rb") as handle:
            response = requests.post(
                f"{base}/media",
                headers=headers,
                data={"messaging_product": "whatsapp", "type": upload.mime_type},
                files={"file": (upload.original_name, handle, upload.mime_type)},
                timeout=(5, 60),
            )
        response.raise_for_status()
        media_id = str(response.json().get("id") or "")
        if not media_id:
            raise WhatsAppError("Meta media upload did not return a media ID")
        return media_id

    def _contact_phone(self, contact: Contact) -> str:
        if contact.owner_id != self.owner_id:
            raise WhatsAppError("Contact does not belong to this user")
        phone = self.box.decrypt(contact.phone_ciphertext)
        if not phone:
            raise WhatsAppError("Contact phone number is unavailable")
        return phone


def verify_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    secret = current_app.config["META_APP_SECRET"]
    if not secret or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


def apply_status_webhook(payload: dict[str, Any]) -> int:
    updated = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for status in change.get("value", {}).get("statuses", []):
                provider_id = str(status.get("id") or "")
                state = str(status.get("status") or "")
                record = WhatsAppMessage.query.filter_by(provider_message_id=provider_id).first()
                if not record or state not in {"sent", "delivered", "read", "failed"}:
                    continue
                now = datetime.now(UTC)
                record.status = state
                if state == "sent":
                    record.sent_at = record.sent_at or now
                elif state == "delivered":
                    record.delivered_at = now
                elif state == "read":
                    record.read_at = now
                elif state == "failed":
                    record.failed_at = now
                updated += 1
    if updated:
        db.session.commit()
    return updated
