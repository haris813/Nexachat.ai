"""Small concurrent HTTP latency smoke test for a running NexaChat instance."""

from __future__ import annotations

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def request_once(url: str, timeout: float) -> tuple[float, int]:
    started = time.perf_counter()
    response = requests.get(url, timeout=timeout)
    return (time.perf_counter() - started) * 1000, response.status_code


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")

    url = f"{args.base_url.rstrip('/')}/api/health"
    results: list[tuple[float, int]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(request_once, url, args.timeout) for _ in range(args.requests)]
        for future in as_completed(futures):
            results.append(future.result())

    latencies = [latency for latency, _ in results]
    failures = sum(status != 200 for _, status in results)
    print(
        f"requests={len(results)} failures={failures} "
        f"mean_ms={statistics.fmean(latencies):.1f} "
        f"p50_ms={percentile(latencies, 0.50):.1f} "
        f"p95_ms={percentile(latencies, 0.95):.1f} "
        f"max_ms={max(latencies):.1f}"
    )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
