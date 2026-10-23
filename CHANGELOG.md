# Changelog

All notable changes to NutriOptimize will be recorded here. The project follows
[Semantic Versioning](https://semver.org/) while it is in beta.

## 0.1.0-beta.1 - 2026-10-23

### Changed

- Prepared the repository for the first public single-user beta.
- Updated OAuth token validation to a patched PyJWT release.
- Made first-time setup recover cleanly after an interruption.
- Made synthetic onboarding data follow the current date so a fresh fixture
  sync always produces a useful example day.
- Added the MIT License for the public beta.

### Fixed

- Made runtime file ownership independent of the server checkout permissions so
  the restricted container user can always read the application code.

### Security

- Removed the owner-specific ChatGPT plugin package from the distributable
  repository. Each operator creates a private plugin for their own endpoint.
- Replaced the server-specific SSH account in the hardening example with a
  clearly marked placeholder.
- Added dependency monitoring and privacy-safe contribution templates.
- Pinned container images and the CI checkout action to reviewed revisions.
- Limited the operator REST bearer token to the API container.
