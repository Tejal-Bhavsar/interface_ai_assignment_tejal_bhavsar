from __future__ import annotations

import os

from abc import (
    ABC,
    abstractmethod,
)

from collections.abc import (
    Sequence,
)

from cua.models import (
    ActionType,
    AgentAction,
    Observation,
)

from cua.llm.schemas import (
    LLMActionProposal,
)


class LLMProviderError(
    RuntimeError
):
    pass


class LLMConfigurationError(
    LLMProviderError
):
    pass


class LLMRefusalError(
    LLMProviderError
):
    pass


class LLMIncompleteResponseError(
    LLMProviderError
):
    pass


class LLMValidationError(
    LLMProviderError
):
    pass


def require_api_key(
    env_name: str | None,
) -> str:

    if not env_name:
        raise LLMConfigurationError(
            "This provider requires "
            "api_key_env in config."
        )

    value = os.getenv(
        env_name
    )

    if not value:
        raise LLMConfigurationError(
            (
                f"Environment variable "
                f"'{env_name}' is not "
                f"configured."
            )
        )

    return value


def proposal_to_agent_action(
    proposal: LLMActionProposal,
) -> AgentAction:
    """
    Structural JSON validation is not enough.

    We also enforce action-specific semantic rules.
    """

    action = (
        proposal.to_agent_action()
    )

    target_required = {
        ActionType.CLICK,
        ActionType.FILL,
        ActionType.SELECT,
        ActionType.EXTRACT,
    }

    if (
        action.action
        in target_required
    ):
        if (
            action.target is None
            or not action.target.locators
        ):
            raise LLMValidationError(
                (
                    f"{action.action.value} "
                    f"requires a target with "
                    f"at least one locator."
                )
            )

    if action.action in {
        ActionType.FILL,
        ActionType.SELECT,
        ActionType.NAVIGATE,
    }:
        if (
            not isinstance(
                action.value,
                str,
            )
            or not action.value.strip()
        ):
            raise LLMValidationError(
                (
                    f"{action.action.value} "
                    f"requires a non-empty "
                    f"string value."
                )
            )

    if (
        action.action
        == ActionType.EXTRACT
    ):
        if not action.output_name:
            raise LLMValidationError(
                (
                    "extract requires "
                    "output_name."
                )
            )

    return action


class ActionProvider(ABC):
    """
    The provider-neutral reasoning contract.
    """

    def __init__(
        self,
        *,
        provider_alias: str,
        model_name: str,
    ):
        self.provider_alias = (
            provider_alias
        )

        self.model_name = model_name

        self.last_request_id: (
            str | None
        ) = None

    @abstractmethod
    async def decide(
        self,
        *,
        goal: str,
        observation: Observation,
        previous_actions: Sequence[
            AgentAction
        ] = (),
        step_index: int = 1,
        max_steps: int = 12,
    ) -> AgentAction:
        raise NotImplementedError