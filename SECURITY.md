# Security Policy

## Reporting a vulnerability

If you find a security issue, please email **rosscyking@gmail.com** with a description and
steps to reproduce. Please do not open a public issue for anything exploitable — allow a
reasonable window to address it before disclosure.

## Scope and design notes

This is a public data project with **no accounts, authentication, or user data** — there is
nothing to breach on the hosted app. A few deliberate choices keep it safe:

- **No secrets in the repository.** Credentials live only in a local, gitignored `.env`
  (see [.env.example](.env.example)); nothing sensitive is committed. dbt reads them via
  `env_var()`, never inline.
- **The AI assistant is bring-your-own-key.** The free-form chat uses a key the visitor
  supplies in their browser session only — it is never stored, logged, or committed, and the
  owner's key is never placed in the public deploy.
- **Read-only data access.** The MCP server and the app query committed Parquet through DuckDB
  with curated, read-only tools — no arbitrary SQL, no writes.

## Supported versions

This project tracks `main`; fixes land there. It cuts no tagged releases.
