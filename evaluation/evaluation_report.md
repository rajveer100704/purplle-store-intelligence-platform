# Pipeline Accuracy Evaluation Report

Compares pipeline outputs to manual ground-truth annotations.

## Verification Summary

| Video File | Metric | Ground Truth | Pipeline | Error % | Status |
|---|---|---|---|---|---|
| CAM 1.mp4 | Entries | 38 | 34 | 10.5% | WARN |
| CAM 1.mp4 | Exits | 36 | 27 | 25.0% | WARN |
| CAM 2.mp4 | Entries | 12 | 41 | 241.7% | WARN |
| CAM 2.mp4 | Exits | 11 | 13 | 18.2% | WARN |
| CAM 3.mp4 | Entries | 18 | 31 | 72.2% | WARN |
| CAM 3.mp4 | Exits | 17 | 27 | 58.8% | WARN |

## Overall Metrics

- **Total Ground Truth Entries**: 68
- **Total Pipeline Entries**: 106
- **Average Entry Count Error**: 55.9%
- **Average Exit Count Error**: 4.7%

