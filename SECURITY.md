# Security policy

## Supported version

OpenFabro is a developer preview. Security fixes are developed on the current `main` branch;
there is no long-term maintenance commitment for older snapshots.

## Report a vulnerability

Use the repository's [private vulnerability reporting form](https://github.com/AllenPeng0209/OpenFabro/security/advisories/new)
when available. If private reporting is unavailable, open a minimal issue requesting a private
reporting channel without including exploit details, credentials, access links, or private
project files.

Include the affected commit, environment, reproduction steps, expected impact, and a minimal
sanitized example. Do not post API keys, settings files, supplier-link secrets, personal data,
or unrestricted archives of a real project.

## Local operation

The default `python -m openfabro` command binds to `127.0.0.1`. The application can access local
project files and use configured AI and supplier credentials. Keep it on trusted devices and
configure authentication before making it reachable from another computer. The legacy
`run.sh`/`run.bat` launchers listen on all network interfaces unless a host override is supplied.

Local operation does not make AI inference offline: configured cloud providers receive the
context sent to them. Review provider settings and project-sharing permissions for your use case.
