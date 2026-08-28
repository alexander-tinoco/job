"""Populate a running stack with the golden-set candidates, for a look at the panel.

    .venv/bin/python scripts/seed_demo.py [base_url]

Talks to the HTTP API rather than the database, so it exercises the same path a
real applicant does: upload, extraction, integrity check. Evaluation is then
triggered synchronously per candidate — about a cent for the whole set.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json  # noqa: E402
import mimetypes  # noqa: E402
import uuid  # noqa: E402
from typing import Any  # noqa: E402

from scripts.compare_models import COMPANY_CONTEXT, CRITERIA, JOB_TITLE, WEIGHTS  # noqa: E402
from tests.golden.candidates import CANDIDATES  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
TOKEN = os.environ.get("ADMIN_TOKEN", "demo-token")
PDFS = Path(__file__).resolve().parent.parent / "tests" / "golden" / "pdfs"


def call(method: str, path: str, body: object = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    request.add_header("X-Admin-Token", TOKEN)
    if data:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def upload(slug: str, name: str, email: str, pdf: Path) -> None:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in (("full_name", name), ("email", email), ("consent", "true")):
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode()
        )
    mime = mimetypes.guess_type(pdf.name)[0] or "application/pdf"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="resume"; '
        f'filename="{pdf.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
    )
    parts.append(pdf.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"{BASE}/openings/{slug}/apply", data=b"".join(parts), method="POST"
    )
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(request, timeout=120):
        pass


def main() -> int:
    company = call("POST", "/api/v1/companies", {"name": "Mercadis"})
    slug = "data-analyst-demo"
    opening = call(
        "POST",
        f"/api/v1/companies/{company['id']}/openings",
        {
            "title": JOB_TITLE,
            "slug": slug,
            "description": "Own the questions the product team cannot answer yet.",
            "company_context": COMPANY_CONTEXT,
            "criteria": [
                {
                    "name": criterion.name,
                    "description": criterion.description,
                    "weight": WEIGHTS[criterion.name],
                    "mandatory": criterion.mandatory,
                }
                for criterion in CRITERIA
            ],
        },
    )
    opening_id = opening["opening"]["id"]
    print(f"opening {opening_id} at /openings/{slug}")

    # Ten clean candidates plus the tampered one, so the panel shows both.
    keys = [c.key for c in CANDIDATES] + ["ibarra_injected"]
    for key in keys:
        name = next((c.name for c in CANDIDATES if c.key == key), "Tomás Ibarra (tampered)")
        try:
            upload(slug, name, f"{key}@example.com", PDFS / f"{key}.pdf")
            print(f"  uploaded {key}")
        except urllib.error.HTTPError as exc:
            print(f"  {key}: {exc.code} {exc.read().decode()[:90]}")

    page = call("GET", f"/api/v1/openings/{opening_id}/applications?limit=50")
    for item in page["items"]:
        try:
            call("POST", f"/api/v1/applications/{item['id']}/evaluate")
            print(f"  evaluated {item['candidate_name']}")
        except urllib.error.HTTPError as exc:
            print(f"  {item['candidate_name']}: {exc.code} {exc.read().decode()[:90]}")

    final = call("GET", f"/api/v1/openings/{opening_id}/applications?limit=50")
    print(f"\n{final['evaluated']}/{final['total']} evaluated")
    for item in final["items"]:
        score = item["overall_score"]
        print(f"  {str(score or '—'):>7}  {item['candidate_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
