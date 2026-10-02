from src import app as app_module


def test_home_renders_only_valid_optional_https_destinations(monkeypatch):
    monkeypatch.setenv("SBI_INVESTOR_PORTAL_URL", "https://investor.example.test/login")
    monkeypatch.setenv("GROWW_DASHBOARD_URL", "http://groww.example.test/dashboard")

    response = app_module.app.test_client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-investor-url="https://investor.example.test/login"' in html
    assert 'data-groww-url=""' in html
    assert 'data-nav-view="schemes"' in html


def test_home_defaults_optional_destinations_to_empty(monkeypatch):
    monkeypatch.delenv("SBI_INVESTOR_PORTAL_URL", raising=False)
    monkeypatch.delenv("GROWW_DASHBOARD_URL", raising=False)

    html = app_module.app.test_client().get("/").get_data(as_text=True)

    assert 'data-investor-url=""' in html
    assert 'data-groww-url=""' in html


def test_configured_destination_rejects_credentials_malformed_and_non_https():
    assert app_module._configured_https_url("https://example.test/path") == "https://example.test/path"
    for value in (
        "http://example.test/path",
        "https://user:password@example.test/path",
        "https://example.test:bad/path",
        "//example.test/path",
        "https://example.test/path with space",
    ):
        assert app_module._configured_https_url(value) == ""
