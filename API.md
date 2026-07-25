# API reference

All application endpoints are under `/api`. Browser mutations require the `X-CSRF-Token` returned by `GET /api/config`. Authentication uses the HttpOnly session cookie. Every resource query is owner-scoped; identifiers from another session return 404.

JSON errors use:

```json
{"error": "Human-readable safe message"}
```

Typical status codes are 200/201/204, 400 validation, 401 unauthenticated provider callback, 403 CSRF, 404 absent or unowned, 409 conflict/confirmation requirement, 413 size limit, and 429 rate limit.

## Platform and chat

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Database readiness |
| GET | `/config` | Public capabilities, provider status, models, and CSRF token |
| GET | `/stats` | Conversation/model usage summary |
| GET | `/analytics` | Plans, tools, artifacts, contacts, latency, and estimated cost |
| GET | `/conversations` | List owned conversations |
| POST | `/conversations` | Create a conversation |
| DELETE | `/conversations` | Delete all owned conversations |
| GET | `/conversations/{id}` | Conversation plus messages |
| PATCH | `/conversations/{id}` | Rename, pin, select model/persona, or set instructions |
| DELETE | `/conversations/{id}` | Delete conversation |
| POST | `/conversations/{id}/duplicate` | Clone conversation/messages |
| POST | `/conversations/{id}/messages` | Stream a direct chat response |
| POST | `/conversations/{id}/regenerate` | Replace latest assistant response |
| POST | `/conversations/{id}/archive` | Archive |
| POST | `/conversations/{id}/unarchive` | Restore |

Create a conversation:

```http
POST /api/conversations
X-CSRF-Token: <token>
Content-Type: application/json

{"persona":"product","model":"gpt-5-mini"}
```

Direct chat response content type is `text/event-stream`. Events are `delta`, optional `metadata`, `done`, and `error`. A current-data prompt returns HTTP 409 with `requires_plan: true` so the client can create an approved research plan.

## Plans and tools

| Method | Path | Purpose |
|---|---|---|
| GET | `/tools` | Tool names, descriptions, input schemas, side-effect flag |
| POST | `/plans` | Classify a request and persist its proposed plan |
| GET | `/plans` | Recent plans |
| GET | `/plans/{id}` | Plan, steps, tool runs, sources, artifacts |
| POST | `/plans/{id}/execute` | Execute as a progress SSE stream |
| POST | `/plans/{id}/cancel` | Cancel a non-terminal plan |

```http
POST /api/plans
X-CSRF-Token: <token>
Content-Type: application/json

{
  "request": "Research the five richest people and create an Excel report",
  "conversation_id": 12,
  "upload_ids": []
}
```

Execution emits `status`, `tool_start`, `tool_result`, `artifact`, `answer`, `done`, and `error` events. External-message plans stop at `awaiting_confirmation`; they do not send from the plan stream.

## Uploads, voice, and artifacts

| Method | Path | Purpose |
|---|---|---|
| POST | `/uploads` | Multipart upload under field `file` |
| GET | `/uploads` | List owned uploads |
| DELETE | `/uploads/{uuid}` | Delete upload if not retained by an audit dependency |
| POST | `/uploads/{uuid}/transcribe` | Transcribe owned audio |
| POST | `/speech` | Stream synthesized audio from `{text, voice?}` |
| GET | `/artifacts` | Filterable artifact list |
| GET | `/artifacts/{uuid}/download` | Owned attachment download |
| PATCH | `/artifacts/{uuid}` | Rename metadata |
| DELETE | `/artifacts/{uuid}` | Soft-delete and remove owned file |
| POST | `/artifacts/{uuid}/convert` | Convert supported artifact types |
| POST | `/conversations/{id}/artifact-export` | Export chat as Markdown, Word, or PDF |

Upload responses include MIME, size, checksum, extraction status, and an opaque upload id. Never construct filesystem paths in clients.

Create speech:

```http
POST /api/speech
X-CSRF-Token: <token>
Content-Type: application/json

{"text":"Your report is ready.","voice":"alloy"}
```

## Contacts and WhatsApp

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/contacts` | Search/list or create contacts |
| GET/PATCH/DELETE | `/contacts/{uuid}` | Read/update/delete contact |
| POST | `/contacts/import` | Import UTF-8 CSV (`name`, `phone`, optional fields) |
| POST | `/whatsapp/prepare` | Create pending text/audio action |
| POST | `/whatsapp/{uuid}/confirm-send` | Consume confirmation token and send |
| GET | `/whatsapp/messages` | Owned delivery audit history |
| GET/POST | `/whatsapp/webhook` | Meta verification and signed status callbacks |

Prepare:

```json
{
  "contact_id": "contact-uuid",
  "message_type": "text",
  "body": "I will arrive 20 minutes late."
}
```

The response contains a masked number, exact body, provider mode, and one-time `confirmation_token`. Only the confirmation endpoint may send:

```json
{"confirmation_token":"one-time-token-from-prepare"}
```

For audio, send `message_type: "audio"` and an owned audio `upload_id`; the original bytes are uploaded to Meta media before the message reference is sent.

## Preferences and authentication

| Method | Path | Purpose |
|---|---|---|
| GET/PATCH | `/preferences` | Language, styles, theme, auto-speech, explicit memory |
| DELETE | `/preferences/memory` | Clear memory |
| POST | `/auth/register` | Register and replace current guest session |
| POST | `/auth/login` | Authenticate |
| POST | `/auth/logout` | Clear identity and create a new guest on next request |
| GET | `/auth/me` | Current owner |

Passwords require at least 12 characters and are stored with scrypt. Setting `AUTH_REQUIRED=true` blocks product routes until a registered session is present.

## Schemas and examples

The machine-readable subset is in [docs/openapi.yaml](docs/openapi.yaml). An importable collection is in [docs/NexaChat.postman_collection.json](docs/NexaChat.postman_collection.json). The server’s `/api/tools` response is the authoritative runtime JSON Schema catalog for tool inputs.
