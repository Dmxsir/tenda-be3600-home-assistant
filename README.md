# Tenda BE3600 Mesh for Home Assistant

[![Validate](https://github.com/Dmxsir/tenda-be3600-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/Dmxsir/tenda-be3600-home-assistant/actions/workflows/validate.yml)
[![GitHub release](https://img.shields.io/github/v/release/Dmxsir/tenda-be3600-home-assistant)](https://github.com/Dmxsir/tenda-be3600-home-assistant/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

A local, read-only Home Assistant integration for the Tenda ME3 Pro BE3600 mesh system. It polls the router directly on the local network; no cloud account is required.

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with, endorsed by, or supported by Tenda.

## Compatibility

- Tenda ME3 Pro BE3600, internally reported as `MX12V3.0`
- Tested firmware: `V16.03.60.62_multi`
- Tested topology: one controller and two Ethernet-backhauled agents
- Validated on Home Assistant Core 2026.7.4; older versions have not been tested

The router API is undocumented and may change in future firmware releases.

## Features

- One Home Assistant device per mesh node, linked to the controller
- WAN and internet connectivity state
- WAN download/upload throughput and connection duration
- System uptime
- Mesh node count and total connected client count
- Per-node online state, connected clients, connection duration, and wired-backhaul state
- Dynamic client device trackers with connection details
- Redacted diagnostics based on a strict allowlist

All entities, including client trackers, are enabled by default. When upgrading from 0.1.2 or earlier, entities previously disabled by the integration are enabled automatically; entities disabled manually by the user remain disabled.

The integration is intentionally read-only. It does not expose switches, reboot controls, client blocking, or configuration changes.

## Install with HACS

1. Open HACS in Home Assistant.
2. Select **Integrations**.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add `https://github.com/Dmxsir/tenda-be3600-home-assistant` with category **Integration**.
5. Search for **Tenda BE3600 Mesh** and install it.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration**, search for **Tenda BE3600 Mesh**, and enter the router host and administrator password.

Use the router's local IP address if `tendawifi.com` does not resolve from Home Assistant.

## Manual installation

Download the versioned ZIP and checksum from the [latest release](https://github.com/Dmxsir/tenda-be3600-home-assistant/releases/latest), verify the SHA-256 checksum, and extract it into the Home Assistant configuration directory. The final path must be:

```text
/config/custom_components/tenda_be3600/
```

Restart Home Assistant, then add the integration from **Settings → Devices & services**.

## How it works

The integration authenticates directly with the router, stores only the uppercase MD5 digest required by the local API, and keeps session tokens and cookies in memory. The digest is password-equivalent and must be protected like the original password. A single coordinator polls safe, read-only modules every 30 seconds with a 10-second timeout.

No telemetry is sent by this integration. Home Assistant may still retain entity history according to your recorder settings.

## Known limitations

- No CPU, memory, temperature, Ethernet port speed, or duplex telemetry is exposed by the known API modules.
- Client RSSI values reported as `0` are treated as unavailable.
- New mesh nodes may require an integration reload before their entities appear.
- Only the model and firmware listed above have been verified.

## Troubleshooting

### Valid password is rejected

- Confirm the same password works in the router web interface.
- Prefer the router IP address over `tendawifi.com`.
- Wait before trying again if the router reports a temporary login lockout. The router exposes a three-attempt limit.
- Make sure another browser or application is not repeatedly replacing the router session.

### Entities are unavailable

- Confirm Home Assistant can reach the router on the local network.
- Reload the integration once after the router or Home Assistant restarts.
- Check that the router firmware has not changed.

When sharing logs, remove passwords, password digests, cookies, `stok`, `sign`, URLs containing session tokens, IP addresses, MAC addresses, serial numbers, client names, and hostnames. Never attach raw HAR, CFG, or diagnostics files to a public issue.

## Removal

Remove the integration entry from **Settings → Devices & services**. If installed manually, also delete `/config/custom_components/tenda_be3600` and restart Home Assistant. HACS installations can be removed from HACS.

## Reporting issues

Use the [issue templates](https://github.com/Dmxsir/tenda-be3600-home-assistant/issues/new/choose) and include Home Assistant version, integration version, router model, firmware version, and sanitized error text. Security issues must be reported privately as described in [SECURITY.md](SECURITY.md).

## Roadmap

- Optional per-client throughput and link-rate sensors
- LED, IPTV, and IGMP status
- Dynamic discovery of newly added mesh nodes without a reload
- Additional node, Ethernet port, Wi-Fi channel, channel width, and IPv6 telemetry when safe API captures become available

No write controls are planned for the read-only integration.

## Development

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q custom_components tests
powershell -File scripts/build_release.ps1
powershell -File scripts/verify_release.ps1
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and privacy requirements.

## License

[MIT](LICENSE)
