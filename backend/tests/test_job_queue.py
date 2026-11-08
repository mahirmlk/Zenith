"""Queue recovery tests using a fake Redis Streams client."""
import asyncio

import pytest

from services import job_queue


class FakeRedis:
    def __init__(self):
        self.groups = []
        self.added = []
        self.claimed = []
        self.read = []
        self.acked = []

    async def xgroup_create(self, stream, group, id, mkstream):
        self.groups.append((stream, group, id, mkstream))

    async def xadd(self, stream, fields):
        self.added.append((stream, fields))
        return "1-0"

    async def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count):
        return ("0-0", self.claimed)

    async def xreadgroup(self, group, consumer, streams, count, block):
        return self.read

    async def xack(self, stream, group, message_id):
        self.acked.append((stream, group, message_id))


@pytest.mark.asyncio
async def test_enqueue_uses_redis_stream(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(job_queue, "_use_redis", lambda: True)
    monkeypatch.setattr(job_queue, "_redis_client", lambda: _return(fake))

    await job_queue.enqueue("run-1")

    assert fake.groups == [(job_queue.QUEUE_KEY, job_queue.CONSUMER_GROUP, "0", True)]
    assert fake.added == [(job_queue.QUEUE_KEY, {"run_id": "run-1"})]


@pytest.mark.asyncio
async def test_dequeue_reclaims_idle_pending_job_before_new_work(monkeypatch):
    fake = FakeRedis()
    fake.claimed = [("7-0", {"run_id": "recovered-run"})]
    monkeypatch.setattr(job_queue, "_use_redis", lambda: True)
    monkeypatch.setattr(job_queue, "_redis_client", lambda: _return(fake))

    message = await job_queue._dequeue()

    assert message.run_id == "recovered-run"
    assert message.message_id == "7-0"
    assert fake.read == []


@pytest.mark.asyncio
async def test_dequeue_reads_new_job_when_no_pending_job(monkeypatch):
    fake = FakeRedis()
    fake.read = [(job_queue.QUEUE_KEY, [("8-0", {"run_id": "fresh-run"})])]
    monkeypatch.setattr(job_queue, "_use_redis", lambda: True)
    monkeypatch.setattr(job_queue, "_redis_client", lambda: _return(fake))

    message = await job_queue._dequeue()

    assert message.run_id == "fresh-run"
    assert message.message_id == "8-0"


@pytest.mark.asyncio
async def test_acknowledges_redis_stream_message(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(job_queue, "_redis_client", lambda: _return(fake))

    await job_queue._ack(job_queue.QueueMessage("run-1", "9-0"))

    assert fake.acked == [(job_queue.QUEUE_KEY, job_queue.CONSUMER_GROUP, "9-0")]


@pytest.mark.asyncio
async def test_worker_poll_retries_after_redis_failure(monkeypatch):
    recovered = asyncio.Event()
    calls = 0

    async def dequeue():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("redis unavailable")
        recovered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(job_queue, "_dequeue", dequeue)
    task = asyncio.create_task(job_queue.worker_loop())
    try:
        await asyncio.wait_for(recovered.wait(), timeout=3)
        assert calls >= 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stop_worker_waits_for_worker_shutdown(monkeypatch):
    started = asyncio.Event()

    async def dequeue():
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(job_queue, "_dequeue", dequeue)
    monkeypatch.setattr(job_queue, "_use_redis", lambda: False)
    job_queue.start_worker()
    await started.wait()

    await job_queue.stop_worker()

    assert job_queue._worker_task is None


async def _return(value):
    return value
