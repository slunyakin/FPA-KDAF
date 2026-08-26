# Security Policy

## Supported Versions

KDAF is pre-1.0. Security fixes are handled on the default branch until versioned release branches exist.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately by opening a GitHub security advisory for this repository, or by contacting the repository owner through GitHub if advisories are unavailable.

Do not open a public issue for secrets, credential exposure, privilege escalation, or data-leak vulnerabilities.

## Local Development Secrets

The credentials in `.env.example` and `config/kdaf.example.toml` are development placeholders. Replace them before using KDAF with any non-local data or shared environment.

## Package Publication

KDAF package publication uses PyPI Trusted Publishing with GitHub OIDC and protected environments.
Do not add long-lived PyPI API tokens to repository or environment secrets. Release artifacts must be
built once, validated, and published without rebuilding. A live adapter selected without its optional
driver returns the corresponding installation extra without returning connection settings or secrets.
