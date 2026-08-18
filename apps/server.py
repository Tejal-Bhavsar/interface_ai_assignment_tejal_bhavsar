from __future__ import annotations

import html

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse


app = FastAPI(
    title="LegacyCore X Demo"
)


MEMBERS = {
    "1001": {
        "name": "Alex Rivera",
        "checking": "$2,103.44",
        "savings": "$8,421.22",
    },

    "1002": {
        "name": "Jordan Lee",
        "checking": "$5,008.19",
        "savings": "$6,320.40",
    },

    "3333": {
        "name": "Session Recovery",
        "checking": "$1,010.00",
        "savings": "$3,333.33",
    },

    "4444": {
        "name": "Security Challenge",
        "checking": "$4,000.00",
        "savings": "$4,444.44",
    },

    "5555": {
        "name": "Transient Busy",
        "checking": "$5,000.00",
        "savings": "$5,555.55",
    },
}


def layout(title: str, body: str) -> str:

    return f"""
    <!doctype html>

    <html>

    <head>

        <title>{html.escape(title)}</title>

        <style>

            body {{
                font-family: Arial, sans-serif;
                background: #dedede;
                margin: 0;
            }}

            .top {{
                background: #173b65;
                color: white;
                padding: 10px;
                font-weight: bold;
            }}

            .shell {{
                width: 930px;
                margin: 14px auto;
                background: #f5f2e8;
                border: 2px solid #777;
                padding: 12px;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
            }}

            td,
            th {{
                border: 1px solid #888;
                padding: 8px;
                text-align: left;
            }}

            th {{
                background: #d6d2c4;
            }}

            .nav {{
                background: #c7c2b4;
                padding: 8px;
                margin-bottom: 12px;
            }}

            .error {{
                border: 2px solid #a00;
                background: #fee;
                padding: 15px;
            }}

            .warn {{
                border: 2px solid #b77700;
                background: #fff4ce;
                padding: 15px;
            }}

            button,
            input,
            select {{
                font: inherit;
                padding: 5px;
            }}

            .modal {{
                position: fixed;
                inset: 0;
                background: #0008;

                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .modalbox {{
                width: 520px;
                background: white;
                border: 4px solid #b77700;
                padding: 25px;
            }}

            .small {{
                font-size: 12px;
                color: #555;
            }}

        </style>

    </head>

    <body>

        <div class="top">
            NORTHSTAR CREDIT UNION — LEGACYCORE X
        </div>

        <div class="shell">

            <div class="nav">
                Accounts &gt; Member Servicing
                &nbsp; | &nbsp;
                System: DEMO
            </div>

            {body}

            <hr>

            <div class="small">
                Synthetic training data only.
            </div>

        </div>

    </body>

    </html>
    """


def search_page() -> str:

    body = """
        <h2>Member Search</h2>

        <form
            method="post"
            action="/legacy/search"
        >

            <table>

                <tr>

                    <th>
                        <label for="member-input">
                            Member ID
                        </label>
                    </th>

                    <td>
                        <input
                            data-sensitive="true"
                            id="member-input"
                            name="member_id"
                            autocomplete="off"
                        />
                    </td>

                </tr>

                <tr>

                    <td colspan="2">

                        <button type="submit">
                            Search
                        </button>

                    </td>

                </tr>

            </table>

        </form>

        <p class="small">

            Demo IDs:

            1001 success,
            9999 not found,
            5555 transient busy,
            3333 session expiry,
            7007 permission denied,
            2222 app error,
            4444 human handoff.

        </p>
    """

    return layout(
        "LegacyCore Search",
        body,
    )



@app.get(
    "/",
    response_class=HTMLResponse,
)
async def home():

    return HTMLResponse(
        """
        <h1>Computer-Use Assignment Demo</h1>

        <ul>
            <li>
                <a href="/legacy">
                    Legacy Bank
                </a>
            </li>
        </ul>
        """
    )

@app.get(
    "/legacy",
    response_class=HTMLResponse,
)
async def legacy():

    return HTMLResponse(
        search_page()
    )

@app.post(
    "/legacy/search",
)
async def search(
    member_id: str = Form(...),
):

    return RedirectResponse(
        f"/legacy/member/{member_id}",
        status_code=303,
    )


def fault_or_member(
    request: Request,
    member_id: str,
):

    if member_id == "9999":

        return HTMLResponse(
            layout(
                "Not Found",
                """
                <div class="error">

                    <h2>
                        Member not found
                    </h2>

                    <p>
                        No record matched the supplied identifier.
                    </p>

                </div>
                """,
            )
        )

    if member_id == "7007":

        return HTMLResponse(
            layout(
                "Permission Denied",
                """
                <div class="error">

                    <h2>
                        Permission denied
                    </h2>

                    <p>
                        Your operator role cannot view this member.
                    </p>

                </div>
                """,
            ),
            status_code=403,
        )

    if member_id == "2222":

        return HTMLResponse(
            layout(
                "Application Error",
                """
                <div class="error">

                    <h2>
                        Application Error
                    </h2>

                    <p>
                        LegacyCore error code LC-500.
                    </p>

                </div>
                """,
            ),
            status_code=500,
        )
    if (
        member_id == "3333"
        and not request.cookies.get(
            "session_recovered_3333"
        )
    ):

        response = HTMLResponse(
            layout(
                "Session Expired",
                """
                <div class="warn">

                    <h2>
                        Session expired
                    </h2>

                    <p>
                        Your session timed out.
                        Re-establish the session and retry.
                    </p>

                </div>
                """,
            )
        )

        response.set_cookie(
            "session_recovered_3333",
            "1",
        )

        return response

    if (
        member_id == "5555"
        and not request.cookies.get(
            "busy_seen_5555"
        )
    ):

        response = HTMLResponse(
            layout(
                "System Busy",
                """
                <div class="warn">

                    <h2>
                        System temporarily busy
                    </h2>

                    <p>
                        Host response delayed.
                        Retry this screen.
                    </p>

                </div>
                """,
            )
        )

        response.set_cookie(
            "busy_seen_5555",
            "1",
        )

        return response

    if member_id not in MEMBERS:

        return HTMLResponse(
            layout(
                "Not Found",
                """
                <div class="error">

                <h2>
                    Member not found
                </h2>

                <p>
                    No record matched the supplied identifier.
                </p>

            </div>
            """,
        )
    )
    

    member = MEMBERS[member_id]

    body = f"""

        <h2>
            Member Details
        </h2>

        <table>

            <tr>

                <th>
                    Member ID
                </th>

                <td data-sensitive="true">
                    {html.escape(member_id)}
                </td>

            </tr>

            <tr>

                <th>
                    Name
                </th>

                <td data-sensitive="true">
                    {html.escape(member["name"])}
                </td>

            </tr>

        </table>


        <h3>
            Accounts
        </h3>


        <table>

            <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Action</th>
            </tr>


            <tr>

                <td>
                    Checking
                </td>

                <td>
                    Open
                </td>

                <td>

                    <a
                        href="/legacy/member/{member_id}/account/checking"
                    >
                        Checking
                    </a>

                </td>

            </tr>


            <tr>

                <td>
                    Savings
                </td>

                <td>
                    Open
                </td>

                <td>

                    <a
                        href="/legacy/member/{member_id}/account/savings"
                    >
                        Savings
                    </a>

                </td>

            </tr>

        </table>
    """

    return HTMLResponse(
        layout(
            "Member Details",
            body,
        )
    )

@app.get(
    "/legacy/member/{member_id}",
    response_class=HTMLResponse,
)
async def member(
    request: Request,
    member_id: str,
):

    return fault_or_member(
        request,
        member_id,
    )


def account_page(
    member_id: str,
    kind: str,
):

    if member_id not in MEMBERS:
        return layout(
        "Not Found",
        """
        <div class="error">
            <h2>Member not found</h2>
        </div>
        """,
    )

    if kind not in {"checking", "savings"}:
        return layout(
        "Account Not Found",
        """
        <div class="error">
            <h2>Account type not found</h2>
        </div>
        """,
    )
    
    member = MEMBERS[member_id]

    balance = member[kind]

    modal = ""

    if (
        member_id == "4444"
        and kind == "savings"
    ):

        modal = """

        <div
            class="modal"
            id="security-modal"
        >

            <div class="modalbox">

                <h2>
                    Security verification required
                </h2>

                <p>
                    This exceptional state requires
                    operator acknowledgement.
                </p>

                <button
                    onclick="
                        document
                            .getElementById('security-modal')
                            .remove()
                    "
                >
                    Acknowledge &amp; Continue
                </button>

            </div>

        </div>
        """

    body = f"""

        <h2>
            Account Details
        </h2>


        <table>

            <tr>

                <th>
                    Account Type
                </th>

                <td>
                    {kind.title()}
                </td>

            </tr>


            <tr>

                <th>
                    Current Balance
                </th>

                <td data-sensitive="true">
                    {balance}
                </td>

            </tr>


            <tr>

                <th>
                    Status
                </th>

                <td>
                    Open
                </td>

            </tr>

        </table>


        <p>

            <a href="/legacy/member/{member_id}">
                Back to Member
            </a>

        </p>


        <form
            method="get"
            action="/legacy/member/{member_id}/open-subaccount"
        >

            <button type="submit">
                Open Sub-Account
            </button>

        </form>


        {modal}
    """

    return HTMLResponse(
        layout(
            "Account Details",
            body,
        )
    )
@app.get(
    "/legacy/member/{member_id}/account/{kind}",
    response_class=HTMLResponse,
)
async def account(
    member_id: str,
    kind: str,
):

    return account_page(
        member_id,
        kind,
    )

@app.get(
    "/legacy/member/{member_id}/open-subaccount",
    response_class=HTMLResponse,
)
async def open_subaccount(
    member_id: str,
):

    body = f"""

        <h2>
            Open Sub-Account
        </h2>


        <div class="warn">

            This operation changes customer state
            and requires approval.

        </div>


        <form>

            <table>

                <tr>

                    <th>
                        Product
                    </th>

                    <td>

                        <select name="product">

                            <option>
                                Savings Plus
                            </option>

                            <option>
                                Holiday Club
                            </option>

                        </select>

                    </td>

                </tr>


                <tr>

                    <td colspan="2">

                        <button type="button">
                            Confirm Open Sub-Account
                        </button>

                    </td>

                </tr>

            </table>

        </form>
    """

    return HTMLResponse(
        layout(
            "Open Sub-Account",
            body,
        )
    )

