"""YAMNet loading and feature extraction shared by training and inference.

Replaces the CNN-Transformer era's log-mel + Sobel/Laplacian preprocessing in
the removed model/dataset.py. YAMNet does its own internal framing (0.96s
windows, 0.48s hop) directly from a raw 16kHz mono waveform, so there is no
fixed-length padding/truncation step here -- a clip-level embedding is the
mean of however many frames the clip produces.
"""

import numpy as np
import soundfile as sf
import librosa
import tensorflow as tf
import tensorflow_hub as hub

from audio_classes import SAMPLE_RATE, YAMNET_HANDLE, MEDIA_CONTEXT_AUDIOSET_INDICES

_MEDIA_INDICES = list(MEDIA_CONTEXT_AUDIOSET_INDICES.keys())


def load_yamnet():
    """Loads the frozen, pretrained YAMNet model from TF-Hub."""
    return hub.load(YAMNET_HANDLE)


def load_waveform(path_or_bytes, sr=None):
    """Loads audio as mono float32 at SAMPLE_RATE. Accepts a file path or an
    (audio_array, sample_rate) tuple already read by the caller."""
    if isinstance(path_or_bytes, tuple):
        audio, source_sr = path_or_bytes
    else:
        audio, source_sr = sf.read(path_or_bytes, dtype="float32")

    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = audio.astype(np.float32)

    target_sr = sr or SAMPLE_RATE
    if source_sr != target_sr:
        audio = librosa.resample(audio, orig_sr=source_sr, target_sr=target_sr)

    return audio


EMBEDDING_DIM = 2048  # mean-pooled 1024 + max-pooled 1024, see embed_waveform


def embed_waveform(yamnet, waveform):
    """Runs YAMNet on a waveform and returns:
      - clip_embedding: a 2048-d [mean-pooled | max-pooled] embedding across
        frames. Mean-only pooling washes out short, transient hazard sounds
        (a gunshot or glass break is often 1-2 of many 0.96s frames, the
        rest near-silence); concatenating a max-pooled component keeps the
        single most salient frame's signal instead of averaging it away.
      - frame_scores: (num_frames, 521) raw AudioSet class probabilities
    A silent/near-empty waveform can produce zero frames; callers must handle
    that (see media_context_score below and the two-pass detector).
    """
    scores, embeddings, _ = yamnet(waveform)
    scores = scores.numpy()
    embeddings = embeddings.numpy()
    if embeddings.shape[0] == 0:
        return np.zeros(EMBEDDING_DIM, dtype=np.float32), scores
    mean_pooled = embeddings.mean(axis=0)
    max_pooled = embeddings.max(axis=0)
    clip_embedding = np.concatenate([mean_pooled, max_pooled]).astype(np.float32)
    return clip_embedding, scores


def media_context_score(frame_scores):
    """Max probability YAMNet assigned to any media-context AudioSet class
    across frames. A weak automatic acoustic signal, not proof."""
    if frame_scores.size == 0:
        return 0.0
    return float(frame_scores[:, _MEDIA_INDICES].max())
