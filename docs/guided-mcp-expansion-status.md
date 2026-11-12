# Guided MCP expansion: release status

This branch prepares five connection paths. **None is published or integrated by this branch.** The two format-1 catalog candidates live under `agents/<id>/draft/`, outside the `agents/*/catalog-*.json` path that [automatically publishes on merge](../.github/workflows/publish.yml). Their missing `connection.guide.checked` value is intentional: a fresh-account walkthrough and second reviewer have not happened.

| Source | Hosting and auth | What this branch contains | Release blocker |
|---|---|---|---|
| Grafana Cloud | Grafana-hosted fixed HTTPS MCP; user OAuth | Read-only draft catalog and [setup guide](../agents/grafana-cloud/guide/README.md) | Live OAuth and `tools/list`, fresh-account screenshots, second-person guide check |
| Zapier MCP | Zapier-hosted third-party gateway; per-server bearer connection token | Read-only agentic-mode draft catalog and [setup guide](../agents/zapier/guide/README.md) | Live token and tool probe, static read-tool check, fresh-account screenshots, second-person guide check |
| Databricks Genie One | Databricks-managed, workspace URL and user OAuth | [Staged guide](../agents/databricks/guide/README.md) | Account-URL wizard in the separate app, live tool probe, screenshots and reviewer |
| Snowflake-managed MCP | Snowflake-managed, account URL and customer OAuth app | [Staged guide](../agents/snowflake/guide/README.md) | Account-URL wizard in the separate app, live tool probe, screenshots and reviewer |
| Self-managed Grafana | Customer-hosted local MCP and scoped service-account token | [Staged guide](../agents/grafana-self-managed/guide/README.md) | Signed outbound bridge, local tool filtering, screenshots and reviewer |

## Before publishing Grafana Cloud or Zapier

1. On a fresh vendor test account, perform the guide exactly as written and capture focused screenshots directly in that source's `guide/` folder, as the catalog image loader expects. Mask account identifiers and every secret. A second person repeats the setup; record their test-account type and the check date in the PR. Follow [the guide standard](connection-guides.md).
2. Run a real authenticated MCP `tools/list` and one harmless read call through the Kaliper catalog page. Verify every proposed tool name, description, and read-only behavior. For Grafana, grant **Read** only; Query can run mutating SQL. For Zapier, check the server remains in agentic mode and that the exposed router tool list excludes action enabling and write execution. The Zapier bearer token still has broader server-side power and must be protected accordingly.
3. After verification, move each candidate from `draft/catalog-1.0.0.json` to `agents/<id>/catalog-1.0.0.json`. Add screenshot metadata with `uv run catalog guide-images agents/<id>/catalog-1.0.0.json`, set `connection.guide.checked` to the verified date, and validate the entry. Run the full suite and inspect the catalog page at desktop and phone widths before merging.
4. Only then merge. A catalog file under the top-level agent folder triggers automatic publication. If a probe, consent flow, or guide check fails, leave the candidate in `draft/` and record the specific failure; do not substitute a documentation screenshot or an invented `checked` date.

## Follow-on connection work

Databricks and Snowflake need per-connection vendor-host validation, OAuth identity binding, and authenticated tool discovery in Kaliper's separate app. The format-1 catalog stores one global `service.url` and cannot safely express those account URLs. Self-managed Grafana needs the customer-side outbound bridge; no customer token belongs in Slack or the global catalog. Generic private MCP support is outside this release.

## Source verification

- [Grafana Cloud MCP](https://grafana.com/docs/grafana-cloud/ai-tools/mcp-servers/cloud-mcp/): hosted Streamable HTTP, OAuth, Read/Query/Write consent levels.
- [Zapier custom-client connection](https://docs.zapier.com/mcp/get-started/connect/other) and [tool modes](https://docs.zapier.com/mcp/overview/how-tools-work): bearer token at a fixed endpoint; agentic mode has stable meta-tools, including separate read and write execution.
- [Databricks Genie One](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp) and [MCP authentication](https://docs.databricks.com/aws/en/agents/mcp-tools/authentication-networking): workspace-specific service and user identity.
- [Snowflake-managed MCP](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp): account-specific server and OAuth security integration without dynamic registration.
- [Self-managed Grafana MCP](https://grafana.com/docs/grafana/latest/ai-tools/mcp/): local server, scoped service-account authentication, tool controls.
- Draft logos come from [Grafana's own SVG icon](https://github.com/grafana/grafana/blob/main/public/img/grafana_icon.svg) and [Zapier's official press assets](https://zapier.com/press). Both are embedded in their draft catalog JSON.
