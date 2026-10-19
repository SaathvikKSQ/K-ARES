"""Phase 4: compare / export / dashboard endpoints (FR-F3, FR-H, FR-G1).

The run worker is disabled in tests (conftest); runs are driven
synchronously. A regression is injected by uploading dataset version 2 with
a mismatched expected answer and a trigger_error case, then comparing.
"""

from __future__ import annotations

import csv
import io
import json
import uuid as _uuid

from fastapi.testclient import TestClient

from app.services import run_service

BASE_ROWS = [
    {"id": "q1", "input": "Question 1?", "expected_output": "MOCK-ANSWER: Question 1?"},
    {"id": "q2", "input": "Question 2?", "expected_output": "MOCK-ANSWER: Question 2?"},
    {"id": "q3", "input": "Question 3?", "expected_output": "MOCK-ANSWER: Question 3?"},
]
# Same external ids, injected regression: q2 expected answer no longer matches
# the mock echo (metric regression); q3 makes the application error out.
REGRESSED_ROWS = [
    BASE_ROWS[0],
    {"id": "q2", "input": "Question 2?", "expected_output": "INTENTIONALLY WRONG"},
    {
        "id": "q3",
        "input": "please trigger_error now",
        "expected_output": "MOCK-ANSWER: Question 3?",
    },
]
METRICS = [
    "answer.exact_match",
    "reliability.success_rate",
    "performance.latency",
    "performance.token_usage",
]


def _jsonl(rows: list[dict]) -> bytes:
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


def _upload_dataset(client: TestClient, headers: dict, name: str, rows: list[dict]) -> str:
    resp = client.post(
        "/api/v1/datasets",
        files={
            "file": (
                f"{name}.jsonl",
                io.BytesIO(_jsonl(rows)),
                "application/x-ndjson",
            )
        },
        data={"name": name, "application_type": "llm", "description": "phase 4"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["dataset"]["id"]


def _make_app(client: TestClient, headers: dict) -> str:
    resp = client.post(
        "/api/v1/applications",
        json={
            "name": f"Compare App {_uuid.uuid4().hex[:8]}",
            "application_type": "llm",
            "integration_type": "mock",
            "capabilities": {
                "exposes_retrieved_docs": False,
                "exposes_citations": False,
                "exposes_traces": False,
                "exposes_token_usage": True,
                "streaming": False,
            },
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _run_completed(client: TestClient, headers: dict, app_id: str, dataset_id: str) -> str:
    resp = client.post(
        "/api/v1/evaluations",
        json={
            "application_id": app_id,
            "dataset_id": dataset_id,
            "metric_ids": METRICS,
        },
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["id"]
    run_service.execute_run(run_id)
    detail = client.get(f"/api/v1/evaluations/{run_id}", headers=headers).json()
    assert detail["status"] == "completed", detail
    return run_id


def _compare(client: TestClient, headers: dict, baseline: str, candidate: str):
    return client.post(
        "/api/v1/evaluations/compare",
        json={"baseline_run_id": baseline, "candidate_run_id": candidate},
        headers=headers,
    )


def test_compare_flags_injected_regression(client: TestClient, auth_headers):
    app_id = _make_app(client, auth_headers)
    dataset_id = _upload_dataset(client, auth_headers, f"cmp-{_uuid.uuid4().hex[:6]}", BASE_ROWS)
    baseline = _run_completed(client, auth_headers, app_id, dataset_id)
    # Same dataset name -> same dataset, new immutable version 2 with regression.
    dataset_id_v2 = _upload_dataset(
        client, auth_headers,
        next(
            d["name"]
            for d in client.get("/api/v1/datasets", headers=auth_headers).json()
            if d["id"] == dataset_id
        ),
        REGRESSED_ROWS,
    )
    assert dataset_id_v2 == dataset_id
    candidate = _run_completed(client, auth_headers, app_id, dataset_id)

    resp = _compare(client, auth_headers, baseline, candidate)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["baseline_run_id"] == baseline
    assert body["candidate_run_id"] == candidate
    assert body["dataset_compatible"] is False  # different content hash, matched by id
    deltas = {d["evaluator_id"]: d for d in body["metric_deltas"]}
    assert deltas["reliability.success_rate"]["regression"] is True
    assert deltas["reliability.success_rate"]["baseline"] == 1.0
    assert deltas["reliability.success_rate"]["delta"] < 0
    assert deltas["answer.exact_match"]["regression"] is True
    assert deltas["answer.exact_match"]["candidate"] < 1.0
    assert body["newly_failing_case_ids"] == ["q3"]
    assert body["resolved_case_ids"] == []
    assert body["latency_delta"] is not None
    assert "baseline_mean_ms" in body["latency_delta"]
    assert body["baseline"]["application_name"] == body["candidate"]["application_name"]

    assert body["baseline"]["application_name"] == body["candidate"]["application_name"]


def test_compare_validates_runs(client: TestClient, auth_headers):
    app_id = _make_app(client, auth_headers)
    dataset_id = _upload_dataset(client, auth_headers, f"cmpv-{_uuid.uuid4().hex[:6]}", BASE_ROWS)
    run_id = client.post(
        "/api/v1/evaluations",
        json={
            "application_id": app_id,
            "dataset_id": dataset_id,
            "metric_ids": ["reliability.success_rate"],
        },
        headers=auth_headers,
    ).json()["id"]  # stays queued

    missing = _compare(client, auth_headers, "00000000-0000-0000-0000-000000000000", run_id)
    assert missing.status_code == 404
    not_completed = _compare(client, auth_headers, run_id, run_id)
    assert not_completed.status_code == 409


def test_export_json_matches_stored_run(client: TestClient, auth_headers):
    app_id = _make_app(client, auth_headers)
    dataset_id = _upload_dataset(client, auth_headers, f"exp-{_uuid.uuid4().hex[:6]}", BASE_ROWS)
    run_id = _run_completed(client, auth_headers, app_id, dataset_id)

    resp = client.get(
        f"/api/v1/evaluations/{run_id}/export", params={"format": "json"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert f"run-{run_id}-export.json" in resp.headers["content-disposition"]
    report = resp.json()
    assert report["report_version"] == "1.0.0"
    assert report["run"]["id"] == run_id
    assert report["run"]["status"] == "completed"
    assert report["application"]["application_type"] == "llm"
    assert report["dataset"]["valid_case_count"] == 3
    assert len(report["metric_definitions"]) == len(METRICS)
    # Only run-scope metrics produce aggregates; case metrics stay per case.
    assert len(report["summary_metrics"]) == 3
    assert "answer.exact_match" in [
        m["evaluator_id"] for m in report["cases"][0]["metrics"]
    ]
    assert len(report["cases"]) == 3
    assert all(c["outcome"] == "success" for c in report["cases"])
    assert report["failed_cases"] == []
    assert report["cases"][0]["expected_output"] == "MOCK-ANSWER: Question 1?"
    # NFR-4: no secrets in exports.
    assert "password" not in json.dumps(report).lower()
    assert report["application"].get("has_credentials") is None


def test_export_csv_rows_and_aggregates(client: TestClient, auth_headers):
    app_id = _make_app(client, auth_headers)
    dataset_id = _upload_dataset(client, auth_headers, f"csvg-{_uuid.uuid4().hex[:6]}", BASE_ROWS)
    run_id = _run_completed(client, auth_headers, app_id, dataset_id)

    resp = client.get(
        f"/api/v1/evaluations/{run_id}/export", params={"format": "csv"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    rows = [r for r in csv.reader(io.StringIO(resp.text)) if r]
    header = rows[0]
    assert header[0] == "case_id" and "answer.exact_match" in header
    case_rows = [r for r in rows[1:] if r[0] != "evaluator_id"][:3]
    assert len(case_rows) == 3
    exact_col = header.index("answer.exact_match")
    assert all(r[exact_col] == "1.0" for r in case_rows)
    aggregate_start = next(i for i, r in enumerate(rows) if r[0] == "evaluator_id")
    aggregate_ids = [r[0] for r in rows[aggregate_start + 1 :]]
    assert "reliability.success_rate" in aggregate_ids


def test_export_rejects_unknown_format_and_run(client: TestClient, auth_headers):
    bad_format = client.get(
        "/api/v1/evaluations/00000000-0000-0000-0000-000000000000/export",
        params={"format": "pdf"},
        headers=auth_headers,
    )
    assert bad_format.status_code in (400, 422)
    unknown_run = client.get(
        "/api/v1/evaluations/00000000-0000-0000-0000-000000000000/export",
        params={"format": "json"},
        headers=auth_headers,
    )
    assert unknown_run.status_code == 404


def test_dashboard_overview_from_real_data(client: TestClient, auth_headers):
    app_id = _make_app(client, auth_headers)
    dataset_id = _upload_dataset(
        client, auth_headers, f"ovr-{_uuid.uuid4().hex[:6]}", REGRESSED_ROWS
    )
    run_id = _run_completed(client, auth_headers, app_id, dataset_id)

    resp = client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totals"]["applications"] >= 1
    assert body["totals"]["datasets"] >= 1
    assert body["totals"]["runs"] >= 1
    breakdown = {b["status"]: b["count"] for b in body["status_breakdown"]}
    assert breakdown.get("completed", 0) >= 1
    assert any(r["id"] == run_id for r in body["recent_runs"])
    assert body["key_metrics"], "latest completed run must appear with key metrics"
    latest = body["key_metrics"][0]
    assert latest["run_id"] == run_id
    assert latest["application_name"]
    # q3 is a trigger_error case -> appears under recent failures.
    assert body["recent_failures"], "injected failing case must surface"
    assert any(f["outcome"] == "application_error" for f in body["recent_failures"])
