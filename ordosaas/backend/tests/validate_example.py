"""
Script de validation de l'implementation CPSATSolver.
Compare avec expected_output.json de l'instance exemple.
Usage : python -m tests.validate_example
"""
import csv
import json
import os
import sys

from scheduling.models.job import Job, Operation, ProblemInstance
from scheduling.solvers.cpsat_solver import CPSATSolver

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def parse_jobs_csv(path):
    with open(path, newline="") as f:
        return [
            {"job_id": r["job_id"], "deadline": int(r["deadline"]), "weight": float(r["weight"])}
            for r in csv.DictReader(f)
        ]


def parse_ops_csv(path):
    with open(path, newline="") as f:
        return [
            {
                "job_id": r["job_id"],
                "machine_id": r["machine_id"],
                "duration": int(r["duration"]),
                "position": int(r["position"]),
            }
            for r in csv.DictReader(f)
        ]


def parse_setups_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return [
            {
                "from_job": r["from_job"],
                "to_job": r["to_job"],
                "machine_id": r["machine_id"],
                "duration": int(r["duration"]),
            }
            for r in csv.DictReader(f)
        ]


def build_jobs(jobs_rows, ops_rows):
    ops_by_job = {}
    for o in ops_rows:
        ops_by_job.setdefault(o["job_id"], []).append(
            Operation(o["job_id"], o["machine_id"], o["duration"], o["position"])
        )
    jobs = []
    for j in jobs_rows:
        jobs.append(
            Job(
                id=j["job_id"],
                operations=sorted(ops_by_job.get(j["job_id"], []), key=lambda o: o.position),
                deadline=j["deadline"],
                weight=j["weight"],
            )
        )
    return jobs


def validate_precedence(schedule, instance):
    by_job = {}
    for e in schedule.entries:
        by_job.setdefault(e.job_id, []).append(e)
    for job_id, entries in by_job.items():
        ordered = sorted(entries, key=lambda e: e.position_in_job)
        for k in range(len(ordered) - 1):
            if ordered[k].end_time > ordered[k + 1].start_time:
                print(f"[FAIL] Precedence violated for {job_id}")
                sys.exit(1)
    print("[PASS] Precedence constraints satisfied")


def validate_no_overlap(schedule, instance):
    from collections import defaultdict

    slots = defaultdict(list)
    for e in schedule.entries:
        slots[e.machine_id].append((e.start_time, e.end_time))
        if e.setup and e.setup.duration > 0:
            slots[e.machine_id].append((e.setup.start_time, e.setup.end_time))
    for machine, intervals in slots.items():
        intervals.sort()
        for i in range(len(intervals) - 1):
            if intervals[i][1] > intervals[i + 1][0]:
                print(f"[FAIL] Overlap on {machine}: {intervals[i]} and {intervals[i + 1]}")
                sys.exit(1)
    print("[PASS] NoOverlap constraints satisfied")


def main():
    jobs = parse_jobs_csv(os.path.join(FIXTURES_DIR, "jobs.csv"))
    ops = parse_ops_csv(os.path.join(FIXTURES_DIR, "operations.csv"))
    setups = parse_setups_csv(os.path.join(FIXTURES_DIR, "setups.csv"))

    jobs_list = build_jobs(jobs, ops)
    setup_dict = {(r["from_job"], r["to_job"], r["machine_id"]): r["duration"] for r in setups}
    machines = sorted({o["machine_id"] for o in ops})
    instance = ProblemInstance(jobs=jobs_list, machines=machines, setup_times=setup_dict, wr=2)

    print("Solving...")
    schedule = CPSATSolver(timeout_seconds=30).solve(instance)
    if schedule is None:
        print("[FAIL] No solution found")
        sys.exit(1)

    with open(os.path.join(FIXTURES_DIR, "expected_output.json")) as f:
        expected = json.load(f)

    exp_twt = expected["kpis"]["total_weighted_tardiness"]
    act_twt = schedule.total_weighted_tardiness
    tolerance = 0.01

    print("\n=== Validation CPSATSolver ===")
    print(f"Expected TWT : {exp_twt}")
    print(f"Actual TWT   : {act_twt}")
    print(f"Jobs late    : {schedule.nb_jobs_late} (expected {expected['kpis']['nb_jobs_late']})")
    print(f"Method       : {schedule.method_used}")

    delta = abs(act_twt - exp_twt) / max(exp_twt, 1)
    if delta <= tolerance:
        print(f"[PASS] TWT within {tolerance:.0%} tolerance (delta={delta:.3%})")
    else:
        print(f"[FAIL] TWT delta={delta:.3%} exceeds {tolerance:.0%}")
        sys.exit(1)

    validate_precedence(schedule, instance)
    validate_no_overlap(schedule, instance)

    print("\n[PASS] ALL VALIDATIONS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
