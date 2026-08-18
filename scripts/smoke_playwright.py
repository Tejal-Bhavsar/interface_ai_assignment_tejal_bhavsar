import asyncio

from cua.models import (
    LocatorCandidate,
    LocatorKind,
    TargetDescriptor,
)

from cua.playwright_surface import (
    PlaywrightSurface,
)


async def main():
    async with PlaywrightSurface(
        headless=False,
        slow_mo_ms=300,
    ) as surface:

        await surface.navigate(
            "http://127.0.0.1:8000/legacy"
        )

        observation = (
            await surface.observe()
        )

        print(
            "TITLE:",
            observation.title,
        )

        print(
            "URL:",
            observation.url,
        )

        print(
            "CONTROLS:"
        )

        for control in (
            observation.controls
        ):
            print(
                control.model_dump()
            )

        member_input = TargetDescriptor(
            description="Member ID input",
            locators=[
                LocatorCandidate(
                    kind=LocatorKind.LABEL,
                    value="Member ID",
                )
            ],
        )

        resolved_input = (
            await surface.resolve_target(
                member_input
            )
        )

        await surface.fill(
            resolved_input,
            "1001",
        )

        search_button = TargetDescriptor(
            description="Search button",
            locators=[
                LocatorCandidate(
                    kind=LocatorKind.ROLE,
                    role="button",
                    name="Search",
                )
            ],
        )

        resolved_search = (
            await surface.resolve_target(
                search_button
            )
        )

        await surface.click(
            resolved_search
        )

        await surface.wait(500)

        print(
            "AFTER SEARCH:",
            surface.current_url,
        )

        await surface.wait(
            3000
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )