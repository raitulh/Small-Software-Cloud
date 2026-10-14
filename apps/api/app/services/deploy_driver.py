"""Deployment-driver subsystem.
Supports:
- MockDeploymentDriver: safe simulation without customer code execution.
- DockerDeploymentDriver: local container execution with resource limits and Traefik routing.
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import os
import shutil
import tempfile
from typing import Awaitable, Callable
from app.core.config import settings

logger = logging.getLogger("smallcloud.deploy_driver")

LogCallback = Callable[[str, str], Awaitable[None]]

@dataclass
class DriverResult:
    image_digest: str | None = None
    output_url: str | None = None

class BaseDeploymentDriver(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def deploy(
        self,
        *,
        service_id: str,
        service_slug: str,
        deployment_id: str,
        runtime: str,
        kind: str,
        source_repo: str | None,
        branch: str,
        image_ref: str | None,
        internal_port: int,
        memory_mb: int,
        cpu_millicores: int,
        env_vars: dict[str, str],
        log_callback: LogCallback | None = None
    ) -> DriverResult:
        pass

class MockDeploymentDriver(BaseDeploymentDriver):
    name = "mock"

    async def deploy(
        self,
        *,
        service_id: str,
        service_slug: str,
        deployment_id: str,
        runtime: str,
        kind: str,
        source_repo: str | None,
        branch: str,
        image_ref: str | None,
        internal_port: int,
        memory_mb: int,
        cpu_millicores: int,
        env_vars: dict[str, str],
        log_callback: LogCallback | None = None
    ) -> DriverResult:
        if log_callback:
            await log_callback("INFO", f"MockDriver: initializing lifecycle simulation for '{service_slug}' ({runtime}).")
            await log_callback("INFO", f"MockDriver: declared resources: {memory_mb} MB RAM, {cpu_millicores} mCPU.")
            if env_vars:
                await log_callback("INFO", f"MockDriver: {len(env_vars)} environment variable(s) loaded.")
            await asyncio.sleep(0.3)
            await log_callback("INFO", "MockDriver: simulation completed successfully.")
            await log_callback("WARN", "MockDriver: no live container was started (DEPLOYMENT_DRIVER=mock).")

        return DriverResult(
            image_digest=f"sha256:mock-{deployment_id[:16]}",
            output_url=f"http://{service_slug}.mock.{settings.apps_domain}"
        )

class DockerDeploymentDriver(BaseDeploymentDriver):
    name = "docker"

    async def _run_cmd(self, cmd: list[str], log_callback: LogCallback | None = None, cwd: str | None = None) -> tuple[int, str]:
        cmd_str = " ".join(cmd)
        logger.debug("Executing: %s", cmd_str)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace").strip()
        err_text = stderr.decode("utf-8", errors="replace").strip()

        combined = out_text
        if err_text:
            combined = f"{out_text}\n{err_text}".strip()

        if proc.returncode != 0 and log_callback and combined:
            await log_callback("WARN", f"Command exited {proc.returncode}: {combined[:200]}")

        return proc.returncode or 0, combined

    async def _ensure_network(self, network_name: str, log_callback: LogCallback | None = None):
        code, _ = await self._run_cmd(["docker", "network", "inspect", network_name])
        if code != 0:
            if log_callback:
                await log_callback("INFO", f"Creating Docker application network '{network_name}'...")
            await self._run_cmd(["docker", "network", "create", network_name], log_callback)

    async def deploy(
        self,
        *,
        service_id: str,
        service_slug: str,
        deployment_id: str,
        runtime: str,
        kind: str,
        source_repo: str | None,
        branch: str,
        image_ref: str | None,
        internal_port: int,
        memory_mb: int,
        cpu_millicores: int,
        env_vars: dict[str, str],
        log_callback: LogCallback | None = None
    ) -> DriverResult:
        if not shutil.which("docker"):
            err = "Docker executable is not found in PATH on the host system."
            if log_callback:
                await log_callback("ERROR", err)
            raise RuntimeError(err)

        container_name = f"sc-{service_id[:12]}"
        image_tag = f"smallcloud/{service_slug}:{deployment_id[:8]}"
        network_name = settings.apps_network

        await self._ensure_network(network_name, log_callback)

        if runtime == "docker_image":
            if not image_ref:
                raise ValueError("Runtime 'docker_image' requires image_ref")
            if log_callback:
                await log_callback("INFO", f"Pulling container image '{image_ref}'...")
            code, out = await self._run_cmd(["docker", "pull", image_ref], log_callback)
            if code != 0:
                raise RuntimeError(f"Failed to pull image {image_ref}: {out}")
            final_image = image_ref
        else:
            # Build from Git Source
            if not source_repo:
                raise ValueError(f"Runtime '{runtime}' requires a valid source_repo")

            with tempfile.TemporaryDirectory(prefix="smallcloud_build_") as build_dir:
                if log_callback:
                    await log_callback("INFO", f"Cloning repository {source_repo} (branch: {branch})...")

                code, out = await self._run_cmd(
                    ["git", "clone", "--depth", "1", "--branch", branch, source_repo, "."],
                    log_callback,
                    cwd=build_dir
                )
                if code != 0:
                    raise RuntimeError(f"Git clone failed: {out}")

                # Check for Dockerfile or synthesize one
                dockerfile_path = os.path.join(build_dir, "Dockerfile")
                if not os.path.isfile(dockerfile_path):
                    if log_callback:
                        await log_callback("INFO", f"No Dockerfile found. Generating default container spec for {runtime}...")
                    if runtime == "python":
                        dockerfile_content = f"""FROM python:3.12-slim
WORKDIR /app
COPY requirements*.txt pyproject.toml* ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true
COPY . .
EXPOSE {internal_port}
CMD ["python", "main.py"]
"""
                    elif runtime == "node":
                        dockerfile_content = f"""FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE {internal_port}
CMD ["npm", "start"]
"""
                    else:
                        raise ValueError(f"Unsupported runtime: {runtime}")

                    with open(dockerfile_path, "w", encoding="utf-8") as f:
                        f.write(dockerfile_content)

                if log_callback:
                    await log_callback("INFO", f"Building container image '{image_tag}'...")

                code, out = await self._run_cmd(
                    ["docker", "build", "-t", image_tag, "."],
                    log_callback,
                    cwd=build_dir
                )
                if code != 0:
                    raise RuntimeError(f"Docker build failed: {out}")

                final_image = image_tag

        # Retrieve image digest
        code, digest_out = await self._run_cmd(["docker", "inspect", "--format={{index .Id}}", final_image])
        image_digest = digest_out.strip() if code == 0 else f"sha256:{deployment_id[:16]}"

        # Stop existing container for this service if running
        if log_callback:
            await log_callback("INFO", f"Stopping previous container instance '{container_name}' (if running)...")
        await self._run_cmd(["docker", "rm", "-f", container_name])

        # Prepare Run Command with Resource Limits and Traefik Ingress Labels
        cpus_arg = f"{cpu_millicores / 1000.0:.2f}"
        mem_arg = f"{memory_mb}m"
        router_host = f"{service_slug}.{settings.apps_domain}"

        run_args = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", network_name,
            "--restart", "unless-stopped",
            f"--cpus={cpus_arg}",
            f"--memory={mem_arg}",
            "--label", "traefik.enable=true",
            "--label", f"traefik.http.routers.{container_name}.rule=Host(`{router_host}`)",
            "--label", f"traefik.http.routers.{container_name}.entrypoints=web",
            "--label", f"traefik.http.services.{container_name}.loadbalancer.server.port={internal_port}",
        ]

        # Pass environment variables
        for k, v in env_vars.items():
            run_args.extend(["-e", f"{k}={v}"])

        run_args.append(final_image)

        if log_callback:
            await log_callback("INFO", f"Starting container '{container_name}' on network '{network_name}'...")

        code, run_out = await self._run_cmd(run_args, log_callback)
        if code != 0:
            raise RuntimeError(f"Failed to run container: {run_out}")

        container_id = run_out.strip()[:12]
        if log_callback:
            await log_callback("INFO", f"Container started successfully! Container ID: {container_id}")
            await log_callback("INFO", f"Ingress Route registered at: http://{router_host}")

        return DriverResult(
            image_digest=image_digest,
            output_url=f"http://{router_host}"
        )

def get_deployment_driver() -> BaseDeploymentDriver:
    driver = settings.deployment_driver.lower().strip()
    if driver in {"docker", "local_docker"}:
        return DockerDeploymentDriver()
    if driver == "mock":
        return MockDeploymentDriver()
    raise RuntimeError(f"Configured deployment driver '{driver}' is not supported")
