import asyncio

from cua.llm import (
    create_action_provider,
)

from cua.models import (
    Observation,
    ObservedControl,
)


async def main():

    observation = Observation(
        url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),

        title="LegacyCore Search",

        visible_text=(
            "Member Search\n"
            "Member ID\n"
            "Search"
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

    provider = (
        create_action_provider()
    )

    print(
        "PROVIDER:",
        provider.provider_alias,
    )

    print(
        "MODEL:",
        provider.model_name,
    )

    action = await provider.decide(
        goal=(
            "Look up member 1001 "
            "and return the current "
            "savings balance."
        ),

        observation=observation,
    )

    print(
        action.model_dump_json(
            indent=2
        )
    )

    print(
        "REQUEST ID:",
        provider.last_request_id,
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )