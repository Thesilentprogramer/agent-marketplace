# Snowflake-managed MCP setup — staged guide

**Status:** Draft for an account-URL and OAuth wizard. No Snowflake catalog entry is shipped: the current catalog has one global `service.url`, while each customer creates its own Snowflake MCP server. These steps are based on [Snowflake's managed MCP documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp) and await a fresh-account run and second-person verification.

## Before you start

- A Snowflake administrator can create an MCP server object and an OAuth security integration.
- A dedicated role can use only the intended Cortex Search and Cortex Analyst objects. Grant it only to users who need the connection.
- Know the account URL, database, schema, and MCP server name. A Snowflake warehouse and network-policy change may also be required.

**Access:** Begin with Search and Analyst tools only. Do not expose SQL execution, generic procedures, coding agents, or mutating tools in the first release. Each person signs in with their own Snowflake identity; the administrator's OAuth client secret stays in Kaliper's encrypted web setup, never in Slack.

## Setup steps to verify on a test account

1. Create and grant a narrow role for the intended Search and Analyst objects. Confirm the role can access the MCP server and underlying objects. [Access control](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp#access-control).
2. Create a Snowflake-managed MCP server with only those reviewed tools. Record its fully qualified database, schema, and server name. [Create an MCP server](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp#create-an-mcp-server).
3. Create a Snowflake OAuth security integration for Kaliper's callback URL, restrict its allowed roles, and disable secondary roles. Snowflake does not support dynamic client registration for this server. [Set up OAuth](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp#set-up-oauth-authentication).
4. In the future Kaliper account-URL wizard, enter the account URL, database, schema, MCP server name, OAuth client ID, and client secret. Kaliper must construct and verify `https://<account_url>/api/v2/databases/<database>/schemas/<schema>/mcp-servers/<name>` rather than accept an arbitrary destination. [MCP server URL](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp#mcp-server-url).
5. Sign in as a user with the narrow MCP role. Run **Test connection**: list tools and run one harmless Search or Analyst request. Check the effective role and that SQL execution and unapproved objects are absent before **Save and turn on**.

## Troubleshooting to confirm during the hands-on run

- **OAuth consent fails:** Compare the callback URL character for character with `OAUTH_REDIRECT_URI` and check the current client secret.
- **Sign-in succeeds but no tools appear:** Check the user's default role, `USAGE` on the MCP server, and object grants.
- **`invalid_client` with valid credentials:** Check Snowflake network policy; Kaliper's outbound IP must be allowed where the account requires it.

## Screenshot capture plan

Reserve this `guide/` folder for real cropped WebP captures of the role grants, MCP server tool selection, OAuth integration, copied server URL, consent, and successful read-only test. The screenshots and guide `checked` date must come from the same fresh-account run and second-person check. Follow [the repo standard](../../../docs/connection-guides.md).
