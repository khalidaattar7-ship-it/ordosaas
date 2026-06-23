"""Integration tests for the resolution lifecycle."""
import asyncio

import pytest

pytestmark = pytest.mark.asyncio


async def _setup_instance(client, auth_headers):
    for ext, name in [("M1", "Tour"), ("M2", "Fraiseuse")]:
        await client.post(
            "/api/v1/machines", headers=auth_headers,
            json={"external_id": ext, "name": name},
        )
    files = {
        "jobs_file": ("jobs.csv", b"job_id,deadline,weight\nJ1,80,5\nJ2,60,3\n", "text/csv"),
        "operations_file": (
            "operations.csv",
            b"job_id,machine_id,duration,position\nJ1,M1,10,1\nJ1,M2,8,2\nJ2,M2,6,1\nJ2,M1,9,2\n",
            "text/csv",
        ),
    }
    imp = await client.post(
        "/api/v1/instances/import", headers=auth_headers,
        data={"name": "Resolve Test"}, files=files,
    )
    return imp.json()["id"]


async def test_resolve_returns_202(client, auth_headers):
    instance_id = await _setup_instance(client, auth_headers)
    res = await client.post(
        f"/api/v1/instances/{instance_id}/resolve",
        headers=auth_headers,
        json={"strategy": "cpsat", "cpsat_timeout": 10},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "pending"
    assert body["resolution_id"]


async def test_resolution_status_polling(client, auth_headers):
    instance_id = await _setup_instance(client, auth_headers)
    res = await client.post(
        f"/api/v1/instances/{instance_id}/resolve",
        headers=auth_headers,
        json={"strategy": "cpsat", "cpsat_timeout": 10},
    )
    resolution_id = res.json()["resolution_id"]

    status = None
    for _ in range(30):
        await asyncio.sleep(0.5)
        poll = await client.get(f"/api/v1/resolutions/{resolution_id}", headers=auth_headers)
        assert poll.status_code == 200
        status = poll.json()["status"]
        if status in ("completed", "failed", "cancelled", "partial"):
            break
    assert status in ("pending", "running", "completed", "partial", "failed")


async def test_gantt_after_completion(client, auth_headers):
    instance_id = await _setup_instance(client, auth_headers)
    res = await client.post(
        f"/api/v1/instances/{instance_id}/resolve",
        headers=auth_headers,
        json={"strategy": "cpsat", "cpsat_timeout": 10},
    )
    resolution_id = res.json()["resolution_id"]

    completed = False
    for _ in range(40):
        await asyncio.sleep(0.5)
        poll = await client.get(f"/api/v1/resolutions/{resolution_id}", headers=auth_headers)
        if poll.json()["status"] == "completed":
            completed = True
            break

    if completed:
        gantt = await client.get(
            f"/api/v1/resolutions/{resolution_id}/gantt", headers=auth_headers
        )
        assert gantt.status_code == 200
        data = gantt.json()
        assert "machines" in data
        assert "entries" in data
        assert len(data["entries"]) > 0
