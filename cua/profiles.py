from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from cua.models import ApplicationProfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROFILE_PATH = (
    PROJECT_ROOT
    / "config"
    / "app_profiles.json"
)


class ApplicationProfilesConfig(BaseModel):
    profiles: dict[str, ApplicationProfile]


def load_profiles(
    path: Path | str = DEFAULT_PROFILE_PATH,
) -> ApplicationProfilesConfig:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Application profile file not found: "
            f"{config_path}"
        )

    raw = json.loads(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    return ApplicationProfilesConfig.model_validate(
        raw
    )


def get_profile(
    vendor_family: str,
    path: Path | str = DEFAULT_PROFILE_PATH,
) -> ApplicationProfile:
    config = load_profiles(path)

    profile = config.profiles.get(
        vendor_family
    )

    if profile is None:
        available = ", ".join(
            sorted(config.profiles.keys())
        )

        raise KeyError(
            f"No application profile found for "
            f"vendor family '{vendor_family}'. "
            f"Available profiles: {available}"
        )

    return profile