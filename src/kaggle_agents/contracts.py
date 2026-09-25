"""Provisional v0 contracts for the first offline telemetry slice."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")]
Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0)]
Status = Literal["SUCCEEDED", "FAILED", "TIMED_OUT", "INTERRUPTED", "BUDGET_EXHAUSTED"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class Budget(Contract):
    max_wall_seconds: Positive
    max_attempts: Annotated[int, Field(ge=1, le=10)] = 1


class Metric(Contract):
    name: Identifier
    direction: Literal["minimize", "maximize"]


class TaskSpec(Contract):
    schema_version: Literal["0"]
    task_id: Identifier
    competition: Text
    objective: Text
    rules_ref: Text
    metric: Metric
    budget: Budget


class ExperimentSpec(Contract):
    schema_version: Literal["0"]
    experiment_id: Identifier
    hypothesis: Text
    split_id: Identifier
    seed: Annotated[int, Field(ge=0, le=2**32 - 1)]
    script: Text
    input_files: Annotated[list[Text], Field(min_length=1, max_length=100)]
    params: dict[str, JsonValue] = Field(default_factory=dict)
    timeout_seconds: Positive
    retry_on: list[Literal["EXECUTION", "TIMEOUT"]] = Field(default_factory=list)


class DatasetSpec(Contract):
    """One numeric prediction per ID, with competition-owned column names."""

    schema_version: Literal["0"]
    train: Text
    test: Text
    sample_submission: Text
    id_column: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    target_column: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    prediction_column: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    min_prediction: float | None = None
    max_prediction: float | None = None

    @model_validator(mode="after")
    def check_columns_and_bounds(self) -> "DatasetSpec":
        if self.id_column in {self.target_column, self.prediction_column}:
            raise ValueError("ID must differ from target and prediction columns")
        if (
            self.min_prediction is not None
            and self.max_prediction is not None
            and self.min_prediction > self.max_prediction
        ):
            raise ValueError("Prediction bounds are reversed")
        return self


class Usage(Contract):
    """Normalized aggregate; total_tokens must not double-count cached/reasoning tokens."""

    scope: Literal["llm"] = "llm"
    total_tokens: Count | None = None
    cost_usd: NonNegative | None = None
    cost_source: Literal["unknown", "reported", "estimated", "not_applicable"] = "unknown"

    @model_validator(mode="after")
    def check_cost_source(self) -> "Usage":
        if (self.cost_source == "unknown") != (self.cost_usd is None):
            raise ValueError("unknown cost requires null; known cost requires a value")
        if self.cost_source == "not_applicable" and (self.cost_usd != 0 or self.total_tokens != 0):
            raise ValueError("not_applicable requires explicit zero cost and tokens")
        return self


class WorkerOutput(Contract):
    schema_version: Literal["0"]
    metrics: Annotated[dict[Identifier, float], Field(min_length=1, max_length=20)]
    usage: Usage = Field(default_factory=Usage)
    artifacts: Annotated[list[Text], Field(max_length=20)] = Field(default_factory=list)


class Artifact(Contract):
    path: str
    sha256: str
    size_bytes: Count


class AttemptResult(Contract):
    schema_version: Literal["0"] = "0"
    attempt_id: str
    status: Status
    failure_code: str | None
    exit_code: int | None
    started_at: str
    finished_at: str
    wall_seconds: NonNegative
    metric_value: float | None
    usage: Usage
    artifacts: list[Artifact]


class UsageSummary(Contract):
    scope: Literal["llm"] = "llm"
    total_tokens: Count | None
    known_tokens: Count
    unknown_token_attempts: Count
    total_cost_usd: NonNegative | None
    known_cost_usd: NonNegative
    unknown_cost_attempts: Count
    estimated_cost_attempts: Count


class RunResult(Contract):
    schema_version: Literal["0"] = "0"
    run_id: str
    task_id: str
    experiment_id: str
    status: Status
    decision: Literal["review", "reject"]
    rationale: str
    metric: Metric
    metric_value: float | None
    wall_seconds: NonNegative
    attempt_count: Count
    usage: UsageSummary
    result_path: str
