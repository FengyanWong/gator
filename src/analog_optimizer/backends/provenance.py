"""Content identities for the PDK-specific parameter and validation contract."""
from dataclasses import asdict
import hashlib
import json


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()


def profile_contract(profile):
    return content_hash(dict(design=profile.design, reference=profile.reference,
                             mapping=asdict(profile.parser.config), conditions=profile.condition_config,
                             graph=asdict(profile.graph), bounds=profile.width_bounds, step=profile.width_step))

