# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.1.4] - 2026-08-01

### Fixed

- Associate client trackers with the existing Tenda mesh-node device serving each client at setup.
- Expose a privacy-safe `mesh_node` attribute that follows roaming without frequent Device Registry writes.

## [0.1.3] - 2026-08-01

### Changed

- Enable new client device trackers by default.
- Safely enable existing Tenda entities disabled by the integration while preserving entities disabled by the user.

## [0.1.2] - 2026-08-01

### Added

- HACS-compatible repository metadata, documentation, validation, and automated release packaging.
- A local integration brand icon.

### Fixed

- Capture and reuse the router's dynamic authentication cookie.
- Retry one time after an expired HTML login response without reporting a false password error.
- Use Home Assistant's scanner entity base for client trackers while preserving stable MAC-based unique IDs.
- Remove stale foreign device-registry links previously associated with this config entry.

### Security

- Keep session tokens and cookies in memory only.
- Limit diagnostics to an explicit non-identifying allowlist.

[Unreleased]: https://github.com/Dmxsir/tenda-be3600-home-assistant/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/Dmxsir/tenda-be3600-home-assistant/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/Dmxsir/tenda-be3600-home-assistant/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Dmxsir/tenda-be3600-home-assistant/releases/tag/v0.1.2
