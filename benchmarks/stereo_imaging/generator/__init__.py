"""Generator package for the stereo_imaging benchmark (v3 source layer and dataset build)."""

from .build import CANONICAL_SEED, generate_dataset

__all__ = ["CANONICAL_SEED", "generate_dataset"]
