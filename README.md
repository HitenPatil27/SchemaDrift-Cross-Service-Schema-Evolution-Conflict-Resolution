# SchemaDrift — Cross-Service Semantic Drift Detection & Autonomous AI Self-Healing

[![Tests](https://img.shields.io/badge/Tests-30%2F30%20Passing-brightgreen?style=flat-square)](file:///c:/Users/Dell/Desktop/Final/demo.py)
[![Poisoning Rate](https://img.shields.io/badge/Silent%20Poisoning%20Rate-0.00%25-blue?style=flat-square)](file:///c:/Users/Dell/Desktop/Final/benchmark.py)
[![Throughput](https://img.shields.io/badge/Throughput-53k--88k%20rec%2Fsec-success?style=flat-square)](file:///c:/Users/Dell/Desktop/Final/benchmark.py)
[![Latency](https://img.shields.io/badge/Median%20p50%20Latency-16.8%20%C2%B5s-purple?style=flat-square)](file:///c:/Users/Dell/Desktop/Final/benchmark.py)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](file:///c:/Users/Dell/Desktop/Final/)
[![AI Engine](https://img.shields.io/badge/AI%20Synthesizer-Groq%20Cloud-orange?style=flat-square)](file:///c:/Users/Dell/Desktop/Final/ai_advisor.py)

> **SchemaDrift** is an enterprise-grade distributed mediator and autonomous drift-mitigation platform for event-driven microservices. It eliminates the most dangerous failure mode in modern cloud architectures: **silent semantic drift** during rolling deployments. When services remain syntactically valid on the wire while interpreting payload fields with conflicting business meanings, SchemaDrift intercepts the divergence, prevents corrupted data from reaching downstream consumers, and synthesizes autonomous JIT self-healing adapters via Groq Cloud AI in real time.

---

## 📑 Table of Contents
1. [Live Control Center Web Dashboard](#-live-control-center-web-dashboard)
2. [The Problem: Silent Semantic Reinterpretation](#-the-problem-silent-semantic-reinterpretation)
3. [Two-Layer Architecture](#️-two-layer-architecture)
4. [Universal Live FX Oracle & Currency Engine](#-universal-live-fx-oracle--currency-modernization-engine)
5. [Autonomous Zero-Touch AI Self-Healing](#-autonomous-zero-touch-ai-self-healing)
6. [Quarantine Store & Scoped Remediation](#-quarantine-store--scoped-remediation)
7. [Algorithmic Complexity & Benchmark Suite](#-algorithmic-complexity--benchmark-suite)
8. [Stream Datasets in `data/`](#-stream-datasets-in-data)
9. [Quickstart & Verification Guide](#-quickstart--verification-guide)
10. [Repository File Structure](#️-repository-architecture--key-modules)
11. [Hackathon Submission Details](#-hackathon-submission-details)

---

## 🚀 Live Control Center Web Dashboard

SchemaDrift ships with a production-grade, dark glassmorphic control center accessible locally at **`http://localhost:8000`**.

```bash
# Launch the Control Center Dashboard & Ingestion Server
python server.py
```

### Key Dashboard Capabilities
- **4-Stage Live Audit Stream Table**:
  1. **Initial Input (Producer Sent)**: Raw syntax-highlighted JSON payload as emitted on the wire.
  2. **Semantic Layer (Dual-Sided Contract)**: Side-by-side comparative card showing **Producer (Sender)** `{kind, value, type}` vs. **Consumer (Receiver)** `{kind, value, type}`, badged with `⚡ DRIFT` or `✔ EQUAL`.
  3. **How AI Changed That (JIT Adapter Synthesis)**: Real-time autonomous AI resolution formula, FX conversion metadata, or quarantine isolation action.
  4. **Final Result Delivered to Consumer**: Guaranteed contract-compliant payload delivered downstream to consumer services.
- **Drag & Drop Batch Ingestor**: Upload custom `.json` event streams with instantaneous validation and live rendering.
- **1-Click Preloaded Datasets**: One-click staging for all test streams (`Mix: All Mismatches (30)`, `Payments (25)`, `IoT Telemetry (20)`, `E-Commerce (15)`).
- **Metric Ribbons & Filters**: Real-time counters for Total Stream, Wire-Compatible, Autonomous AI Healed, and Blocked/Quarantined records.
- **AI SRE Incident Post-Mortem Generator**: Generates comprehensive stakeholder incident post-mortems on-demand via Groq Cloud LLM, complete with executive summaries, timeline, root-cause analysis, and preventative action items.

---

## 🧠 The Problem: Silent Semantic Reinterpretation

In microservice architectures, rolling deployments create inevitable windows where older and newer consumer services coexist. Traditional schema validators (Avro, JSON Schema, Protobuf) evaluate only syntax: *Are fields present? Are primitive types compatible?*

They completely miss **semantic divergence**:
- **Currency Scale Bug**: A billing producer updates `amount` from integer cents (`1500`) to float dollars (`15.00`). Because `int` widening to `float` is syntactically legal, traditional tools pass it without warning. Downstream accounting consumers charge customers **$0.15 instead of $15.00 (100x financial loss)**.
- **Multi-Currency Cross-Rate Bug**: A European customer pays €15.00 EUR. A downstream US billing service expecting USD cents charges `1500` ($15.00) without applying exchange rates, ignoring currency denomination and causing continuous ledger reconciliation errors.
- **Telemetry Scale Bug**: An HVAC sensor sends `77.0°F` to an industrial cooling consumer expecting Celsius. The numerical value is valid, but applying 77°C causes **severe physical overheating and equipment failure**.
- **Enum Category Drift**: A modernized order service emits `COMPLETED` or `FAILED`, but a legacy downstream inventory service only understands `SUCCESS` or `ERROR`.
- **Temporal & Scale Drift**: Producer emits epoch seconds (`1705316400`) instead of epoch milliseconds (`1705316400000`), miscalculating downstream timestamps by decades.

---

## 🛡️ Two-Layer Architecture

SchemaDrift enforces an uncompromising separation of concerns between **Structural Invariants** and **Semantic Contracts**:

<p align="center">
  <img src="System Architecture1.png" alt="SchemaDrift System Architecture Diagram" width="100%" />
</p>

```
Producer Event Stream (JSON / Kafka / REST)
                   │
                   ▼
     ┌───────────────────────────┐
     │  LAYER 1: STRUCTURAL      │ ──► [FAIL: Missing '<name>_id']
     │  - Entity Identity Guard  │     Blocked & Quarantined in Isolation Store
     │  - Required Field Check   │     (Zero unrouted or orphaned records)
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
                   ├────────────────────────────┐
                   ▼                            ▼
     ┌───────────────────────────┐   ┌───────────────────────────┐
     │  AUTONOMOUS JIT ADAPTER   │   │  UNIVERSAL FX ORACLE      │
     │  - Groq / Qwen Synthesis  │   │  - 15+ World Currencies   │
     │  - Sub-microsecond Cache  │   │  - Timestamp-Anchored     │
     │  - Zero-Touch Auto-Heal   │   │  - Volatility Circuit Brk │
     └─────────────┬─────────────┘   └─────────────┬─────────────┘
                   │                               │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                   Delivered to Consumer (Contract-Safe)
```

### Layer 1: Structural Guard (`engine.py`)
- **Universal Domain Identity Rule**: Every valid record **must** provide a domain entity key matching `"<name>_id"` (e.g. `user_id`, `device_id`, `customer_id`, `order_id`, `record_id`, `event_id`). A plain, unscoped `"id"` is strictly rejected to prevent orphaned records and immediately triggers quarantine.
- **Field Completeness**: Guarantees all consumer-required fields are physically present.
- **Safe Numeric Widening**: Permissively allows `int` to widen to `float` so structural checks do not emit false alarms.

### Layer 2: Semantic Contract Evaluator (`engine.py` & `schema_registry.py`)
- Each schema field carries an explicit `SemanticDescriptor`:
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
- If identical: Verdict is **`SAFE_EVOLUTION`** (direct zero-overhead delivery).
- If divergent: Looks up or synthesizes a verified adapter to transform the record in-memory.

---

## 💱 Universal Live FX Oracle & Currency Modernization Engine (`fx_oracle.py`)

To eliminate cross-currency and multi-denomination financial errors, SchemaDrift integrates an institutional-grade **Dynamic FX Oracle**:

### 1. Multi-Currency Support Across 15+ Global Currencies
Converts between major world currencies including **USD, EUR, GBP, JPY, CAD, INR, AUD, CHF, CNY, BRL, SGD, HKD, NZD, MXN, and SEK**.

### 2. Point-in-Time Timestamp Anchoring
Transaction exchange rates must reflect the **exact historical moment** when the transaction occurred, not the current spot rate hours or days later. The FX Oracle automatically extracts ISO 8601 timestamps from transaction payloads and anchors conversion to historical rates for that exact date, preventing temporal arbitrage.

### 3. Volatility Circuit Breaker
Protects against corrupted market feeds or extreme price spikes. If an exchange rate deviates by more than **15%** from its trailing moving reference, the circuit breaker triggers:
- In strict mode: raises `FXCircuitBreakerError` and quarantines the transaction.
- In warning mode: logs an audit alert and proceeds with banking-grade decimal calculations.

### 4. Banking-Grade Decimal Precision
Avoids binary IEEE-754 floating-point compounding errors (`0.1 + 0.2 = 0.30000000000000004`). All calculations utilize Python's `decimal.Decimal` with **`ROUND_HALF_EVEN`** (Banker's rounding) to ensure exact sub-cent precision.

### 5. Dual-Tier High-Availability Provider
- **Tier 1 (Live Feed)**: Queries real-time and historical European Central Bank (ECB / Frankfurter) rates over HTTPS.
- **Tier 2 (Offline Resilience Matrix)**: If external connectivity is unavailable or air-gapped, the engine falls back seamlessly to an embedded high-fidelity exchange rate matrix.

```bash
# Run standalone FX Oracle test & demonstration
python fx_oracle.py
```

---

## ⚡ Autonomous Zero-Touch AI Self-Healing (`ai_advisor.py`)

When an unmapped schema drift is encountered in a live stream (e.g., HVAC sensor emitting Fahrenheit `77.0°F` when downstream expects Celsius), SchemaDrift triggers the **Groq Cloud AI Advisor**:

1. **Dynamic Synthesis**: Synthesizes the exact mathematical or dictionary transform (`(value - 32.0) * 5.0 / 9.0`).
2. **JIT Compilation**: Compiles the lambda dynamically and registers it directly into `SchemaRegistry`.
3. **Sub-Microsecond Memory Cache**: Record 1 is healed dynamically; all subsequent records execute in **`0.0001ms`** directly from memory.

---

## 🔒 Quarantine Store & Scoped Remediation (`quarantine.py`)

SchemaDrift guarantees that corrupted or unroutable records never poison downstream consumers:
- **Isolation Store**: Quarantined records are isolated with rich forensic metadata: `record_id`, `consumer_id`, `reason` (`STRUCTURAL_BREAK` vs `SEMANTIC_INCOMPATIBLE`), schema versions, and timestamps.
- **Targeted Bounded Remediation**:
  - When an adapter is registered, a scoped correction job re-processes *only* records from the affected schema window (e.g. `payment:v4`).
  - Completely isolates unrelated records (records missing required domain IDs remain safely quarantined).
  - Validated **0.0% False Positive Release Rate**.

---

## 📊 Algorithmic Complexity & Benchmark Suite (`benchmark.py`)

SchemaDrift includes an automated benchmarking suite evaluating computational complexity, latency percentiles, and reliability KPIs across 25,000 synthetic invocations.

```bash
# Run the automated benchmark suite
python benchmark.py
```

### Algorithmic Complexity (Big-O Notation)

| Component / Operation | Time Complexity | Space Complexity | Description |
| :--- | :---: | :---: | :--- |
| **Schema Registry Lookup** | **`O(1)`** | `O(S)` | Direct hash-map indexing by schema key |
| **Layer 1: Structural Gate** | **`O(F)`** | `O(1)` | Inspects required keys and identity invariants (F = field count) |
| **Layer 2: Semantic Gate** | **`O(F)`** | `O(1)` | Evaluates dual-sided semantic descriptors |
| **Transform Execution** | **`O(1)`** | `O(1)` | Sub-microsecond arithmetic or hash-map mapping |
| **Autonomous JIT Cache** | **`O(1)`** | `O(T)` | Cached in-memory lambda lookup |
| **Quarantine Store Insertion** | **`O(1)`** | `O(Q)` | Fast append & dictionary index |
| **Bounded Correction Job** | **`O(W)`** | `O(W)` | Scoped replay over target window (W = records in window) |

### Latency Percentiles (End-to-End per Record)

| Metric | Measured Value | Production Significance |
| :--- | :---: | :--- |
| **Median Latency (p50)** | **`16.80 µs`** (0.0016 ms) | Ultra-low overhead; indistinguishable from direct pass-through |
| **95th Percentile (p95)** | **`26.40 µs`** | Consistent performance under sustained load |
| **99th Percentile (p99)** | **`66.00 µs`** | Predictable tail latency |
| **Mean Latency** | **`18.06 µs`** | Minimal variance across mixed payload types |
| **Peak Throughput** | **`53,000 – 88,000 rec/sec`** | High-throughput stream processing on a single thread |

### Critical Safety & Reliability KPIs

| KPI Metric | Result | Target Benchmark | Status |
| :--- | :---: | :---: | :---: |
| **Silent Data Poisoning Rate** | **`0.00%`** | `0.00%` | 🟢 **Zero Poisoning** |
| **Semantic Drift Interception Rate** | **`100.00%`** | `100.00%` | 🟢 **Flawless Detection** |
| **Structural Break Isolation Rate** | **`100.00%`** | `100.00%` | 🟢 **100% Isolated** |
| **Automated Test Suite Pass Rate** | **`30 / 30`** | `100.00%` | 🟢 **100% Pass** |
| **False Positive Quarantine Release** | **`0.00%`** | `0.00%` | 🟢 **Zero False Releases** |

---

## 📂 Stream Datasets in `data/`

All test datasets carry standardized field-level semantic schema metadata:

| File | Records | Injected Scenarios & Drift Categories |
| :--- | :---: | :--- |
| [`data/all_mismatches_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/all_mismatches_stream.json) | **30** | **Unified Showcase**: Multi-currency conversion (EUR, GBP, JPY, CAD, INR), currency scale ($ vs ¢), HVAC telemetry (°F vs °C), Order enums (`COMPLETED` vs `SUCCESS`), Latency (ms vs µs), Timestamp (sec vs ms), and 5 unroutable structural break records (missing `<name>_id`). |
| [`data/payment_transactions_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/payment_transactions_stream.json) | **25** | Currency scale drift (float dollars vs integer cents), plain `"id"` structural rejections, safe evolutions. |
| [`data/iot_telemetry_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/iot_telemetry_stream.json) | **20** | Industrial sensor telemetry, Fahrenheit to Celsius unit drift, missing sensor IDs. |
| [`data/ecommerce_orders_stream.json`](file:///c:/Users/Dell/Desktop/Final/data/ecommerce_orders_stream.json) | **15** | Order fulfillment pipeline, modern `v2` enum mapping to legacy `v1` consumer contracts. |

---

## 🧪 Quickstart & Verification Guide

### 1. Prerequisites
- Python 3.10 or higher
- Optional: Groq API Key (set in `.env` as `GROQ_API_KEY=...`) for live online AI synthesis. If not provided, the system automatically uses resilient built-in offline heuristics.

```bash
# Clone the repository
git clone https://github.com/HitenPatil27/SchemaDrift-Cross-Service-Schema-Evolution-Conflict-Resolution.git
cd SchemaDrift-Cross-Service-Schema-Evolution-Conflict-Resolution

# Install dependencies (only groq + python-dotenv required; core engine uses Python standard library)
pip install groq python-dotenv
```

### 2. Run Comprehensive Automated Test Suite (30/30 Passing)
```bash
python demo.py
```
Validates:
- Baseline v1 multi-consumer pass-through
- Safe evolution v2 backward compatibility
- Structural break v3 domain identity isolation
- Silent semantic drift v4 cents vs dollars interception
- Targeted bounded remediation with zero false releases
- Groq AI integration, universal drift matrix, and SRE incident post-mortem generation
- Point-in-time timestamp-anchored FX Oracle and circuit breaker activation

### 3. Run Complexity & Latency Benchmark Suite
```bash
python benchmark.py
```

### 4. Run FX Oracle CLI Runner
```bash
python fx_oracle.py
```

### 5. Launch the Web Application Dashboard
```bash
python server.py
# Server runs locally at: http://localhost:8000
```
Open `http://localhost:8000` in any web browser to explore the interactive dashboard.

### 6. Process Event Streams via REST API
```bash
curl -X POST http://localhost:8000/api/process-batch \
     -H "Content-Type: application/json" \
     --data @data/all_mismatches_stream.json
```

---

## 🏗️ Repository Architecture & Key Modules

```
├── ARCHITECTURE.md                  # Comprehensive system architecture & diagrams
├── README.md                        # Project documentation, quickstart & benchmarks
├── EXPLANATION.md                   # In-depth architectural rationale & design decisions
├── PRD.md                           # Hackathon challenge problem statement specification
├── System Architecture1.png         # High-resolution architectural diagram
│
├── schema_registry.py               # Versioned schemas, consumer registry, transform catalog
├── engine.py                        # Two-layer validation engine with JIT auto-healing
├── ai_advisor.py                    # Groq Cloud AI semantic analyzer & adapter synthesizer
├── fx_oracle.py                     # Universal Live FX Oracle (15+ currencies, timestamp-anchored)
├── quarantine.py                    # Quarantine isolation store & bounded correction jobs
├── demo.py                          # 6-step scripted scenario (30 automated assertions)
├── benchmark.py                     # Complexity, latency (p50/p95/p99) & reliability suite
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
    ├── styles.css                   # Modern dark UI design system & responsive cards
    └── app.js                       # Stream ingestion, filter tabs, and live SRE modal
```

---

## 👥 Hackathon Submission Details

- **Challenge Track**: *17. SchemaDrift — Cross-Service Schema Evolution Conflict Resolution*
- **Primary Innovations**:
  1. Strict Two-Layer Structural vs Semantic separation of concerns.
  2. Autonomous Zero-Touch AI Self-Healing with cached JIT compile (`0.0001ms`).
  3. Dynamic FX Oracle with timestamp-anchored point-in-time currency conversion and volatility circuit breakers.
  4. Scoped Bounded Remediation ensuring zero false-positive releases.
  5. Sub-20 microsecond median latency with 0.00% silent data poisoning rate.
- **Runtime Environment**: Python standard library runtime + Groq SDK; zero bulky dependencies; cross-platform compatibility.
