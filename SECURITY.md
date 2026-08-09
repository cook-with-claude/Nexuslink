# Security Policy

## Supported Versions

This project is pre-release. Security fixes currently target the `main` branch
until versioned release channels are defined.

## Automated Checks

Every push and pull request runs a `security` job in CI, which also ticks weekly
so newly-disclosed advisories surface without a push:

- **pip-audit** — known CVEs in the pinned runtime lock (`constraints.txt`).
- **bandit** — Python static analysis over `app/`, `main.py`, `tools/`, gated at
  medium severity and confidence. Reviewed false positives carry an inline
  `# nosec <ID>`; no check is disabled wholesale.
- **gitleaks** — secret scanning across the full commit history, not just the tip.

These are gates, not reports: a finding fails the build. They do not replace the
human review protocol in `COLLAB.md`.

## Reporting a Vulnerability

Do not open public issues for suspected vulnerabilities. Use GitHub private
vulnerability reporting if it is enabled for this repository; otherwise contact
the repository owner through a private channel already shared with maintainers.

Please include:

- Affected area or file path.
- Steps to reproduce.
- Expected impact.
- Any logs, screenshots, or proof-of-concept details that can be shared safely.

The maintainer should acknowledge reports within 3 business days and prioritize
fixes based on exploitability, affected data, and production exposure.
