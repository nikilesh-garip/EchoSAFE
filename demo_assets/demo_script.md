# ECHO — Demo Script & Panel Presentation Guide

This guide details how to demonstrate the Echo prototype during panel evaluation.

## Preparation
1. Start the FastAPI backend server:
   ```bash
   cd backend
   python -m uvicorn main:app --reload
   ```
2. Open a browser and navigate to: `http://127.0.0.1:8010`
3. You will see the **ECHO Dashboard** containing a simulated smartphone running the Echo mobile application frame.

---

## Presentation Scenarios

### Scenario 1 — Isolated Gunshot (Acoustic Hazard)
* **Action**:
  1. Navigate to the **Demo** tab.
  2. Under **Method B (WAV Injection)**, click the **1. Gunshot** button.
* **Explanation to Panel**:
  > *"We are injecting a prepared clip directly into the local pipeline. For transient sounds such as gunshots, Echo shows provisional urgent guidance from Pass 1; it does not claim the audio proves an emergency. Nearby results are shown only when the provider responds, and any fallback is labeled."*
* **Expected Outcome**:
  - Screen switches to **Monitor**.
  - Sound: Gunshot detected.
  - Critical Alert overlay triggers.
  - Displays "Possible Gunshot Detected" and "Nearby Police Station".

---

### Scenario 2 — Distress Scream
* **Action**:
  1. Dismiss the previous alert (click "I'm Safe").
  2. In the **Demo** tab, click **2. Distress Scream**.
* **Explanation to Panel**:
  > *"Here we test a distress scream. Pass 1 detects the scream signature. Pass 2 confirms it. The context scorer determines a POSSIBLE_DANGER state and prompts safety guidance on withdrawing to public zones."*
* **Expected Outcome**:
  - Screen switches to **Monitor**.
  - Live Monitor shows scream class with high confidence.
  - Alert overlay displays scream guidance.

---

### Scenario 3 — Glass Breakage
* **Action**:
  1. Dismiss the alert.
  2. Click **3. Glass Break**.
* **Explanation to Panel**:
  > *"Glass breaking represents a suspicious environmental event. The model performs the two-pass verification, and the context scorer rates this as SUSPICIOUS or POSSIBLE_DANGER, indicating potential intrusion or accident."*
* **Expected Outcome**:
  - Logs glass breaking event.
  - Show appropriate safety actions.

---

### Scenario 4 — Normal Environment (Negative Class)
* **Action**:
  1. Click **8. Background**.
* **Explanation to Panel**:
  > *"This represents normal background audio. The YAMNet-based classifier should output 'NORMAL' and keep the monitor idle. This demo result is not a real-world accuracy claim."*
* **Expected Outcome**:
  - Status remains NORMAL.
  - No alert triggers.

---

### Scenario 5 — Movie Action Scene (False-Positive Defense)
* **Action**:
  1. Go to the **Home** tab.
  2. Check **Media Playback Active (Action Movie)**.
  3. Go to the **Demo** tab, and click **1. Gunshot**.
* **Explanation to Panel**:
  > *"An action movie can trigger acoustic gunshot detections. Media playback is a manual context signal in the browser prototype, so it reduces interruption only when no other danger signal conflicts. This is a review state, not proof the sound is safe."*
* **Expected Outcome**:
  - Spectrogram/model detects gunshot.
  - **BUT** Risk Score is reduced below the High Risk threshold (shows SUSPICIOUS or POSSIBLE_DANGER instead of HIGH_RISK alert). No critical emergency sequence initiates.

---

### Scenario 6 — Multi-Event Threat Sequence (Temporal Scorer)
* **Action**:
  1. Ensure **Media Playback** and **Sudden Motion** are off.
  2. Go to **Demo** tab.
  3. Click **1. Gunshot**, dismiss alert immediately, click **2. Distress Scream**, dismiss, then click **7. Shouting**.
* **Explanation to Panel**:
  > *"Echo contains a temporal event buffer. An isolated sound is concerning, but multiple related hazards happening in rapid succession indicate an active danger zone. As we trigger Gunshot, Scream, and Shouting consecutively, the repeated impulse count increases. The context score escalates from 62 to 70 and finally to 85 (HIGH_RISK) even if the individual confidences were moderate."*
* **Expected Outcome**:
  - The final event triggers a severe **HIGH_RISK** warning due to compound temporal scoring.
