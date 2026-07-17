# Security policy

## Reporting a vulnerability

If you find a security issue, email **rosscyking@gmail.com** with a description and steps to
reproduce it. Do not open a public issue for an exploitable problem. Please allow time for a fix
before disclosing it.

## Scope and design notes

This public-data project has **no accounts, authentication or user data**. The hosted app has a
small security surface:

- **No secrets in the repository.** Credentials live only in a local, gitignored `.env`
  (see [.env.example](.env.example)); nothing sensitive is committed. dbt reads them via
  `env_var()`, never inline.
- **The AI assistant is bring-your-own-key.** The free-form chat uses a key the visitor
  supplies for the current browser session. It is never stored, logged or committed, and the
  owner's key is never placed in the public deploy.
- **Read-only data access.** The MCP server and the app query committed Parquet through DuckDB
  with curated, read-only tools. They accept no arbitrary SQL and perform no writes.

## Supported versions

Security fixes land on `main`. The portable reliability-reference suite is also published as the
tagged `v0.2.0` release.
