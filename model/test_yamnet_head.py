import numpy as np
import tensorflow as tf

from audio_classes import NUM_CLASSES
from yamnet_features import EMBEDDING_DIM, load_yamnet, load_waveform, embed_waveform, media_context_score
from train_yamnet import build_classifier_head


def test_classifier_head_output_shape_and_softmax():
    model = build_classifier_head(NUM_CLASSES, hidden_units=32, dropout=0.1)
    dummy_embeddings = np.random.randn(4, EMBEDDING_DIM).astype(np.float32)
    probs = model.predict(dummy_embeddings, verbose=0)
    assert probs.shape == (4, NUM_CLASSES)
    assert np.allclose(probs.sum(axis=1), np.ones(4), atol=1e-4), "Softmax outputs must sum to 1"


def test_classifier_head_respects_a_different_class_count():
    # The demo profile's head has 9 outputs (8 production classes + firecracker);
    # this is what actually prevents a taxonomy mismatch from compiling silently.
    model = build_classifier_head(9, hidden_units=32, dropout=0.1)
    dummy_embeddings = np.random.randn(4, EMBEDDING_DIM).astype(np.float32)
    probs = model.predict(dummy_embeddings, verbose=0)
    assert probs.shape == (4, 9)


def test_yamnet_embedding_shape_and_media_context_score():
    yamnet = load_yamnet()

    # A 2-second silent waveform still produces frames; the embedding must be
    # the full mean+max concatenation, not the raw 1024-d YAMNet output.
    waveform = load_waveform((np.zeros(32000, dtype=np.float32), 16000))
    embedding, frame_scores = embed_waveform(yamnet, waveform)
    assert embedding.shape == (EMBEDDING_DIM,)
    assert frame_scores.shape[1] == 521

    score = media_context_score(frame_scores)
    assert 0.0 <= score <= 1.0


def test_media_context_score_handles_empty_frames():
    assert media_context_score(np.zeros((0, 521))) == 0.0


if __name__ == "__main__":
    test_classifier_head_output_shape_and_softmax()
    test_classifier_head_respects_a_different_class_count()
    test_yamnet_embedding_shape_and_media_context_score()
    test_media_context_score_handles_empty_frames()
    print("YAMNet head tests passed.")
