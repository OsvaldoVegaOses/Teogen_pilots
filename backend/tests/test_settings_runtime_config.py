from app.core.settings import Settings


def _clear_theory_runtime_env(monkeypatch):
    for key in (
        "APP_ENV",
        "THEORY_ENV_PROFILE",
        "THEORY_USE_JUDGE",
        "THEORY_JUDGE_WARN_ONLY",
        "THEORY_SYNC_CLAIMS_NEO4J",
        "THEORY_SYNC_CLAIMS_QDRANT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_theory_runtime_profile_auto_production_enables_strict_defaults(monkeypatch):
    _clear_theory_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("THEORY_ENV_PROFILE", "auto")

    settings = Settings(_env_file=None)

    assert settings.THEORY_ENV_PROFILE_EFFECTIVE == "production"
    assert settings.THEORY_USE_JUDGE is True
    assert settings.THEORY_JUDGE_WARN_ONLY is False
    assert settings.THEORY_SYNC_CLAIMS_NEO4J is True
    assert settings.THEORY_SYNC_CLAIMS_QDRANT is True
    assert settings.THEORY_CONFIG_ISSUES == []


def test_theory_runtime_profile_auto_staging_enables_shadow_mode(monkeypatch):
    _clear_theory_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("THEORY_ENV_PROFILE", "auto")

    settings = Settings(_env_file=None)

    assert settings.THEORY_ENV_PROFILE_EFFECTIVE == "staging"
    assert settings.THEORY_USE_JUDGE is True
    assert settings.THEORY_JUDGE_WARN_ONLY is True
    assert settings.THEORY_SYNC_CLAIMS_NEO4J is True
    assert settings.THEORY_SYNC_CLAIMS_QDRANT is False
    assert settings.THEORY_CONFIG_ISSUES == []


def test_theory_runtime_profile_production_detects_incoherent_explicit_overrides(monkeypatch):
    _clear_theory_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("THEORY_ENV_PROFILE", "manual")
    monkeypatch.setenv("THEORY_USE_JUDGE", "false")
    monkeypatch.setenv("THEORY_JUDGE_WARN_ONLY", "true")
    monkeypatch.setenv("THEORY_SYNC_CLAIMS_NEO4J", "false")
    monkeypatch.setenv("THEORY_SYNC_CLAIMS_QDRANT", "false")

    settings = Settings(_env_file=None)
    issues = settings.THEORY_CONFIG_ISSUES

    assert settings.THEORY_ENV_PROFILE_EFFECTIVE == "manual"
    assert len(issues) >= 3
    assert any("THEORY_USE_JUDGE=true" in issue for issue in issues)
    assert any("THEORY_JUDGE_WARN_ONLY=false" in issue for issue in issues)
    assert any("THEORY_SYNC_CLAIMS_NEO4J=true" in issue for issue in issues)
    assert any("THEORY_SYNC_CLAIMS_QDRANT=true" in issue for issue in issues)


def test_theory_runtime_config_summary_includes_status(monkeypatch):
    _clear_theory_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("THEORY_ENV_PROFILE", "manual")
    monkeypatch.setenv("THEORY_USE_JUDGE", "false")

    settings = Settings(_env_file=None)
    summary = settings.theory_runtime_config_summary()

    assert summary["app_env"] == "development"
    assert summary["profile_effective"] == "manual"
    assert "ok" in summary
    assert isinstance(summary["issues"], list)
