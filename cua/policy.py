from __future__ import annotations

import json

from pathlib import Path
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field, field_validator

from cua.models import (
    ActionType,
    PolicyDecision,
    ResolvedTargetInfo,
    RiskLevel,
)


class PolicyError(RuntimeError):
    pass


class PolicyConfigurationError(PolicyError):
    pass


class RiskyActionMode(str):
    REQUIRE_HUMAN = "require_human"
    BLOCK = "block"


class PolicyConfig(BaseModel):
    """
    Global runtime guardrails.

    Capability safety and global policy are deliberately separate:
      - capability safety says what that artifact was reviewed to do
      - global policy says what this deployment permits at runtime

    Both boundaries must permit an action.
    """

    schema_version: str = "1.0"

    allowed_origins: list[str] = Field(
        min_length=1
    )

    allowed_route_prefixes: list[str] = Field(
        min_length=1
    )

    allowed_actions: list[
        ActionType
    ] = Field(
        min_length=1
    )

    risky_phrases: list[str] = Field(
        default_factory=list
    )

    blocked_phrases: list[str] = Field(
        default_factory=list
    )

    risky_action_mode: str = (
        RiskyActionMode.REQUIRE_HUMAN
    )

    @field_validator(
        "allowed_origins"
    )
    @classmethod
    def validate_origins(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized: list[str] = []

        for value in values:
            parsed = urlparse(
                value
            )

            if parsed.scheme not in {
                "http",
                "https",
            }:
                raise ValueError(
                    (
                        "Allowed origin must "
                        "use http or https."
                    )
                )

            if not parsed.netloc:
                raise ValueError(
                    (
                        "Allowed origin must "
                        "include a host."
                    )
                )

            if (
                parsed.path
                not in {
                    "",
                    "/",
                }
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    (
                        "allowed_origins must "
                        "contain origins only, "
                        "not paths/query/fragment."
                    )
                )

            normalized.append(
                (
                    f"{parsed.scheme}"
                    f"://{parsed.netloc}"
                )
                .lower()
            )

        return normalized

    @field_validator(
        "allowed_route_prefixes"
    )
    @classmethod
    def validate_routes(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized: list[str] = []

        for value in values:
            if not value.startswith(
                "/"
            ):
                raise ValueError(
                    (
                        "Allowed route prefixes "
                        "must begin with '/'."
                    )
                )

            route = (
                value.rstrip("/")
                or "/"
            )

            normalized.append(
                route
            )

        return normalized

    @field_validator(
        "risky_action_mode"
    )
    @classmethod
    def validate_risky_mode(
        cls,
        value: str,
    ) -> str:
        if value not in {
            RiskyActionMode
            .REQUIRE_HUMAN,
            RiskyActionMode.BLOCK,
        }:
            raise ValueError(
                (
                    "risky_action_mode must "
                    "be 'require_human' "
                    "or 'block'."
                )
            )

        return value


class PolicyEvaluation(BaseModel):
    """
    Structured, non-sensitive decision suitable for evidence.

    We intentionally store only the matched configured phrase,
    not arbitrary target text or input values.
    """

    decision: PolicyDecision

    code: str
    reason: str

    action: (
        ActionType
        | None
    ) = None

    risk_level: RiskLevel = (
        RiskLevel.SAFE
    )

    current_url_allowed: bool = True

    destination_url_allowed: (
        bool | None
    ) = None

    matched_phrase: (
        str | None
    ) = None

    evaluated_live_target: bool = False


class PolicyEngine:
    """
    Deterministic runtime policy.

    No LLM participates in any policy decision.
    """

    def __init__(
        self,
        config: PolicyConfig,
    ):
        self.config = config

    @classmethod
    def from_path(
        cls,
        path: Path | str,
    ) -> "PolicyEngine":
        source = Path(
            path
        )

        try:
            data = json.loads(
                source.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise PolicyConfigurationError(
                (
                    "Could not load policy "
                    f"configuration: {source}"
                )
            ) from exc

        try:
            config = (
                PolicyConfig
                .model_validate(
                    data
                )
            )
        except Exception as exc:
            raise PolicyConfigurationError(
                (
                    "Invalid policy "
                    f"configuration: {source}"
                )
            ) from exc

        return cls(
            config
        )

    # ========================================================
    # URL allowlist
    # ========================================================

    @staticmethod
    def _origin(
        url: str,
    ) -> str | None:
        parsed = urlparse(
            url
        )

        if (
            parsed.scheme
            not in {
                "http",
                "https",
            }
            or not parsed.netloc
        ):
            return None

        return (
            f"{parsed.scheme}"
            f"://{parsed.netloc}"
        ).lower()

    def _route_allowed(
        self,
        path: str,
    ) -> bool:
        normalized = (
            path
            or "/"
        )

        for prefix in (
            self.config
            .allowed_route_prefixes
        ):
            if prefix == "/":
                return True

            if normalized == prefix:
                return True

            if normalized.startswith(
                prefix + "/"
            ):
                return True

        return False

    def is_url_allowed(
        self,
        url: str,
    ) -> bool:
        origin = self._origin(
            url
        )

        if origin is None:
            return False

        if (
            origin
            not in self.config
            .allowed_origins
        ):
            return False

        parsed = urlparse(
            url
        )

        return self._route_allowed(
            parsed.path
        )

    def evaluate_current_url(
        self,
        url: str,
    ) -> PolicyEvaluation:
        """
        Verify the page the browser actually ended up on.

        This catches navigations caused indirectly by buttons/forms
        where no href was available before the click.
        """

        if not self.is_url_allowed(
            url
        ):
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_POST_ACTION_URL_BLOCKED"
                ),
                reason=(
                    "Browser reached a page "
                    "outside the configured "
                    "origin/route allowlist."
                ),
                current_url_allowed=False,
            )

        return PolicyEvaluation(
            decision=(
                PolicyDecision.ALLOW
            ),
            code="POLICY_ALLOW",
            reason=(
                "Current browser page is "
                "within the configured "
                "allowlist."
            ),
            current_url_allowed=True,
        )

    def evaluate_navigation(
        self,
        url: str,
    ) -> PolicyEvaluation:
        if not self.is_url_allowed(
            url
        ):
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_URL_BLOCKED"
                ),
                reason=(
                    "Navigation target is "
                    "outside the configured "
                    "origin/route allowlist."
                ),
                action=(
                    ActionType.NAVIGATE
                ),
                destination_url_allowed=False,
            )

        if (
            ActionType.NAVIGATE
            not in self.config
            .allowed_actions
        ):
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_ACTION_BLOCKED"
                ),
                reason=(
                    "Navigation is not an "
                    "allowed action type."
                ),
                action=(
                    ActionType.NAVIGATE
                ),
                destination_url_allowed=True,
            )

        return PolicyEvaluation(
            decision=(
                PolicyDecision.ALLOW
            ),
            code="POLICY_ALLOW",
            reason=(
                "Navigation is within "
                "the configured allowlist."
            ),
            action=(
                ActionType.NAVIGATE
            ),
            destination_url_allowed=True,
        )

    # ========================================================
    # Action + live target evaluation
    # ========================================================

    @staticmethod
    def _normalized_text(
        value: str | None,
    ) -> str:
        return (
            value
            or ""
        ).strip().lower()

    @classmethod
    def _first_phrase_match(
        cls,
        phrases: list[str],
        values: list[
            str | None
        ],
    ) -> str | None:
        haystacks = [
            cls._normalized_text(
                value
            )
            for value in values
            if value
        ]

        for phrase in phrases:
            normalized_phrase = (
                cls
                ._normalized_text(
                    phrase
                )
            )

            if not normalized_phrase:
                continue

            if any(
                normalized_phrase
                in haystack
                for haystack
                in haystacks
            ):
                return phrase

        return None

    @staticmethod
    def _resolved_values(
        resolved_info: (
            ResolvedTargetInfo
            | None
        ),
    ) -> list[
        str | None
    ]:
        if resolved_info is None:
            return []

        return [
            resolved_info.text,
            resolved_info.name,
            resolved_info.aria_label,
            resolved_info.placeholder,
            resolved_info.href,
            resolved_info.role,
            resolved_info.tag,
        ]

    def evaluate_action(
        self,
        *,
        action: ActionType,
        current_url: str,
        risk_level: (
            RiskLevel
            | None
        ) = None,
        target_description: (
            str | None
        ) = None,
        resolved_info: (
            ResolvedTargetInfo
            | None
        ) = None,
        destination_url: (
            str | None
        ) = None,
    ) -> PolicyEvaluation:
        risk = (
            risk_level
            or RiskLevel.SAFE
        )

        if not self.is_url_allowed(
            current_url
        ):
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_CURRENT_URL_BLOCKED"
                ),
                reason=(
                    "Current page is outside "
                    "the configured "
                    "origin/route allowlist."
                ),
                action=action,
                risk_level=risk,
                current_url_allowed=False,
                evaluated_live_target=(
                    resolved_info
                    is not None
                ),
            )

        if (
            action
            not in self.config
            .allowed_actions
        ):
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_ACTION_BLOCKED"
                ),
                reason=(
                    f"Action '{action.value}' "
                    "is not globally allowed."
                ),
                action=action,
                risk_level=risk,
                evaluated_live_target=(
                    resolved_info
                    is not None
                ),
            )

        destination_allowed: (
            bool | None
        ) = None

        if destination_url:
            absolute_destination = (
                urljoin(
                    current_url,
                    destination_url,
                )
            )

            destination_allowed = (
                self.is_url_allowed(
                    absolute_destination
                )
            )

            if not destination_allowed:
                return PolicyEvaluation(
                    decision=(
                        PolicyDecision.BLOCK
                    ),
                    code=(
                        "POLICY_DESTINATION_BLOCKED"
                    ),
                    reason=(
                        "Resolved action "
                        "destination is outside "
                        "the configured "
                        "origin/route allowlist."
                    ),
                    action=action,
                    risk_level=risk,
                    destination_url_allowed=False,
                    evaluated_live_target=(
                        resolved_info
                        is not None
                    ),
                )

        semantic_values = [
            target_description,
            *self._resolved_values(
                resolved_info
            ),
        ]

        blocked_phrase = (
            self
            ._first_phrase_match(
                self.config
                .blocked_phrases,
                semantic_values,
            )
        )

        if blocked_phrase is not None:
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_BLOCKED_PHRASE"
                ),
                reason=(
                    "The resolved action "
                    "matches a globally "
                    "blocked operation."
                ),
                action=action,
                risk_level=risk,
                destination_url_allowed=(
                    destination_allowed
                ),
                matched_phrase=(
                    blocked_phrase
                ),
                evaluated_live_target=(
                    resolved_info
                    is not None
                ),
            )

        # Irreversible model classification always wins even if
        # no text phrase happens to match.
        if (
            risk
            == RiskLevel.IRREVERSIBLE
        ):
            return PolicyEvaluation(
                decision=(
                    PolicyDecision.BLOCK
                ),
                code=(
                    "POLICY_IRREVERSIBLE_BLOCKED"
                ),
                reason=(
                    "Irreversible actions are "
                    "blocked from unattended "
                    "deterministic replay."
                ),
                action=action,
                risk_level=risk,
                destination_url_allowed=(
                    destination_allowed
                ),
                evaluated_live_target=(
                    resolved_info
                    is not None
                ),
            )

        risky_phrase = (
            self
            ._first_phrase_match(
                self.config
                .risky_phrases,
                semantic_values,
            )
        )

        is_risky = (
            risk
            == RiskLevel.RISKY
            or risky_phrase
            is not None
        )

        if is_risky:
            if (
                self.config
                .risky_action_mode
                == RiskyActionMode.BLOCK
            ):
                return PolicyEvaluation(
                    decision=(
                        PolicyDecision.BLOCK
                    ),
                    code=(
                        "POLICY_RISKY_BLOCKED"
                    ),
                    reason=(
                        "Risky action was "
                        "blocked by global "
                        "policy configuration."
                    ),
                    action=action,
                    risk_level=(
                        RiskLevel.RISKY
                    ),
                    destination_url_allowed=(
                        destination_allowed
                    ),
                    matched_phrase=(
                        risky_phrase
                    ),
                    evaluated_live_target=(
                        resolved_info
                        is not None
                    ),
                )

            return PolicyEvaluation(
                decision=(
                    PolicyDecision
                    .REQUIRE_HUMAN
                ),
                code=(
                    "POLICY_HUMAN_REQUIRED"
                ),
                reason=(
                    "Risky action requires "
                    "human review before "
                    "execution."
                ),
                action=action,
                risk_level=(
                    RiskLevel.RISKY
                ),
                destination_url_allowed=(
                    destination_allowed
                ),
                matched_phrase=(
                    risky_phrase
                ),
                evaluated_live_target=(
                    resolved_info
                    is not None
                ),
            )

        return PolicyEvaluation(
            decision=(
                PolicyDecision.ALLOW
            ),
            code="POLICY_ALLOW",
            reason=(
                "Action satisfies global "
                "runtime policy."
            ),
            action=action,
            risk_level=risk,
            destination_url_allowed=(
                destination_allowed
            ),
            evaluated_live_target=(
                resolved_info
                is not None
            ),
        )