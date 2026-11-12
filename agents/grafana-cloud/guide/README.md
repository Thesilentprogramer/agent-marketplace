# Grafana Cloud MCP setup — publication candidate

**Status:** Guide draft from [Grafana's official Cloud MCP documentation](https://grafana.com/docs/grafana-cloud/ai-tools/mcp-servers/cloud-mcp/). The endpoint and documented read tools are identified, but no fresh Grafana account has completed OAuth or an authenticated `tools/list` probe for this branch. The catalog candidate is under `draft/`, outside the automatic publisher.

## Before you start

- A Grafana Cloud stack with Assistant available and its required terms accepted.
- The connecting user has the **Assistant Cloud MCP User** role or `grafana-assistant-app.cloud-mcp:access` permission.
- The user can read only the intended dashboards, metrics, logs, and traces through Grafana RBAC.

**Access:** Sign in as each Grafana user. Grant **Read** only; clear **Query** and **Write** on the OAuth consent page. Grafana says Query access can execute raw SQL that modifies data if the underlying data source allows it. Kaliper must expose only reviewed read tools and hold each user's OAuth token in its connection store.

## Setup steps to verify on a test stack

1. Ask a Grafana Cloud administrator to check **Assistant** availability and grant the intended user **Assistant Cloud MCP User** access. [Prerequisites](https://grafana.com/docs/grafana-cloud/ai-tools/mcp-servers/cloud-mcp/#before-you-begin).
2. In Kaliper's catalog, choose **Grafana Cloud** and **Sign in with Grafana**. The vendor endpoint is `https://mcp.grafana.com/mcp`; Grafana's stack-specific path can also identify one stack. [Connect your AI agent](https://grafana.com/docs/grafana-cloud/ai-tools/mcp-servers/cloud-mcp/#connect-your-ai-agent).
3. Choose the intended Grafana Cloud stack in the browser. If the user has several stacks, verify the one shown in the consent page before authorizing.
4. On the Grafana consent page, leave **Read access** selected and clear **Query access** and **Write access**. [Configure access](https://grafana.com/docs/grafana-cloud/ai-tools/mcp-servers/cloud-mcp/#configure-access).
5. Back in Kaliper, run **Test connection**. Search for a known permitted dashboard and confirm no write or raw SQL tools are exposed. Choose **Save and turn on** for the intended Slack workspace.

## Troubleshooting to confirm during the hands-on run

- **Access is unavailable:** Check Assistant availability, terms acceptance, and the user's MCP role.
- **Wrong stack:** Revoke this connection in Grafana Assistant settings and reconnect to the intended stack.
- **Unexpected write or SQL tools:** Stop and revoke; reconnect with only Read selected before enabling the agent.

## Screenshot capture plan

Reserve this `guide/` folder for real cropped WebP captures of the Cloud MCP access screen, stack choice, consent checkboxes with only Read selected, and Kaliper's successful read test. Do not use vendor documentation page captures as substitutes for a fresh-account run. A second person must repeat the steps and confirm light, dark, and phone-width layout before adding a `connection.guide.checked` date. Follow [the repo standard](../../../docs/connection-guides.md).
