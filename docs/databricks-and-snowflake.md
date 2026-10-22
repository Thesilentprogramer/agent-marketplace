# Databricks and Snowflake

Supabase and BigQuery are catalog entries because each has one public MCP address. Databricks and Snowflake do not. A catalog entry stores one `service.url`, and every client server calls that same address. These two cannot.

The pages on [mcpservers.org](https://mcpservers.org/) are a directory. That site is not an MCP server, so it cannot be a `service.url`.

## Databricks

The listing is [databrickslabs/mcp](https://mcpservers.org/servers/databrickslabs/mcp).

That repository is experimental and not covered by a Databricks support agreement. Its Unity Catalog server is marked deprecated on the page. Databricks tells you to use the managed MCP instead.

The managed address is per workspace:

```text
https://<workspace-hostname>/ai-gateway/mcp-services/<mcp-name>
```

The same repository can also be deployed as a Databricks App. The address is then that customer's app, and it must end with `/api/mcp/`:

```text
https://<app-name>.databricksapps.com/api/mcp/
```

There is no single public host. One catalog row would point every client server at one workspace. The local `stdio` server is not a remote MCP address either, so the catalog cannot point at it.

## Snowflake

The listing is [Snowflake-Labs/mcp](https://mcpservers.org/servers/Snowflake-Labs/mcp).

That page marks the project deprecated and says to use the official Snowflake-managed MCP server. The deprecated server runs where you start it. The address in its docs is `http://localhost:9000/snowflake-mcp`.

The official server is one the customer creates inside their own account:

```text
https://<account_url>/api/v2/databases/<database>/schemas/<schema>/mcp-servers/<name>
```

The account, database, schema, and server name are different for each customer. The server does not do automatic client registration: the customer creates an OAuth security integration and supplies its client id and secret. A catalog entry cannot invent that URL, and it cannot share one OAuth app across accounts.

## What would not fix it

Publishing either GitHub repository as a package, the way Slack is packaged, would ship a server its own page says to leave. The catalog would still need each client's workspace or account address, which `service.url` does not take from a form field.
