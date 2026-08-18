from __future__ import annotations

from collections.abc import (
    Sequence,
)
from typing import Any

import httpx

from cua.models import (
    AgentAction,
    Observation,
)
from cua.llm.normalization import (
    parse_text_proposal,
)

from cua.llm.base import (
    ActionProvider,
    LLMProviderError,
    proposal_to_agent_action,
)

from cua.llm.config import (
    ProviderConfig,
)

from cua.llm.prompts import (
    DISCOVERY_INSTRUCTIONS,
    build_discovery_input,
)

from cua.llm.schemas import (
    LLMActionProposal,
)


class OllamaProvider(
    ActionProvider
):

    def __init__(
        self,
        *,
        provider_alias: str,
        config: ProviderConfig,
        client: Any | None = None,
    ):
        super().__init__(
            provider_alias=(
                provider_alias
            ),
            model_name=config.model,
        )

        self.config = config

        self.base_url = (
            config.base_url
            or (
                "http://127.0.0.1:"
                "11434"
            )
        ).rstrip("/")

        self.client = client

    async def _post(
        self,
        payload: dict[str, Any],
    ) -> httpx.Response:

        if self.client is not None:
            return await self.client.post(
                (
                    f"{self.base_url}"
                    "/api/chat"
                ),
                json=payload,
            )

        async with httpx.AsyncClient(
            timeout=(
                self.config
                .timeout_seconds
            )
        ) as client:

            return await client.post(
                (
                    f"{self.base_url}"
                    "/api/chat"
                ),
                json=payload,
            )

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

        input_text = (
            build_discovery_input(
                goal=goal,
                observation=(
                    observation
                ),
                previous_actions=(
                    previous_actions
                ),
                step_index=step_index,
                max_steps=max_steps,
            )
        )

        options = {
            "temperature": 0,
            **self.config.options,
        }

        payload = {
            "model": self.model_name,

            "messages": [
                {
                    "role": "system",
                    "content": (
                        DISCOVERY_INSTRUCTIONS
                    ),
                },
                {
                    "role": "user",
                    "content": input_text,
                },
            ],

            "stream": False,

            "format": (
                LLMActionProposal
                .model_json_schema()
            ),

            "options": options,
        }

        try:
            response = await self._post(
                payload
            )

            response.raise_for_status()

            body = response.json()

        except Exception as exc:
            raise LLMProviderError(
                (
                    "Ollama request "
                    f"failed: {exc}"
                )
            ) from exc

        self.last_request_id = (
            response.headers.get(
                "x-request-id"
            )
        )

        content = (
            body
            .get(
                "message",
                {},
            )
            .get(
                "content"
            )
        )

        if not content:
            raise LLMProviderError(
                (
                    "Ollama response "
                    "contained no "
                    "message content."
                )
            )

        proposal = (
    parse_text_proposal(
        content
    )
)

        return proposal_to_agent_action(
            proposal
        )