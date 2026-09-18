import random
from typing import NamedTuple

# (hardwareConcurrency, deviceMemory) pairs kept plausible together — real machines
# don't pair e.g. 4 cores with 32 GB of RAM.
_HARDWARE_PROFILES: list[tuple[int, int]] = [
    (4, 4),
    (4, 8),
    (6, 8),
    (8, 8),
    (8, 16),
    (12, 16),
    (16, 16),
]

_COLOR_DEPTHS: list[int] = [24, 30]

_LANGUAGE_PROFILES: list[list[str]] = [
    ['ru-RU', 'ru', 'en-US', 'en'],
    ['ru-RU', 'ru'],
    ['ru-RU', 'ru', 'en-US', 'en', 'en-GB'],
]


class OzonFingerprintProfile(NamedTuple):
    hardware_concurrency: int
    device_memory: int
    color_depth: int
    languages: list[str]


def generate_ozon_fingerprint_profile() -> OzonFingerprintProfile:
    hardware_concurrency, device_memory = random.choice(_HARDWARE_PROFILES)
    return OzonFingerprintProfile(
        hardware_concurrency=hardware_concurrency,
        device_memory=device_memory,
        color_depth=random.choice(_COLOR_DEPTHS),
        languages=random.choice(_LANGUAGE_PROFILES),
    )
