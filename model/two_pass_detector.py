import logging

import numpy as np
import tensorflow as tf

from audio_classes import MEDIA_CONTEXT_THRESHOLD
from model_profiles import REAL_PROFILE, get_profile
from yamnet_features import load_yamnet, load_waveform, embed_waveform, media_context_score

logger = logging.getLogger(__name__)


class TwoPassDetector:
    """Two-pass hazard detector over a frozen YAMNet backbone.

    The class taxonomy is no longer global: a detector is bound to a
    :class:`model_profiles.ModelProfile` (``real`` or ``demo``), because the
    demo head has one extra class and its own alias map. Passing a bare
    checkpoint path still works and defaults to the production profile, so
    existing callers are unaffected.
    """

    def __init__(self, head_model_path=None, profile=None, yamnet=None):
        if isinstance(profile, str):
            profile = get_profile(profile)
        self.profile = profile or REAL_PROFILE
        self.head_model_path = head_model_path or self.profile.checkpoint_path
        # The YAMNet backbone is identical for every profile and costs ~30s
        # and a few hundred MB to load, so callers holding several detectors
        # should share one instance instead of loading it per head.
        self.yamnet = yamnet if yamnet is not None else load_yamnet()
        self.head = tf.keras.models.load_model(self.head_model_path)
        self.idx_to_class = self.profile.idx_to_class
        self.class_mapping = self.profile.class_mapping

        head_outputs = int(self.head.output_shape[-1])
        if head_outputs != self.profile.num_classes:
            # A head whose output width does not match its profile's taxonomy
            # would silently mislabel every prediction (index 8 read as index
            # 7, and so on) -- an unacceptable failure mode for a safety
            # classifier, so refuse to run instead.
            raise ValueError(
                "Checkpoint {} outputs {} classes but profile '{}' defines {}.".format(
                    self.head_model_path, head_outputs, self.profile.name,
                    self.profile.num_classes,
                )
            )

    def _classify(self, audio_np, sr):
        waveform = load_waveform((audio_np, sr))
        embedding, frame_scores = embed_waveform(self.yamnet, waveform)
        probs = self.head.predict(embedding[np.newaxis, :], verbose=0)[0]
        acoustic_media_score = media_context_score(frame_scores)
        return probs, acoustic_media_score

    def resolve_class(self, class_name):
        """Head-native class -> the class the risk scorer and safety policy use.

        For the demo profile this is where ``firecracker`` becomes
        ``gunshot``; the caller keeps the raw class for the record.
        """
        return self.profile.resolve_class(class_name)

    def run_pass_1(self, audio_2s_np, sr, threshold=None):
        """
        Pass 1: Primary detection with a 2-second window.
        Threshold: the profile default (0.50 real / 0.55 demo) unless the
        caller passes one.
        Also returns an automatically-detected acoustic media-context score
        (see audio_classes.MEDIA_CONTEXT_AUDIOSET_INDICES) as weak supporting
        evidence, distinct from the user/platform-reported media_playback
        toggle -- it never overrides that toggle, only supplements it.
        """
        if threshold is None:
            threshold = self.profile.default_pass1_threshold
        probs, acoustic_media_score = self._classify(audio_2s_np, sr)

        max_prob = 0.0
        candidate_idx = 0
        for idx in range(1, len(self.idx_to_class)):
            if probs[idx] > max_prob:
                max_prob = float(probs[idx])
                candidate_idx = idx

        if logger.isEnabledFor(logging.DEBUG):
            probs_str = ", ".join(
                "{}={:.4f}".format(self.idx_to_class[i], probs[i])
                for i in range(len(self.idx_to_class))
            )
            logger.debug("Pass 1 probabilities (%s): %s", self.profile.name, probs_str)

        candidate_class = self.idx_to_class[candidate_idx]
        logger.debug(
            "Pass 1 selected candidate: %s (max_hazard_prob=%.4f, acoustic_media_score=%.4f)",
            candidate_class if max_prob >= threshold else "normal", max_prob, acoustic_media_score,
        )

        if max_prob >= threshold:
            return True, candidate_class, max_prob, acoustic_media_score

        return False, "normal", float(probs[0]), acoustic_media_score

    def run_pass_2(self, audio_5s_np, sr, target_class, threshold=None):
        """
        Pass 2: Verification detection centered around candidate event (5-second window).
        Threshold: the profile default (0.70 real / 0.60 demo) unless the
        caller passes one.
        """
        if threshold is None:
            threshold = self.profile.default_pass2_threshold

        probs, acoustic_media_score = self._classify(audio_5s_np, sr)
        target_idx = self.class_mapping.get(target_class, 0)
        verification_prob = float(probs[target_idx])

        is_verified = verification_prob >= threshold
        return is_verified, verification_prob, acoustic_media_score

    @staticmethod
    def acoustic_media_signal_active(acoustic_media_score):
        return acoustic_media_score >= MEDIA_CONTEXT_THRESHOLD
