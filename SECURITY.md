# Security policy

## Supported versions

Security fixes are provided for the latest published release.

## Report a vulnerability privately

Do not open a public issue for a security vulnerability. Use GitHub's [private vulnerability reporting](https://github.com/Dmxsir/tenda-be3600-home-assistant/security/advisories/new).

Describe the impact, affected version, reproduction steps, and a proposed mitigation if known. Allow reasonable time for investigation before public disclosure.

## Sensitive data

Never submit router passwords, uppercase MD5 password digests, cookies, `stok`, `sign`, URLs containing session tokens, IP or MAC addresses, serial numbers, client names, hostnames, or raw diagnostics. Do not upload HAR, CFG, or log files from the router or Home Assistant.

The integration stores the router's uppercase MD5 password digest in the Home Assistant config entry because the local API requires it. That digest is password-equivalent. Session tokens and the dynamic router cookie are kept in memory only.
