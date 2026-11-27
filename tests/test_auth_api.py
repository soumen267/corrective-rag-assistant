import auth_routes


def test_login_success_returns_bearer_token(client, make_user):
    _user, password = make_user("alice")

    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": password},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_accepts_email_as_username(client, make_user):
    _user, password = make_user("alice")

    response = client.post(
        "/auth/login",
        json={"username": "alice@example.com", "password": password},
    )

    assert response.status_code == 200


def test_wrong_password_and_unknown_user_look_identical(client, make_user):
    make_user("alice")

    wrong_password = client.post(
        "/auth/login",
        json={"username": "alice", "password": "not-the-password"},
    )
    unknown_user = client.post(
        "/auth/login",
        json={"username": "nobody", "password": "not-the-password"},
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_inactive_user_cannot_log_in(client, make_user):
    _user, password = make_user("alice", active=False)

    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": password},
    )

    assert response.status_code == 401


def test_login_is_rate_limited_after_repeated_failures(client, make_user):
    make_user("alice")

    for _ in range(auth_routes.LOGIN_MAX_ATTEMPTS):
        assert (
            client.post(
                "/auth/login",
                json={"username": "alice", "password": "bad-password-1"},
            ).status_code
            == 401
        )

    blocked = client.post(
        "/auth/login",
        json={"username": "alice", "password": "bad-password-1"},
    )

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limit_blocks_even_the_correct_password(client, make_user):
    _user, password = make_user("alice")

    for _ in range(auth_routes.LOGIN_MAX_ATTEMPTS):
        client.post(
            "/auth/login",
            json={"username": "alice", "password": "bad-password-1"},
        )

    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": password},
    )

    assert response.status_code == 429


def test_protected_endpoints_require_a_token(client):
    assert client.get("/documents").status_code == 401
    assert client.post("/chat", json={"question": "hi"}).status_code == 401
    assert client.delete("/sessions/abc").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_garbage_token_is_rejected(client):
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not.a.jwt"},
    )

    assert response.status_code == 401


def test_me_returns_profile_without_password_data(client, auth_headers):
    headers = auth_headers("alice")

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert "password" not in str(body).lower()


def test_logout_revokes_the_token(client, auth_headers):
    headers = auth_headers("alice")

    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200

    revoked = client.get("/auth/me", headers=headers)

    assert revoked.status_code == 401
    assert "revoked" in revoked.json()["detail"].lower()


def test_deactivated_user_loses_access_with_existing_token(
    client, auth_headers, sqlite_session_factory
):
    from user_models import User

    headers = auth_headers("alice")

    with sqlite_session_factory() as db:
        user = db.query(User).filter(User.username == "alice").one()
        user.is_active = False
        db.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_regular_user_cannot_create_accounts(client, auth_headers):
    headers = auth_headers("alice", role="user")

    response = client.post(
        "/auth/users",
        headers=headers,
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "a-long-enough-password",
        },
    )

    assert response.status_code == 403


def test_admin_can_create_accounts_and_duplicates_conflict(client, auth_headers):
    headers = auth_headers("root", role="admin")
    payload = {
        "username": "bob",
        "email": "bob@example.com",
        "password": "a-long-enough-password",
    }

    created = client.post("/auth/users", headers=headers, json=payload)
    duplicate = client.post("/auth/users", headers=headers, json=payload)

    assert created.status_code == 201
    assert "password" not in str(created.json()).lower()
    assert duplicate.status_code == 409


def test_new_account_rejects_weak_password(client, auth_headers):
    headers = auth_headers("root", role="admin")

    response = client.post(
        "/auth/users",
        headers=headers,
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422
