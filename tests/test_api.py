from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def sensor_payload(code: str | None = None) -> dict:
    return {
        "code": code or f"TEMP-{uuid4().hex[:8]}",
        "name": "Test temperature",
        "sensor_type": "temperature",
        "unit": "C",
        "location": "Test room",
        "min_value": 10,
        "max_value": 35,
    }


def test_sensor_crud_and_duplicate_validation() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        payload = sensor_payload()
        created = client.post("/sensors", json=payload)
        assert created.status_code == 201
        sensor_id = created.json()["id"]

        assert client.post("/sensors", json=payload).status_code == 409
        assert client.get("/sensors").status_code == 200
        assert client.get(f"/sensors/{sensor_id}").json()["code"] == payload["code"]

        updated = client.patch(
            f"/sensors/{sensor_id}",
            json={"name": "Updated sensor", "location": "Room 2"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Updated sensor"

        deleted = client.delete(f"/sensors/{sensor_id}")
        assert deleted.status_code == 204
        assert client.get(f"/sensors/{sensor_id}").status_code == 404


def test_reading_history_alert_and_websocket() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        sensor = client.post("/sensors", json=sensor_payload())
        assert sensor.status_code == 201
        sensor_id = sensor.json()["id"]

        with client.websocket_connect("/ws/readings") as websocket:
            reading = client.post(
                f"/sensors/{sensor_id}/readings",
                json={"value": 40, "measured_at": "2026-11-20T07:00:00Z"},
            )
            assert reading.status_code == 201
            message = websocket.receive_json()
            assert message["sensor_id"] == sensor_id
            assert message["unit"] == "C"
            assert message["alert"]["level"] == "warning"

        latest = client.get(f"/sensors/{sensor_id}/readings/latest")
        assert latest.status_code == 200
        assert latest.json()["value"] == 40
        assert client.get(f"/sensors/{sensor_id}/readings").status_code == 200
        assert client.get("/readings").status_code == 200


def test_validation_and_missing_resources() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        invalid_threshold = sensor_payload()
        invalid_threshold["min_value"] = 50
        invalid_threshold["max_value"] = 10
        assert client.post("/sensors", json=invalid_threshold).status_code == 422

        assert client.post("/sensors/999/readings", json={"value": 20}).status_code == 404
        assert client.get("/sensors/999/readings/latest").status_code == 404
        assert client.get("/sensors/999/readings").status_code == 404

        sensor = client.post("/sensors", json=sensor_payload())
        sensor_id = sensor.json()["id"]
        assert client.post(
            f"/sensors/{sensor_id}/readings",
            content='{"value": "not-a-number"}',
            headers={"Content-Type": "application/json"},
        ).status_code == 422

        client.patch(f"/sensors/{sensor_id}", json={"active": False})
        assert client.post(
            f"/sensors/{sensor_id}/readings",
            json={"value": 20},
        ).status_code == 409


def test_dashboard_and_openapi() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/").status_code == 200
        assert "Hệ thống giám sát cảm biến IoT" in client.get("/").text
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
