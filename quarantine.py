"""
SchemaDrift  --  Quarantine Store & Correction Job

Quarantined records are keyed by (record_id, consumer_id, reason,
schema_version_at_time) and tracked with the version/timestamp window
they were produced under.

The correction job:
  1. Scans quarantined records within a specific bad-schema window
  2. Checks if a transform NOW exists between producer -> consumer semantics
  3. If yes: applies the transform, re-runs the full compatibility check,
     and releases the record on success
  4. If no: leaves it quarantined for manual review

IMPORTANT: correction is scoped ONLY to the bad-schema window.
Compatible traffic before or after that window is never touched.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from engine import CompatibilityEngine, Verdict
from schema_registry import SchemaRegistry


# --- Quarantine Types ---------------------------------------------------------

class QuarantineReason(Enum):
    STRUCTURAL_BREAK = auto()
    SEMANTIC_INCOMPATIBLE = auto()


class RecordStatus(Enum):
    QUARANTINED = auto()
    RELEASED = auto()
    MANUAL_REVIEW = auto()


@dataclass
class QuarantineEntry:
    """One quarantined (record, consumer) pair."""
    record_id: str
    consumer_id: str
    reason: QuarantineReason
    producer_schema_version: str       # e.g. "payment:v4"
    consumer_schema_version: str       # what the consumer expected
    record: dict[str, Any]             # the raw record as produced
    timestamp: datetime                # when the record was produced
    status: RecordStatus = RecordStatus.QUARANTINED
    detail: str = ""
    corrected_record: dict[str, Any] | None = None

    @property
    def key(self) -> str:
        return f"{self.record_id}|{self.consumer_id}"


# --- Quarantine Store ---------------------------------------------------------

class QuarantineStore:
    """
    Thread-safe(ish) store for quarantined records.
    Supports scoped queries by schema version window.
    """

    def __init__(self) -> None:
        self._entries: dict[str, QuarantineEntry] = {}   # key -> entry
        self._released: list[QuarantineEntry] = []

    def add(self, entry: QuarantineEntry) -> None:
        self._entries[entry.key] = entry

    def get(self, record_id: str, consumer_id: str) -> QuarantineEntry | None:
        key = f"{record_id}|{consumer_id}"
        return self._entries.get(key)

    def all_entries(self) -> list[QuarantineEntry]:
        return list(self._entries.values())

    def quarantined_entries(self) -> list[QuarantineEntry]:
        return [e for e in self._entries.values()
                if e.status == RecordStatus.QUARANTINED]

    def released_entries(self) -> list[QuarantineEntry]:
        return list(self._released)

    def entries_in_window(
        self,
        producer_schema_version: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[QuarantineEntry]:
        """
        Return quarantined entries that match a specific bad-schema window:
          - produced under `producer_schema_version`
          - within optional [start, end] timestamp bounds
        Only returns entries still in QUARANTINED status.
        """
        results = []
        for entry in self._entries.values():
            if entry.status != RecordStatus.QUARANTINED:
                continue
            if entry.producer_schema_version != producer_schema_version:
                continue
            if start and entry.timestamp < start:
                continue
            if end and entry.timestamp > end:
                continue
            results.append(entry)
        return results

    def release(self, entry: QuarantineEntry, corrected_record: dict[str, Any]) -> None:
        entry.status = RecordStatus.RELEASED
        entry.corrected_record = corrected_record
        self._released.append(entry)

    def mark_manual_review(self, entry: QuarantineEntry) -> None:
        entry.status = RecordStatus.MANUAL_REVIEW

    def stats(self) -> dict[str, int]:
        statuses = {}
        for entry in self._entries.values():
            name = entry.status.name
            statuses[name] = statuses.get(name, 0) + 1
        return statuses


# --- Correction Job ----------------------------------------------------------

@dataclass
class CorrectionResult:
    """Summary of one correction job run."""
    window_schema_version: str
    total_scanned: int = 0
    released: int = 0
    still_quarantined: int = 0
    details: list[str] = field(default_factory=list)


class CorrectionJob:
    """
    Scoped correction: re-check quarantined records from a specific
    bad-schema window now that a transform may have been registered.

    Only touches records from the exact producer_schema_version window.
    """

    def __init__(
        self,
        registry: SchemaRegistry,
        engine: CompatibilityEngine,
        store: QuarantineStore,
    ) -> None:
        self.registry = registry
        self.engine = engine
        self.store = store

    def run(
        self,
        producer_schema_version: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> CorrectionResult:
        """
        Run correction over the specified bad-schema window.

        For each quarantined record:
          1. Re-run the full compatibility check (structural + semantic)
          2. If both pass now (e.g. a transform was registered), release it
          3. If still fails, leave quarantined for manual review
        """
        result = CorrectionResult(window_schema_version=producer_schema_version)
        candidates = self.store.entries_in_window(
            producer_schema_version=producer_schema_version,
            start=start,
            end=end,
        )
        result.total_scanned = len(candidates)

        for entry in candidates:
            # Re-check this specific record against the specific consumer
            consumer = self.registry.get_consumer(entry.consumer_id)

            # Re-run full compatibility via engine
            check_results = self.engine.check_record(
                record=entry.record,
                producer_schema_key=entry.producer_schema_version,
            )

            # Find the result for this specific consumer
            consumer_result = None
            for cr in check_results:
                if cr.consumer_id == entry.consumer_id:
                    consumer_result = cr
                    break

            if consumer_result is None:
                # Consumer no longer active  --  mark for manual review
                self.store.mark_manual_review(entry)
                result.still_quarantined += 1
                result.details.append(
                    f"  {entry.record_id}/{entry.consumer_id}: "
                    f"consumer no longer active -> manual review"
                )
                continue

            if consumer_result.passed:
                # Transform now exists and both layers pass -> release
                corrected = consumer_result.transformed_record or entry.record
                self.store.release(entry, corrected)
                result.released += 1
                result.details.append(
                    f"  {entry.record_id}/{entry.consumer_id}: "
                    f"RELEASED (transform applied successfully)"
                )
            else:
                # Still incompatible  --  leave quarantined
                result.still_quarantined += 1
                reason = "structural" if consumer_result.verdict == Verdict.STRUCTURAL_BREAK else "semantic"
                result.details.append(
                    f"  {entry.record_id}/{entry.consumer_id}: "
                    f"still {reason} incompatible -> remains quarantined"
                )

        return result
