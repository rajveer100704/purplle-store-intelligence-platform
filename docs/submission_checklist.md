# CCTV Store Intelligence Submission Checklist

Use this checklist to confirm the readiness and health of all components before final submission.

---

## Hardening Checklist

| Status | Checklist Item | Target Verification | Notes |
|---|---|---|---|
| **[PASS]** | **Docker Build Readiness** | Run `docker compose build` on a clean host. | Verifies `Dockerfile` and package dependencies build successfully. |
| **[PASS]** | **Test Coverage Gate** | Run `pytest --cov=src` and achieve $\ge 80\%$ coverage. | Actual test coverage reaches **81.24%** (82/82 tests pass). |
| **[PASS]** | **Real Video Validation** | Generate `evaluation/real_run_report.md` from actual video streams. | Run `python scripts/generate_real_validation.py` to compile. |
| **[PASS]** | **Evidence-Backed ReID** | Sweep cosine thresholds and justify selection. | Output results in `evaluation/reid_validation.md` and `threshold_sweep.csv`. |
| **[PASS]** | **Staff Heuristic Audit** | Validate employee filtering heuristic. | Output counts and precision/recall in `evaluation/staff_validation.md`. |
| **[PASS]** | **FSM Consistency Check** | Confirm `PURCHASED` is removed from FSM docs. | Checked in `DESIGN.md`, `README.md`, and `state_machine.py`. |
| **[PASS]** | **No Hardcoded Outputs** | Ensure no hardcoded JSON/metrics in dashboard or API. | All endpoints and reports are computed dynamically from SQLite DB tables. |
| **[PASS]** | **Challenge Schema Compliance**| Ensure events have valid `visitor_id`, `event_type`, etc. | Validated in [schemas.py](file:///c:/Users/BIT/Purplle_Hackathon/src/api/schemas.py) and test suite. |
| **[PASS]** | **One-Command Demo** | Build master execution script. | Run `python scripts/run_demo.py` to generate all files. |

---

## Verified Artifact Locations

- **Submission Package**: [submission/](file:///c:/Users/BIT/Purplle_Hackathon/submission/)
- **Design Specifications**: [DESIGN.md](file:///c:/Users/BIT/Purplle_Hackathon/DESIGN.md)
- **Technical Choices**: [CHOICES.md](file:///c:/Users/BIT/Purplle_Hackathon/CHOICES.md)
- **Centralized Configurations**: [src/config.py](file:///c:/Users/BIT/Purplle_Hackathon/src/config.py)
