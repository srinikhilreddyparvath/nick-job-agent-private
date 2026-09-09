#!/usr/bin/env python3
"""Run RoleCall's privacy-safe golden evaluation evaluation suites."""
from __future__ import annotations

import subprocess
import sys


SUITES = [
    "tests/test_candidate_isolation.py",
    "tests/test_candidate_onboarding.py",
    "tests/test_resume_compatibility.py",
    "tests/test_career_intelligence.py",
    "tests/test_contact_intelligence.py",
    "tests/test_external_content_security.py",
]


def main() -> int:
    print("RoleCall Golden Evals\n=====================")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *SUITES], check=False)
    print(f"\nOverall: {'PASS' if result.returncode == 0 else 'FAIL'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
