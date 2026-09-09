# Security

Report vulnerabilities privately to Nick Parvath at [tonickred@gmail.com](mailto:tonickred@gmail.com) before public disclosure. Do not include live API keys, candidate records, résumés, or other secrets in a public issue. The unreleased development branch and the latest tagged `0.1.x` release, once published, are the supported versions.

This project intentionally has no built-in authentication. A publicly reachable deployment exposes its dashboard and API. Operators are responsible for understanding that choice and for keeping secrets and candidate data out of images, logs, source control, and public artifact URLs.

API keys and database credentials must be supplied through environment variables. Browser automation must not bypass CAPTCHA, authentication, rate limits, or access controls. Submission safeguards—validation, idempotency, caps, pause controls, receipts, and uncertainty handling—must remain enabled independently of deployment access.
