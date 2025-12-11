"""ML Model Versioning with MLflow Integration

Provides centralized model versioning, tracking, and registry using MLflow.

Features:
- Automatic version tagging with timestamps
- Model performance metric logging
- Model artifact storage
- Model lineage tracking
- A/B testing support
- Rollback capabilities
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# Conditional MLflow import
# Initialize for type checkers; set to module if available
mlflow: Any | None = None
try:
    import mlflow
    import mlflow.sklearn
    import mlflow.xgboost

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    log.warning("model_versioning.mlflow_not_available")


@dataclass
class ModelMetadata:
    """Metadata for a trained model."""

    model_name: str
    version: str
    trained_at: datetime
    training_samples: int
    metrics: dict[str, float]
    model_type: str  # 'sklearn', 'xgboost', 'custom'
    git_commit: str | None = None
    tags: dict[str, str] | None = None


class ModelVersionManager:
    """Manages model versions with MLflow integration.

    Handles:
    - Model registration and versioning
    - Performance metric tracking
    - Model artifact storage (local and MLflow)
    - Version comparison and rollback
    """

    def __init__(self, tracking_uri: str | None = None, local_models_dir: Path | None = None):
        """Initialize model version manager.

        Args:
            tracking_uri: MLflow tracking server URI (defaults to env var)
            local_models_dir: Local directory for model backups
        """
        self.local_models_dir = local_models_dir or Path("models")
        self.local_models_dir.mkdir(parents=True, exist_ok=True)

        # Setup MLflow if available
        self.mlflow_enabled = MLFLOW_AVAILABLE and mlflow is not None
        if self.mlflow_enabled and mlflow is not None:
            tracking_uri = tracking_uri or os.getenv(
                "MLFLOW_TRACKING_URI", "http://localhost:5000"
            )
            mlflow.set_tracking_uri(tracking_uri)
            log.info("model_versioning.mlflow_enabled", uri=tracking_uri)
        else:
            log.warning("model_versioning.mlflow_disabled")

    def _generate_version(self) -> str:
        """Generate version string with timestamp."""
        return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def _get_git_commit(self) -> str | None:
        """Get current git commit hash if available."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def save_model(
        self,
        model: Any,
        model_name: str,
        metrics: dict[str, float] | None = None,
        training_samples: int = 0,
        model_type: str = "sklearn",
        tags: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Save model with versioning.

        Args:
            model: Trained model object
            model_name: Name of the model
            metrics: Performance metrics dict
            training_samples: Number of training samples
            model_type: Type of model ('sklearn', 'xgboost', 'custom')
            tags: Additional tags for the model
            params: Model hyperparameters

        Returns:
            Version string
        """
        version = self._generate_version()
        metrics = metrics or {}
        tags = tags or {}
        params = params or {}

        # Add system tags
        tags.update(
            {
                "model_name": model_name,
                "version": version,
                "model_type": model_type,
                "training_samples": str(training_samples),
            }
        )

        # Add git commit if available
        git_commit = self._get_git_commit()
        if git_commit:
            tags["git_commit"] = git_commit

        # Save locally (always as backup)
        local_path = self._save_local(
            model, model_name, version, metrics, training_samples, model_type
        )

        # Save to MLflow if available
        if self.mlflow_enabled:
            try:
                self._save_mlflow(
                    model, model_name, version, metrics, params, tags, model_type
                )
            except Exception:
                log.exception("model_versioning.mlflow_save_failed", model=model_name)

        log.info(
            "model_versioning.saved",
            model=model_name,
            version=version,
            local_path=str(local_path),
            samples=training_samples,
        )

        return version

    def _save_local(
        self,
        model: Any,
        model_name: str,
        version: str,
        metrics: dict,
        training_samples: int,
        model_type: str,
    ) -> Path:
        """Save model locally with versioning."""
        # Main model file (latest version)
        model_path = self.local_models_dir / f"{model_name}.pkl"

        # Versioned archive
        archive_dir = self.local_models_dir / "archive" / model_name
        archive_dir.mkdir(parents=True, exist_ok=True)
        versioned_path = archive_dir / f"{model_name}_{version}.pkl"

        # Create checkpoint
        checkpoint = {
            "model": model,
            "model_name": model_name,
            "version": version,
            "trained_at": datetime.utcnow().isoformat(),
            "training_samples": training_samples,
            "metrics": metrics,
            "model_type": model_type,
            "git_commit": self._get_git_commit(),
        }

        # Save both current and versioned
        with open(model_path, "wb") as f:
            pickle.dump(checkpoint, f)

        with open(versioned_path, "wb") as f:
            pickle.dump(checkpoint, f)

        return model_path

    def _save_mlflow(
        self,
        model: Any,
        model_name: str,
        version: str,
        metrics: dict,
        params: dict,
        tags: dict,
        model_type: str,
    ) -> None:
        """Save model to MLflow."""
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        experiment_name = f"arbitrage_{model_name}"

        # Set or create experiment
        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                mlflow.create_experiment(experiment_name)
            mlflow.set_experiment(experiment_name)
        except Exception:
            log.exception("model_versioning.experiment_setup_failed")
            return

        # Start run
        with mlflow.start_run(run_name=f"{model_name}_{version}"):
            # Log parameters
            for key, value in params.items():
                mlflow.log_param(key, value)

            # Log metrics
            for key, value in metrics.items():
                mlflow.log_metric(key, value)

            # Log tags
            for key, value in tags.items():
                mlflow.set_tag(key, value)

            # Log model based on type
            if model_type == "sklearn":
                mlflow.sklearn.log_model(model, "model", registered_model_name=model_name)
            elif model_type == "xgboost":
                mlflow.xgboost.log_model(model, "model", registered_model_name=model_name)
            else:
                # Custom model - save as pickle artifact
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
                    pickle.dump(model, tmp)
                    tmp.flush()
                    mlflow.log_artifact(tmp.name, "model")

    def load_model(
        self, model_name: str, version: str | None = None, source: str = "local"
    ) -> tuple[Any, ModelMetadata]:
        """Load model by name and optionally version.

        Args:
            model_name: Name of the model
            version: Specific version to load (None = latest)
            source: 'local' or 'mlflow'

        Returns:
            Tuple of (model, metadata)
        """
        if source == "local":
            return self._load_local(model_name, version)
        elif source == "mlflow" and self.mlflow_enabled:
            return self._load_mlflow(model_name, version)
        else:
            raise ValueError(f"Invalid source: {source}")

    def _load_local(
        self, model_name: str, version: str | None = None
    ) -> tuple[Any, ModelMetadata]:
        """Load model from local storage."""
        if version:
            # Load specific version from archive
            versioned_path = (
                self.local_models_dir / "archive" / model_name / f"{model_name}_{version}.pkl"
            )
            if not versioned_path.exists():
                raise FileNotFoundError(f"Model version not found: {versioned_path}")
            load_path = versioned_path
        else:
            # Load latest version
            model_path = self.local_models_dir / f"{model_name}.pkl"
            if not model_path.exists():
                raise FileNotFoundError(f"Model not found: {model_path}")
            load_path = model_path

        with open(load_path, "rb") as f:
            checkpoint = pickle.load(f)

        # Extract metadata
        metadata = ModelMetadata(
            model_name=checkpoint.get("model_name", model_name),
            version=checkpoint.get("version", "unknown"),
            trained_at=datetime.fromisoformat(checkpoint["trained_at"])
            if "trained_at" in checkpoint
            else datetime.utcnow(),
            training_samples=checkpoint.get("training_samples", 0),
            metrics=checkpoint.get("metrics", {}),
            model_type=checkpoint.get("model_type", "unknown"),
            git_commit=checkpoint.get("git_commit"),
        )

        return checkpoint["model"], metadata

    def _load_mlflow(
        self, model_name: str, version: str | None = None
    ) -> tuple[Any, ModelMetadata]:
        """Load model from MLflow registry."""
        if mlflow is None:
            raise RuntimeError("MLflow is not available")

        if version:
            model_uri = f"models:/{model_name}/{version}"
        else:
            model_uri = f"models:/{model_name}/latest"

        # Load model
        model = mlflow.sklearn.load_model(model_uri)

        # Get run metadata
        client = mlflow.tracking.MlflowClient()
        model_version = client.get_latest_versions(model_name, stages=["None"])[0]
        run = client.get_run(model_version.run_id)

        metadata = ModelMetadata(
            model_name=model_name,
            version=model_version.version,
            trained_at=datetime.fromtimestamp(run.info.start_time / 1000),
            training_samples=int(run.data.tags.get("training_samples", 0)),
            metrics=run.data.metrics,
            model_type=run.data.tags.get("model_type", "sklearn"),
            git_commit=run.data.tags.get("git_commit"),
            tags=run.data.tags,
        )

        return model, metadata

    def list_versions(self, model_name: str, source: str = "local") -> list[dict]:
        """List all versions of a model.

        Args:
            model_name: Name of the model
            source: 'local' or 'mlflow'

        Returns:
            List of version info dicts
        """
        if source == "local":
            return self._list_versions_local(model_name)
        elif source == "mlflow" and self.mlflow_enabled:
            return self._list_versions_mlflow(model_name)
        else:
            return []

    def _list_versions_local(self, model_name: str) -> list[dict]:
        """List local model versions."""
        archive_dir = self.local_models_dir / "archive" / model_name

        if not archive_dir.exists():
            return []

        versions = []
        for path in sorted(archive_dir.glob(f"{model_name}_*.pkl"), reverse=True):
            try:
                with open(path, "rb") as f:
                    checkpoint = pickle.load(f)

                versions.append(
                    {
                        "version": checkpoint.get("version", "unknown"),
                        "trained_at": checkpoint.get("trained_at"),
                        "training_samples": checkpoint.get("training_samples", 0),
                        "metrics": checkpoint.get("metrics", {}),
                        "path": str(path),
                    }
                )
            except Exception:
                log.warning("model_versioning.version_read_failed", path=str(path))

        return versions

    def _list_versions_mlflow(self, model_name: str) -> list[dict]:
        """List MLflow model versions."""
        if mlflow is None:
            return []

        try:
            client = mlflow.tracking.MlflowClient()
            versions_info = client.search_model_versions(f"name='{model_name}'")

            versions = []
            for v in versions_info:
                run = client.get_run(v.run_id)
                versions.append(
                    {
                        "version": v.version,
                        "trained_at": datetime.fromtimestamp(
                            run.info.start_time / 1000
                        ).isoformat(),
                        "training_samples": int(run.data.tags.get("training_samples", 0)),
                        "metrics": run.data.metrics,
                        "stage": v.current_stage,
                    }
                )

            return sorted(versions, key=lambda x: x["version"], reverse=True)

        except Exception:
            log.exception("model_versioning.mlflow_list_failed", model=model_name)
            return []

    def compare_versions(
        self, model_name: str, version1: str, version2: str
    ) -> dict[str, Any]:
        """Compare two model versions.

        Args:
            model_name: Name of the model
            version1: First version
            version2: Second version

        Returns:
            Comparison dict
        """
        _, meta1 = self.load_model(model_name, version1)
        _, meta2 = self.load_model(model_name, version2)

        comparison = {
            "model_name": model_name,
            "version1": version1,
            "version2": version2,
            "metrics_diff": {},
            "sample_count_diff": meta2.training_samples - meta1.training_samples,
        }

        # Compare metrics
        all_metrics = set(meta1.metrics.keys()) | set(meta2.metrics.keys())
        for metric in all_metrics:
            v1 = meta1.metrics.get(metric, 0)
            v2 = meta2.metrics.get(metric, 0)
            comparison["metrics_diff"][metric] = {
                "v1": v1,
                "v2": v2,
                "diff": v2 - v1,
                "pct_change": ((v2 - v1) / v1 * 100) if v1 != 0 else 0,
            }

        return comparison


# Global singleton
_manager: ModelVersionManager | None = None


def get_model_version_manager() -> ModelVersionManager:
    """Get global ModelVersionManager instance."""
    global _manager
    if _manager is None:
        _manager = ModelVersionManager()
    return _manager
