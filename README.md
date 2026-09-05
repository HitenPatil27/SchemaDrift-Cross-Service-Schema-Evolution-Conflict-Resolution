# SchemaDrift — Cross-Service Semantic Drift Detection & Autonomous AI Self-Healing

[![Status](https://img.shields.io/badge/Status-Production%20Ready-success)]()
[![Tests](https://img.shields.io/badge/Tests-27%2F27%20Passing-brightgreen)]()
[![AI Engine](https://img.shields.io/badge/AI%20Engine-Groq%20Qwen%203.8%2027B%20%2F%20Llama%203.3-blueviolet)]()
[![UI](https://img.shields.io/badge/UI-Modern%20Dark%20Glassmorphic%20Dashboard-cyan)]()

> **SchemaDrift** is an enterprise-grade distributed mediator that eliminates the most dangerous class of microservice bugs: **silent semantic drift** during rolling deployments. When services remain syntactically healthy on the wire while interpreting the same data with conflicting business meanings, SchemaDrift intercepts the divergence, prevents corrupted data from reaching downstream consumers, and synthesizes autonomous JIT self-healing adapters via Groq AI in real time.

---

## 🚀 Live Control Center Web Dashboard

The system includes a modern dark glassmorphic control center running locally at **`http://localhost:8000`**.

```bash
# Launch the Control Center Dashboard
python server.py
```

### Dashboard Features
- **4-Stage Live Audit Stream Table**:
  1. **Initial Input (Producer Sent)**: Raw syntax-highlighted JSON payload.
  2. **Semantic Layer (Dual-Sided Contract)**: Side-by-side card comparing **Producer (Sender)** `{kind, value, type}` against **Consumer (Receiver)** `{kind, value, type}`, badged with `⚡ DRIFT` or `✔ EQUAL`.
  3. **How AI Changed That (JIT Adapter Synthesis)**: Real-time autonomous AI resolution formula and registry cache installation.
  4. **Final Result Delivered to Consumer**: Guaranteed contract-compliant payload delivered downstream.
- **Drag & Drop Batch Ingestor**: Upload custom `.json` event streams with instantaneous validation.
- **1-Click Preloaded Datasets**: One-click staging for all test streams (`Mix: All Mismatches (30)`, `Payments (25)`, `IoT Telemetry (20)`, `E-Commerce (15)`).
- **Metric Ribbons & Filters**: Real-time counters for Total Stream, Autonomous AI Healed, Wire-Compatible, and Blocked/Quarantined.
- **AI SRE Incident Post-Mortem Generator**: Generates comprehensive stakeholder incident reports on-demand using Groq Cloud LLM.

---

## 🧠 The Problem: Silent Semantic Reinterpretation

In microservice architectures, rolling deployments create windows where old and new consumers coexist. Conventional schema validators (Avro, JSON Schema, Protobuf) check only syntax: *Are fields present? Are primitive types compatible?*

They completely miss **semantic drift**:
- **Currency Bug**: A billing producer upgrades `amount` from integer cents (`1500`) to float dollars (`15.00`). Because `int` widening to `float` is syntactically legal, traditional tools say "looks fine!" — and downstream consumers charge customers **$0.15 instead of $15.00 (100x revenue loss)**.
- **Telemetry Bug**: An HVAC sensor sends `77.0°F` (Fahrenheit) to an industrial cooling consumer expecting Celsius. The numerical value is valid, but applying 77°C causes **severe physical overheating**.
- **Enum Drift**: Modern order service emits `COMPLETED` / `FAILED`, but a legacy accounting service only understands `SUCCESS` / `ERROR`.
- **Temporal & Scale Drift**: Producer emits milliseconds instead of microseconds, or epoch seconds instead of milliseconds.

---

## 🛡️ Two-Layer Architecture

SchemaDrift enforces an uncompromising separation of concerns between **Structural Invariants** and **Semantic Contracts**:

```
Producer Event Stream (JSON / Kafka / REST)
                   │
                   ▼
     ┌───────────────────────────┐
     │  LAYER 1: STRUCTURAL      │ ──► [FAIL: Missing '<name>_id']
     │  - Entity Identity Guard  │     Blocked & Quarantined in Isolation Store
     │  - Required Field Check   │
     │  - Type Widening Rules    │
     └─────────────┬─────────────┘
                   │ [PASS]
                   ▼
     ┌───────────────────────────┐
     │  LAYER 2: SEMANTIC        │ ──► [MATCH] ──► Direct Pass-Through (0.0001ms)
     │  - Dual-Sided Compare     │
     │  - Sender vs Receiver     │
     │  - Unit / Scale / Enums   │
     └─────────────┬─────────────┘
                   │ [DRIFT DETECTED]
                   ▼
     ┌───────────────────────────┐
     │  AUTONOMOUS JIT ADAPTER   │ ──► [COMPILE] ──► Schema Registry Memory Cache
     │  - Groq / Qwen Synthesis  │                   │
     │  - Zero-Touch Auto-Heal   │ ◄─────────────────┘
     └─────────────┬─────────────┘
                   │
                   ▼
     Delivered to Consumer (Corrected & Contract-Safe)
```

### Layer 1: Structural Guard (`engine.py`)
- **Universal Domain Identity Rule**: Every valid record **must** supply a domain entity key matching `"<name>_id"` (e.g. `user_id`, `device_id`, `customer_id`, `order_id`, `record_id`, `event_id`). Plain `"id"` is strictly rejected as non-specific, immediately triggering `STRUCTURAL_BREAK` quarantine.
- **Field Completeness**: Guarantees all consumer-required fields are physically present.
- **Safe Numeric Widening**: Permissively allows `int` to widen to `float` so structural checks do not emit false alarms.

### Layer 2: Semantic Contract Evaluator (`engine.py` & `schema_registry.py`)
- Each field carries an explicit `SemanticDescriptor`:
  ```json
  {
    "field": "amount",
    "type": "float",
    "required": true,
    "semantic": {
      "kind": "unit",
      "value": "dollars",
      "type": "float"
    }
  }
  ```
- Compares declared Producer semantics with Consumer expected semantics.
- If identical: Verdict is **`SAFE_EVOLUTION`**.
- If divergent: Fetches or synthesizes an autonomous transformation adapter.

---

## ⚡ Autonomous Zero-Touch AI Self-Healing (`ai_advisor.py`)

When an unmapped drift is encountered (e.g. `77.0°F` to Celsius), the engine triggers the **Groq AI Advisor**:
1. **Dynamic Synthesis**: Synthesizes the exact mathematical or dictionary transform (`(value - 32.0) * 5.0 / 9.0`).
2. **JIT Compilation**: Compiles the lambda and registers it directly into `SchemaRegistry`.
3. **Sub-Microsecond Caching**: Record 1 is healed dynamically; all subsequent records execute in **`0.0001ms`** directly from memory.

---

## 📂 Stream Datasets in `data/`

All test datasets carry the standardized field-level semantic schema metadata:

| File | Records | Injected Scenarios & Drift Categories |
| :--- | :---: | :--- |
| [`data/all_mismatches_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/all_mismatches_stream.json) | **30** | **Unified Showcase**: Currency scale ($ vs ¢), HVAC telemetry (°F vs °C), Order enums (`COMPLETED` vs `SUCCESS`), Latency (ms vs µs), Timestamp (sec vs ms), and 5 unroutable structural break records (missing `<name>_id`). |
| [`data/payment_transactions_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/payment_transactions_stream.json) | **25** | Currency scale drift (float dollars vs integer cents), plain `"id"` structural rejections, safe evolutions. |
| [`data/iot_telemetry_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/iot_telemetry_stream.json) | **20** | Industrial sensor telemetry, Fahrenheit to Celsius unit drift, missing sensor IDs. |
| [`data/ecommerce_orders_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/ecommerce_orders_stream.json) | **15** | Order fulfillment pipeline, modern `v2` enum mapping to legacy `v1` consumer contracts. |

---

## 🧪 Verification & Running Tests

### 1. Automated Test Suite
Run the comprehensive automated test suite with **27/27 assertions passing**:

```bash
python demo.py
```

```
======================================================================
  Final Summary
======================================================================
  Quarantine store: {'QUARANTINED': 2, 'RELEASED': 2}

  Assertions: 27/27 passed -- ALL PASSED
```

The test suite validates:
- **Baseline (v1)**: Multi-consumer pass-through.
- **Safe Evolution (v2)**: Optional field additions with zero consumer disruption.
- **Structural Break (v3)**: Immediate quarantine of missing required domain IDs.
- **Silent Semantic Drift (v4)**: Detection of cents ⇏ dollars without false structural alarms.
- **Targeted Bounded Remediation (v5)**: Scoped correction of only affected records while unrelated traffic remains isolated.
- **Autonomous AI JIT Healing (v6)**: Groq Qwen/Llama integration, universal drift matrix, and SRE post-mortem generation.

### 2. Launching the Web Application
```bash
python server.py
# Server running at: http://localhost:8000
```
Open `http://localhost:8000` in any modern browser to view the interactive control center.

### 3. API Batch Processing Endpoint
You can process custom JSON streams directly via `curl` or HTTP client:

```bash
curl -X POST http://localhost:8000/api/process-batch \
     -H "Content-Type: application/json" \
     --data @data/all_mismatches_stream.json
```

---

## 🏗️ Repository Architecture & Key Modules

```
├── ARCHITECTURE.md                  # Comprehensive system architecture & diagrams
├── README.md                        # Project documentation & user guide
├── EXPLANATION.md                   # In-depth architectural rationale & decisions
├── prd (2).md                       # Problem statement specification
│
├── schema_registry.py               # Versioned schemas, consumer registry, transform catalog
├── engine.py                        # Two-layer validation engine with JIT auto-healing
├── ai_advisor.py                    # Groq Cloud AI semantic analyzer & adapter synthesizer
├── quarantine.py                    # Quarantine isolation store & bounded correction jobs
├── demo.py                          # 6-step scripted scenario (27 automated assertions)
├── server.py                        # HTTP Server & Batch Stream Processor (:8000)
│
├── data/                            # Stream Datasets with Rich Semantic Metadata
│   ├── all_mismatches_stream.json   # 30 records: unified demonstration of all mismatch categories
│   ├── payment_transactions_stream.json # 25 records: currency scale, dollars vs cents
│   ├── iot_telemetry_stream.json    # 20 records: Fahrenheit vs Celsius telemetry
│   └── ecommerce_orders_stream.json # 15 records: modern vs legacy status enums
│
└── web/                             # Control Center Dashboard
    ├── index.html                   # Glassmorphic layout with 4-stage audit table
    ├── styles.css                   # Dark theme, dual-sided semantic cards & micro-animations
    └── app.js                       # Stream ingestion, filter tabs, and live SRE modal
```

---

## 👥 Hackathon Submission Details

- **Challenge Topic**: *17. SchemaDrift — Cross-Service Schema Evolution Conflict Resolution*
- **Primary Innovation**: Two-Layer Structural vs Semantic separation + Zero-Touch Autonomous AI Self-Healing Pipeline.
- **Performance**: Sub-microsecond (`0.0001ms`) execution for cached adapters; zero downtime rolling deployments.
