"""Integration tests for instance import and job management."""
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def valid_jobs_csv():
    return b"job_id,deadline,weight\nJ1,120,8.5\nJ2,95,3.0\n"


@pytest.fixture
def valid_ops_csv():
    return (
        b"job_id,machine_id,duration,position\n"
        b"J1,M1,30,1\nJ1,M2,20,2\nJ2,M2,25,1\nJ2,M1,18,2\n"
    )


async def _create_machines(client, auth_headers):
    for ext, name in [("M1", "Tour CNC"), ("M2", "Fraiseuse")]:
        await client.post(
            "/api/v1/machines",
            headers=auth_headers,
            json={"external_id": ext, "name": name},
        )


async def _import(client, auth_headers, jobs_csv, ops_csv, name="Instance Test"):
    files = {
        "jobs_file": ("jobs.csv", jobs_csv, "text/csv"),
        "operations_file": ("operations.csv", ops_csv, "text/csv"),
    }
    return await client.post(
        "/api/v1/instances/import",
        headers=auth_headers,
        data={"name": name},
        files=files,
    )


async def test_import_valid_csv(client, auth_headers, valid_jobs_csv, valid_ops_csv):
    await _create_machines(client, auth_headers)
    res = await _import(client, auth_headers, valid_jobs_csv, valid_ops_csv)
    assert res.status_code == 201
    body = res.json()
    assert body["nb_jobs"] == 2
    assert body["nb_operations"] == 4


async def test_import_invalid_csv(client, auth_headers, valid_ops_csv):
    await _create_machines(client, auth_headers)
    bad_jobs = b"job_id,deadline\nJ1,120\n"  # missing weight column
    res = await _import(client, auth_headers, bad_jobs, valid_ops_csv)
    assert res.status_code == 400


async def test_import_unknown_machine(client, auth_headers, valid_jobs_csv):
    # No machines created -> operations reference unknown machine.
    ops = b"job_id,machine_id,duration,position\nJ1,MX,30,1\nJ2,MX,25,1\n"
    res = await _import(client, auth_headers, valid_jobs_csv, ops)
    assert res.status_code in (400, 422)


async def test_list_instances(client, auth_headers, valid_jobs_csv, valid_ops_csv):
    await _create_machines(client, auth_headers)
    await _import(client, auth_headers, valid_jobs_csv, valid_ops_csv)
    res = await client.get("/api/v1/instances", headers=auth_headers)
    assert res.status_code == 200
    assert "data" in res.json()
    assert "pagination" in res.json()


async def test_list_and_patch_jobs(client, auth_headers, valid_jobs_csv, valid_ops_csv):
    await _create_machines(client, auth_headers)
    imp = await _import(client, auth_headers, valid_jobs_csv, valid_ops_csv)
    instance_id = imp.json()["id"]

    jobs = await client.get(f"/api/v1/instances/{instance_id}/jobs", headers=auth_headers)
    assert jobs.status_code == 200
    job = jobs.json()["data"][0]

    patched = await client.patch(
        f"/api/v1/instances/{instance_id}/jobs/{job['id']}",
        headers=auth_headers,
        json={"deadline": 200, "weight": 9.0},
    )
    assert patched.status_code == 200
    assert patched.json()["deadline"] == 200


async def test_delete_instance(client, auth_headers, valid_jobs_csv, valid_ops_csv):
    await _create_machines(client, auth_headers)
    imp = await _import(client, auth_headers, valid_jobs_csv, valid_ops_csv)
    instance_id = imp.json()["id"]
    res = await client.delete(f"/api/v1/instances/{instance_id}", headers=auth_headers)
    assert res.status_code == 204
