# Security policy

flowjAI Inventory Manager is designed to run inside a laboratory network. It is not intended to be exposed to the internet.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for a security problem.

Email **feedback.flowjai@gmail.com** with "SECURITY" in the subject line, describing:

- the version (shown on the About page),
- what the problem is and how it can be triggered,
- what an attacker could do with it.

Do not include databases, patient identifiers, lab IDs or other laboratory data.

You will receive an acknowledgement, and a fix will be released as soon as practical. Reporters are credited in the release notes unless they prefer otherwise.

## Supported versions

Security fixes are made to the latest release only. Please upgrade to the latest version from the [Releases page](https://github.com/ananthvikas/flowjai-inventory/releases) before reporting.

## Known limitations

These are documented design limitations, not vulnerabilities:

- HTTPS is not built in. Use a TLS reverse proxy if the app must be reached beyond a trusted local network.
- There is no login rate limiting. Keep the app on the internal network.
