"""
SchemaDrift  --  Schema Registry

Versioned schema definitions with structural and semantic metadata,
compatibility contracts, consumer registry, and transformation registry.

The key design decision: every field carries BOTH structural info (name, type,
required) AND semantic info (unit, encoding). These are checked independently
by the engine  --  a record can be structurally valid but semantically wrong.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# --- Field Definitions -------------------------------------------------------

@dataclass(frozen=True)
class SemanticDescriptor:
    """Machine-readable meaning of a field's value."""
    unit: str          # e.g. "cents", "dollars", "epoch_seconds"
    encoding: str      # e.g. "integer", "float", "iso8601"

    def matches(self, other: "SemanticDescriptor") -> bool:
        return self.unit == other.unit and self.encoding == other.encoding


@dataclass(frozen=True)
class FieldDef:
    """Single field in a schema version."""
    name: str
    type: type                          # Python type: int, float, str, …
    required: bool = True
    semantic: Optional[SemanticDescriptor] = None
    default: Any = None                 # used when field is optional


# --- Schema Version ----------------------------------------------------------

@dataclass
class SchemaVersion:
    """
    One immutable version of a service's schema.

    `structurally_compatible_with` lists prior version tags this version
    is wire-compatible with (required fields are a subset, types match).
    This is declared at registration time and verified by the engine.
    """
    service: str
    version: str
    fields: dict[str, FieldDef]                         # name -> FieldDef
    structurally_compatible_with: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.service}:{self.version}"

    def required_fields(self) -> dict[str, FieldDef]:
        return {n: f for n, f in self.fields.items() if f.required}

    def optional_fields(self) -> dict[str, FieldDef]:
        return {n: f for n, f in self.fields.items() if not f.required}


# --- Semantic Transformation -------------------------------------------------

@dataclass
class SemanticTransform:
    """
    A registered transformation between two semantic representations
    of the same logical field.

    Example: amount_cents (int) <-> amount_dollars (float)
    """
    field_name: str
    from_semantic: SemanticDescriptor
    to_semantic: SemanticDescriptor
    transform_fn: Callable[[Any], Any]     # from_value -> to_value
    description: str = ""

    @property
    def key(self) -> str:
        return (
            f"{self.field_name}:"
            f"{self.from_semantic.unit}({self.from_semantic.encoding})"
            f"->{self.to_semantic.unit}({self.to_semantic.encoding})"
        )


# --- Consumer Registration ---------------------------------------------------

@dataclass
class Consumer:
    """A downstream service that expects records matching a specific schema version."""
    consumer_id: str
    expected_schema_version: str   # e.g. "payment:v1"
    active: bool = True


# --- Registry ----------------------------------------------------------------

class SchemaRegistry:
    """
    Central registry holding:
      1. Schema versions per service
      2. Consumers and which version each expects
      3. Semantic transformations between field representations
    """

    def __init__(self) -> None:
        self._schemas: dict[str, SchemaVersion] = {}       # key -> SchemaVersion
        self._consumers: dict[str, Consumer] = {}           # consumer_id -> Consumer
        self._transforms: dict[str, SemanticTransform] = {} # transform key -> Transform

    # -- Schema management -------------------------------------------------

    def register_schema(self, schema: SchemaVersion) -> None:
        if schema.key in self._schemas:
            raise ValueError(f"Schema {schema.key} already registered")
        self._schemas[schema.key] = schema

    def get_schema(self, key: str) -> SchemaVersion:
        if key not in self._schemas:
            raise KeyError(f"Schema {key} not found")
        return self._schemas[key]

    def list_schemas(self, service: str | None = None) -> list[SchemaVersion]:
        schemas = list(self._schemas.values())
        if service:
            schemas = [s for s in schemas if s.service == service]
        return schemas

    # -- Consumer management -----------------------------------------------

    def register_consumer(self, consumer: Consumer) -> None:
        self._consumers[consumer.consumer_id] = consumer

    def get_consumer(self, consumer_id: str) -> Consumer:
        return self._consumers[consumer_id]

    def active_consumers(self) -> list[Consumer]:
        return [c for c in self._consumers.values() if c.active]

    # -- Transform management ---------------------------------------------

    def register_transform(self, transform: SemanticTransform) -> None:
        self._transforms[transform.key] = transform

    def find_transform(
        self,
        field_name: str,
        from_semantic: SemanticDescriptor,
        to_semantic: SemanticDescriptor,
    ) -> SemanticTransform | None:
        """Look up a registered transform between two semantic descriptors."""
        search_key = (
            f"{field_name}:"
            f"{from_semantic.unit}({from_semantic.encoding})"
            f"->{to_semantic.unit}({to_semantic.encoding})"
        )
        return self._transforms.get(search_key)

    def list_transforms(self) -> list[SemanticTransform]:
        return list(self._transforms.values())

    # -- Convenience -------------------------------------------------------

    def apply_transform(
        self,
        transform: SemanticTransform,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a new record with the transform applied to the relevant field."""
        result = copy.deepcopy(record)
        if transform.field_name in result:
            val = result[transform.field_name]
            try:
                # Try contextual transform (value, full_record) e.g. for timestamped FX
                result[transform.field_name] = transform.transform_fn(val, result)
            except TypeError:
                # Standard single-argument transform (value)
                result[transform.field_name] = transform.transform_fn(val)
        return result
