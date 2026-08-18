from __future__ import annotations

from collections.abc import (
    Sequence,
)

from cua.models import (
    AgentAction,
    Observation,
)

from cua.llm.base import (
    ActionProvider,
    LLMProviderError,
)


class MockActionProvider(
    ActionProvider
):
    """
    Deterministic provider for tests.

    Mock runs are NOT genuine LLM evidence.
    """

    def __init__(
        self,
        *,
        provider_alias: str = "mock",
        model_name: str = "mock",
        actions: Sequence[
            AgentAction
        ] = (),
    ):
        super().__init__(
            provider_alias=(
                provider_alias
            ),
            model_name=model_name,
        )

        self._actions = list(
            actions
        )

        self._index = 0

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

        if (
            self._index
            >= len(self._actions)
        ):
            raise LLMProviderError(
                (
                    "MockActionProvider "
                    "has no scripted "
                    "action for this step."
                )
            )

        action = (
            self._actions[
                self._index
            ]
        )

        self._index += 1

        self.last_request_id = (
            f"mock-{self._index}"
        )

        return action