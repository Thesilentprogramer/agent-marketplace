# Databricks Genie One MCP setup — staged guide

**Status:** Draft for an account-specific connection wizard. Kaliper cannot save a Databricks workspace MCP URL in the current format-1 catalog. No Databricks catalog entry or live connection is shipped here. The steps below come from [Databricks' Genie One MCP guide](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp) and [MCP authentication guide](https://docs.databricks.com/aws/en/agents/mcp-tools/authentication-networking); they have not been followed in a fresh customer-like workspace.

## Before you start

- A Databricks workspace administrator can enable and share the Genie One MCP service.
- The connecting user has Consumer access, `EXECUTE` on `system.ai.genie_one_mcp`, and `USE CATALOG` / `USE SCHEMA` on its parent objects.
- The user can read only the Genie spaces and underlying data relevant to the intended Slack workspace.

**Access:** Use each user's Databricks OAuth identity. Genie One answers questions over governed business data; this setup does not grant SQL write access. Keep tokens in the Kaliper web connection store, never in Slack.

## Setup steps to verify on a test workspace

1. Ask the Databricks admin to open **Unity Gateway → MCPs** and enable the Databricks-provided **Genie One MCP** if it is not available. [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services).
2. Grant the intended user Consumer access and the minimum MCP and data permissions. Do not grant workspace-wide access for convenience. [MCP authentication](https://docs.databricks.com/aws/en/agents/mcp-tools/authentication-networking).
3. Copy the full Genie One MCP URL from **Unity Gateway → MCPs**. It must use `https://<workspace-hostname>/ai-gateway/mcp-services/system.ai.genie_one_mcp?o=<workspace-id>`; the `o` value is the workspace ID. Do not use the deprecated `/api/2.0/mcp/genie` endpoint or another customer's URL. [Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp).
4. In the future Kaliper account-URL wizard, choose **Databricks**, enter that full MCP URL, and sign in as the intended user with OAuth requesting the `ai-gateway` scope. The wizard must verify the host, service path, and workspace ID and bind the connection to that user.
5. Run **Test connection**. List tools and ask a harmless question about a permitted Genie space. Confirm that a space the user cannot access remains unavailable before **Save and turn on**.

## Troubleshooting to confirm during the hands-on run

- **No tools appear:** Check Consumer access, `EXECUTE`, and parent catalog/schema privileges. Recheck that the URL names the intended MCP service.
- **Sign-in succeeds but a question fails:** Check the user's Genie space and underlying Unity Catalog permissions. Do not broaden the connection to a service principal.
- **Workspace is unreachable:** Check Databricks IP access lists and Kaliper's outbound network path.

## Screenshot capture plan

This `guide/` folder is reserved for real, cropped WebP screenshots from the same fresh-account run. Capture the MCP selection, permission grant, workspace URL, OAuth consent, and successful read-only test. See [the repository screenshot standard](../../../docs/connection-guides.md). Add a checked date only after a second person repeats the guide end to end.
