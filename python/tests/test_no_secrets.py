"""Guard against publishing credentials or personal contact details.

Scans every file git would publish (tracked plus new, not ignored) for key and token patterns,
personal email addresses and banned characters. Runs locally with pytest and in CI.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOREPLY = "users.noreply.github.com"

PATTERNS = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "service account key": re.compile(r'"type"\s*:\s*"service_account"'),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Google OAuth secret": re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    "Google OAuth refresh token": re.compile(r"\b1//0[0-9A-Za-z_\-]{30,}"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{40,}"),
    "Hugging Face token": re.compile(r"\bhf_[0-9A-Za-z]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "password assignment": re.compile(r"(?i)\b(?:password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"),
    "email address": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
}
# The only address that may be published is the GitHub no-reply identity.
ALLOWED_EMAIL = re.compile(rf"{re.escape(NOREPLY)}$")
EM_DASH = chr(0x2014)
BINARY = {".png", ".pdf", ".parquet", ".gz", ".jpg", ".jpeg", ".ico", ".pptx", ".xlsx"}


def publishable_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p and Path(p).suffix.lower() not in BINARY]


def test_no_secrets_or_personal_emails():
    problems = []
    for path in publishable_files():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                if name == "email address" and ALLOWED_EMAIL.search(m.group(0)):
                    continue
                if path.name == Path(__file__).name and name != "email address":
                    continue  # this file defines the patterns
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{path.relative_to(ROOT)}:{line} {name}")
    assert not problems, "Possible secret or personal detail:\n" + "\n".join(problems)


def test_no_em_dashes():
    hits = [f"{p.relative_to(ROOT)}" for p in publishable_files()
            if p.is_file() and EM_DASH in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, "Em dashes found (house style bans them):\n" + "\n".join(hits)
