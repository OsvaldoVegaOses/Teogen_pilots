from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx


@dataclass
class RunResult:
    enqueue_ms: float
    total_ms: float
    final_status: str
    task_id: str | None
    error: str | None = None


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = int(round((p / 100.0) * (len(ordered) - 1)))
    return ordered[k]


async def run_single_user(
    client: httpx.AsyncClient,
    base_api: str,
    project_id: str,
    poll_interval: float,
    timeout_seconds: float,
) -> RunResult:
    start = time.perf_counter()
    task_id: str | None = None

    try:
        enqueue_start = time.perf_counter()
        response = await client.post(
            f"{base_api}/projects/{project_id}/generate-theory",
            json={"min_interviews": 1, "use_model_router": True},
        )
        enqueue_ms = (time.perf_counter() - enqueue_start) * 1000.0

        if response.status_code != 202:
            detail = response.text[:500]
            return RunResult(
                enqueue_ms=enqueue_ms,
                total_ms=(time.perf_counter() - start) * 1000.0,
                final_status="enqueue_failed",
                task_id=None,
                error=f"status={response.status_code} detail={detail}",
            )

        payload = response.json()
        task_id = payload.get("task_id")
        if not task_id:
            return RunResult(
                enqueue_ms=enqueue_ms,
                total_ms=(time.perf_counter() - start) * 1000.0,
                final_status="enqueue_invalid",
                task_id=None,
                error="missing task_id",
            )

        deadline = time.perf_counter() + timeout_seconds
        status = "pending"

        while time.perf_counter() < deadline:
            status_resp = await client.get(
                f"{base_api}/projects/{project_id}/generate-theory/status/{task_id}"
            )
            if status_resp.status_code != 200:
                return RunResult(
                    enqueue_ms=enqueue_ms,
                    total_ms=(time.perf_counter() - start) * 1000.0,
                    final_status="status_failed",
                    task_id=task_id,
                    error=f"status endpoint returned {status_resp.status_code}",
                )

            status_payload = status_resp.json()
            status = status_payload.get("status", "unknown")
            if status in {"completed", "failed"}:
                return RunResult(
                    enqueue_ms=enqueue_ms,
                    total_ms=(time.perf_counter() - start) * 1000.0,
                    final_status=status,
                    task_id=task_id,
                    error=status_payload.get("error") if status == "failed" else None,
                )

            next_poll = max(poll_interval, float(status_payload.get("next_poll_seconds", poll_interval)))
            await asyncio.sleep(next_poll)

        return RunResult(
            enqueue_ms=enqueue_ms,
            total_ms=(time.perf_counter() - start) * 1000.0,
            final_status="timeout",
            task_id=task_id,
            error="poll timeout exceeded",
        )

    except Exception as exc:
        return RunResult(
            enqueue_ms=0.0,
            total_ms=(time.perf_counter() - start) * 1000.0,
            final_status="exception",
            task_id=task_id,
            error=str(exc),
        )


async def run_load_test(args: argparse.Namespace) -> Dict[str, Any]:
    base_api = args.base_url.rstrip("/")
    if not base_api.endswith("/api"):
        base_api = f"{base_api}/api"

    headers = {"Authorization": f"Bearer {args.token}"}
    timeout = httpx.Timeout(connect=10.0, read=args.request_timeout, write=10.0, pool=10.0)

    async with httpx.AsyncClient(headers=headers, timeout=timeout, verify=not args.insecure) as client:
        tasks = []
        for i in range(args.users):
            project_id = args.project_ids[i % len(args.project_ids)]
            tasks.append(
                run_single_user(
                    client=client,
                    base_api=base_api,
                    project_id=project_id,
                    poll_interval=args.poll_interval,
                    timeout_seconds=args.pipeline_timeout,
                )
            )
            await asyncio.sleep(args.spawn_interval)

        results = await asyncio.gather(*tasks)

    enqueue_values = [r.enqueue_ms for r in results if r.enqueue_ms > 0]
    total_values = [r.total_ms for r in results]

    by_status: Dict[str, int] = {}
    for result in results:
        by_status[result.final_status] = by_status.get(result.final_status, 0) + 1

    summary = {
        "users": args.users,
        "projects": args.project_ids,
        "status_counts": by_status,
        "enqueue_ms": {
            "avg": round(statistics.mean(enqueue_values), 2) if enqueue_values else 0.0,
            "p50": round(_percentile(enqueue_values, 50), 2),
            "p95": round(_percentile(enqueue_values, 95), 2),
            "max": round(max(enqueue_values), 2) if enqueue_values else 0.0,
        },
        "total_ms": {
            "avg": round(statistics.mean(total_values), 2) if total_values else 0.0,
            "p50": round(_percentile(total_values, 50), 2),
            "p95": round(_percentile(total_values, 95), 2),
            "max": round(max(total_values), 2) if total_values else 0.0,
        },
        "errors": [
            {"task_id": r.task_id, "status": r.final_status, "error": r.error}
            for r in results
            if r.error
        ][:50],
    }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TheoGen load test for theory pipeline endpoints")
    parser.add_argument("--base-url", required=True, help="API base URL (with or without /api)")
    parser.add_argument("--token", required=True, help="Bearer token")
    parser.add_argument(
        "--project-ids",
        required=True,
        nargs="+",
        help="One or more project IDs. Users are distributed round-robin.",
    )
    parser.add_argument("--users", type=int, default=100, help="Concurrent simulated users")
    parser.add_argument("--spawn-interval", type=float, default=0.1, help="Seconds between user starts")
    parser.add_argument("--poll-interval", type=float, default=4.0, help="Minimum poll interval seconds")
    parser.add_argument("--pipeline-timeout", type=float, default=900.0, help="Max seconds per pipeline")
    parser.add_argument("--request-timeout", type=float, default=30.0, help="HTTP read timeout seconds")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification")
    parser.add_argument("--output", default="", help="Optional JSON output file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    summary = asyncio.run(run_load_test(args))
    summary["wall_time_seconds"] = round(time.perf_counter() - started, 2)

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
