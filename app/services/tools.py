from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from jsonschema import Draft202012Validator


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    side_effect: bool = False
    confirmation_required: bool = False

    def validate(self, arguments: dict[str, Any]) -> None:
        errors = sorted(
            Draft202012Validator(self.input_schema).iter_errors(arguments), key=lambda item: item.path
        )
        if errors:
            raise ToolValidationError(f"{self.name}: {errors[0].message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "side_effect": self.side_effect,
            "confirmation_required": self.confirmation_required,
        }


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_DEFINITIONS = [
    ToolDefinition(
        "web_search",
        "Search a configured live web-search provider. Required for current or time-sensitive facts.",
        _object_schema(
            {
                "query": {"type": "string", "minLength": 2, "maxLength": 500},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            ["query"],
        ),
    ),
    ToolDefinition(
        "fetch_webpage",
        "Fetch readable public webpage text with SSRF and redirect protections.",
        _object_schema({"url": {"type": "string", "format": "uri"}}, ["url"]),
    ),
    ToolDefinition(
        "calculate",
        "Evaluate a bounded arithmetic expression without executing code.",
        _object_schema({"expression": {"type": "string", "minLength": 1, "maxLength": 300}}, ["expression"]),
    ),
    ToolDefinition(
        "generate_excel",
        "Create a styled XLSX workbook with tables, charts, previews, and a metadata/source sheet.",
        _object_schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 180},
                "rows": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                "sources": {"type": "array", "items": {"type": "object"}},
            },
            ["title", "rows"],
        ),
    ),
    ToolDefinition(
        "generate_word",
        "Create a professional DOCX with cover, contents, headings, tables, page numbers, and references.",
        _object_schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 180},
                "sections": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                "template": {"type": "string", "maxLength": 50},
            },
            ["title", "sections"],
        ),
    ),
    ToolDefinition(
        "generate_powerpoint",
        "Create a 16:9 PPTX with an intentional theme, agenda, content slides, and sources.",
        _object_schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 180},
                "slides": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                "theme": {"type": "string", "maxLength": 50},
            },
            ["title", "slides"],
        ),
    ),
    ToolDefinition(
        "generate_pdf",
        "Create a professional PDF report with headings, tables, page numbers, and citations.",
        _object_schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 180},
                "sections": {"type": "array", "minItems": 1, "items": {"type": "object"}},
            },
            ["title", "sections"],
        ),
    ),
    ToolDefinition(
        "analyze_file",
        "Analyze a validated user-owned upload without executing its contents.",
        _object_schema({"upload_id": {"type": "string", "format": "uuid"}}, ["upload_id"]),
    ),
    ToolDefinition(
        "extract_document_text",
        "Return bounded extracted text from a validated PDF, Office document, CSV, JSON, or text upload.",
        _object_schema({"upload_id": {"type": "string", "format": "uuid"}}, ["upload_id"]),
    ),
    ToolDefinition(
        "create_chart",
        "Create a downloadable PNG chart from labels and numeric values.",
        _object_schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 180},
                "labels": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "values": {"type": "array", "minItems": 1, "items": {"type": "number"}},
            },
            ["title", "labels", "values"],
        ),
    ),
    ToolDefinition(
        "transcribe_audio",
        "Transcribe a validated audio upload. The transcript is returned for user review.",
        _object_schema({"upload_id": {"type": "string", "format": "uuid"}}, ["upload_id"]),
    ),
    ToolDefinition(
        "text_to_speech",
        "Generate an MP3 spoken response from user-approved text.",
        _object_schema({"text": {"type": "string", "minLength": 1, "maxLength": 4096}}, ["text"]),
    ),
    ToolDefinition(
        "search_contacts",
        "Search only the current user's saved contacts by name.",
        _object_schema({"query": {"type": "string", "minLength": 1, "maxLength": 120}}, ["query"]),
    ),
    ToolDefinition(
        "prepare_whatsapp_message",
        "Prepare but do not send a WhatsApp text or audio message; returns an exact confirmation card.",
        _object_schema(
            {
                "contact_id": {"type": "string", "format": "uuid"},
                "message_type": {"type": "string", "enum": ["text", "audio"]},
                "body": {"type": "string", "maxLength": 4096},
                "upload_id": {"type": "string", "format": "uuid"},
            },
            ["contact_id", "message_type"],
        ),
        side_effect=False,
        confirmation_required=True,
    ),
    ToolDefinition(
        "send_whatsapp_message",
        "Send a previously prepared WhatsApp action only when its one-time confirmation token is supplied.",
        _object_schema(
            {
                "message_id": {"type": "string", "format": "uuid"},
                "confirmation_token": {"type": "string", "minLength": 20},
            },
            ["message_id", "confirmation_token"],
        ),
        side_effect=True,
        confirmation_required=True,
    ),
    ToolDefinition(
        "export_conversation",
        "Export a user-owned conversation as a downloadable artifact.",
        _object_schema(
            {
                "conversation_id": {"type": "integer", "minimum": 1},
                "format": {"type": "string", "enum": ["markdown", "pdf", "word", "powerpoint"]},
            },
            ["conversation_id", "format"],
        ),
    ),
]

TOOL_REGISTRY = {tool.name: tool for tool in TOOL_DEFINITIONS}


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> None:
    definition = TOOL_REGISTRY.get(name)
    if definition is None:
        raise ToolValidationError(f"Unknown tool: {name}")
    definition.validate(arguments)


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_calculate(expression: str) -> float:
    validate_tool_arguments("calculate", {"expression": expression})
    tree = ast.parse(expression, mode="eval")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left, right = evaluate(node.left), evaluate(node.right)
            if abs(left) > 1e100 or abs(right) > 1e100:
                raise ToolValidationError("Calculation operands are too large")
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ToolValidationError("Exponent is outside the safe range")
            operation = cast(Callable[[float, float], float], _BINARY_OPERATORS[type(node.op)])
            return operation(left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            unary_operation = cast(Callable[[float], float], _UNARY_OPERATORS[type(node.op)])
            return unary_operation(evaluate(node.operand))
        raise ToolValidationError("Only numeric arithmetic operators are allowed")

    result = evaluate(tree)
    if not isinstance(result, (int, float)) or abs(result) > 1e100:
        raise ToolValidationError("Calculation result is outside the safe range")
    return float(result)
