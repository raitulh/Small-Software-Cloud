from functools import lru_cache
from typing import Literal
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "Small Software Cloud"
    cloud_env: str = "development"
    api_v1_prefix: str = "/v1"
    web_origin: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    jwt_secret_key: str = "local-only-replace-this-with-a-random-secret-at-least-32-characters"
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str = "postgresql+asyncpg://cloud:cloud_dev_only@localhost:5432/smallcloud"
    redis_url: str = "redis://localhost:6379/0"
    deployment_driver: str = "mock"
    deployment_job_timeout_seconds: int = 300
    max_deployments_per_org_per_hour: int = 60
    allow_signups: bool = True
    max_projects_per_org: int = 20
    max_services_per_org: int = 50
    default_service_memory_mb: int = 256
    default_service_cpu_millicores: int = 250
    max_service_memory_mb: int = 2048
    max_service_cpu_millicores: int = 2000
    runtime_agent_url: str | None = None
    runtime_agent_shared_secret: str | None = None
    workload_sandbox: str = "disabled"
    apps_domain: str = "localhost"
    apps_network: str = "smallcloud_apps"

    @field_validator("cloud_env")
    @classmethod
    def valid_env(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"development", "test", "staging", "production"}:
            raise ValueError("CLOUD_ENV must be development, test, staging, or production")
        return value

    @field_validator("deployment_driver")
    @classmethod
    def valid_driver(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"mock", "docker", "local_docker"}:
            raise ValueError("DEPLOYMENT_DRIVER must be 'mock', 'docker', or 'local_docker'")
        return value


    @model_validator(mode="after")
    def production_safety(self):
        if self.cloud_env == "production" and (len(self.jwt_secret_key) < 32 or self.jwt_secret_key.startswith("local-only-")):
            raise ValueError("Production requires a unique JWT_SECRET_KEY of at least 32 characters")
        if self.cloud_env == "production" and self.allow_signups:
            raise ValueError("Production requires ALLOW_SIGNUPS=false until verified onboarding and abuse controls are implemented")
        if self.default_service_memory_mb > self.max_service_memory_mb:
            raise ValueError("Default memory cannot exceed max service memory")
        if self.default_service_cpu_millicores > self.max_service_cpu_millicores:
            raise ValueError("Default CPU cannot exceed max service CPU")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
