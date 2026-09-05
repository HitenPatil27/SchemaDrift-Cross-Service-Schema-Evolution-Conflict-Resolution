"""
SchemaDrift  --  Compatibility Engine

Two independent compatibility layers, checked sequentially:

  1. STRUCTURAL: Are all required fields present? Do types match?
     -> Fails fast on obvious breaks (removed/renamed required fields).

  2. SEMANTIC (only if structural passes): Does each field's declared
     meaning (unit, encoding) match what the consumer expects, or is
     there a registered transformation bridging the gap?
     -> Catches silent reinterpretation  --  same field name, plausible
       type, but the VALUE means something different.

These two checks are NEVER collapsed. A record can pass structural
and fail semantic  --  that's the whole point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from schema_registry import (
    Consumer,
    SchemaRegistry,
    SchemaVersion,
    SemanticDescriptor,
)


# --- Check Result Types ------------------------------------------------------

class Verdict(Enum):
    SAFE_EVOLUTION = auto()            # both layers pass
    STRUCTURAL_BREAK = auto()          # obvious break  --  blocked immediately
    SEMANTIC_INCOMPATIBLE = auto()     # silent reinterpretation  --  quarantined


@dataclass
class FieldIssue:
    field_name: str
    issue_type: str     # "missing_required", "type_mismatch", "semantic_mismatch"
    detail: str


@dataclass
class CompatibilityResult:
    consumer_id: str
    verdict: Verdict
    structural_issues: list[FieldIssue] = field(default_factory=list)
    semantic_issues: list[FieldIssue] = field(default_factory=list)
    transformed_record: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.SAFE_EVOLUTION


# --- Engine -------------------------------------------------------------------

class CompatibilityEngine:
    """
    For each outgoing record, check against every ACTIVE consumer:
      a) structural fails  -> block, log as "obvious break"
      b) structural passes, semantic fails -> block, quarantine as
         "silent reinterpretation"
      c) both pass -> deliver ("safe evolution")
    """

    def __init__(self, registry: SchemaRegistry, auto_heal: bool = False) -> None:
        self.registry = registry
        self.auto_heal = auto_heal

    # -- Public entry point ------------------------------------------------

    def check_record(
        self,
        record: dict[str, Any],
        producer_schema_key: str,
    ) -> list[CompatibilityResult]:
        """
        Check one record against all active consumers.
        Returns one CompatibilityResult per active consumer.
        """
        producer_schema = self.registry.get_schema(producer_schema_key)
        results: list[CompatibilityResult] = []

        for consumer in self.registry.active_consumers():
            consumer_schema = self.registry.get_schema(
                consumer.expected_schema_version
            )
            if consumer_schema.service != producer_schema.service:
                continue
            result = self._check_for_consumer(
                record, producer_schema, consumer
            )
            results.append(result)

        return results

    # -- Per-consumer check ------------------------------------------------

    def _check_for_consumer(
        self,
        record: dict[str, Any],
        producer_schema: SchemaVersion,
        consumer: Consumer,
    ) -> CompatibilityResult:
        consumer_schema = self.registry.get_schema(
            consumer.expected_schema_version
        )

        # LAYER 1  --  Structural check
        structural_issues = self._structural_check(
            record, producer_schema, consumer_schema
        )
        if structural_issues:
            return CompatibilityResult(
                consumer_id=consumer.consumer_id,
                verdict=Verdict.STRUCTURAL_BREAK,
                structural_issues=structural_issues,
            )

        # LAYER 2  --  Semantic check (only if structural passed)
        semantic_issues, transformed = self._semantic_check(
            record, producer_schema, consumer_schema
        )
        if semantic_issues:
            return CompatibilityResult(
                consumer_id=consumer.consumer_id,
                verdict=Verdict.SEMANTIC_INCOMPATIBLE,
                semantic_issues=semantic_issues,
            )

        return CompatibilityResult(
            consumer_id=consumer.consumer_id,
            verdict=Verdict.SAFE_EVOLUTION,
            transformed_record=transformed,
        )

    # -- Layer 1: Structural -----------------------------------------------

    def _structural_check(
        self,
        record: dict[str, Any],
        producer_schema: SchemaVersion,
        consumer_schema: SchemaVersion,
    ) -> list[FieldIssue]:
        """
        Verify that all fields the consumer requires are present in the
        record and that types are compatible.
        """
        issues: list[FieldIssue] = []
        consumer_required = consumer_schema.required_fields()

        for fname, fdef in consumer_required.items():
            # Check presence
            if fname not in record:
                issues.append(FieldIssue(
                    field_name=fname,
                    issue_type="missing_required",
                    detail=(
                        f"Consumer requires '{fname}' but it is absent "
                        f"from the record"
                    ),
                ))
                continue

            # Check type compatibility
            value = record[fname]
            if not isinstance(value, fdef.type):
                # Numeric types (int, float) are structurally compatible
                # in both directions  --  the SEMANTIC layer is what catches
                # meaning differences (e.g. cents vs dollars).
                numeric_types = (int, float)
                if fdef.type in numeric_types and isinstance(value, numeric_types):
                    continue
                issues.append(FieldIssue(
                    field_name=fname,
                    issue_type="type_mismatch",
                    detail=(
                        f"Consumer expects type {fdef.type.__name__} for "
                        f"'{fname}', got {type(value).__name__}"
                    ),
                ))

        return issues

    # -- Layer 2: Semantic -------------------------------------------------

    def _semantic_check(
        self,
        record: dict[str, Any],
        producer_schema: SchemaVersion,
        consumer_schema: SchemaVersion,
    ) -> tuple[list[FieldIssue], dict[str, Any] | None]:
        """
        For every field that exists in both producer and consumer schemas and
        carries semantic descriptors, verify that semantics match or a
        registered transform bridges the gap.

        Returns (issues, transformed_record_or_None).
        """
        issues: list[FieldIssue] = []
        transformed_record = dict(record)  # shallow copy for transforms

        for fname, consumer_fdef in consumer_schema.fields.items():
            if fname not in producer_schema.fields:
                continue  # field not produced -> not a semantic concern
            if fname not in record:
                continue  # not in this record (optional field)

            producer_fdef = producer_schema.fields[fname]

            # If neither side declares semantics, nothing to check
            if producer_fdef.semantic is None and consumer_fdef.semantic is None:
                continue

            # If only one side declares, flag as ambiguous
            if producer_fdef.semantic is None or consumer_fdef.semantic is None:
                issues.append(FieldIssue(
                    field_name=fname,
                    issue_type="semantic_mismatch",
                    detail=(
                        f"Semantic descriptor present on one side but not "
                        f"the other for '{fname}'"
                    ),
                ))
                continue

            # Both have semantics  --  do they match?
            if producer_fdef.semantic.matches(consumer_fdef.semantic):
                continue  # identical semantics -> safe

            # Semantics differ  --  is there a registered transform?
            transform = self.registry.find_transform(
                field_name=fname,
                from_semantic=producer_fdef.semantic,
                to_semantic=consumer_fdef.semantic,
            )
            if transform is not None:
                # Apply transform -> record is safe after conversion
                transformed_record = self.registry.apply_transform(
                    transform, transformed_record
                )
                continue

            # Autonomous Self-Healing: synthesize and register transform on-the-fly
            if self.auto_heal:
                try:
                    from ai_advisor import ai_synthesize_universal_transform
                    from schema_registry import SemanticTransform

                    synth = ai_synthesize_universal_transform(
                        field_name=fname,
                        from_unit=producer_fdef.semantic.unit,
                        from_encoding=producer_fdef.semantic.encoding,
                        to_unit=consumer_fdef.semantic.unit,
                        to_encoding=consumer_fdef.semantic.encoding,
                        sample_value=record.get(fname),
                    )
                    if synth.get("verified") and synth.get("confidence") in ("high", "medium"):
                        auto_transform = SemanticTransform(
                            field_name=fname,
                            from_semantic=producer_fdef.semantic,
                            to_semantic=consumer_fdef.semantic,
                            transform_fn=synth["transform_fn"],
                            description=f"[AI-Auto-Healed] {synth.get('description', '')}",
                        )
                        self.registry.register_transform(auto_transform)
                        transformed_record = self.registry.apply_transform(
                            auto_transform, transformed_record
                        )
                        continue
                except Exception:
                    pass

            # No transform -> SEMANTIC INCOMPATIBILITY
            issues.append(FieldIssue(
                field_name=fname,
                issue_type="semantic_mismatch",
                detail=(
                    f"'{fname}' producer semantics "
                    f"({producer_fdef.semantic.unit}/{producer_fdef.semantic.encoding}) "
                    f"differ from consumer "
                    f"({consumer_fdef.semantic.unit}/{consumer_fdef.semantic.encoding}) "
                    f"and no transform is registered"
                ),
            ))

        if issues:
            return issues, None
        return [], transformed_record
