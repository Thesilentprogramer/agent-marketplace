# MotherDuck setup reference

**Draft reference, not a tested catalog guide.** The image is a screenshot of [MotherDuck's public MCP documentation](https://motherduck.com/docs/sql-reference/mcp/), captured 2026-11-09. It documents the fixed remote URL and OAuth support; it does not show Kaliper's authorization screen.

![MotherDuck documentation identifying its remote MCP endpoint](vendor-doc-reference.png)

## Proposed customer path

1. Confirm your MotherDuck user can see the database to connect.
2. In Kaliper, add MotherDuck and choose **Sign in with MotherDuck**.
3. Approve the MotherDuck OAuth request for that user.
4. Use **Test connection**, ask for the accessible databases, then **Save and turn on**.

MotherDuck's remote server offers read and write functionality; this catalog only exposes its read tools. Capture the actual OAuth and Kaliper test screens on a fresh account, verify tool restrictions, and have a second person complete the path before publishing a `connection.guide`.
