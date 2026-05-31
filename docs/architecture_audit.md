# CCTV Store Intelligence Architecture Audit

This document audits the consistency across all data layers, state machines, schemas, and interfaces of the platform.

---

## 1. Visitor FSM vs. Emitted Events

The visitor state machine (`VisitorStateMachine`) coordinates movements and triggers challenge-compliant event outputs.

| FSM State | Trigger Action | Emitted Event Type | Event Meaning |
|---|---|---|---|
| **`OUTSIDE`** | `entry_line_crossed` | `ENTRY` | Customer enters the store. |
| **`ENTERED`** | `zone_enter` | `ZONE_ENTER` | Enters a named brand zone (e.g. `LAKME`). |
| **`IN_ZONE`** | `zone_exit` | `ZONE_EXIT` | Leaves a brand display area. |
| **`IN_ZONE`** | `zone_dwell` | `ZONE_DWELL` | Continuous presence for 30s (repeating). |
| **`ENTERED`** | `billing_enter` | *(None)* | Internal state transition to track queue entry. |
| **`IN_BILLING`**| Queue depth > 0 | `BILLING_QUEUE_JOIN` | Joins checkout queue. |
| **`IN_BILLING`**| exit without purchase | `BILLING_QUEUE_ABANDON`| Customer leaves queue without buying. |
| **`EXITED`** | `entry_line_crossed` | `REENTRY` | Customer returns after a prior exit. |

---

## 2. Database Models vs. API Schemas

Database entities mapped via SQLAlchemy ORM are aligned directly with Pydantic serialization models used by FastAPI:

* **Event Ingestion**: `EventORM` ([models.py](file:///c:/Users/BIT/Purplle_Hackathon/src/db/models.py)) maps directly to `EventSchema` ([schemas.py](file:///c:/Users/BIT/Purplle_Hackathon/src/api/schemas.py)). Idempotency is enforced on `event_id` via SQL merge/upsert operations.
* **POS Transactions**: `POSTransactionORM` maps total invoices, matching timestamps, and visitor links.
* **Metrics Endpoint (`GET /stores/{id}/metrics`)**: Serves footfall, conversion percentages, matched revenue, queue abandonment metrics, and brand-specific conversions derived from `EventORM` and `POSTransactionORM` queries.
* **Funnel Endpoint (`GET /stores/{id}/funnel`)**: Compiles sequential conversion drop-offs across **Entry → Zone Visit → Billing Queue → POS Purchase**.

---

## 3. UI Dashboard Alignment

The Streamlit dashboard (`dashboard/app.py`) mirrors the API data structures:
- **Heatmap Chart**: Renders zone visits and dwell times utilizing brand display zone names (`LAKME`, `FACES_CANADA`) directly.
- **Funnel Chart**: Visualizes the 4-stage funnel returned by the `GET /funnel` endpoint.
- **Anomalies Feed**: Polls `GET /anomalies` to render operational alerts (e.g., dead zones or queue bottlenecks).
