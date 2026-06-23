"""
Runner de benchmarks Avgerinos.

Genere les instances |M| in {2,5,10}, |J| in {5|M|, 10|M|}, tau in {0.5, 0.8},
lance CPSATSolver et ATCSSolver, calcule Err = (ATCS - CPSAT) / ATCS.

Cible : Err ATCS < 15%.

Usage : python -m tests.benchmarks.run_benchmarks [--quick]
"""
import json
import logging
import os
import sys
import time

from scheduling.solvers.atcs_solver import ATCSSolver
from scheduling.solvers.cpsat_solver import CPSATSolver
from tests.benchmarks.avgerinos import generate_avgerinos_instance

logging.disable(logging.INFO)

MACHINE_SIZES = [2, 5, 10]
JOB_RATIOS = [5, 10]
TAUS = [0.5, 0.8]


def run(quick=False, cpsat_timeout=15):
    machine_sizes = [2, 5] if quick else MACHINE_SIZES
    results = []

    for m in machine_sizes:
        for ratio in JOB_RATIOS:
            nb_jobs = ratio * m
            for tau in TAUS:
                inst = generate_avgerinos_instance(
                    nb_machines=m, nb_jobs=nb_jobs, tau=tau, seed=42
                )
                t0 = time.time()
                atcs = ATCSSolver().solve(inst)
                t_atcs = time.time() - t0

                t1 = time.time()
                cpsat = CPSATSolver(timeout_seconds=cpsat_timeout).solve(inst)
                t_cpsat = time.time() - t1

                atcs_twt = atcs.total_weighted_tardiness
                cpsat_twt = cpsat.total_weighted_tardiness if cpsat else None
                err = (
                    (atcs_twt - cpsat_twt) / atcs_twt
                    if cpsat_twt is not None and atcs_twt > 0
                    else 0.0
                )
                row = {
                    "machines": m,
                    "jobs": nb_jobs,
                    "tau": tau,
                    "atcs_twt": atcs_twt,
                    "cpsat_twt": cpsat_twt,
                    "err": round(err, 4),
                    "atcs_time_s": round(t_atcs, 3),
                    "cpsat_time_s": round(t_cpsat, 3),
                }
                results.append(row)
                print(
                    f"M={m:>2} J={nb_jobs:>3} tau={tau} | ATCS={atcs_twt:>10.1f} "
                    f"CPSAT={cpsat_twt if cpsat_twt is None else f'{cpsat_twt:>10.1f}'} "
                    f"Err={err:>7.2%} | t_cpsat={t_cpsat:.1f}s"
                )

    out_path = os.path.join(os.path.dirname(__file__), "benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    errs = [r["err"] for r in results if r["cpsat_twt"] is not None]
    avg_err = sum(errs) / len(errs) if errs else 0.0
    print("\n=== Resume ===")
    print(f"Instances : {len(results)}")
    print(f"Err moyen (ATCS vs CPSAT) : {avg_err:.2%}")
    print(f"Cible : Err < 15% -> {'[PASS]' if avg_err < 0.15 else '[WARN]'}")
    print(f"Resultats sauvegardes : {out_path}")
    return results


if __name__ == "__main__":
    run(quick="--quick" in sys.argv)
