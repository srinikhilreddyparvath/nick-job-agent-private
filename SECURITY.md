# Security

Report vulnerabilities privately to the repository maintainer before public disclosure.

This project intentionally has no built-in authentication. A publicly reachable deployment exposes its dashboard and API. Operators are responsible for understanding that choice and for keeping secrets and candidate data out of images, logs, source control, and public artifact URLs.

API keys and database credentials must be supplied through environment variables. Browser automation must not bypass CAPTCHA, authentication, rate limits, or access controls. Submission safeguards—validation, idempotency, caps, pause controls, receipts, and uncertainty handling—must remain enabled independently of deployment access.
