def test_health_endpoint_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["version"] == "1.0.0"
    assert "checks" in data


def test_health_contains_check_keys(client):
    data = client.get("/health").json()
    assert "database" in data["checks"]
    assert "redis" in data["checks"]
    assert "llm" in data["checks"]
    assert data["checks"]["llm"] == "ok"
