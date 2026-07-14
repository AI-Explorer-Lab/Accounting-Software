from config.config import load_environment, validate_settings


def test_development_configuration_is_valid() -> None:
    config = load_environment("development")
    validate_settings(config)
    assert config.environment.name == "development"
    assert config.db.name == "account"
