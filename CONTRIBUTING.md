# Contributing

Contributions are welcome when they preserve the integration's local, read-only scope.

## Before opening a pull request

1. Keep changes focused and avoid new dependencies unless Home Assistant requires them.
2. Do not add switches, reboot actions, client blocking, or router configuration writes.
3. Never commit HAR, CFG, log, diagnostic, credential, token, cookie, or real network-identifier data.
4. Use synthetic documentation-range addresses and identifiers in tests.
5. Update the changelog for user-visible changes.
6. Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q custom_components tests
python scripts/validate_repository.py
powershell -File scripts/build_release.ps1
powershell -File scripts/verify_release.ps1
```

## Bug reports

Use the issue template and provide only sanitized text. If reproducing a new firmware response requires a capture, do not attach it publicly. First open a sanitized issue describing which fields or modules are missing, or use private vulnerability reporting if the capture contains security-sensitive behavior.
