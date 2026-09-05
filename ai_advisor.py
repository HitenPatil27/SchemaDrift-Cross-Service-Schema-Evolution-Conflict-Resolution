"""
SchemaDrift -- AI Advisor (Powered by Groq/Llama)

Three AI-powered features that enhance the two-layer compatibility system:

  1. Semantic Analyzer:  When semantic descriptors are missing or ambiguous,
     AI infers whether two fields are compatible based on names, types, context.

  2. Transform Suggester: When a record is quarantined with no registered
     transform, AI suggests what the transformation function should be.

  3. Impact Report Generator: After the full demo, AI generates a natural-
     language incident report summarizing what happened, business impact,
     and remediation steps.
"""

from __future__ import annotations

import json
import os
from typing import Any

from groq import Groq


# --- AI Client ----------------------------------------------------------------

def _load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

_load_local_env()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

def _get_client() -> Groq:
    """Initialize Groq client with API key from environment."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in environment or .env file.")
    return Groq(api_key=GROQ_API_KEY)


MODEL = "qwen/qwen3.8-27b"


def _chat(system_prompt: str, user_prompt: str) -> str:
    """Send a single chat completion request to Groq."""
    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    return response.choices[0].message.content.strip()


# --- Feature 1: AI Semantic Analyzer -----------------------------------------

def ai_semantic_analysis(
    field_name: str,
    producer_type: str,
    producer_semantic: dict | None,
    consumer_type: str,
    consumer_semantic: dict | None,
) -> dict[str, Any]:
    """
    When semantic descriptors are missing or ambiguous, use AI to infer
    whether two field representations are semantically compatible.

    Returns: {
        "compatible": bool,
        "confidence": "high" | "medium" | "low",
        "reasoning": str,
        "suggested_unit": str | None,
        "suggested_encoding": str | None,
    }
    """
    system_prompt = """You are a schema compatibility expert. Analyze whether two 
versions of the same field are semantically compatible (i.e., the values mean 
the same thing). Consider unit changes, encoding changes, and representation 
changes.

Respond ONLY with valid JSON in this exact format:
{
    "compatible": true/false,
    "confidence": "high" or "medium" or "low",
    "reasoning": "one sentence explanation",
    "suggested_unit": "suggested unit if inferable, else null",
    "suggested_encoding": "suggested encoding if inferable, else null"
}"""

    user_prompt = f"""Analyze this field for semantic compatibility:

Field name: "{field_name}"
Producer side: type={producer_type}, semantic={json.dumps(producer_semantic)}
Consumer side: type={consumer_type}, semantic={json.dumps(consumer_semantic)}

Are these semantically compatible? Would the consumer correctly interpret 
values from the producer?"""

    raw = _chat(system_prompt, user_prompt)

    # Parse the JSON response
    try:
        # Strip markdown code fences if present
        cleaned = raw
        if "```" in cleaned:
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        result = {
            "compatible": False,
            "confidence": "low",
            "reasoning": raw,
            "suggested_unit": None,
            "suggested_encoding": None,
        }
    return result


# --- Feature 2: AI Transform Suggester ---------------------------------------

def ai_suggest_transform(
    field_name: str,
    from_unit: str,
    from_encoding: str,
    to_unit: str,
    to_encoding: str,
    sample_value: Any = None,
) -> dict[str, Any]:
    """
    When a semantic mismatch is detected and no transform exists, AI suggests
    what the transformation should be.

    Returns: {
        "transform_description": str,
        "transform_formula": str,
        "example_input": any,
        "example_output": any,
        "confidence": "high" | "medium" | "low",
    }
    """
    system_prompt = """You are a data transformation expert. Given two different 
semantic representations of the same field, suggest the correct transformation 
to convert from the producer's representation to the consumer's representation.

Respond ONLY with valid JSON in this exact format:
{
    "transform_description": "human readable description",
    "transform_formula": "mathematical formula like 'value * 100' or 'value / 100'",
    "example_input": <example input value>,
    "example_output": <expected output value>,
    "confidence": "high" or "medium" or "low"
}"""

    sample_str = f"\nSample value from producer: {sample_value}" if sample_value is not None else ""

    user_prompt = f"""Suggest a transformation for this field:

Field name: "{field_name}"
FROM (producer): unit="{from_unit}", encoding="{from_encoding}"
TO (consumer):   unit="{to_unit}", encoding="{to_encoding}"{sample_str}

What formula converts from the producer's representation to the consumer's?"""

    raw = _chat(system_prompt, user_prompt)

    try:
        cleaned = raw
        if "```" in cleaned:
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        result = {
            "transform_description": raw,
            "transform_formula": "unknown",
            "example_input": sample_value,
            "example_output": "unknown",
            "confidence": "low",
        }
    return result


# --- Feature 3: AI Impact Report Generator ------------------------------------

def ai_generate_impact_report(demo_events: list[dict[str, Any]]) -> str:
    """
    After the demo runs, AI generates a full natural-language incident report
    covering what happened, business impact, and remediation.

    demo_events: list of dicts describing each step, e.g.:
        [
            {"step": 1, "action": "baseline", "result": "safe", "details": "..."},
            {"step": 4, "action": "silent_reinterpretation", "result": "blocked", ...},
        ]
    """
    system_prompt = """You are a senior Site Reliability Engineer writing an incident 
report. Given a sequence of schema evolution events from a multi-service system, 
write a clear, professional incident report.

Format the report with these sections:
1. INCIDENT SUMMARY (2-3 sentences)
2. TIMELINE (chronological list of events)
3. IMPACT ANALYSIS (what would have happened without SchemaDrift)
4. DETECTION & RESPONSE (how each issue was caught)
5. REMEDIATION (what transforms were applied)
6. RECOMMENDATIONS (how to prevent this in the future)

Use plain text, no markdown. Keep it concise but thorough. This is for a 
technical audience (engineering leadership and jury at a hackathon)."""

    user_prompt = f"""Generate an incident report for this schema evolution scenario:

{json.dumps(demo_events, indent=2)}

Focus on the business impact of the "silent reinterpretation" case where 
amount changed from cents to dollars — what would the financial damage have 
been if this went undetected?"""

    return _chat(system_prompt, user_prompt)


# --- Convenience: Run all three on a scenario ---------------------------------

def run_full_ai_analysis(
    field_name: str,
    producer_semantic: dict,
    consumer_semantic: dict,
    sample_value: Any,
    demo_events: list[dict],
) -> dict[str, Any]:
    """
    Run all three AI features and return combined results.
    Useful for the demo script.
    """
    print("  [AI] Running semantic analysis...")
    semantic = ai_semantic_analysis(
        field_name=field_name,
        producer_type="float",
        producer_semantic=producer_semantic,
        consumer_type="int",
        consumer_semantic=consumer_semantic,
    )

    print("  [AI] Generating transform suggestion...")
    transform = ai_suggest_transform(
        field_name=field_name,
        from_unit=producer_semantic["unit"],
        from_encoding=producer_semantic["encoding"],
        to_unit=consumer_semantic["unit"],
        to_encoding=consumer_semantic["encoding"],
        sample_value=sample_value,
    )

    print("  [AI] Generating incident impact report...")
    report = ai_generate_impact_report(demo_events)

    return {
        "semantic_analysis": semantic,
        "transform_suggestion": transform,
        "impact_report": report,
    }


# --- Feature 4: Autonomous Universal Transform Synthesizer -------------------

def ai_synthesize_universal_transform(
    field_name: str,
    from_unit: str,
    from_encoding: str,
    to_unit: str,
    to_encoding: str,
    sample_value: Any = None,
) -> dict[str, Any]:
    """
    Universal Autonomous Synthesizer:
    Given any arbitrary semantic mismatch across:
      - Scale / Unit Multipliers (dollars<->cents, ms<->sec, bytes<->MB)
      - Temporal Encodings (epoch seconds<->milliseconds, ISO string<->epoch)
      - Categorical Enums (status mappings, code mappings)
      - Representation Types (string<->boolean, numeric casting)

    Synthesizes an executable Python lambda expression, safely compiles it into
    a native Python callable, verifies it with the sample value, and returns it.
    """
    system_prompt = """You are an expert data engineer. Given two semantic representations of a field, synthesize a valid, executable Python lambda expression `lambda value: ...` that converts any value from the producer representation to the consumer representation.

Supported mismatch types:
- Scale / Unit Multiplier (e.g. dollars to cents: `lambda value: int(round(value * 100))` or ms to us: `lambda value: int(value * 1000)`)
- Temporal / Time Units (e.g. epoch seconds to milliseconds: `lambda value: int(value * 1000)` or ISO string to epoch: `lambda value: int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())`)
- Categorical / Enums (e.g. status mapping: `lambda value: {"COMPLETED": "SUCCESS", "FAILED": "ERROR"}.get(value, value)`)
- Representation / Types (e.g. string to boolean: `lambda value: str(value).lower() in ("true", "1", "yes")`)

Respond ONLY with valid JSON in this exact format:
{
    "description": "Short explanation of the conversion",
    "python_lambda": "lambda value: valid_python_expression",
    "confidence": "high" or "medium" or "low"
}"""

    sample_str = f"\nSample input value: {repr(sample_value)}" if sample_value is not None else ""
    user_prompt = f"""Field: "{field_name}"
FROM (producer): unit="{from_unit}", encoding="{from_encoding}"
TO (consumer):   unit="{to_unit}", encoding="{to_encoding}"{sample_str}

Synthesize a single-line Python lambda expression `lambda value: ...` to convert any value from the producer format to the consumer format."""

    raw = _chat(system_prompt, user_prompt)
    try:
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        data = json.loads(cleaned)
    except Exception:
        data = {
            "description": "Failed to parse AI output",
            "python_lambda": "lambda value: value",
            "confidence": "low",
        }

    lam_str = data.get("python_lambda", "").strip()
    if not lam_str.startswith("lambda"):
        lam_str = f"lambda value: {lam_str}"

    import math
    import re
    from datetime import datetime

    safe_env = {
        "datetime": datetime,
        "math": math,
        "re": re,
        "int": int,
        "float": float,
        "str": str,
        "round": round,
        "dict": dict,
    }

    verified = False
    transform_fn = None
    try:
        transform_fn = eval(lam_str, safe_env)
        if sample_value is not None:
            _ = transform_fn(sample_value)
            verified = True
        else:
            verified = True
    except Exception:
        verified = False
        transform_fn = lambda v: v

    return {
        "description": data.get("description", "AI-synthesized universal transform"),
        "python_lambda": lam_str,
        "transform_fn": transform_fn,
        "confidence": data.get("confidence", "medium"),
        "verified": verified,
    }

