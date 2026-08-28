# ECHO Model Training & Validation Run Trace

*Trace started at: 2026-07-24 07:27:51 UTC*


## 🏁 PHASE: INITIAL SETUP

### 📋 Task: Ingesting and Cleaning Dataset
Executing prepare_dataset.py to map raw files to the 5 active classes...
* **[SUCCESS]** Successfully mapped and prepared datasets.

## 🏁 PHASE: VALIDATION LOOP ITERATION 1 (LEARNING RATE = 0.001)

### 📋 Task: Model Training (Iteration 1)
Training CRNN model for 15 epochs with LR=0.001...
* **[SUCCESS]** Training completed in 142.9s.

### 📋 Task: Model Evaluation (Iteration 1)
Running evaluate.py on the test split...
* **[EVALUATION_METRICS]** Test Accuracy: 93.18%, Test F1 Score: 0.8677
* **[QUALITY_GATE_FAILED]** Iteration F1 score 0.8677 did not meet target 0.9.

## 🏁 PHASE: VALIDATION LOOP ITERATION 2 (LEARNING RATE = 0.0005)

### 📋 Task: Model Training (Iteration 2)
Training CRNN model for 15 epochs with LR=0.0005...
* **[SUCCESS]** Training completed in 138.4s.

### 📋 Task: Model Evaluation (Iteration 2)
Running evaluate.py on the test split...
* **[EVALUATION_METRICS]** Test Accuracy: 96.59%, Test F1 Score: 0.9358
* **[QUALITY_GATE_PASSED]** Quality gate F1 score >= 0.9 achieved!

---

## 📈 Final Summary Report
* **Duration**: 312.55 seconds
* **Start Time**: 2026-07-24T07:27:51.423791Z
* **End Time**: 2026-07-24T07:33:03.974304Z

### Metrics Details:
```
==================================================
AUTOMATED DEVELOPMENT LOOP METRICS REPORT
==================================================
Iteration 1:
  - Learning Rate   : 0.00100
  - Train Loss      : 0.2061
  - Val Loss        : 0.3219
  - Val Accuracy    : 88.57%
  - Test F1 Score   : 0.8677
  - Test Accuracy   : 93.18%
  - Elapsed Time    : 169.6s
  ----------------------------------------
Iteration 2:
  - Learning Rate   : 0.00050
  - Train Loss      : 0.0711
  - Val Loss        : 0.1937
  - Val Accuracy    : 94.29%
  - Test F1 Score   : 0.9358
  - Test Accuracy   : 96.59%
  - Elapsed Time    : 312.5s
  ----------------------------------------
*** BEST PERFORMANCE MODEL (Iteration 2) ***
  - Test F1 Score   : 0.9358
  - Test Accuracy   : 96.59%
  - Final Val Acc   : 94.29%
  - Final Val Loss  : 0.1937
Total duration: 312.55 seconds
==================================================

```

