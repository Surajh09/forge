# @suhe09/forge-cli

The developer-machine half of [Forge](https://github.com/Surajh09/forge): a Local Context Store, evidence
collection, and a local MCP server that serves coding agents from a replica instead of the network.

Forge gives developers and coding agents a shared, versioned, provenance-backed Context Bank scoped to a
feature. This package is what puts it on your machine.

## Install

```bash
npm install -g @suhe09/forge-cli
forge login      # OAuth in your browser, the same flow an agent uses
forge init       # point .mcp.json at the local stdio MCP server
forge doctor     # credential, server and store health
```

## Context

```bash
forge context pull PAYMENT   # fetch a feature into the local store
forge status                 # local vs cloud drift, and anything queued
forge context sync           # push what was captured offline, then pull
forge context show PAYMENT   # what this machine holds
forge context purge          # delete the store; the cloud keeps everything
```

## The store is disposable

It lives in `.forge/` as plain JSON, is gitignored, and holds only a replica plus an outbox. The cloud is
authoritative. `purge` refuses to run while statements are still queued, so nothing unsynced is lost.

**Offline works.** Reads fall back to the replica; writes queue in the outbox and upload on the next sync.
Evidence — branch, commit, changed files — is collected from the repository automatically, because Forge
Cloud cannot see your machine.

## MCP

`forge mcp` runs a local stdio MCP server that proxies the cloud: reads come from the replica when it is
fresh, writes go to the cloud and queue locally when offline.

```bash
claude mcp add --scope project --transport stdio forge -- npx -y @suhe09/forge-cli mcp
```

Agents without this package installed can still connect to the remote HTTP server at `/mcp`.

## Credentials

`forge login` runs OAuth 2.1 with PKCE against your Forge deployment. The resulting grant acts as you, capped
at the developer role, and narrowed by scopes (`context.read`, `context.write`, `context.supersede`,
`session.write`) plus an optional feature allow-list. Revoke any credential from the Forge UI at `/agent`.

Requires Node 20+.

MIT
