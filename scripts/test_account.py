"""Exercise account persistence against the running local API and PostgreSQL.

Run from the backend directory: python -m scripts.test_account
Creates two isolated test customers and removes only those fixtures on exit.
No OTPs or emails are sent, and existing customer records are not changed.
"""

import argparse
import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.tokens import create_customer_token


def run(base_url: str) -> None:
    engine = create_engine(get_settings().DATABASE_URL.replace("+asyncpg", "+psycopg2"))
    user_id, other_id = uuid.uuid4(), uuid.uuid4()
    token = create_customer_token(str(user_id))
    other_token = create_customer_token(str(other_id))

    def request(method, path, body=None, *, expected=200, auth=token):
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(base_url.rstrip("/") + path, data=data, method=method, headers=headers)
        try:
            response = urlopen(req, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            assert response.status == expected, f"{method} {path}: expected {expected}, got {response.status}: {raw}"
            return json.loads(raw) if raw else None

    address_data = {
        "full_name": "Account Test", "phone": "9876543210",
        "line1": "1 Test Street", "line2": "Test Area", "landmark": "Test Landmark",
        "city": "Delhi", "state": "Delhi", "pincode": "110001",
    }
    try:
        with engine.begin() as connection:
            for fixture_id in (user_id, other_id):
                connection.execute(text("""
                    INSERT INTO users (id, role, email, is_active, failed_logins, created_at, updated_at)
                    VALUES (:id, 'customer', :email, true, 0, now(), now())
                """), {"id": fixture_id, "email": f"account-test-{fixture_id.hex}@example.com"})

        request("GET", "/health")
        initial = request("GET", "/me")
        assert initial["full_name"] is None and initial["phone"] is None
        profile = request("PATCH", "/me", {"full_name": "  Account Test  ", "phone": " 9876543210 "})
        assert profile["full_name"] == "Account Test" and profile["phone"] == "9876543210"
        assert request("GET", "/me")["full_name"] == "Account Test"
        with engine.connect() as connection:
            saved = connection.execute(text("SELECT full_name, phone FROM users WHERE id=:id"), {"id": user_id}).one()
            assert tuple(saved) == ("Account Test", "9876543210")
        request("PATCH", "/me", {"full_name": " "}, expected=422)
        request("PATCH", "/me", {"phone": "123"}, expected=422)
        request("PATCH", "/me", {"role": "admin"}, expected=422)
        request("PATCH", "/me", {"email": "changed@example.com"}, expected=422)
        request("PATCH", "/me", {"phone": None})
        assert request("GET", "/me")["phone"] is None
        assert request("GET", "/me", auth=other_token)["full_name"] is None
        print("PASS: profile updates commit to PostgreSQL, reload correctly, and reject invalid/privileged changes")

        first = request("POST", "/addresses", address_data, expected=201)
        assert first["is_default"]
        first_path = f"/addresses/{first['id']}"
        second = request("POST", "/addresses", {**address_data, "line1": "2 Test Street"}, expected=201)
        second_path = f"/addresses/{second['id']}"
        assert not second["is_default"]
        assert len(request("GET", "/addresses")) == 2
        updated = request("PATCH", first_path, {"line1": "Updated Street", "line2": None, "landmark": None})
        assert updated["line1"] == "Updated Street" and updated["line2"] is None and updated["landmark"] is None
        request("PATCH", first_path, {"line1": None}, expected=422)
        request("PATCH", first_path, {"phone": "123"}, expected=422)
        request("PATCH", first_path, {"is_default": None}, expected=422)
        request("PATCH", first_path, {"line1": "Forbidden"}, auth=other_token, expected=404)
        request("DELETE", first_path, auth=other_token, expected=404)
        request("POST", first_path + "/default", auth=other_token, expected=404)
        assert request("GET", "/addresses", auth=other_token) == []
        with engine.connect() as connection:
            saved = connection.execute(text("SELECT line1, line2, landmark FROM addresses WHERE id=:id AND user_id=:user_id"),
                                       {"id": uuid.UUID(first["id"]), "user_id": user_id}).one()
            assert tuple(saved) == ("Updated Street", None, None)
        print("PASS: addresses persist, optional fields clear, validation and customer ownership hold")

        assert request("POST", second_path + "/default")["is_default"]
        active = request("GET", "/addresses")
        assert [a["id"] for a in active if a["is_default"]] == [second["id"]]
        assert request("PATCH", second_path, {"is_default": False})["is_default"]
        request("DELETE", second_path, expected=204)
        active = request("GET", "/addresses")
        assert len(active) == 1 and active[0]["id"] == first["id"] and active[0]["is_default"]
        request("PATCH", second_path, {"line1": "Deleted"}, expected=404)
        request("DELETE", first_path, expected=204)
        assert request("GET", "/addresses") == []
        with engine.connect() as connection:
            count = connection.execute(text("SELECT count(*) FROM addresses WHERE user_id=:id AND deleted_at IS NOT NULL"),
                                       {"id": user_id}).scalar_one()
            assert count == 2
        print("PASS: default selection, default promotion and soft deletion persist")
    finally:
        with engine.begin() as connection:
            for fixture_id in (user_id, other_id):
                connection.execute(text("DELETE FROM addresses WHERE user_id=:id"), {"id": fixture_id})
                connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": fixture_id})
        engine.dispose()
        print("Test fixtures removed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    run(parser.parse_args().base_url)
