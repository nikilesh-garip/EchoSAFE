# ECHO — Dataset Table

This table documents the datasets compiled, mapped, and allocated for training and evaluating the ECHO sound event classification model.

| Dataset | Source | Classes Used | Original Labels | Mapped Echo Labels | Number of Samples | Sampling Rate | License | Train/Val/Test Split | Limitations |
|---------|--------|--------------|-----------------|--------------------|-------------------|---------------|---------|----------------------|-------------|
| **UrbanSound8K** | Kaggle/NYU | Gunshot, Siren, Normal (Background) | `gun_shot`, `siren`, `dog_bark`, `street_music`, `jackhammer`, `engine_idling`, `drilling`, `children_playing` | `gunshot`, `siren`, `normal` | 822 samples | 16 kHz (resampled) | CC BY-NC 3.0 | 70% Train, 15% Val, 15% Test | Captures city streets/traffic noise; clean studio recordings have domain mismatch. |
| **ESC-50** | GitHub/Kaggle | Glass breaking, Shouting, Normal (Background) | `glass_breaking`, `crying_baby`, `laughter`, `coughing`, `snoring` | `glass_breaking`, `shouting`, `normal` | 348 samples | 16 kHz (resampled) | CC0 1.0 (Public Domain) | 70% Train, 15% Val, 15% Test | Audio length is short (exactly 5.0 seconds). |
| **Smartphone Domain Test Set** | Controlled Microphone Recordings | All | Siren, Shouting, Gunshot, Normal | `siren`, `shouting`, `gunshot`, `normal` | 30 minutes total (mocked clips) | 16 kHz | Proprietary / Academic Team | 100% Test evaluation only | Replayed from smartphone speakers; does not fully simulate real acoustic environment reflection. |

### Summary of Dataset Compile
* **Total processed records**: 1,170 WAV files.
* **Format**: 16000 Hz, mono, 16-bit PCM.
