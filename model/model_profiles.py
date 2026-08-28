"""Model profile registry: the production head and the demo head.

Echo ships two classifier heads on top of the *same* frozen YAMNet backbone:

``real``
    The production head. Eight classes, tuned on real hazard audio. It must
    never be trained on firecracker recordings -- resistance to celebratory
    fireworks is one of the properties that makes an acoustic gunshot alarm
    defensible in India at all.

``demo``
    A presentation head. Nine classes: the same eight plus ``firecracker``,
    trained on Diwali cracker audio (single crackers, "ladi" chains, aerial
    shells). At inference it aliases ``firecracker -> gunshot`` so a cracker
    lit in the demo room drives the complete alert path -- risk scoring,
    safety policy, contact call, Telegram clip -- exactly like a gunshot
    would, while every record keeps ``raw_class="firecracker"`` and
    ``profile="demo"``, so no artifact ever claims a real gunshot was heard.

Splitting them this way means the demo can be loud and reliable without
degrading the model that would have to work in a real emergency, and a
reviewer can always see which head produced any given result.
"""

import os
from dataclasses import dataclass, field

from audio_classes import (
    CLASS_MAPPING,
    DEMO_ALIAS_MAP,
    DEMO_CLASS_MAPPING,
)

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))

REAL_PROFILE_NAME = "real"
DEMO_PROFILE_NAME = "demo"


@dataclass(frozen=True)
class ModelProfile:
    name: str
    description: str
    checkpoint_path: str
    manifest_path: str
    dataset_dir: str
    class_mapping: dict
    alias_map: dict = field(default_factory=dict)
    # Pass 1 keeps the caller-supplied sensitivity; these are the profile's
    # defaults. The demo head is trained on a class with a very distinctive
    # transient signature, so it can afford a slightly higher pass-1 bar and a
    # lower pass-2 bar than the production head: crackers are easy to detect
    # but their 5-second window is often a chain of bursts rather than one
    # sustained event.
    default_pass1_threshold: float = 0.50
    default_pass2_threshold: float = 0.70
    # Shown verbatim in the app and attached to every incident this profile
    # produces, so a demo result is never mistaken for a production result.
    banner: str = ""

    @property
    def idx_to_class(self):
        return {index: name for name, index in self.class_mapping.items()}

    @property
    def num_classes(self):
        return len(self.class_mapping)

    @property
    def checkpoint_exists(self):
        return os.path.exists(self.checkpoint_path)

    def resolve_class(self, class_name):
        """Maps a head-native class to the class the rest of Echo reasons about."""
        return self.alias_map.get(class_name, class_name)

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "classes": sorted(self.class_mapping, key=self.class_mapping.get),
            "alias_map": dict(self.alias_map),
            "default_pass1_threshold": self.default_pass1_threshold,
            "default_pass2_threshold": self.default_pass2_threshold,
            "checkpoint_available": self.checkpoint_exists,
            "banner": self.banner,
        }


REAL_PROFILE = ModelProfile(
    name=REAL_PROFILE_NAME,
    description="Production hazard head: 8 classes trained on real hazard audio.",
    checkpoint_path=os.path.join(MODEL_DIR, "checkpoints", "yamnet_head.keras"),
    manifest_path=os.path.join(MODEL_DIR, "data", "processed", "metadata.csv"),
    dataset_dir=os.path.join(MODEL_DIR, "data", "processed"),
    class_mapping=CLASS_MAPPING,
    alias_map={},
    default_pass1_threshold=0.50,
    default_pass2_threshold=0.70,
    banner="",
)

DEMO_PROFILE = ModelProfile(
    name=DEMO_PROFILE_NAME,
    description=(
        "Demonstration head: the 8 production classes plus a dedicated "
        "'firecracker' class (Diwali crackers). Firecracker detections are "
        "aliased to gunshot so the full alert path runs on stage, and every "
        "record keeps raw_class=firecracker."
    ),
    checkpoint_path=os.path.join(MODEL_DIR, "checkpoints", "yamnet_head_demo.keras"),
    manifest_path=os.path.join(MODEL_DIR, "data", "processed_demo", "metadata.csv"),
    dataset_dir=os.path.join(MODEL_DIR, "data", "processed_demo"),
    class_mapping=DEMO_CLASS_MAPPING,
    alias_map=DEMO_ALIAS_MAP,
    default_pass1_threshold=0.55,
    default_pass2_threshold=0.60,
    banner="DEMO PROFILE - firecracker audio is treated as a gunshot for this demonstration.",
)

PROFILES = {
    REAL_PROFILE.name: REAL_PROFILE,
    DEMO_PROFILE.name: DEMO_PROFILE,
}


def get_profile(name):
    """Returns a profile by name. Unknown names fail loudly: silently falling
    back to the production head would let a demo request run on the real model
    (or worse, the reverse) with nobody noticing."""
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(
            "Unknown model profile '{}'; expected one of {}.".format(
                name, sorted(PROFILES)
            )
        )


def available_profiles():
    return [profile.to_dict() for profile in PROFILES.values()]
