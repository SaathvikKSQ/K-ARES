"""Phase 3: evaluations API end-to-end with the mock adapter (FR-C/FR-F).

The run worker is disabled in tests (conftest); happy-path tests drive
``run_service.execute_run`` synchronously for determinism.
"""

from __future__ import annotations

import io
import json
import uuid as _uuid

from fastapi.testclient import TestClient

from app.services import run_service


def _jsonl(rows: list[dict]) -> bytes:
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


def _app_payload(**overrides) -> dict:
    payload = {
        "name": f"Mock App {_uuid.uuid4().hex[:8]}",
        "description": "mock app for eval tests",
        "application_type": "llm",
        "integration_type": "mock",
        "capabilities": {
            "exposes_retrieved_docs": False,
            "exposes_citations": False,
            "exposes_traces": False,
            "exposes_token_usage": True,
            "streaming": False,
        },
    }
    payload.update(overrides)
    return payload


def _make_app_and_dataset(client: TestClient, headers: dict, rows: list[dict]):
    app = client.post(
        "/api/v1/applications", json=_app_payload(), headers=headers
    ).json()
    ds = client.post(
        "/api/v1/datasets",
        files={
            "file": (
                f"ds-{_uuid.uuid4().hex[:6]}.jsonl",
                io.BytesIO(_jsonl(rows)),
                "application/x-ndjson",
            )
        },
        data={
            "name": f"Eval DS {_uuid.uuid4().hex[:8]}",
            "application_type": "llm",
            "description": "test",
        },
        headers=headers,
    ).json()
    return app["id"], ds["dataset"]["id"]


def _create_run(client, headers, app_id, dataset_id, metric_ids, run_config=None):
    payload = {
        "application_id": app_id,
        "dataset_id": dataset_id,
        "metric_ids": metric_ids,
    }
    if run_config:
        payload["run_config"] = run_config
    return client.post("/api/v1/evaluations", json=payload, headers=headers)


def _make_app_and_dataset(
    client: TestClient, headers: dict, rows: list[dict], capabilities_token_usage: bool = True
):
    app = client.post(
        "/api/v1/applications",
        json=_app_payload(
            capabilities={
                "exposes_retrieved_docs": False,
                "exposes_citations": False,
                "exposes_traces": False,
                "exposes_token_usage": capabilities_token_usage,
                "streaming": False,
            }
        ),
        headers=headers,
    ).json()
    ds = client.post(
        "/api/v1/datasets",
        files={
            "file": (
                f"ds-{_uuid.uuid4().hex[:6]}.jsonl",
                io.BytesIO(_jsonl(rows)),
                "application/x-ndjson",
            )
        },
        data={
            "name": f"Eval DS {_uuid.uuid4().hex[:8]}",
            "application_type": "llm",
            "description": "test",
        },
        headers=headers,
    ).json()
    return app["id"], ds["dataset"]["id"]


def _create_run(client, headers, app_id, dataset_id, metric_ids, run_config=None):
    payload = {
        "application_id": app_id,
        "dataset_id": dataset_id,
        "metric_ids": metric_ids,
    }
    if run_config:
        payload["run_config"] = run_config
    return client.post("/api/v1/evaluations", json=payload, headers=headers)


ROWS = [
    {"id": f"q{i}", "input": f"Question {i}?", "expected_output": f"Answer {i}"}
    for i in range(1, 4)
]

def test_metrics_endpoint_lists_evaluators(client: TestClient, auth_headers):
    resp = client.get("/api/v1/metrics", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    metrics = resp.json()
    ids = [m["id"] for m in metrics]
    assert "reliability.success_rate" in ids and "answer.exact_match" in ids
    by_id = {m["id"]: m for m in metrics}
    assert by_id["answer.exact_match"]["scope"] == "case"
    assert by_id["reliability.success_rate"]["scope"] == "run"
    assert by_id["answer.exact_match"]["required_fields"] == ["expected_output"]


def test_metrics_requires_authentication(client: TestClient):
    assert client.get("/api/v1/metrics").status_code == 401


def test_validate_config_reports_applicability(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    resp = client.post(
        "/api/v1/evaluations/validate-config",
        json={
            "application_id": app_id,
            "dataset_id": dataset_id,
            "metric_ids": ["answer.exact_match", "reliability.success_rate"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["applicable"]) == {"answer.exact_match", "reliability.success_rate"}
    assert body["inapplicable"] == []
    assert body["estimated_cases"] == 3


def test_create_run_rejects_inapplicable_metric(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(
        client, auth_headers, ROWS, capabilities_token_usage=False
    )
    resp = _create_run(
        client,
        auth_headers,
        app_id,
        dataset_id,
        ["performance.token_usage", "reliability.success_rate"],
    )
    assert resp.status_code == 422, resp.text
    message = resp.json()["error"]["message"]
    assert "performance.token_usage" in message
    assert "exposes_token_usage" in message


def test_create_run_rejects_unknown_metric(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    resp = _create_run(client, auth_headers, app_id, dataset_id, ["not.a_metric"])
    assert resp.status_code == 400


def test_create_run_rejects_disabled_application(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    client.patch(
        f"/api/v1/applications/{app_id}",
        json={"is_enabled": False},
        headers=auth_headers,
    )
    resp = _create_run(
        client, auth_headers, app_id, dataset_id, ["reliability.success_rate"]
    )
    assert resp.status_code == 400


def test_create_run_requires_authentication(client: TestClient):
    resp = client.post(
        "/api/v1/evaluations",
        json={
            "application_id": "x",
            "dataset_id": "y",
            "metric_ids": ["answer.exact_match"],
        },
    )
    assert resp.status_code == 401

def test_run_lifecycle_end_to_end(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    resp = _create_run(
        client,
        auth_headers,
        app_id,
        dataset_id,
        [
            "answer.exact_match",
            "reliability.success_rate",
            "performance.latency",
            "cost.estimated_total",
        ],
    )
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["id"]
    assert resp.json()["status"] == "queued"

    detail = client.get(f"/api/v1/evaluations/{run_id}", headers=auth_headers).json()
    assert detail["status"] == "queued"
    assert detail["progress"]["total"] == 3
    assert detail["configuration_snapshot"]["application"]["model_name"] is None
    assert detail["configuration_snapshot"]["dataset"]["version_number"] == 1

    run_service.execute_run(run_id)

    detail = client.get(f"/api/v1/evaluations/{run_id}", headers=auth_headers).json()
    assert detail["status"] == "completed", detail
    assert detail["progress"]["completed"] == 3
    summary = {m["evaluator_id"]: m for m in detail["summary_metrics"]}
    success = summary["reliability.success_rate"]
    assert success["status"] == "computed" and success["score"] == 1.0
    assert summary["performance.latency"]["status"] == "computed"
    # No model metadata configured -> cost explicitly unavailable (never fabricated)
    assert summary["cost.estimated_total"]["status"] == "unavailable"
    assert "model" in summary["cost.estimated_total"]["unavailable_reason"]

    results = client.get(
        f"/api/v1/evaluations/{run_id}/results", headers=auth_headers
    ).json()
    assert results["total"] == 3
    first = results["items"][0]
    assert first["outcome"] == "success"
    assert "answer.exact_match" in [m["evaluator_id"] for m in first["metrics"]]

    detail_resp = client.get(
        f"/api/v1/evaluations/{run_id}/results/{first['id']}", headers=auth_headers
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["case_input"] == {"input": "Question 1?"}


def test_cancel_queued_run_and_conflict_after(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    resp = _create_run(
        client, auth_headers, app_id, dataset_id, ["reliability.success_rate"]
    )
    run_id = resp.json()["id"]
    cancel = client.post(f"/api/v1/evaluations/{run_id}/cancel", headers=auth_headers)
    assert cancel.status_code == 202
    assert cancel.json()["status"] == "cancelled"
    again = client.post(f"/api/v1/evaluations/{run_id}/cancel", headers=auth_headers)
    assert again.status_code == 409


def test_cancel_completed_run_conflicts(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    run_id = _create_run(
        client, auth_headers, app_id, dataset_id, ["reliability.success_rate"]
    ).json()["id"]
    run_service.execute_run(run_id)
    resp = client.post(f"/api/v1/evaluations/{run_id}/cancel", headers=auth_headers)
    assert resp.status_code == 409


def test_list_runs_filter_by_status(client: TestClient, auth_headers):
    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    run_id = _create_run(
        client, auth_headers, app_id, dataset_id, ["reliability.success_rate"]
    ).json()["id"]
    resp = client.get(
        "/api/v1/evaluations", params={"status": "queued"}, headers=auth_headers
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert run_id in ids


def test_create_run_requires_editor_role(client: TestClient, auth_headers, db_session):
    from app.services.user_service import create_user, get_user_by_email

    email = f"viewer-{_uuid.uuid4().hex[:8]}@kaers.dev"
    if get_user_by_email(db_session, email) is None:
        create_user(db_session, email, "viewer-password-123", role="viewer")
        db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "viewer-password-123"}
    )
    assert login.status_code == 200, login.text
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    app_id, dataset_id = _make_app_and_dataset(client, auth_headers, ROWS)
    resp = _create_run(
        client, viewer_headers, app_id, dataset_id, ["reliability.success_rate"]
    )
    assert resp.status_code == 403
