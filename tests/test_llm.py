from types import SimpleNamespace

import httpx
import pytest
import json
from cua.llm.anthropic_provider import (
    AnthropicProvider,
)

from cua.llm.config import (
    ProviderConfig,
    ProviderType,
    load_llm_config,
)

from cua.llm.factory import (
    create_action_provider,
)

from cua.llm.gemini_provider import (
    GeminiProvider,
)
from cua.llm.normalization import (
    canonicalize_known_enums,
    parse_text_proposal,
    strip_outer_code_fence,
)

from cua.llm.base import (
    LLMValidationError,
)
from cua.llm.grok_provider import (
    GrokProvider,
)

from cua.llm.mock_provider import (
    MockActionProvider,
)

from cua.llm.ollama_provider import (
    OllamaProvider,
)

from cua.llm.openai_compatible_provider import (
    OpenAICompatibleProvider,
)

from cua.llm.openai_provider import (
    OpenAIProvider,
)

from cua.llm.schemas import (
    LLMActionProposal,
    LLMProposedLocator,
    LLMProposedTarget,
)

from cua.models import (
    ActionType,
    AgentAction,
    LocatorKind,
    Observation,
    ObservedControl,
    RiskLevel,
    TargetDescriptor,
)


def make_observation() -> Observation:

    return Observation(
        url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),

        title="LegacyCore Search",

        visible_text=(
            "Member Search "
            "Member ID Search"
        ),

        controls=[
            ObservedControl(
                tag="input",
                role="textbox",
                name="Member ID",
            ),

            ObservedControl(
                tag="button",
                role="button",
                name="Search",
                text="Search",
                input_type="submit",
            ),
        ],
    )


def make_proposal(
) -> LLMActionProposal:

    return LLMActionProposal(
        action=ActionType.FILL,

        target=LLMProposedTarget(
            description=(
                "Member ID input"
            ),

            locators=[
                LLMProposedLocator(
                    kind=LocatorKind.LABEL,
                    role=None,
                    name=None,
                    value="Member ID",
                    reference_text=None,
                    relation=None,
                    exact=True,
                    frame_hint=None,
                    description=(
                        "Member ID field"
                    ),
                )
            ],
        ),

        value="1001",

        output_name=None,

        reason=(
            "Enter the member "
            "identifier."
        ),

        success_condition=None,

        risk_hint=RiskLevel.SAFE,
    )


def provider_config(
    provider_type: ProviderType,
    *,
    model: str = "test-model",
    base_url: str | None = None,
) -> ProviderConfig:

    return ProviderConfig(
        type=provider_type,
        model=model,
        api_key_env=None,
        base_url=base_url,
    )


def test_strip_outer_json_fence():

    raw = """```json
{
  "action": "fill"
}
```"""

    result = (
        strip_outer_code_fence(
            raw
        )
    )

    assert result.startswith("{")
    assert result.endswith("}")

    assert "```" not in result

def test_plain_json_is_unchanged():

    raw = """
    {
      "action": "fill"
    }
    """

    result = (
        strip_outer_code_fence(
            raw
        )
    )

    assert json.loads(
        result
    ) == {
        "action": "fill"
    }

def test_known_enum_casing_is_normalized():

    raw = {
        "action": "FILL",

        "risk_hint": "SAFE",

        "target": {
            "locators": [
                {
                    "kind": "ROLE"
                }
            ]
        },
    }

    result = (
        canonicalize_known_enums(
            raw
        )
    )

    assert (
        result["action"]
        == "fill"
    )

    assert (
        result["risk_hint"]
        == "safe"
    )

    assert (
        result["target"]
        ["locators"][0]
        ["kind"]
        == "role"
    )

def test_unknown_enum_is_not_guessed():

    raw = {
        "risk_hint":
            "probably_safe"
    }

    result = (
        canonicalize_known_enums(
            raw
        )
    )

    assert (
        result["risk_hint"]
        == "probably_safe"
    )

def test_parse_fenced_uppercase_proposal():

    proposal = (
        make_proposal()
        .model_dump(
            mode="json"
        )
    )

    proposal[
        "action"
    ] = "FILL"

    proposal[
        "risk_hint"
    ] = "SAFE"

    proposal[
        "target"
    ][
        "locators"
    ][0][
        "kind"
    ] = "LABEL"

    raw = (
        "```json\n"
        + json.dumps(
            proposal
        )
        + "\n```"
    )

    parsed = (
        parse_text_proposal(
            raw
        )
    )

    assert (
        parsed.action
        == ActionType.FILL
    )

    assert (
        parsed.risk_hint
        == RiskLevel.SAFE
    )

    assert (
        parsed.target
        is not None
    )

    assert (
        parsed.target
        .locators[0]
        .kind
        == LocatorKind.LABEL
    )

def test_invalid_risk_value_fails_closed():

    proposal = (
        make_proposal()
        .model_dump(
            mode="json"
        )
    )

    proposal[
        "risk_hint"
    ] = "probably_safe"

    raw = json.dumps(
        proposal
    )

    with pytest.raises(
        LLMValidationError
    ):
        parse_text_proposal(
            raw
        )

def test_arbitrary_prose_is_rejected():

    raw = (
        "I think you should "
        "click the search button."
    )

    with pytest.raises(
        LLMValidationError
    ):
        parse_text_proposal(
            raw
        )


def test_load_llm_config_with_mock_active(
    tmp_path,
):
    config_file = (
        tmp_path / "llm.json"
    )

    config_file.write_text(
        """
        {
          "active_provider": "mock",

          "providers": {
            "mock": {
              "type": "mock",
              "model": "mock",
              "enabled": true,
              "api_key_env": null,
              "base_url": null,
              "timeout_seconds": 10,
              "max_output_tokens": 1200,
              "options": {}
            }
          }
        }
        """,
        encoding="utf-8",
    )

    config = load_llm_config(
        config_file
    )

    assert (
        config.active_provider
        == "mock"
    )


def test_factory_can_explicitly_select_mock():
    provider = (
        create_action_provider(
            provider_name="mock"
        )
    )

    assert isinstance(
        provider,
        MockActionProvider,
    )

    assert (
        provider.provider_alias
        == "mock"
    )

    assert (
        provider.model_name
        == "mock"
    )


def test_schema_converts_to_agent_action():

    action = (
        make_proposal()
        .to_agent_action()
    )

    assert (
        action.action
        == ActionType.FILL
    )

    assert action.value == "1001"

    assert action.target is not None


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic():

    expected = AgentAction(
        action=ActionType.CLICK,

        target=TargetDescriptor(
            description="Search button",
            locators=[],
        ),

        reason="test",
    )

    provider = MockActionProvider(
        actions=[expected]
    )

    result = await provider.decide(
        goal="test",
        observation=make_observation(),
    )

    assert result is expected


class FakeResponses:

    def __init__(
        self,
        response,
    ):
        self.response = response

        self.last_kwargs = None

    async def parse(
        self,
        **kwargs,
    ):
        self.last_kwargs = kwargs

        return self.response


class FakeOpenAIClient:

    def __init__(
        self,
        response,
    ):
        self.responses = (
            FakeResponses(response)
        )


@pytest.mark.asyncio
async def test_openai_provider():

    response = SimpleNamespace(
        id="resp-openai",
        status="completed",
        output_parsed=(
            make_proposal()
        ),
        output=[],
    )

    client = FakeOpenAIClient(
        response
    )

    provider = OpenAIProvider(
        provider_alias="openai",

        config=provider_config(
            ProviderType.OPENAI
        ),

        client=client,
    )

    action = await provider.decide(
        goal="Find member 1001",
        observation=make_observation(),
    )

    assert (
        action.action
        == ActionType.FILL
    )

    assert (
        provider.last_request_id
        == "resp-openai"
    )

    assert (
        client.responses
        .last_kwargs[
            "text_format"
        ]
        is LLMActionProposal
    )


class FakeAnthropicMessages:

    def parse(
        self,
        **kwargs,
    ):
        return SimpleNamespace(
            id="msg-anthropic",
            stop_reason="end_turn",
            parsed_output=(
                make_proposal()
            ),
        )


class FakeAnthropicClient:

    messages = (
        FakeAnthropicMessages()
    )


@pytest.mark.asyncio
async def test_anthropic_provider():

    provider = AnthropicProvider(
        provider_alias="anthropic",

        config=provider_config(
            ProviderType.ANTHROPIC
        ),

        client=FakeAnthropicClient(),
    )

    action = await provider.decide(
        goal="Find member 1001",
        observation=make_observation(),
    )

    assert (
        action.action
        == ActionType.FILL
    )

    assert (
        provider.last_request_id
        == "msg-anthropic"
    )


class FakeGeminiModels:

    def __init__(self):
        self.last_kwargs = None

    async def generate_content(
        self,
        **kwargs,
    ):
        self.last_kwargs = kwargs

        return SimpleNamespace(
            response_id="gemini-test",

            text=(
                make_proposal()
                .model_dump_json()
            ),
        )


class FakeGeminiAio:

    def __init__(self):
        self.models = (
            FakeGeminiModels()
        )


class FakeGeminiClient:

    def __init__(self):
        self.aio = FakeGeminiAio()


@pytest.mark.asyncio
async def test_gemini_provider():

    client = FakeGeminiClient()

    provider = GeminiProvider(
        provider_alias="gemini",

        config=provider_config(
            ProviderType.GEMINI
        ),

        client=client,
    )

    action = await provider.decide(
        goal="Find member 1001",
        observation=make_observation(),
    )

    assert (
        action.action
        == ActionType.FILL
    )

    assert (
        provider.last_request_id
        == "gemini-test"
    )

    kwargs = (
        client
        .aio
        .models
        .last_kwargs
    )

    assert kwargs is not None

    assert (
        kwargs["model"]
        == "test-model"
    )

    config = kwargs["config"]

    assert (
        config.response_mime_type
        == "application/json"
    )

    assert (
        config.response_json_schema
        is not None
    )


class FakeGrokCompletions:

    async def parse(
        self,
        **kwargs,
    ):
        return SimpleNamespace(
            id="grok-test",

            choices=[
                SimpleNamespace(
                    message=(
                        SimpleNamespace(
                            parsed=(
                                make_proposal()
                            ),
                            refusal=None,
                        )
                    )
                )
            ],
        )


class FakeGrokChat:

    completions = (
        FakeGrokCompletions()
    )


class FakeGrokBeta:

    chat = FakeGrokChat()


class FakeGrokClient:

    beta = FakeGrokBeta()


@pytest.mark.asyncio
async def test_grok_provider():

    provider = GrokProvider(
        provider_alias="grok",

        config=provider_config(
            ProviderType.GROK,
            base_url=(
                "https://api.x.ai/v1"
            ),
        ),

        client=FakeGrokClient(),
    )

    action = await provider.decide(
        goal="Find member 1001",
        observation=make_observation(),
    )

    assert (
        action.action
        == ActionType.FILL
    )

    assert (
        provider.last_request_id
        == "grok-test"
    )


@pytest.mark.asyncio
async def test_ollama_provider():

    async def handler(
        request: httpx.Request,
    ):
        return httpx.Response(
            200,

            json={
                "message": {
                    "role": "assistant",

                    "content": (
                        make_proposal()
                        .model_dump_json()
                    ),
                }
            },
        )

    transport = httpx.MockTransport(
        handler
    )

    async with httpx.AsyncClient(
        transport=transport
    ) as client:

        provider = OllamaProvider(
            provider_alias="ollama",

            config=provider_config(
                ProviderType.OLLAMA,
                model="llama3.2",
                base_url=(
                    "http://127.0.0.1:"
                    "11434"
                ),
            ),

            client=client,
        )

        action = (
            await provider.decide(
                goal="Find member 1001",

                observation=(
                    make_observation()
                ),
            )
        )

    assert (
        action.action
        == ActionType.FILL
    )


class FakeCompatibleCompletions:

    async def create(
        self,
        **kwargs,
    ):
        return SimpleNamespace(
            id="compat-test",

            choices=[
                SimpleNamespace(
                    message=(
                        SimpleNamespace(
                            content=(
                                make_proposal()
                                .model_dump_json()
                            )
                        )
                    )
                )
            ],
        )


class FakeCompatibleChat:

    completions = (
        FakeCompatibleCompletions()
    )


class FakeCompatibleClient:

    chat = FakeCompatibleChat()


@pytest.mark.asyncio
async def test_openai_compatible_provider():

    provider = (
        OpenAICompatibleProvider(
            provider_alias="vllm",

            config=provider_config(
                (
                    ProviderType
                    .OPENAI_COMPATIBLE
                ),

                base_url=(
                    "http://127.0.0.1:"
                    "8001/v1"
                ),
            ),

            client=(
                FakeCompatibleClient()
            ),
        )
    )

    action = await provider.decide(
        goal="Find member 1001",
        observation=make_observation(),
    )

    assert (
        action.action
        == ActionType.FILL
    )

    assert (
        provider.last_request_id
        == "compat-test"
    )