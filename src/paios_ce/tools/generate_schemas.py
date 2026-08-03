"""Generate JSON Schemas from the pydantic protocol/config models.

Outputs the Phase 3 schema files (config + protocol). The protocol schemas
are structurally consistent with the Phase 2 JSON Schemas because the models
use the same field names, enums, and extra="forbid".

Run:  python -m paios_ce.tools.generate_schemas --out <dir>

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Type

from ..config.models import PrivateConfig, PublicConfig, RuntimeConfig
from ..protocols.models import (
    ActionRequest,
    ActionResult,
    AuditEvent,
    ErrorEnvelope,
    TaskEnvelope,
    TaskPlan,
)

MODELS: Dict[str, Type] = {
    "public_config.schema.json": PublicConfig,
    "private_config.schema.json": PrivateConfig,
    "runtime_config.schema.json": RuntimeConfig,
    "task_envelope.schema.json": TaskEnvelope,
    "task_plan.schema.json": TaskPlan,
    "action_request.schema.json": ActionRequest,
    "action_result.schema.json": ActionResult,
    "error_envelope.schema.json": ErrorEnvelope,
    "audit_event.schema.json": AuditEvent,
}


def _model_schema(model: Type) -> Dict:
    schema = model.model_json_schema()
    # add ids for stability
    base = schema.get("title", model.__name__).lower().replace(" ", "-")
    schema.setdefault("$id", f"https://paios.ce/schemas/{base}/v0.1.json")
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    return schema


def generate_schemas(out_dir: Path) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for filename, model in MODELS.items():
        schema = _model_schema(model)
        target = out_dir / filename
        target.write_text(json.dumps(schema, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        written[filename] = target
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="schemas", type=Path)
    args = parser.parse_args()
    written = generate_schemas(args.out)
    for name, path in sorted(written.items()):
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":  # pragma: no cover
    main()
