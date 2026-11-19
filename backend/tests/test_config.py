def test_settings_have_default_model():
    from app.config.settings import settings
    assert settings.groq_model
