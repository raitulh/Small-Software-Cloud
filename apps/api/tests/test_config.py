import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.services.deploy_driver import DockerDeploymentDriver, MockDeploymentDriver, get_deployment_driver

def test_default_driver_is_mock():
    cfg = Settings(_env_file=None)
    assert cfg.deployment_driver == "mock"

def test_cors_list_parses_csv():
    cfg = Settings(_env_file=None, cors_origins="https://a.example,https://b.example")
    assert cfg.cors_origin_list == ["https://a.example", "https://b.example"]

def test_production_requires_signups_disabled():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            cloud_env="production",
            jwt_secret_key="a-unique-production-secret-longer-than-32-chars",
            allow_signups=True,
        )

def test_docker_driver_setting_accepted():
    cfg = Settings(_env_file=None, deployment_driver="docker")
    assert cfg.deployment_driver == "docker"
    cfg_local = Settings(_env_file=None, deployment_driver="local_docker")
    assert cfg_local.deployment_driver == "local_docker"

def test_invalid_driver_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_driver="kubernetes_unsupported")

def test_driver_factory():
    driver = get_deployment_driver()
    assert isinstance(driver, (MockDeploymentDriver, DockerDeploymentDriver))
