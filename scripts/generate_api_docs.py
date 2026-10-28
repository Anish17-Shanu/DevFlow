"""Render docs/API.md from the live OpenAPI schema.

Usage:
    python scripts/generate_api_docs.py           # write docs/API.md
    python scripts/generate_api_docs.py --check   # fail when the file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "API.md"
METHOD_ORDER = ["get", "post", "put", "patch", "delete", "options", "head"]


def schema_name(schema: dict | None) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        return f"array<{schema_name(schema.get('items'))}>"
    return schema.get("type", "object")


def render() -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.main import app

    spec = app.openapi()
    lines: list[str] = [
        "# API Guide",
        "",
        "Generated from the OpenAPI schema by `scripts/generate_api_docs.py`.",
        "Run the script (or `python scripts/generate_api_docs.py --check` in CI) after changing routes.",
        "",
        f"Base URL: `{spec.get('servers', [{}])[0].get('url', '/')}` · API version `{spec['info']['version']}`",
        "",
        "## Authentication",
        "",
        "Send a scoped API key in the `X-API-Key` header (or `Authorization: Bearer <key>`).",
        "Roles: `viewer` (read), `operator` (run/cancel/edit), `admin` (keys, secrets, webhooks, archive).",
        "",
        "## Errors",
        "",
        "Every error uses one envelope:",
        "",
        "```json",
        '{"code": "forbidden", "message": "Readable summary.", "request_id": "…", "details": null}',
        "```",
        "",
        "`X-Request-ID` is echoed on every response and included in structured logs.",
        "",
        "## Versioning",
        "",
        "Routes live under `/api/v1`. Additive changes ship in place; breaking changes require a new",
        "prefix and a deprecation window of at least one minor release. `/health*` and `/metrics` are",
        "unversioned operational endpoints.",
        "",
        "## Endpoints",
        "",
    ]

    for path in sorted(spec["paths"]):
        methods = spec["paths"][path]
        for method in METHOD_ORDER:
            operation = methods.get(method)
            if not operation:
                continue
            summary = operation.get("summary") or operation.get("operationId") or ""
            lines.append(f"### `{method.upper()} {path}`")
            lines.append("")
            if summary:
                lines.append(summary)
                lines.append("")
            if operation.get("deprecated"):
                lines.append("**Deprecated.**")
                lines.append("")
            params = operation.get("parameters", [])
            if params:
                lines.append("| Parameter | In | Required | Type |")
                lines.append("| --- | --- | --- | --- |")
                for parameter in params:
                    lines.append(
                        f"| `{parameter['name']}` | {parameter['in']} | "
                        f"{'yes' if parameter.get('required') else 'no'} | "
                        f"{schema_name(parameter.get('schema'))} |"
                    )
                lines.append("")
            body = operation.get("requestBody")
            if body:
                for media_type, media in body.get("content", {}).items():
                    lines.append(f"Request body (`{media_type}`): `{schema_name(media.get('schema'))}`")
                lines.append("")
            responses = operation.get("responses", {})
            if responses:
                rendered = ", ".join(
                    f"{status} {response.get('description', '')}".strip() for status, response in sorted(responses.items())
                )
                lines.append(f"Responses: {rendered}")
                lines.append("")
            if operation.get("security"):
                scopes = sorted(
                    {scope for requirement in operation["security"] for granted in requirement.values() for scope in granted}
                )
                lines.append(f"Requires an API key{(' with scopes: ' + ', '.join(scopes)) if scopes else ''}.")
                lines.append("")

    lines.extend(
        [
            "## WebSocket streaming",
            "",
            "`GET /ws/executions/{execution_id}?api_key=<key>` upgrades to a WebSocket. The socket is",
            "authenticated per execution and closed with code `1008` for missing keys, invalid keys,",
            "unknown executions, or cross-tenant access. Send the text frame `subscribe` to receive",
            "event notifications; clients should fall back to polling `/logs` while disconnected.",
            "",
            "## Schemas",
            "",
        ]
    )
    for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items()):
        description = schema.get("description") or ""
        lines.append(f"- **{name}** — {description}".rstrip(" —"))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail when docs/API.md is out of date.")
    arguments = parser.parse_args()

    rendered = render()
    if arguments.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print("docs/API.md is out of date. Run: python scripts/generate_api_docs.py", file=sys.stderr)
            return 1
        print("docs/API.md matches the OpenAPI schema.")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(rendered.splitlines())} lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
