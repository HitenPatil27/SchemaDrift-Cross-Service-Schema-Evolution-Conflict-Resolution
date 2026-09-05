"""
SchemaDrift  --  Demo Script

Runs the exact scripted scenario:
  1. Baseline:              v1 -> both consumers, all safe
  2. Safe evolution:        v2 adds optional `currency` -> no impact
  3. Obvious break:         v3 removes required `user_id` -> structural fail
  4. Silent reinterpretation: v4 changes amount from cents->dollars -> semantic fail
  5. Correction:            register transform, re-run quarantined window -> release

Each step prints a detailed pass/fail table showing exactly what happened.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

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
    RecordStatus,
)


# --- Pretty Printing ---------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def banner(title: str) -> None:
    line = "=" * 70
    print(f"\n{BOLD}{CYAN}{line}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{line}{RESET}")

def step_header(num: int, title: str) -> None:
    print(f"\n{BOLD}{'-' * 60}{RESET}")
    print(f"{BOLD}  STEP {num}: {title}{RESET}")
    print(f"{BOLD}{'-' * 60}{RESET}")

def verdict_str(v: Verdict) -> str:
    if v == Verdict.SAFE_EVOLUTION:
        return f"{GREEN}[PASS] SAFE EVOLUTION{RESET}"
    elif v == Verdict.STRUCTURAL_BREAK:
        return f"{RED}[FAIL] STRUCTURAL BREAK{RESET}"
    elif v == Verdict.SEMANTIC_INCOMPATIBLE:
        return f"{YELLOW}[WARN] SEMANTIC INCOMPATIBLE{RESET}"
    return str(v)

def print_results_table(results, record: dict) -> None:
    print(f"\n  {DIM}Record: {record}{RESET}\n")
    print(f"  {'Consumer':<22} {'Verdict':<40} {'Issues'}")
    print(f"  {'-' * 22} {'-' * 40} {'-' * 40}")
    for r in results:
        issues = []
        for i in r.structural_issues:
            issues.append(f"[STRUCT] {i.detail}")
        for i in r.semantic_issues:
            issues.append(f"[SEMAN] {i.detail}")
        issue_str = "; ".join(issues) if issues else f"{GREEN}none{RESET}"
        print(f"  {r.consumer_id:<22} {verdict_str(r.verdict):<55} {issue_str}")
    print()


def print_quarantine_summary(store: QuarantineStore) -> None:
    entries = store.all_entries()
    if not entries:
        print(f"  {DIM}Quarantine: empty{RESET}")
        return
    print(f"\n  {'Record':<14} {'Consumer':<22} {'Reason':<24} {'Status':<14} {'Schema'}")
    print(f"  {'-' * 14} {'-' * 22} {'-' * 24} {'-' * 14} {'-' * 20}")
    for e in entries:
        status_color = GREEN if e.status == RecordStatus.RELEASED else (
            YELLOW if e.status == RecordStatus.MANUAL_REVIEW else RED
        )
        print(
            f"  {e.record_id:<14} {e.consumer_id:<22} "
            f"{e.reason.name:<24} "
            f"{status_color}{e.status.name:<14}{RESET} "
            f"{e.producer_schema_version}"
        )
    print()


# --- Assertion helpers --------------------------------------------------------

assertion_count = 0
assertion_pass = 0
assertion_fail = 0

def assert_check(condition: bool, label: str) -> None:
    global assertion_count, assertion_pass, assertion_fail
    assertion_count += 1
    if condition:
        assertion_pass += 1
        print(f"  {GREEN}[PASS]{RESET} {label}")
    else:
        assertion_fail += 1
        print(f"  {RED}[FAIL]{RESET} {label}")


# --- Semantic descriptors ----------------------------------------------------

SEM_CENTS = SemanticDescriptor(unit="cents", encoding="integer")
SEM_DOLLARS = SemanticDescriptor(unit="dollars", encoding="float")


# --- Schema Definitions ------------------------------------------------------

def make_v1() -> SchemaVersion:
    """Baseline: user_id (str), amount (int/cents), timestamp (str)."""
    return SchemaVersion(
        service="payment",
        version="v1",
        fields={
            "user_id": FieldDef(name="user_id", type=str, required=True),
            "amount": FieldDef(
                name="amount", type=int, required=True,
                semantic=SEM_CENTS,
            ),
            "timestamp": FieldDef(name="timestamp", type=str, required=True),
        },
    )


def make_v2() -> SchemaVersion:
    """Safe evolution: adds optional `currency` field with default."""
    return SchemaVersion(
        service="payment",
        version="v2",
        fields={
            "user_id": FieldDef(name="user_id", type=str, required=True),
            "amount": FieldDef(
                name="amount", type=int, required=True,
                semantic=SEM_CENTS,
            ),
            "timestamp": FieldDef(name="timestamp", type=str, required=True),
            "currency": FieldDef(
                name="currency", type=str, required=False, default="USD",
            ),
        },
        structurally_compatible_with=["v1"],
    )


def make_v3() -> SchemaVersion:
    """Obvious break: removes required `user_id`."""
    return SchemaVersion(
        service="payment",
        version="v3",
        fields={
            "amount": FieldDef(
                name="amount", type=int, required=True,
                semantic=SEM_CENTS,
            ),
            "timestamp": FieldDef(name="timestamp", type=str, required=True),
        },
        structurally_compatible_with=[],  # explicitly NOT compatible with v1
    )


def make_v4() -> SchemaVersion:
    """Silent reinterpretation: `amount` changes from cents (int) to dollars (float)."""
    return SchemaVersion(
        service="payment",
        version="v4",
        fields={
            "user_id": FieldDef(name="user_id", type=str, required=True),
            "amount": FieldDef(
                name="amount", type=float, required=True,
                semantic=SEM_DOLLARS,  # <-- different semantic!
            ),
            "timestamp": FieldDef(name="timestamp", type=str, required=True),
        },
        structurally_compatible_with=["v1"],  # structurally OK (int->float widens)
    )


# --- Demo ---------------------------------------------------------------------

def main() -> None:
    global assertion_count, assertion_pass, assertion_fail

    banner("SchemaDrift -- Cross-Service Schema Evolution Demo")

    # -- Setup --------------------------------------------------------------
    registry = SchemaRegistry()
    engine = CompatibilityEngine(registry)
    store = QuarantineStore()

    # Register baseline schema
    registry.register_schema(make_v1())

    # Register two consumers, both expecting v1
    registry.register_consumer(Consumer(
        consumer_id="billing-service",
        expected_schema_version="payment:v1",
        active=True,
    ))
    registry.register_consumer(Consumer(
        consumer_id="analytics-service",
        expected_schema_version="payment:v1",
        active=True,
    ))

    now = datetime.now()

    # -- STEP 1: Baseline --------------------------------------------------
    step_header(1, "Baseline -- v1 schema, both consumers active")

    record_1 = {
        "user_id": "user_42",
        "amount": 1500,       # 1500 cents = $15.00
        "timestamp": "2024-01-15T10:30:00Z",
    }

    results = engine.check_record(record_1, "payment:v1")
    print_results_table(results, record_1)

    assert_check(
        all(r.verdict == Verdict.SAFE_EVOLUTION for r in results),
        "All consumers receive v1 records safely",
    )
    assert_check(
        len(store.quarantined_entries()) == 0,
        "No records quarantined",
    )

    # -- STEP 2: Safe Evolution --------------------------------------------
    step_header(2, "Safe Evolution -- v2 adds optional `currency` field")

    registry.register_schema(make_v2())

    record_2 = {
        "user_id": "user_42",
        "amount": 2500,
        "timestamp": "2024-01-15T11:00:00Z",
        "currency": "EUR",    # new optional field
    }

    results = engine.check_record(record_2, "payment:v2")
    print_results_table(results, record_2)

    assert_check(
        all(r.verdict == Verdict.SAFE_EVOLUTION for r in results),
        "Both consumers unaffected by optional field addition",
    )
    assert_check(
        len(store.quarantined_entries()) == 0,
        "No records quarantined",
    )

    # -- STEP 3: Obvious Break ---------------------------------------------
    step_header(3, "Obvious Break -- v3 removes required `user_id`")

    registry.register_schema(make_v3())

    record_3 = {
        "amount": 3000,
        "timestamp": "2024-01-15T12:00:00Z",
        # user_id is GONE
    }

    results = engine.check_record(record_3, "payment:v3")
    print_results_table(results, record_3)

    # Quarantine the blocked records
    for r in results:
        if r.verdict == Verdict.STRUCTURAL_BREAK:
            store.add(QuarantineEntry(
                record_id="rec_003",
                consumer_id=r.consumer_id,
                reason=QuarantineReason.STRUCTURAL_BREAK,
                producer_schema_version="payment:v3",
                consumer_schema_version="payment:v1",
                record=record_3,
                timestamp=now + timedelta(minutes=3),
                detail="; ".join(i.detail for i in r.structural_issues),
            ))

    assert_check(
        all(r.verdict == Verdict.STRUCTURAL_BREAK for r in results),
        "Structural check fails immediately for both consumers",
    )
    assert_check(
        len(store.quarantined_entries()) == 2,
        "Both consumer deliveries quarantined",
    )

    print_quarantine_summary(store)

    # -- STEP 4: Silent Reinterpretation -----------------------------------
    step_header(4, "Silent Reinterpretation -- v4 changes amount from cents->dollars")

    registry.register_schema(make_v4())

    # Rolling deployment: register an UPGRADED consumer that already
    # expects v4 (dollars). This coexists with old consumers (v1/cents)
    # during the rolling update window.
    registry.register_consumer(Consumer(
        consumer_id="upgraded-billing",
        expected_schema_version="payment:v4",
        active=True,
    ))

    record_4 = {
        "user_id": "user_42",
        "amount": 15.00,       # $15.00 as dollars (float)
        "timestamp": "2024-01-15T13:00:00Z",
    }

    results = engine.check_record(record_4, "payment:v4")
    print_results_table(results, record_4)

    # Show what the wrong value would look like
    print(f"  {YELLOW}[!] What the consumer would see if delivered unchecked:{RESET}")
    print(f"    amount = {record_4['amount']}  (consumer interprets as {record_4['amount']} CENTS)")
    print(f"    Actual intended value: ${record_4['amount']:.2f} (DOLLARS)")
    print(f"    Consumer would charge: ${record_4['amount'] / 100:.2f} instead of ${record_4['amount']:.2f}")
    print(f"    {RED}=> 100x undercharge! This is the 'silent reinterpretation' bug.{RESET}\n")

    # Quarantine the semantically incompatible records
    v4_window_start = now + timedelta(minutes=4)
    for r in results:
        if r.verdict == Verdict.SEMANTIC_INCOMPATIBLE:
            store.add(QuarantineEntry(
                record_id="rec_004",
                consumer_id=r.consumer_id,
                reason=QuarantineReason.SEMANTIC_INCOMPATIBLE,
                producer_schema_version="payment:v4",
                consumer_schema_version="payment:v1",
                record=record_4,
                timestamp=v4_window_start,
                detail="; ".join(i.detail for i in r.semantic_issues),
            ))

    structural_results = [r for r in results if r.verdict == Verdict.STRUCTURAL_BREAK]
    semantic_results = [r for r in results if r.verdict == Verdict.SEMANTIC_INCOMPATIBLE]
    safe_results = [r for r in results if r.verdict == Verdict.SAFE_EVOLUTION]

    assert_check(
        len(structural_results) == 0,
        "Structural check PASSES (same field names, float accepts int->float)",
    )
    assert_check(
        len(semantic_results) == 2,
        "Semantic check FAILS for old consumers (cents!=dollars, no transform)",
    )
    assert_check(
        len(safe_results) == 1 and safe_results[0].consumer_id == "upgraded-billing",
        "Rolling deployment: upgraded consumer compatible with v4, old consumers blocked",
    )
    assert_check(
        len(store.quarantined_entries()) == 4,
        "4 total quarantined entries (2 structural + 2 semantic)",
    )

    print_quarantine_summary(store)

    # -- STEP 5: Correction ------------------------------------------------
    step_header(5, "Correction -- register cents<->dollars transform, run correction job")

    # Register the transform
    cents_to_dollars = SemanticTransform(
        field_name="amount",
        from_semantic=SEM_DOLLARS,      # producer sends dollars
        to_semantic=SEM_CENTS,          # consumer expects cents
        transform_fn=lambda v: int(v * 100),   # dollars -> cents
        description="Convert amount from dollars (float) to cents (int)",

    )
    registry.register_transform(cents_to_dollars)
    print(f"  {CYAN}Registered transform: {cents_to_dollars.description}{RESET}")
    print(f"  {DIM}Transform key: {cents_to_dollars.key}{RESET}\n")

    # Run correction job ONLY over the v4 window
    job = CorrectionJob(registry, engine, store)
    correction = job.run(
        producer_schema_version="payment:v4",
        start=v4_window_start - timedelta(seconds=1),
        end=v4_window_start + timedelta(hours=1),
    )

    print(f"  Correction job results for window '{correction.window_schema_version}':")
    print(f"    Scanned:          {correction.total_scanned}")
    print(f"    Released:         {GREEN}{correction.released}{RESET}")
    print(f"    Still quarantined: {correction.still_quarantined}")
    for d in correction.details:
        print(f"    {d}")
    print()

    assert_check(
        correction.released == 2,
        "Both semantic-quarantined records released after transform",
    )

    # Verify the corrected record values
    released = store.released_entries()
    for entry in released:
        if entry.corrected_record:
            print(f"  {GREEN}Released record for {entry.consumer_id}:{RESET}")
            print(f"    Original:  amount = {entry.record['amount']} (dollars, float)")
            print(f"    Corrected: amount = {entry.corrected_record['amount']} (cents, int)")
            assert_check(
                entry.corrected_record["amount"] == 1500,
                f"Corrected amount is 1500 cents for {entry.consumer_id}",
            )

    # Verify v3 structural breaks were NOT touched by the correction job
    v3_entries = store.entries_in_window("payment:v3")
    # entries_in_window returns QUARANTINED only, so if they're still there, good
    # But let's also check via all_entries
    v3_all = [e for e in store.all_entries()
              if e.producer_schema_version == "payment:v3"]
    assert_check(
        all(e.status == RecordStatus.QUARANTINED for e in v3_all),
        "v3 structural-break records were NOT touched by correction (still quarantined)",
    )
    assert_check(
        len(v3_all) == 2,
        "Both v3 entries remain in quarantine",
    )

    print_quarantine_summary(store)

    # -- STEP 6: AI-Powered Analysis ----------------------------------------
    step_header(6, "AI-Powered Analysis (Groq/Llama)")

    ai_available = True
    try:
        from ai_advisor import (
            ai_semantic_analysis,
            ai_suggest_transform,
            ai_generate_impact_report,
        )
    except ImportError:
        print(f"  {YELLOW}groq package not installed. Skipping AI features.{RESET}")
        print(f"  {DIM}Run: pip install groq{RESET}\n")
        ai_available = False

    if ai_available:
        # --- 6a: AI Semantic Analysis ---
        print(f"\n  {BOLD}{CYAN}[6a] AI Semantic Compatibility Analysis{RESET}")
        print(f"  {DIM}Asking AI: Are 'amount (dollars/float)' and 'amount (cents/integer)' compatible?{RESET}\n")

        try:
            sem_result = ai_semantic_analysis(
                field_name="amount",
                producer_type="float",
                producer_semantic={"unit": "dollars", "encoding": "float"},
                consumer_type="int",
                consumer_semantic={"unit": "cents", "encoding": "integer"},
            )
            print(f"  AI Verdict:    {'INCOMPATIBLE' if not sem_result.get('compatible') else 'COMPATIBLE'}")
            print(f"  Confidence:    {sem_result.get('confidence', 'N/A')}")
            print(f"  Reasoning:     {sem_result.get('reasoning', 'N/A')}")
            if sem_result.get('suggested_unit'):
                print(f"  Suggested Unit: {sem_result['suggested_unit']}")
            print()

            assert_check(
                sem_result.get("compatible") == False,
                "AI correctly identifies cents vs dollars as incompatible",
            )
        except Exception as e:
            print(f"  {RED}AI Semantic Analysis error: {e}{RESET}\n")

        # --- 6b: AI Transform Suggestion ---
        print(f"  {BOLD}{CYAN}[6b] AI Transform Suggestion{RESET}")
        print(f"  {DIM}Asking AI: How to convert dollars (float) -> cents (integer)?{RESET}\n")

        try:
            tf_result = ai_suggest_transform(
                field_name="amount",
                from_unit="dollars",
                from_encoding="float",
                to_unit="cents",
                to_encoding="integer",
                sample_value=15.00,
            )
            print(f"  Description:   {tf_result.get('transform_description', 'N/A')}")
            print(f"  Formula:       {tf_result.get('transform_formula', 'N/A')}")
            print(f"  Example:       {tf_result.get('example_input')} -> {tf_result.get('example_output')}")
            print(f"  Confidence:    {tf_result.get('confidence', 'N/A')}")
            print()

            assert_check(
                tf_result.get("confidence") in ("high", "medium"),
                "AI provides a confident transform suggestion",
            )
        except Exception as e:
            print(f"  {RED}AI Transform Suggestion error: {e}{RESET}\n")

        # --- 6c: AI Impact Report ---
        print(f"  {BOLD}{CYAN}[6c] AI Incident Impact Report{RESET}")
        print(f"  {DIM}Generating full incident report from demo events...{RESET}\n")

        demo_events = [
            {
                "step": 1,
                "action": "baseline",
                "schema_version": "v1",
                "result": "safe",
                "details": "All records delivered to billing-service and analytics-service"
            },
            {
                "step": 2,
                "action": "safe_evolution",
                "schema_version": "v2",
                "result": "safe",
                "details": "Added optional currency field, no consumer impact"
            },
            {
                "step": 3,
                "action": "obvious_break",
                "schema_version": "v3",
                "result": "blocked",
                "details": "Removed required user_id field, structural check failed, 2 records quarantined"
            },
            {
                "step": 4,
                "action": "silent_reinterpretation",
                "schema_version": "v4",
                "result": "blocked",
                "details": "Amount changed from cents (int 1500) to dollars (float 15.00). "
                          "Structural check PASSED but semantic check CAUGHT the mismatch. "
                          "Without detection, consumers would interpret $15.00 as 15 cents "
                          "(100x undercharge). 2 records quarantined."
            },
            {
                "step": 5,
                "action": "correction",
                "schema_version": "v4",
                "result": "released",
                "details": "Registered dollars->cents transform (multiply by 100). "
                          "Correction job re-processed only v4 window. "
                          "2 records released with corrected values (15.00 -> 1500). "
                          "v3 structural-break records untouched."
            },
        ]

        try:
            report = ai_generate_impact_report(demo_events)
            print(f"  {'-' * 56}")
            for line in report.split("\n"):
                print(f"  {line}")
            print(f"  {'-' * 56}")
            print()

            assert_check(
                len(report) > 100,
                "AI generated a substantive incident report",
            )
        except Exception as e:
            print(f"  {RED}AI Impact Report error: {e}{RESET}\n")

        # --- 6d: Universal Semantic Drift Matrix ---
        print(f"  {BOLD}{CYAN}[6d] Universal Semantic Drift Matrix (Diverse Mismatch Categories){RESET}")
        print(f"  {DIM}Validating system flexibility across Unit/Scale, Temporal Encoding, and Categorical Enums:{RESET}\n")

        mismatch_cases = [
            {
                "category": "Scale / Unit Multiplier",
                "service": "perf",
                "field": "latency",
                "producer_semantic": SemanticDescriptor("milliseconds", "integer"),
                "consumer_semantic": SemanticDescriptor("microseconds", "integer"),
                "field_type": int,
                "raw_val": 1500,
                "expected_val": 1500000,
                "transform_fn": lambda v: v * 1000,
                "desc": "Convert latency ms -> us (x1000)",
            },
            {
                "category": "Temporal / Time Unit",
                "service": "telemetry",
                "field": "timestamp",
                "producer_semantic": SemanticDescriptor("epoch_seconds", "integer"),
                "consumer_semantic": SemanticDescriptor("epoch_milliseconds", "integer"),
                "field_type": int,
                "raw_val": 1705316400,
                "expected_val": 1705316400000,
                "transform_fn": lambda v: v * 1000,
                "desc": "Convert timestamp epoch_sec -> epoch_ms (x1000)",
            },
            {
                "category": "Categorical / Enum Mapping",
                "service": "orders",
                "field": "status",
                "producer_semantic": SemanticDescriptor("status_v2", "string"),
                "consumer_semantic": SemanticDescriptor("status_v1", "string"),
                "field_type": str,
                "raw_val": "COMPLETED",
                "expected_val": "SUCCESS",
                "transform_fn": lambda s: {"COMPLETED": "SUCCESS", "FAILED": "ERROR"}.get(s, s),
                "desc": "Map modern status 'COMPLETED' -> legacy 'SUCCESS'",
            },
        ]

        print(f"  {'Category':<28} {'Field':<12} {'Raw Value':<16} {'Target Value':<18} {'AI Auto-Formula'}")
        print(f"  {'-' * 28} {'-' * 12} {'-' * 16} {'-' * 18} {'-' * 26}")

        for case in mismatch_cases:
            svc = case["service"]
            f = case["field"]
            v1_schema = SchemaVersion(svc, "v1", {f: FieldDef(f, case["field_type"], True, case["consumer_semantic"])})
            v2_schema = SchemaVersion(svc, "v2", {f: FieldDef(f, case["field_type"], True, case["producer_semantic"])})
            registry.register_schema(v1_schema)
            registry.register_schema(v2_schema)
            registry.register_consumer(Consumer(f"{svc}-consumer", f"{svc}:v1"))

            # 1. Structural passes, semantic fails
            res_before = engine.check_record({f: case["raw_val"]}, f"{svc}:v2")
            assert_check(
                res_before[0].verdict == Verdict.SEMANTIC_INCOMPATIBLE,
                f"[{case['category']}] Caught semantic break before transform",
            )

            # 2. Query AI for transform suggestion
            ai_hint = ai_suggest_transform(
                field_name=f,
                from_unit=case["producer_semantic"].unit,
                from_encoding=case["producer_semantic"].encoding,
                to_unit=case["consumer_semantic"].unit,
                to_encoding=case["consumer_semantic"].encoding,
                sample_value=case["raw_val"],
            )
            formula_str = ai_hint.get("transform_formula", "custom")

            # 3. Register transform and verify resolution
            t = SemanticTransform(
                field_name=f,
                from_semantic=case["producer_semantic"],
                to_semantic=case["consumer_semantic"],
                transform_fn=case["transform_fn"],
                description=case["desc"],
            )
            registry.register_transform(t)

            res_after = engine.check_record({f: case["raw_val"]}, f"{svc}:v2")
            assert_check(
                res_after[0].verdict == Verdict.SAFE_EVOLUTION
                and res_after[0].transformed_record[f] == case["expected_val"],
                f"[{case['category']}] Resolved: {case['raw_val']} -> {case['expected_val']}",
            )

            print(f"  {case['category']:<28} {f:<12} {str(case['raw_val']):<16} {str(case['expected_val']):<18} {formula_str}")

        print()

        # --- 6e: Zero-Touch Autonomous Self-Healing Pipeline ---
        print(f"  {BOLD}{CYAN}[6e] Zero-Touch Self-Healing Pipeline (Autonomous Universal Mediator){RESET}")
        print(f"  {DIM}Testing unmapped schema drift with zero pre-registered transforms (auto_heal=True):{RESET}\n")

        heal_registry = SchemaRegistry()
        heal_engine = CompatibilityEngine(heal_registry, auto_heal=True)

        s_celsius = SemanticDescriptor("celsius", "float")
        s_fahrenheit = SemanticDescriptor("fahrenheit", "float")

        heal_registry.register_schema(SchemaVersion("telemetry", "v1", {
            "temperature": FieldDef("temperature", float, True, s_celsius),
        }))
        heal_registry.register_schema(SchemaVersion("telemetry", "v2", {
            "temperature": FieldDef("temperature", float, True, s_fahrenheit),
        }))
        heal_registry.register_consumer(Consumer("climate-service", "telemetry:v1"))

        # Verify initial state has zero transforms
        assert_check(
            len(heal_registry.list_transforms()) == 0,
            "Initial state: zero transforms registered for stream",
        )

        # Record 1: 77.0 Fahrenheit (auto-heals to 25.0 Celsius)
        rec_heal_1 = {"temperature": 77.0}
        print(f"  {YELLOW}Incoming Record 1:{RESET} temperature = 77.0°F (producer: fahrenheit)")
        res_heal_1 = heal_engine.check_record(rec_heal_1, "telemetry:v2")

        assert_check(
            res_heal_1[0].verdict == Verdict.SAFE_EVOLUTION
            and res_heal_1[0].transformed_record is not None
            and abs(res_heal_1[0].transformed_record.get("temperature", 0) - 25.0) < 0.1,
            "Record 1 auto-healed dynamically: 77.0°F -> 25.0°C",
        )

        # Verify transform was compiled and cached in registry
        auto_transforms = heal_registry.list_transforms()
        assert_check(
            len(auto_transforms) == 1,
            "Engine compiled & registered JIT adapter into SchemaRegistry",
        )
        if auto_transforms:
            print(f"  {GREEN}[JIT Cached]{RESET} {auto_transforms[0].description}")

        # Record 2: 68.0 Fahrenheit (uses cached transform in 0.0001ms)
        rec_heal_2 = {"temperature": 68.0}
        res_heal_2 = heal_engine.check_record(rec_heal_2, "telemetry:v2")
        assert_check(
            res_heal_2[0].verdict == Verdict.SAFE_EVOLUTION
            and res_heal_2[0].transformed_record is not None
            and abs(res_heal_2[0].transformed_record.get("temperature", 0) - 20.0) < 0.1,
            "Record 2 converted via compiled JIT adapter: 68.0°F -> 20.0°C",
        )
        print()

    # -- Summary -----------------------------------------------------------
    banner("Final Summary")
    stats = store.stats()
    print(f"  Quarantine store: {stats}\n")
    print(f"  {BOLD}Assertions: {assertion_pass}/{assertion_count} passed", end="")
    if assertion_fail > 0:
        print(f", {RED}{assertion_fail} FAILED{RESET}")
    else:
        print(f" -- {GREEN}ALL PASSED{RESET}")
    print()

    if assertion_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

