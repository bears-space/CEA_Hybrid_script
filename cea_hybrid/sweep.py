"""Sweep orchestration and multiprocessing execution."""

import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from itertools import product

from cea_hybrid.calculations import build_cea_objects, run_case


_WORKER_CONFIG = None
_WORKER_REACTANTS = None
_WORKER_SOLVER = None


class SweepCancelled(Exception):
    pass


def resolve_cpu_workers(config):
    if config["cpu_workers"] == "auto":
        return os.cpu_count() or 1
    return max(1, int(config["cpu_workers"]))


def iter_case_inputs(config):
    return product(
        config["abs_volume_fractions"],
        config["fuel_temperatures_k"],
        config["oxidizer_temperatures_k"],
        config["ae_at_values"],
        config["of_values"],
    )


def count_total_combinations(config):
    return (
        len(config["abs_volume_fractions"])
        * len(config["fuel_temperatures_k"])
        * len(config["oxidizer_temperatures_k"])
        * len(config["ae_at_values"])
        * len(config["of_values"])
    )


def _init_worker(config):
    global _WORKER_CONFIG, _WORKER_REACTANTS, _WORKER_SOLVER
    _WORKER_CONFIG = config
    _, _WORKER_REACTANTS, _WORKER_SOLVER = build_cea_objects(config)


def _run_case_in_worker(case_input):
    abs_vol_frac, fuel_temp_k, oxidizer_temp_k, ae_at, of_ratio = case_input
    try:
        result = run_case(
            _WORKER_CONFIG,
            _WORKER_REACTANTS,
            _WORKER_SOLVER,
            abs_vol_frac,
            fuel_temp_k,
            oxidizer_temp_k,
            of_ratio,
            ae_at,
        )
    except Exception as exc:
        return {
            "kind": "failure",
            "payload": {
                "abs_vol_frac": abs_vol_frac,
                "fuel_temp_k": fuel_temp_k,
                "oxidizer_temp_k": oxidizer_temp_k,
                "of": of_ratio,
                "ae_at": ae_at,
                "reason": str(exc),
            },
        }

    if result is None:
        return {
            "kind": "failure",
            "payload": {
                "abs_vol_frac": abs_vol_frac,
                "fuel_temp_k": fuel_temp_k,
                "oxidizer_temp_k": oxidizer_temp_k,
                "of": of_ratio,
                "ae_at": ae_at,
                "reason": "CEA did not converge",
            },
        }

    if result.get("exit_diameter_within_limit") is False:
        return {"kind": "skipped", "payload": result}

    return {"kind": "success", "payload": result}


def run_sweep(config, progress_callback=None, cancel_event=None):
    """Evaluate the full cartesian sweep and collect converged and failed cases."""
    cases = []
    failures = []
    cpu_workers = resolve_cpu_workers(config)
    total_combinations = count_total_combinations(config)
    completed = 0

    def update_progress():
        if progress_callback is not None:
            progress_callback(completed, total_combinations)

    update_progress()

    if cpu_workers == 1:
        _init_worker(config)
        for case_input in iter_case_inputs(config):
            if cancel_event is not None and cancel_event.is_set():
                raise SweepCancelled("Sweep cancelled.")
            item = _run_case_in_worker(case_input)
            if item["kind"] == "success":
                cases.append(item["payload"])
            elif item["kind"] == "failure":
                failures.append(item["payload"])
            completed += 1
            update_progress()
    else:
        executor = ProcessPoolExecutor(
            max_workers=cpu_workers,
            initializer=_init_worker,
            initargs=(config,),
        )
        case_iter = iter(iter_case_inputs(config))
        max_pending = max(cpu_workers * 4, cpu_workers)
        pending = {}

        def submit_next():
            try:
                case_input = next(case_iter)
            except StopIteration:
                return False
            future = executor.submit(_run_case_in_worker, case_input)
            pending[future] = case_input
            return True

        try:
            while len(pending) < max_pending and submit_next():
                pass

            while pending:
                if cancel_event is not None and cancel_event.is_set():
                    raise SweepCancelled("Sweep cancelled.")
                done, _ = wait(
                    tuple(pending.keys()),
                    timeout=0.2,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    continue
                for future in done:
                    pending.pop(future, None)
                    item = future.result()
                    if item["kind"] == "success":
                        cases.append(item["payload"])
                    elif item["kind"] == "failure":
                        failures.append(item["payload"])
                    completed += 1
                    update_progress()
                while len(pending) < max_pending and submit_next():
                    pass
        except Exception:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown()

    cases.sort(
        key=lambda row: (
            row["abs_vol_frac"],
            row["fuel_temp_k"],
            row["oxidizer_temp_k"],
            row["ae_at"],
            row["of"],
        )
    )
    failures.sort(
        key=lambda row: (
            row["abs_vol_frac"],
            row["fuel_temp_k"],
            row["oxidizer_temp_k"],
            row["ae_at"],
            row["of"],
        )
    )

    return {
        "cases": cases,
        "failures": failures,
        "total_combinations": total_combinations,
        "cpu_workers": cpu_workers,
        "backend": "cpu-multiprocessing" if cpu_workers > 1 else "cpu-single-process",
        "gpu_enabled": False,
    }
