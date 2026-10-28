from fastapi.testclient import TestClient

from gopya import api


def test_api_uses_the_token_role(gopya, monkeypatch):
    monkeypatch.setattr(api, "engine", lambda: gopya)
    c = TestClient(api.app)
    assert c.post("/ask", json={"question": "hi"}).status_code == 401
    r = c.post("/ask", json={"question": "What is the dry season tariff in FY 2082/83?"},
               headers={"Authorization": "Bearer demo-fin-kabita"})
    assert r.status_code == 200 and "9.16" in r.json()["answer"]
    r = c.post("/ask", json={"question": "What is the dry season tariff in FY 2082/83?"},
               headers={"Authorization": "Bearer demo-staff-bishal"})
    assert r.json()["decision"] == "not_found"
    assert c.get("/me", headers={"Authorization": "Bearer demo-exec-sabina"}).json()["role"] == "executive"
