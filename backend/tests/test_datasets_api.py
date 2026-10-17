"""Phase 2: dataset upload, validation, versioning, samples (FR-B1..B6)."""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

SAMPLE_ROWS = [
    {
        "id": f"q{i}",
        "input": f"Question {i}?",
        "expected_output": f"Answer {i}",
        "relevant_doc_ids": ["doc-1"],
        "category": "factual",
    }
    for i in range(1, 6)
]


def _jsonl(rows: list[dict]) -> bytes:
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


def test_upload_valid_dataset_creates_version(client: TestClient, auth_headers):
    resp = client.post(
        "/api/v1/datasets",
        files={"file": ("sample.jsonl", io.BytesIO(_jsonl(SAMPLE_ROWS)), "application/x-ndjson")},
        data={"name": "Unit RAG Set", "application_type": "rag", "description": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["dataset"]["name"] == "Unit RAG Set"
    assert body["version"]["version_number"] == 1
    assert body["version"]["case_count"] == 5
    assert body["version"]["valid_case_count"] == 5
    assert body["validation_report"]["invalid_rows"] == 0


def test_invalid_rows_are_retained_not_dropped(client: TestClient, auth_headers):
    rows = [
        {"id": "ok-1", "input": "Valid question", "expected_output": "x"},
        {"input": "", "expected_output": "missing input"},
        {"id": "ok-2", "input": "Another valid", "expected_tool": "not_an_object"},
    ]
    resp = client.post(
        "/api/v1/datasets",
        files={"file": ("mixed.jsonl", io.BytesIO(_jsonl(rows)), "application/x-ndjson")},
        data={"name": "Mixed Set", "application_type": "rag"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"]["case_count"] == 3
    assert body["version"]["invalid_case_count"] == 1  # empty input row only
    dataset_id = body["dataset"]["id"]
    cases = client.get(
        f"/api/v1/datasets/{dataset_id}/versions/1/cases", headers=auth_headers
    ).json()
    statuses = {c["position"]: c["status"] for c in cases}
    assert statuses[1] == "valid"
    assert statuses[2] == "invalid"
    assert statuses[3] == "valid"
    invalid_cases = [c for c in cases if c["status"] == "invalid"]
    assert all(c["validation_errors"] for c in invalid_cases)
    # Filter by status (FR-B6)
    only_invalid = client.get(
        f"/api/v1/datasets/{dataset_id}/versions/1/cases",
        params={"case_status": "invalid"},
        headers=auth_headers,
    ).json()
    assert len(only_invalid) == 1


def test_identical_upload_reuses_version(client: TestClient, auth_headers):
    files = {"file": ("same.jsonl", io.BytesIO(_jsonl(SAMPLE_ROWS)), "application/x-ndjson")}
    data = {"name": "Dedupe Set", "application_type": "rag"}
    first = client.post("/api/v1/datasets", files=files, data=data, headers=auth_headers).json()
    files2 = {"file": ("same.jsonl", io.BytesIO(_jsonl(SAMPLE_ROWS)), "application/x-ndjson")}
    second = client.post("/api/v1/datasets", files=files2, data=data, headers=auth_headers).json()
    assert second["version"]["version_number"] == 1  # same version reused
    assert second["version"]["id"] == first["version"]["id"]


def test_modified_upload_creates_new_version(client: TestClient, auth_headers):
    data = {"name": "Versioned Set", "application_type": "rag"}
    v1 = client.post(
        "/api/v1/datasets",
        files={"file": ("a.jsonl", io.BytesIO(_jsonl(SAMPLE_ROWS[:3])), "application/x-ndjson")},
        data=data, headers=auth_headers,
    ).json()
    v2 = client.post(
        "/api/v1/datasets",
        files={"file": ("a.jsonl", io.BytesIO(_jsonl(SAMPLE_ROWS[:4])), "application/x-ndjson")},
        data=data, headers=auth_headers,
    ).json()
    assert v2["version"]["version_number"] == v1["version"]["version_number"] + 1


def test_dry_run_validate_endpoint(client: TestClient, auth_headers):
    rows = [{"input": "Only input, no answer"}]
    resp = client.post(
        "/api/v1/datasets/validate",
        files={"file": ("x.jsonl", io.BytesIO(_jsonl(rows)), "application/x-ndjson")},
        data={"application_type": "llm"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["total_rows"] == 1
    assert report["invalid_rows"] == 0
    assert any(w["field"] == "expected_output" for w in report["warnings"])


def test_csv_upload_supported(client: TestClient, auth_headers):
    csv_content = "id,input,expected_output\nc1,What is 2+2?,4\nc2,Capital of France?,Paris\n"
    resp = client.post(
        "/api/v1/datasets",
        files={"file": ("small.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        data={"name": "CSV Set", "application_type": "llm"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"]["case_count"] == 2


def test_rejects_unsupported_and_empty_files(client: TestClient, auth_headers):
    resp = client.post(
        "/api/v1/datasets",
        files={"file": ("x.txt", io.BytesIO(b"nope"), "text/plain")},
        data={"name": "Bad Type", "application_type": "llm"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/v1/datasets",
        files={"file": ("x.jsonl", io.BytesIO(b""), "application/x-ndjson")},
        data={"name": "Empty Set", "application_type": "llm"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_install_samples_and_list(client: TestClient, auth_headers):
    catalog = client.get("/api/v1/datasets/samples", headers=auth_headers).json()
    keys = {s["key"] for s in catalog}
    expected = {"sample-rag-qa", "sample-llm-basic", "sample-agent-tools", "sample-security-core"}
    assert expected <= keys
    installed = client.post("/api/v1/datasets/samples/install", headers=auth_headers).json()
    assert len(installed) == 4
    for detail in installed:
        assert detail["validation_report"]["invalid_rows"] == 0
        assert detail["version"]["valid_case_count"] == detail["version"]["case_count"]
    # Idempotent re-install: dedupe reuses the same versions.
    again = client.post("/api/v1/datasets/samples/install", headers=auth_headers).json()
    assert [d["version"]["id"] for d in again] == [d["version"]["id"] for d in installed]
    listed = client.get("/api/v1/datasets", headers=auth_headers).json()
    names = {d["name"] for d in listed}
    assert "sample-rag-qa" in names


def test_dataset_requires_auth(client: TestClient, admin_user):
    assert client.get("/api/v1/datasets").status_code == 401
    resp = client.post(
        "/api/v1/datasets",
        files={"file": ("x.jsonl", io.BytesIO(_jsonl(SAMPLE_ROWS)), "application/x-ndjson")},
        data={"name": "NoAuth Set", "application_type": "llm"},
    )
    assert resp.status_code == 401

