import pytest


@pytest.mark.asyncio
async def test_effective_consent_uses_latest_consent_record(monkeypatch):
    from mental_health_wellness.security import compliance

    async def no_schema_sync(_prisma):
        return None

    class FakePrisma:
        async def query_raw(self, _sql):
            return [
                {"scope": "CRISIS_LOCATION", "granted": True},
                {"scope": "VOICE_ANALYSIS", "granted": False},
            ]

    monkeypatch.setattr(compliance, "ensure_compliance_schema", no_schema_sync)

    states = await compliance.get_effective_consent_states(
        FakePrisma(),
        user_id="user_1",
        scopes=["CRISIS_LOCATION", "VOICE_ANALYSIS", "EMERGENCY_CONTACT_ALERTS"],
    )

    assert states["CRISIS_LOCATION"] is True
    assert states["VOICE_ANALYSIS"] is False
    assert states["EMERGENCY_CONTACT_ALERTS"] is None


@pytest.mark.asyncio
async def test_effective_consent_falls_back_when_no_consent_record(monkeypatch):
    from mental_health_wellness.security import compliance

    async def no_schema_sync(_prisma):
        return None

    class FakePrisma:
        async def query_raw(self, _sql):
            return []

    monkeypatch.setattr(compliance, "ensure_compliance_schema", no_schema_sync)

    assert await compliance.effective_scoped_consent(
        FakePrisma(),
        user_id="user_1",
        scope="CRISIS_LOCATION",
        fallback=True,
    ) is True


@pytest.mark.asyncio
async def test_crisis_location_check_allows_consent_record_when_preference_is_stale(monkeypatch):
    from mental_health_wellness.api import crisis_routes

    class StalePreference:
        crisisLocationConsent = False

    class FakeUserPreference:
        async def find_unique(self, where):
            assert where == {"userId": "user_1"}
            return StalePreference()

    class FakePrisma:
        userpreference = FakeUserPreference()

    async def fake_get_prisma_client():
        return FakePrisma()

    async def fake_effective_consent(prisma, *, user_id, scope, fallback):
        assert isinstance(prisma, FakePrisma)
        assert user_id == "user_1"
        assert scope == "CRISIS_LOCATION"
        assert fallback is False
        return True

    monkeypatch.setattr(crisis_routes, "get_prisma_client", fake_get_prisma_client)
    monkeypatch.setattr(crisis_routes, "effective_scoped_consent", fake_effective_consent)

    assert await crisis_routes._has_location_consent("user_1") is True


@pytest.mark.asyncio
async def test_ip_auto_location_endpoint_is_disabled(monkeypatch):
    from mental_health_wellness.api.crisis_routes import AutoLocationRequest, send_location_auto

    monkeypatch.setenv("SENTIMIND_REQUIRE_USER_HEADER", "false")

    class FakeRequest:
        client = None
        headers = {}

    result = await send_location_auto(
        AutoLocationRequest(user_id="user_1", crisis_level="high"),
        FakeRequest(),
    )

    assert result["success"] is False
    assert result["location"] is None
    assert "disabled" in result["error"].lower()
