from __future__ import annotations

from collections.abc import (
    Sequence,
)
from typing import Any

from openai import AsyncOpenAI

from cua.models import (
    AgentAction,
    Observation,
)

from cua.llm.base import (
    ActionProvider,
    LLMIncompleteResponseError,
    LLMProviderError,
    LLMRefusalError,
    proposal_to_agent_action,
    require_api_key,
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


class OpenAIProvider(
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

        if client is None:
            api_key = require_api_key(
                config.api_key_env
            )

            kwargs: dict[
                str,
                Any,
            ] = {
                "api_key": api_key,
                "timeout": (
                    config
                    .timeout_seconds
                ),
            }

            if config.base_url:
                kwargs[
                    "base_url"
                ] = config.base_url

            client = AsyncOpenAI(
                **kwargs
            )

        self.client = client

    @staticmethod
    def _extract_refusal(
        response: Any,
    ) -> str | None:

        for output in getattr(
            response,
            "output",
            [],
        ):
            if (
                getattr(
                    output,
                    "type",
                    None,
                )
                != "message"
            ):
                continue

            for item in getattr(
                output,
                "content",
                [],
            ):
                if (
                    getattr(
                        item,
                        "type",
                        None,
                    )
                    == "refusal"
                ):
                    return getattr(
                        item,
                        "refusal",
                        (
                            "Model refused "
                            "request."
                        ),
                    )

        return None

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

        request_kwargs: dict[
            str,
            Any,
        ] = {
            "model": self.model_name,

            "instructions": (
                DISCOVERY_INSTRUCTIONS
            ),

            "input": input_text,

            "text_format": (
                LLMActionProposal
            ),

            "store": False,

            "max_output_tokens": (
                self.config
                .max_output_tokens
            ),
        }

        reasoning_effort = (
            self.config.options.get(
                "reasoning_effort"
            )
        )

        if reasoning_effort:
            request_kwargs[
                "reasoning"
            ] = {
                "effort": (
                    reasoning_effort
                )
            }

        try:
            response = (
                await self
                .client
                .responses
                .parse(
                    **request_kwargs
                )
            )

        except Exception as exc:
            raise LLMProviderError(
                (
                    "OpenAI request "
                    f"failed: {exc}"
                )
            ) from exc

        self.last_request_id = (
            getattr(
                response,
                "id",
                None,
            )
        )

        proposal = getattr(
            response,
            "output_parsed",
            None,
        )

        if proposal is None:

            refusal = (
                self._extract_refusal(
                    response
                )
            )

            if refusal:
                raise LLMRefusalError(
                    refusal
                )

            if (
                getattr(
                    response,
                    "status",
                    None,
                )
                == "incomplete"
            ):
                raise (
                    LLMIncompleteResponseError(
                        (
                            "OpenAI returned "
                            "an incomplete "
                            "structured "
                            "response."
                        )
                    )
                )

            raise LLMProviderError(
                (
                    "OpenAI response "
                    "contained no "
                    "parsed action."
                )
            )

        if not isinstance(
            proposal,
            LLMActionProposal,
        ):
            proposal = (
                LLMActionProposal
                .model_validate(
                    proposal
                )
            )

        return proposal_to_agent_action(
            proposal
        )