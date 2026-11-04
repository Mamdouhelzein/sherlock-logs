from pydantic import Field

from sherlock_api.config import Settings


class WorkerSettings(Settings):
    model_artifact_dir: str = ""
    worker_model_version: str = Field(default="", pattern=r"^$|^[a-f0-9]{64}$")
    worker_trust_local_artifact: bool = False
    worker_lease_seconds: int = Field(default=60, ge=10, le=900)
    worker_poll_seconds: float = Field(default=2, ge=0.5, le=30)
    worker_history_limit: int = Field(default=10000, ge=100, le=100000)
