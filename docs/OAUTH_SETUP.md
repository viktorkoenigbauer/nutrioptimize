# OAuth setup for the remote MCP server

NutriOptimize uses OAuth only for the public MCP endpoint. The YAZIO password,
database password and imported nutrition data remain on the self-hosted server.
The identity provider receives login metadata, but it never receives diary
entries or YAZIO credentials.

## Why an external identity provider

The application is a resource server, not an identity product. Implementing
password storage, account recovery, MFA, OAuth client registration and token
rotation here would create a large security-sensitive subsystem. V1 therefore
validates short-lived JWT access tokens from an established OAuth provider.
Auth0 is the documented example because it supports the MCP resource parameter,
PKCE and Client ID Metadata Documents (CIMD). The code remains provider-neutral
for any issuer that supplies RS256 JWTs and a public JWKS endpoint.

## Trust chain

```text
user -> AI client -> Auth0 login and consent -> short-lived access token
                                                |
                                                v
                                   NutriOptimize MCP resource server
                                                |
                                     signature, issuer, audience,
                                     expiry, scope and subject checks
                                                |
                                                v
                                          read-only diary tools
```

The AI client receives an access token, never the user's Auth0 or YAZIO
password. The server accepts the token only when all checks succeed.

## Auth0 tenant configuration

Create a separate Auth0 tenant for NutriOptimize, then configure:

1. Create an API named `NutriOptimize MCP`.
2. Use your MCP resource URL, for example
   `https://nutrition.example.com/mcp/`, as its immutable API identifier.
3. Select `RS256` signing and add the permission `nutrition:read`.
4. Enable the Resource Parameter Compatibility Profile in the tenant's
   advanced settings. MCP clients send an RFC 8707 `resource` parameter rather
   than Auth0's historical `audience` parameter.
5. Enable refresh tokens for the API so compatible clients do not require a
   fresh login whenever the short-lived access token expires.
6. Create only the intended human account. Disable public sign-up for the
   database connection unless this deployment is deliberately expanded.
7. Copy the user's immutable Auth0 user ID (`sub`, commonly beginning with
   `auth0|`) from the Auth0 user details page. Do not use an email address as
   the allowlist identity.
8. Register ChatGPT's CIMD client
   `https://chatgpt.com/oauth/client.json` in Auth0. This avoids an open Dynamic
   Client Registration endpoint. Register other AI clients separately rather
   than enabling unrestricted DCR merely for convenience.

Exact dashboard labels can change. Verify the resulting OAuth discovery
document instead of trusting that a toggle was saved.

## Server configuration

Set the following non-secret values in `.env` on the server. Replace the Auth0
tenant hostname and user subject with the real values; preserve the issuer's
trailing slash when Auth0 publishes one.

```text
MCP_AUTH_MODE=oauth
MCP_OAUTH_ISSUER=https://YOUR-TENANT.eu.auth0.com/
MCP_OAUTH_AUDIENCE=https://nutrition.example.com/mcp/
MCP_OAUTH_JWKS_URL=https://YOUR-TENANT.eu.auth0.com/.well-known/jwks.json
MCP_OAUTH_RESOURCE_URL=https://nutrition.example.com/mcp/
MCP_OAUTH_REQUIRED_SCOPES=nutrition:read
MCP_OAUTH_ALLOWED_SUBJECTS=auth0|YOUR-IMMUTABLE-USER-ID
```

These values are identifiers and public metadata, not client secrets. No Auth0
client secret belongs in this repository or in the application container.

Rebuild and restart the API after changing the mode. Keep the existing static
bearer token for the private REST diagnostics under `/v1`; the public MCP route
switches to OAuth.

## Plugin connection declaration

After the live server passes the verification below, add this `mcp.json` to the
NutriOptimize plugin package. Do not publish it before OAuth works on the server,
because that would replace a working skills-only plugin with a broken connection.

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "nutrioptimize": {
      "type": "streamable-http",
      "url": "https://nutrition.example.com/mcp/",
      "extensions": {
        "com.openai": {
          "auth": {
            "type": "oauth",
            "client": {
              "mode": "cimd"
            },
            "resource": "https://nutrition.example.com/mcp/",
            "baseScopes": [
              "nutrition:read",
              "offline_access"
            ]
          }
        }
      }
    }
  }
}
```

`cimd` lets ChatGPT identify itself with its HTTPS metadata document. Auth0 must
approve that document as described above. The `offline_access` scope asks for a
refresh token; the provider and client still decide whether one is issued.

## What the server publishes

For the MCP resource URL ending in `/mcp/`, RFC 9728 discovery is available at:

```text
https://nutrition.example.com/.well-known/oauth-protected-resource/mcp/
```

An unauthenticated request to `/mcp/` returns `401 Unauthorized` with a
`WWW-Authenticate` header pointing to that document. The document tells the
client which authorization server and scope to use.

## Verification order

1. Open the protected-resource metadata URL and verify the exact resource,
   issuer and `nutrition:read` scope.
2. Open the issuer's discovery document and verify its issuer, authorization,
   token and JWKS endpoints plus PKCE `S256` support.
3. Confirm that `/mcp/` returns `401` without a token.
4. Connect with MCP Inspector and complete login and consent.
5. Call `get_profile`; it must return the configured immutable subject.
6. Call `get_sync_status`, one day, and a short range.
7. Try a different Auth0 user; access must fail even if that account can log in.
8. Only then update or connect the ChatGPT plugin.

Never paste access tokens, refresh tokens, client secrets or YAZIO credentials
into an issue, documentation, terminal history or chat.
