# Self-managed Grafana MCP setup — staged guide

**Status:** This is a private-network design guide, not a working Kaliper catalog connection. The [open-source Grafana MCP server](https://grafana.com/docs/grafana/latest/ai-tools/mcp/) runs under the customer's control. Kaliper's outbound bridge is not implemented in this repository, so no Connect button or catalog entry is offered yet.

## Before you start

- A Grafana 9.0+ administrator can create a service account scoped to the intended dashboards and data sources.
- A machine in the customer's network can reach that Grafana instance and run Grafana's official MCP package or container.
- The administrator can install a future signed Kaliper bridge without opening an inbound port.

**Access:** Read-only dashboard and observability tools. Use a least-privileged Grafana service account and disable MCP write tools. Keep its token in the customer's environment; do not send it to Kaliper or paste it into Slack.

## Setup steps to verify when the bridge exists

1. In Grafana, create a dedicated service account with only the dashboards, folders, and data sources that the Slack workspace should read. [Grafana authentication](https://grafana.com/docs/grafana/latest/ai-tools/mcp/configure/authentication/).
2. Create a service account token and store it in the customer's secret store. Configure `GRAFANA_URL` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` locally. Never use the deprecated `GRAFANA_API_KEY` setting. [Authentication](https://grafana.com/docs/grafana/latest/ai-tools/mcp/configure/authentication/).
3. Run the official Grafana MCP inside the same private network with `--disable-write`. Keep raw SQL tools off unless the underlying data-source credential is independently read-only. [Tool controls](https://grafana.com/docs/grafana/latest/ai-tools/mcp/configure/enable-and-disable-tools/).
4. Pair the future Kaliper outbound bridge through the Kaliper web wizard. The bridge should connect outward and expose only the reviewed Grafana tool allowlist; it must not expose a public MCP port.
5. Run **Test connection** to search for one permitted dashboard, and check that an unapproved folder is not visible. Then choose the intended Slack users or channels and **Save and turn on**.

## Troubleshooting to confirm during the hands-on run

- **Unauthorized:** Check token validity and service account RBAC before broadening access.
- **No dashboards:** Check folder and dashboard permissions for the service account.
- **Bridge offline:** Check its outbound TLS connection and local route to Grafana; do not expose Grafana publicly as a workaround.

## Screenshot capture plan

Reserve this `guide/` folder for fresh-account captures of service account creation, scoped permissions, local MCP configuration without the token value, bridge pairing, and the successful read-only test. Verify on a separate test environment with a second person before calling this guide checked. Follow [the repo standard](../../../docs/connection-guides.md).
