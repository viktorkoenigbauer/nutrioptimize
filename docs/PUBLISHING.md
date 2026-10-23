# GitHub publication checklist

This checklist deliberately separates “the current files look safe” from “the
entire repository history is safe.” Complete it before making the repository
public.

## 1. Decide the public scope

- State that the current version is a single-user reference implementation.
- Clearly label the YAZIO integration as unofficial and unsupported, and
  document its access method and terms-related risk.
- Publish only synthetic fixtures and sanitized screenshots.
- Decide which operating systems and deployment methods are supported.

## 2. Verify licensing

NutriOptimize is distributed under the MIT License. Keep `LICENSE` in release
archives and substantial copies of the project.

Third-party packages and copied material must be compatible with the selected
license. Record required notices rather than assuming compatibility.

## 3. Inspect files and history

Search the working tree and every Git commit for:

- `.env` files and Docker secret contents;
- API tokens, passwords, private keys and recovery codes;
- real nutrition exports, database dumps and backups;
- public and private IP addresses, personal hostnames and email addresses;
- logs, screenshots and exception messages containing personal data.

Local ChatGPT/Codex project metadata (`AGENTS.md`, `sources/`, `.agents/`,
`.codex/` and `.aws/`) is excluded by `.gitignore` and is not part of the public
software project.

If a secret ever entered Git history, rotate it first and remove it from history.
A `.gitignore` rule only prevents future additions.

The beta audit found no private keys, access tokens, JWTs, database dumps or
production IP address in the tracked files or commit history. Older commits do
contain the maintainer's public project hostname, contact address and an obsolete
personal plugin identifier. These are not credentials, but the current tree no
longer ships the owner-specific plugin package.

## 4. Quality checks

- run unit tests;
- validate and build the Compose project;
- perform the documented fixture verification sequence;
- read every setup step on a clean VM or have a second person do so;
- verify that comments explain decisions instead of narrating syntax;
- confirm that README, privacy, security and architecture documents agree.

## 5. Configure the GitHub repository

After the initial private push:

- keep the repository private during the final review;
- enable secret scanning and push protection when available;
- enable Dependabot alerts and reviewed update pull requests;
- enable Private Vulnerability Reporting;
- protect the default branch and require passing tests;
- add a minimal CI workflow with pinned, reviewed action versions;
- add issue and pull-request templates that prohibit personal data and secrets.

Only then change visibility to public.

## 6. Release discipline

Create a versioned release only after documenting upgrade and migration steps.
Release notes should identify security, privacy, schema and compatibility
changes. Never attach real configuration, secrets or database samples.

## 7. MCP/plugin packaging later

Once a stable HTTPS MCP endpoint exists, a portable plugin package can reference
that endpoint. The manifest must contain no bearer token, OAuth token or client
secret. OAuth mode is suitable for a private single-user plugin when the stable
subject allowlist is configured. A generally distributed multi-user service
also requires per-user data ownership and authorization; OAuth alone is not
tenant isolation.
