"""Worker 运行时对主分析与记忆链路的统一装配测试。"""

from dataclasses import dataclass
from typing import cast

import pytest

from app.agent.factory import Agent
from app.memory.job import MemoryJobRepository
from app.memory.pricing import ModelTokenPrice
from app.memory.worker import MemoryJobWorker
from app.run.executor import RunExecutor
from app.sandbox.remote import RemoteMemory
from app.store import postgres, redis
from app.worker import runtime as runtime_module
from config import Settings


class FakeEngine:
    def __init__(self) -> None:
        self.closed = False

    async def dispose(self) -> None:
        self.closed = True


class FakeCache:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeCheckpointPool:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class FakeCheckpoint:
    saver: object
    pool: FakeCheckpointPool


async def test_build_worker_wires_one_auxiliary_model_into_recall_jobs_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    cache = FakeCache()
    checkpoint = FakeCheckpoint(saver=object(), pool=FakeCheckpointPool())
    models: list[tuple[str | None, object]] = []

    def create_engine(dsn: str) -> FakeEngine:
        assert dsn
        return engine

    async def check_store(store: object) -> None:
        assert store in {engine, cache}

    def create_cache(url: str) -> FakeCache:
        assert url
        return cache

    async def open_checkpoint(conninfo: str) -> FakeCheckpoint:
        assert conninfo
        return checkpoint

    def create_model(settings: Settings, *, model_name: str | None = None) -> object:
        model = object()
        models.append((model_name, model))
        return model

    monkeypatch.setattr(postgres, "create_engine", create_engine)
    monkeypatch.setattr(postgres, "check", check_store)
    monkeypatch.setattr(redis, "create_client", create_cache)
    monkeypatch.setattr(redis, "check", check_store)
    monkeypatch.setattr(runtime_module, "open_checkpoint", open_checkpoint)
    monkeypatch.setattr(runtime_module, "create_model", create_model)

    settings = Settings(
        deepseek_api_key="sk-test",
        model_aux="aux-memory-model",
        model_aux_price_input=4,
        model_aux_price_cached=0.2,
        model_aux_price_output=12,
        memory_worker_poll_second=2,
        memory_job_max_attempts=4,
        memory_job_stale_second=900,
        _env_file=None,
    )
    runtime = await runtime_module.build_worker(settings)

    assert {name for name, _ in models} == {None, "aux-memory-model"}
    auxiliary_model = next(model for name, model in models if name == "aux-memory-model")
    executor = cast(RunExecutor, runtime.worker._executor)
    agent = cast(Agent, executor._agent)
    memory_worker = cast(MemoryJobWorker, runtime.memory_loop._runner)
    repository = cast(MemoryJobRepository, memory_worker._repository)

    assert isinstance(agent._memory_service, RemoteMemory)
    assert agent._selector_model is auxiliary_model
    assert memory_worker._storage is agent._memory_service
    assert memory_worker._extractor._model is auxiliary_model
    assert memory_worker._consolidator._model is auxiliary_model
    assert memory_worker._max_attempts == 4
    assert executor._memory_usage is repository
    assert executor._selector_model_name == "aux-memory-model"
    assert isinstance(executor._selector_cost, ModelTokenPrice)
    assert memory_worker._cost is executor._selector_cost
    assert runtime.memory_loop._stale_repository is repository
    assert runtime.memory_loop._poll_second == 2
    assert runtime.memory_loop._stale_second == 900

    await runtime.aclose()
    assert engine.closed
    assert cache.closed
    assert checkpoint.pool.closed
