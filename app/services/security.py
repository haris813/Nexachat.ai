from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import phonenumbers
import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


class SecurityError(ValueError):
    """Raised when untrusted input violates a security boundary."""


class SecretBox:
    """Small encryption and deterministic hashing helper for user-owned PII."""

    def __init__(self) -> None:
        configured = current_app.config.get("ENCRYPTION_KEY", "").encode()
        if configured:
            try:
                Fernet(configured)
                key = configured
            except (ValueError, TypeError):
                key = base64.urlsafe_b64encode(hashlib.sha256(configured).digest())
        else:
            seed = f"{current_app.config['SECRET_KEY']}:nexachat-local-encryption".encode()
            key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
        self._fernet = Fernet(key)
        self._hmac_key = hashlib.sha256(key + b":lookup").digest()

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None:
            return None
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str | None) -> str | None:
        if ciphertext is None:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as error:
            raise SecurityError("Encrypted value could not be read") from error

    def digest(self, value: str) -> str:
        return hmac.new(self._hmac_key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_phone(value: str, default_region: str = "IN") -> str:
    raw = value.strip()
    try:
        number = phonenumbers.parse(raw, None if raw.startswith("+") else default_region)
    except phonenumbers.NumberParseException as error:
        raise SecurityError("Enter a valid phone number with country code") from error
    if not phonenumbers.is_valid_number(number):
        raise SecurityError("Enter a valid international phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(e164: str) -> str:
    visible = e164[-4:]
    prefix = e164[: max(2, len(e164) - 8)]
    return f"{prefix}{'•' * max(4, len(e164) - len(prefix) - 4)}{visible}"


def safe_display_name(value: str, fallback: str = "artifact") -> str:
    cleaned = " ".join(value.replace("\x00", "").split()).strip(" .")
    return (cleaned or fallback)[:180]


def _resolved_addresses(hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        records = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise SecurityError("The requested host could not be resolved") from error
    return {ipaddress.ip_address(item[4][0]) for item in records}


def validate_public_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SecurityError("Only public HTTP and HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise SecurityError("URLs containing credentials are not allowed")
    if parsed.port not in {None, 80, 443}:
        raise SecurityError("Non-standard URL ports are not allowed")
    if current_app.config.get("ALLOW_PRIVATE_URLS"):
        return url
    for address in _resolved_addresses(parsed.hostname):
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise SecurityError("Private and local network addresses are blocked")
    return url


@dataclass
class SafeResponse:
    url: str
    status_code: int
    content_type: str
    text: str


def safe_fetch(url: str, *, max_bytes: int = 2_000_000, redirects: int = 3) -> SafeResponse:
    current = validate_public_url(url)
    timeout = current_app.config["WEB_REQUEST_TIMEOUT"]
    headers = {
        "User-Agent": "NexaChatAI/1.2 (+security-conscious research fetcher)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
    }
    for _ in range(redirects + 1):
        with requests.get(
            current,
            headers=headers,
            timeout=(5, timeout),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise SecurityError("Redirect response did not include a destination")
                current = validate_public_url(urljoin(current, location))
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise SecurityError("The URL did not return readable webpage content")
            chunks: list[bytes] = []
            consumed = 0
            for chunk in response.iter_content(65_536):
                consumed += len(chunk)
                if consumed > max_bytes:
                    raise SecurityError("The webpage exceeded the safe retrieval limit")
                chunks.append(chunk)
            encoding = response.encoding or "utf-8"
            return SafeResponse(
                url=current,
                status_code=response.status_code,
                content_type=content_type,
                text=b"".join(chunks).decode(encoding, errors="replace"),
            )
    raise SecurityError("The webpage redirected too many times")
