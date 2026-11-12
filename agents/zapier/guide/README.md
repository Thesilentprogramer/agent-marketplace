# Zapier MCP setup — publication candidate

**Status:** Guide draft from [Zapier's official custom-client instructions](https://docs.zapier.com/mcp/get-started/connect/other). This is a third-party gateway, not an official MCP for each connected app. The bearer endpoint and static agentic-mode read tools are documented, but they have not been verified with a Kaliper-connected test account. The catalog candidate is under `draft/`, outside automatic publishing.

## Before you start

- A Zapier account and app connections containing only data the intended Slack workspace should read.
- Permission to create a Zapier MCP server and generate its connection token.
- An administrator who can review enabled Zapier actions and rotate the token if needed.

**Access:** Kaliper would expose only the reviewed read tools, but the Zapier server's long-lived token itself can run every tool that server offers, including writes outside Kaliper. Anyone holding it can use the server, so enter it only in Kaliper's web form. Never put it in a URL, Slack, a guide screenshot, or a support ticket. Zapier app actions and task billing remain governed by the customer's Zapier account.

## Setup steps to verify on a test account

1. Open [Zapier MCP](https://mcp.zapier.com/), select **Add MCP server**, and choose **Other** as the AI agent. [Custom-client setup](https://docs.zapier.com/mcp/get-started/connect/other).
2. Review the connected apps and remove or disable anything the Slack workspace should not read. Keep the server in agentic mode for the proposed stable read meta-tools; managed mode exposes customer-specific action names instead. [Tool modes](https://docs.zapier.com/mcp/overview/how-tools-work).
3. Open the server's **Settings** tab and select **Generate token** in the **API token** section. Copy the **Token** only, not the Connection URL containing it. Zapier shows the token once. [Generate a connection token](https://docs.zapier.com/mcp/get-started/connect/other#connect-with-a-connection-token).
4. In Kaliper's web catalog, select **Zapier MCP** and paste the token into the password field. Kaliper must send it to `https://mcp.zapier.com/api/v1/connect` as `Authorization: Bearer`, never in the query string.
5. Run **Test connection**. Confirm the server lists the proposed read meta-tools and that a harmless read action succeeds. Check that write, action-enabling, and workflow tools are not exposed by Kaliper before **Save and turn on**.

## Troubleshooting to confirm during the hands-on run

- **Unauthorized:** Check whether the token was rotated. Generate a new one in Zapier Settings and update Kaliper's encrypted form.
- **No useful actions:** Connect the intended app in Zapier and review its available read actions; a new server can be empty.
- **Unexpected tools or actions:** Disable the Kaliper connection, review Zapier server mode and enabled app connections, then repeat the tool-list check.

## Screenshot capture plan

Reserve this `guide/` folder for real cropped WebP captures of server creation, app/action review, Settings token control **before** generating the secret, Kaliper's masked form, and read-only connection test. The token value and token-bearing URL must never appear in any screenshot. A second person must repeat the full flow before adding a `connection.guide.checked` date. Follow [the repo standard](../../../docs/connection-guides.md).
