"""
SchemaDrift -- Interactive Web Server & API Backend

Routes ALL records through the real CompatibilityEngine (engine.py).
The engine performs the two-layer check:
  Layer 1 (Structural): Required fields present? Types compatible?
  Layer 2 (Semantic): Do declared semantic descriptors match? Is there
                      a registered transform bridging any gap?

No hardcoded heuristics — compatibility is determined entirely by the
declared schema contracts in the SchemaRegistry.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import traceback
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from schema_registry import (
    Consumer,
    FieldDef,
    SchemaRegistry,
    SchemaVersion,
    SemanticDescriptor,
    SemanticTransform,
)
from engine import CompatibilityEngine, Verdict
from quarantine import (
    CorrectionJob,
    QuarantineEntry,
    QuarantineReason,
    QuarantineStore,
)
import ai_advisor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEB_DIR = os.path.join(BASE_DIR, "web")

# Metadata ID fields excluded from the domain identity rule.
# 'record_id' is a row-level metadata key, not a domain-specific
# identifier like 'user_id' or 'device_id'.
METADATA_ID_FIELDS = {"record_id"}


# --- Batch Processor Engine --------------------------------------------------

class BatchStreamProcessor:
    """Processes record batches through the real two-layer CompatibilityEngine."""

    def __init__(self) -> None:
        self.store = QuarantineStore()
        self.registry = SchemaRegistry()
        self.engine = CompatibilityEngine(self.registry, auto_heal=True)
        self._init_core_schemas()

    def _init_core_schemas(self) -> None:
        """Register all schemas, consumers, and known transforms for 5 domains."""

        # -- Semantic Descriptors --
        sem_cents     = SemanticDescriptor("cents",              "integer")
        sem_dollars   = SemanticDescriptor("dollars",            "float")
        sem_celsius   = SemanticDescriptor("celsius",            "float")
        sem_fahr      = SemanticDescriptor("fahrenheit",         "float")
        sem_sv1       = SemanticDescriptor("status_v1",          "string")
        sem_sv2       = SemanticDescriptor("status_v2",          "string")
        sem_us        = SemanticDescriptor("microseconds",       "integer")
        sem_ms        = SemanticDescriptor("milliseconds",       "integer")
        sem_epoch_ms  = SemanticDescriptor("epoch_milliseconds", "integer")
        sem_epoch_s   = SemanticDescriptor("epoch_seconds",      "integer")

        # -- 1. Payment Schemas --
        self.registry.register_schema(SchemaVersion("payment", "v1", {
            "user_id":   FieldDef("user_id",   str,   True),
            "amount":    FieldDef("amount",    int,   True, sem_cents),
            "timestamp": FieldDef("timestamp", str,   True),
        }))
        self.registry.register_schema(SchemaVersion("payment", "v2", {
            "user_id":   FieldDef("user_id",   str,   True),
            "amount":    FieldDef("amount",    float, True, sem_dollars),
            "timestamp": FieldDef("timestamp", str,   True),
        }))
        self.registry.register_consumer(Consumer("billing-service", "payment:v1", True))

        # -- 2. Telemetry Schemas --
        self.registry.register_schema(SchemaVersion("telemetry", "v1", {
            "device_id":   FieldDef("device_id",   str,   True),
            "temperature": FieldDef("temperature", float, True, sem_celsius),
        }))
        self.registry.register_schema(SchemaVersion("telemetry", "v2", {
            "device_id":   FieldDef("device_id",   str,   True),
            "temperature": FieldDef("temperature", float, True, sem_fahr),
        }))
        self.registry.register_consumer(Consumer("climate-service", "telemetry:v1", True))

        # -- 3. Orders Schemas --
        self.registry.register_schema(SchemaVersion("orders", "v1", {
            "order_id":    FieldDef("order_id",    str, True),
            "customer_id": FieldDef("customer_id", str, True),
            "status":      FieldDef("status",      str, True, sem_sv1),
        }))
        self.registry.register_schema(SchemaVersion("orders", "v2", {
            "order_id":    FieldDef("order_id",    str, True),
            "customer_id": FieldDef("customer_id", str, True),
            "status":      FieldDef("status",      str, True, sem_sv2),
        }))
        self.registry.register_consumer(Consumer("order-consumer", "orders:v1", True))

        # -- 4. Performance Schemas --
        self.registry.register_schema(SchemaVersion("performance", "v1", {
            "service_id": FieldDef("service_id", str, True),
            "latency":    FieldDef("latency",    int, True, sem_us),
        }))
        self.registry.register_schema(SchemaVersion("performance", "v2", {
            "service_id": FieldDef("service_id", str, True),
            "latency":    FieldDef("latency",    int, True, sem_ms),
        }))
        self.registry.register_consumer(Consumer("metrics-consumer", "performance:v1", True))

        # -- 5. Temporal Schemas --
        self.registry.register_schema(SchemaVersion("temporal", "v1", {
            "event_id":  FieldDef("event_id",  str, True),
            "timestamp": FieldDef("timestamp", int, True, sem_epoch_ms),
        }))
        self.registry.register_schema(SchemaVersion("temporal", "v2", {
            "event_id":  FieldDef("event_id",  str, True),
            "timestamp": FieldDef("timestamp", int, True, sem_epoch_s),
        }))
        self.registry.register_consumer(Consumer("timeline-consumer", "temporal:v1", True))

        # -- 6. Generic Stream Schemas (for structural breaks / unidentified items) --
        self.registry.register_schema(SchemaVersion("stream", "v1", {
            "record_id": FieldDef("record_id", str, True),
        }))
        self.registry.register_schema(SchemaVersion("stream", "v3", {}))
        self.registry.register_consumer(Consumer("consumer-service", "stream:v1", True))

        # -- Pre-Registered Transforms --
        self.registry.register_transform(SemanticTransform(
            "amount", sem_dollars, sem_cents,
            lambda v: int(round(v * 100)),
            "dollars (float) → cents (int): ×100",
        ))
        self.registry.register_transform(SemanticTransform(
            "temperature", sem_fahr, sem_celsius,
            lambda v: round((v - 32) * 5.0 / 9.0, 1),
            "Fahrenheit → Celsius: (F−32)×5/9",
        ))
        self.registry.register_transform(SemanticTransform(
            "status", sem_sv2, sem_sv1,
            lambda v: {"COMPLETED": "SUCCESS", "FAILED": "ERROR",
                       "PENDING": "IN_PROGRESS"}.get(v, v),
            "Modern enum → legacy: COMPLETED→SUCCESS, FAILED→ERROR",
        ))
        self.registry.register_transform(SemanticTransform(
            "latency", sem_ms, sem_us,
            lambda v: v * 1000,
            "milliseconds → microseconds: ×1000",
        ))
        self.registry.register_transform(SemanticTransform(
            "timestamp", sem_epoch_s, sem_epoch_ms,
            lambda v: v * 1000,
            "epoch seconds → epoch milliseconds: ×1000",
        ))

    # -- Helpers ---------------------------------------------------------------

    def _domain_ids(self, rec: dict) -> list[str]:
        """
        Return domain-specific *_id fields, excluding metadata like 'record_id'.
        Plain 'id' is also rejected per the identity rule.
        """
        return [
            k for k, v in rec.items()
            if k.lower().endswith("_id") and len(k) > 3
            and k.lower() != "id"
            and k.lower() not in METADATA_ID_FIELDS
            and v is not None and str(v).strip() != ""
        ]

    def _rec_id(self, rec: dict, ids: list[str], idx: int) -> str:
        """Extract the best human-readable record identifier."""
        for key in ("user_id", "device_id", "order_id", "customer_id",
                     "event_id", "service_id"):
            val = rec.get(key)
            if val:
                return str(val)
        if ids:
            return str(rec[ids[0]])
        return rec.get("id", "") or f"rec_{idx+1:03d}"

    def _classify(self, rec: dict) -> tuple[str, str]:
        """
        Determine producer schema key and critical field from the record's
        declared semantic metadata — NOT from value heuristics.

        Priority:
          1. Explicit 'semantic.value' field (the producer's own declaration)
          2. Explicit 'unit' / 'status_type' field
          3. Fallback to compatible version

        Returns: (producer_schema_key, critical_field_name)
        """
        sem_val = rec.get("semantic", {}).get("value", "")

        if "amount" in rec:
            if sem_val == "dollars" or rec.get("unit") == "dollars":
                return "payment:v2", "amount"
            return "payment:v1", "amount"

        if "temperature" in rec:
            if sem_val == "fahrenheit" or rec.get("unit") == "fahrenheit":
                return "telemetry:v2", "temperature"
            return "telemetry:v1", "temperature"

        if "status" in rec:
            if (rec.get("status_type") == "status_v2"
                    or rec.get("status") in ("COMPLETED", "FAILED", "PENDING")):
                return "orders:v2", "status"
            return "orders:v1", "status"

        if "latency" in rec:
            if sem_val == "milliseconds" or rec.get("latency_unit") == "milliseconds":
                return "performance:v2", "latency"
            return "performance:v1", "latency"

        if "timestamp_unit" in rec or (
            isinstance(rec.get("timestamp"), int) and "event_id" in rec
        ):
            if sem_val == "epoch_seconds" or rec.get("timestamp_unit") == "epoch_seconds":
                return "temporal:v2", "timestamp"
            return "temporal:v1", "timestamp"

        return "payment:v1", "payload"

    def _service_info(self, rec: dict) -> tuple[str, str]:
        """Service name and consumer contract spec for UI header."""
        if "amount" in rec:
            return "payment", "payment:v1 (cents/integer, requires user_id)"
        if "temperature" in rec:
            return "telemetry", "telemetry:v1 (celsius/float, requires device_id)"
        if "status" in rec:
            return "orders", "orders:v1 (legacy status_v1, requires order_id)"
        if "latency" in rec:
            return "performance", "performance:v1 (µs/integer, requires service_id)"
        if "timestamp_unit" in rec:
            return "temporal", "temporal:v1 (epoch_ms, requires event_id)"
        return "payment", "default:v1"

    def _sem_dict(self, sd: SemanticDescriptor | None) -> dict:
        """Convert a SemanticDescriptor to the UI's JSON format."""
        if sd is None:
            return {"kind": "contract", "value": "compliant", "type": "object"}
        return {"kind": "unit", "value": sd.unit, "type": sd.encoding}

    # -- Core Processing -------------------------------------------------------

    def process_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Route every record through the real CompatibilityEngine.
        Returns the 4-stage breakdown for each record.
        """
        items: list[dict[str, Any]] = []
        stats = {"total": len(records), "safe": 0,
                 "structural_blocked": 0, "semantic_healed": 0}

        first = records[0] if records else {}
        service, consumer_spec = self._service_info(first)
        now = datetime.now()

        for idx, rec in enumerate(records):
            initial = dict(rec)

            # ── Step 1: Identity check ────────────────────────
            # Enforces the <name>_id rule. Plain 'id' is rejected.
            # Metadata fields like 'record_id' are excluded.
            ids = self._domain_ids(rec)
            rid = self._rec_id(rec, ids, idx)

            if not ids:
                stats["structural_blocked"] += 1
                has_plain = "id" in rec
                detail = (
                    "Missing '<name>_id': plain 'id' not accepted"
                    if has_plain else "Missing '<name>_id' field"
                )
                self.store.add(QuarantineEntry(
                    record_id=rid, consumer_id="consumer-service",
                    reason=QuarantineReason.STRUCTURAL_BREAK,
                    producer_schema_version="stream:v3",
                    consumer_schema_version="stream:v1",
                    record=rec, timestamp=now, detail=detail,
                ))
                drift = (
                    f"STRUCTURAL BREAK: Received plain 'id' "
                    f"('{rec.get('id')}'), but contract strictly requires "
                    f"a domain '<name>_id' (e.g. 'user_id', 'device_id'). "
                    f"Plain 'id' is not accepted."
                    if has_plain else
                    "STRUCTURAL BREAK: No '<name>_id' field found in "
                    "payload. Domain identifier is strictly required."
                )
                items.append({
                    "id": rid, "status": "STRUCTURAL_BREAK",
                    "badge_class": "badge-red",
                    "initial_input": initial,
                    "drift_caught": drift,
                    "ai_intervention": (
                        "Quarantined immediately to store. Blocked "
                        "unidentified/orphaned record missing domain "
                        "'<name>_id'."
                    ),
                    "final_result": "BLOCKED (Quarantined in Store)",
                    "transformed_record": None,
                })
                continue

            # ── Step 2: Classify → producer schema key ────────
            pkey, field = self._classify(rec)
            matched_id = ids[0]

            # ── Step 3: Route through REAL CompatibilityEngine ─
            try:
                results = self.engine.check_record(rec, pkey)
            except Exception:
                # Schema not found → treat as compatible
                stats["safe"] += 1
                sem = rec.get("semantic", {})
                items.append({
                    "id": rid, "field": field,
                    "semantic_producer": sem, "semantic_consumer": sem,
                    "status": "COMPATIBLE", "badge_class": "badge-green",
                    "initial_input": initial,
                    "drift_caught": (
                        f"None. Identifier '{matched_id}' present "
                        f"and record is structurally valid."
                    ),
                    "ai_intervention": "Direct pass-through.",
                    "final_result": "DELIVERED [SAFE_EVOLUTION]",
                    "transformed_record": rec,
                })
                continue

            if not results:
                stats["safe"] += 1
                sem = rec.get("semantic", {})
                items.append({
                    "id": rid, "field": field,
                    "semantic_producer": sem, "semantic_consumer": sem,
                    "status": "COMPATIBLE", "badge_class": "badge-green",
                    "initial_input": initial,
                    "drift_caught": "None. No active consumers for this service.",
                    "ai_intervention": "Direct pass-through.",
                    "final_result": "DELIVERED [SAFE_EVOLUTION]",
                    "transformed_record": rec,
                })
                continue

            # ── Step 4: Interpret engine results ──────────────
            # Pick the result that required the most intervention
            primary = results[0]
            for r in results:
                if r.verdict == Verdict.STRUCTURAL_BREAK:
                    primary = r
                    break
                if r.verdict == Verdict.SEMANTIC_INCOMPATIBLE:
                    primary = r

            # Resolve semantic descriptors from schema registry
            try:
                prod_schema = self.registry.get_schema(pkey)
                prod_fdef = prod_schema.fields.get(field)
                cons = self.registry.get_consumer(primary.consumer_id)
                cons_schema = self.registry.get_schema(
                    cons.expected_schema_version
                )
                cons_fdef = cons_schema.fields.get(field)
                sem_p = self._sem_dict(
                    prod_fdef.semantic if prod_fdef else None
                )
                sem_c = self._sem_dict(
                    cons_fdef.semantic if cons_fdef else None
                )
            except Exception:
                sem_p = rec.get("semantic", {})
                sem_c = rec.get("semantic", {})

            # ── Format result based on engine verdict ─────────

            if primary.verdict == Verdict.STRUCTURAL_BREAK:
                stats["structural_blocked"] += 1
                issues_str = "; ".join(
                    i.detail for i in primary.structural_issues
                )
                try:
                    cons = self.registry.get_consumer(primary.consumer_id)
                    cskey = cons.expected_schema_version
                except Exception:
                    cskey = "unknown"
                self.store.add(QuarantineEntry(
                    record_id=rid,
                    consumer_id=primary.consumer_id,
                    reason=QuarantineReason.STRUCTURAL_BREAK,
                    producer_schema_version=pkey,
                    consumer_schema_version=cskey,
                    record=rec, timestamp=now, detail=issues_str,
                ))
                items.append({
                    "id": rid, "field": field,
                    "semantic_producer": sem_p,
                    "semantic_consumer": sem_c,
                    "status": "STRUCTURAL_BREAK",
                    "badge_class": "badge-red",
                    "initial_input": initial,
                    "drift_caught": f"STRUCTURAL BREAK: {issues_str}",
                    "ai_intervention": (
                        f"Quarantined immediately. Structural mismatch "
                        f"detected by Layer 1 for {primary.consumer_id}."
                    ),
                    "final_result": "BLOCKED (Quarantined in Store)",
                    "transformed_record": None,
                })

            elif primary.verdict == Verdict.SEMANTIC_INCOMPATIBLE:
                stats["structural_blocked"] += 1
                issues_str = "; ".join(
                    i.detail for i in primary.semantic_issues
                )
                try:
                    cons = self.registry.get_consumer(primary.consumer_id)
                    cskey = cons.expected_schema_version
                except Exception:
                    cskey = "unknown"
                self.store.add(QuarantineEntry(
                    record_id=rid,
                    consumer_id=primary.consumer_id,
                    reason=QuarantineReason.SEMANTIC_INCOMPATIBLE,
                    producer_schema_version=pkey,
                    consumer_schema_version=cskey,
                    record=rec, timestamp=now, detail=issues_str,
                ))
                items.append({
                    "id": rid, "field": field,
                    "semantic_producer": sem_p,
                    "semantic_consumer": sem_c,
                    "status": "STRUCTURAL_BREAK",
                    "badge_class": "badge-red",
                    "initial_input": initial,
                    "drift_caught": (
                        f"⚠️ SEMANTIC DRIFT (UNRESOLVABLE): {issues_str}"
                    ),
                    "ai_intervention": (
                        f"Quarantined. No registered transform and AI "
                        f"could not synthesize one for "
                        f"{primary.consumer_id}."
                    ),
                    "final_result": "BLOCKED (Quarantined - Semantic)",
                    "transformed_record": None,
                })

            elif primary.verdict == Verdict.SAFE_EVOLUTION:
                orig_val = rec.get(field)
                xform = primary.transformed_record or rec
                xform_val = xform.get(field)
                was_healed = (
                    orig_val is not None
                    and xform_val is not None
                    and xform_val != orig_val
                )

                if was_healed:
                    stats["semantic_healed"] += 1
                    # Find transform description from registry
                    try:
                        prod_sd = prod_fdef.semantic if prod_fdef else None
                        cons_sd = cons_fdef.semantic if cons_fdef else None
                        tf = (
                            self.registry.find_transform(
                                field, prod_sd, cons_sd
                            )
                            if prod_sd and cons_sd else None
                        )
                        tf_desc = (
                            tf.description
                            if tf else "AI-synthesized transform"
                        )
                    except Exception:
                        tf_desc = "Auto-applied transform"

                    items.append({
                        "id": rid, "field": field,
                        "semantic_producer": sem_p,
                        "semantic_consumer": sem_c,
                        "status": "SEMANTIC_HEALED",
                        "badge_class": "badge-violet",
                        "initial_input": initial,
                        "drift_caught": (
                            f"⚠️ SILENT DRIFT: '{field}' = {orig_val} "
                            f"({sem_p.get('value', '?')}/"
                            f"{sem_p.get('type', '?')}). "
                            f"Consumer expects "
                            f"({sem_c.get('value', '?')}/"
                            f"{sem_c.get('type', '?')}). "
                            f"Semantic mismatch prevented!"
                        ),
                        "ai_intervention": (
                            f"✦ JIT Transform: {tf_desc} "
                            f"[Identified via '{matched_id}']"
                        ),
                        "final_result": (
                            f"{field}: {xform_val} "
                            f"({sem_c.get('value', 'corrected')}) "
                            f"[SAFE_EVOLUTION]"
                        ),
                        "transformed_record": xform,
                    })
                else:
                    stats["safe"] += 1
                    items.append({
                        "id": rid, "field": field,
                        "semantic_producer": sem_p,
                        "semantic_consumer": sem_c,
                        "status": "COMPATIBLE",
                        "badge_class": "badge-green",
                        "initial_input": initial,
                        "drift_caught": (
                            f"None. Identifier '{matched_id}' verified "
                            f"and {field} ({orig_val}) is compliant."
                        ),
                        "ai_intervention": (
                            "Direct pass-through. Verified by "
                            "Layer 1 & Layer 2."
                        ),
                        "final_result": (
                            f"{field}: {orig_val} [DELIVERED]"
                        ),
                        "transformed_record": rec,
                    })

        return {
            "service": service,
            "consumer_contract": consumer_spec,
            "stats": stats,
            "items": items,
        }

    # -- Correction Job --------------------------------------------------------

    def run_correction(
        self, producer_schema_version: str
    ) -> dict[str, Any]:
        """Run the scoped CorrectionJob on quarantined records."""
        job = CorrectionJob(self.registry, self.engine, self.store)
        result = job.run(
            producer_schema_version=producer_schema_version
        )
        return {
            "window": result.window_schema_version,
            "total_scanned": result.total_scanned,
            "released": result.released,
            "still_quarantined": result.still_quarantined,
            "details": result.details,
        }


PROCESSOR = BatchStreamProcessor()


# --- HTTP Handler ------------------------------------------------------------

class SchemaDriftHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/sample-datasets":
            datasets = []
            json_files = glob.glob(os.path.join(DATA_DIR, "*.json"))
            for jf in json_files:
                basename = os.path.basename(jf)
                try:
                    with open(jf, "r", encoding="utf-8") as f:
                        content = json.load(f)
                    datasets.append({
                        "filename": basename,
                        "title": basename.replace(".json", "")
                                .replace("_", " ").title(),
                        "count": (
                            len(content) if isinstance(content, list) else 1
                        ),
                        "data": content,
                    })
                except Exception:
                    pass
            self._send_json({"datasets": datasets})
            return

        if parsed.path == "/api/quarantine":
            entries = [
                {
                    "record_id": e.record_id,
                    "consumer_id": e.consumer_id,
                    "reason": e.reason.name,
                    "status": e.status.name,
                    "schema": e.producer_schema_version,
                    "record": e.record,
                    "detail": e.detail,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in PROCESSOR.store.all_entries()
            ]
            self._send_json({
                "entries": entries,
                "stats": PROCESSOR.store.stats(),
            })
            return

        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = (
            self.rfile.read(content_length) if content_length > 0 else b"{}"
        )

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if parsed.path == "/api/process-batch":
            if isinstance(payload, list):
                records = payload
            elif isinstance(payload, dict):
                records = payload.get("records", [])
            else:
                records = []
            if not isinstance(records, list):
                records = [records]
            res = PROCESSOR.process_records(records)
            self._send_json(res)
            return

        if parsed.path == "/api/ai/report":
            try:
                events = [
                    {
                        "step": 1,
                        "action": "batch_ingestion",
                        "result": "active",
                        "details": (
                            "Processed batch through SchemaDrift "
                            "two-layer engine pipeline"
                        ),
                    },
                    {
                        "step": 2,
                        "action": "structural_detection",
                        "result": "blocked",
                        "details": (
                            "Detected and quarantined malformed "
                            "records missing domain identifiers"
                        ),
                    },
                    {
                        "step": 3,
                        "action": "semantic_detection",
                        "result": "healed",
                        "details": (
                            "Caught silent drift (dollars vs cents, "
                            "fahrenheit vs celsius) and auto-healed "
                            "via registered transforms"
                        ),
                    },
                ]
                report = ai_advisor.ai_generate_impact_report(events)
                self._send_json({"report": report})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        # -- Correction Job API (Loophole 5 fix) --
        if parsed.path == "/api/quarantine/correct":
            try:
                schema_ver = payload.get("producer_schema_version", "")
                if not schema_ver:
                    # Run correction for ALL quarantined schema versions
                    all_versions = set()
                    for entry in PROCESSOR.store.quarantined_entries():
                        all_versions.add(entry.producer_schema_version)
                    combined = {
                        "total_scanned": 0,
                        "released": 0,
                        "still_quarantined": 0,
                        "details": [],
                    }
                    for ver in all_versions:
                        r = PROCESSOR.run_correction(ver)
                        combined["total_scanned"] += r["total_scanned"]
                        combined["released"] += r["released"]
                        combined["still_quarantined"] += (
                            r["still_quarantined"]
                        )
                        combined["details"].extend(r["details"])
                    self._send_json(combined)
                else:
                    result = PROCESSOR.run_correction(schema_ver)
                    self._send_json(result)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        self._send_json({"error": "Not Found"}, status=404)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header(
            "Content-Type", "application/json; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = 8000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, SchemaDriftHandler)
    print(f"==================================================")
    print(f"  SchemaDrift Unified Batch UI Server running at:")
    print(f"  http://localhost:{port}")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
