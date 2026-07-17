"""Measure real Chromium process-tree cost for 1/2/4 FireMap contexts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass

import psutil
from playwright.async_api import async_playwright

from app.config import get_settings


@dataclass
class Measurement:
    contexts: int
    load_seconds: float
    baseline_rss_mb: float
    loaded_rss_mb: float
    incremental_rss_mb: float
    cpu_seconds_during_load: float
    process_count: int


def _process_tree_metrics() -> tuple[int, int, float]:
    processes = [psutil.Process(os.getpid())]
    try:
        processes.extend(processes[0].children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    rss = 0
    cpu_seconds = 0.0
    live_count = 0
    for process in processes:
        try:
            rss += process.memory_info().rss
            cpu = process.cpu_times()
            cpu_seconds += cpu.user + cpu.system
            live_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rss, live_count, cpu_seconds


async def _measure(url: str, context_count: int, settle_seconds: float) -> Measurement:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        await asyncio.sleep(0.5)
        baseline_rss, _, cpu_before = _process_tree_metrics()
        started = time.perf_counter()

        async def open_context():
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            return context

        contexts = await asyncio.gather(
            *(open_context() for _ in range(context_count))
        )
        await asyncio.sleep(settle_seconds)
        elapsed = time.perf_counter() - started
        loaded_rss, process_count, cpu_after = _process_tree_metrics()

        for context in contexts:
            await context.close()
        await browser.close()

    mib = 1024 * 1024
    return Measurement(
        contexts=context_count,
        load_seconds=round(elapsed, 3),
        baseline_rss_mb=round(baseline_rss / mib, 2),
        loaded_rss_mb=round(loaded_rss / mib, 2),
        incremental_rss_mb=round((loaded_rss - baseline_rss) / mib, 2),
        cpu_seconds_during_load=round(cpu_after - cpu_before, 3),
        process_count=process_count,
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=get_settings().firemap_url)
    parser.add_argument("--contexts", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    measurements = [
        asdict(await _measure(args.url, count, args.settle_seconds))
        for count in args.contexts
    ]
    result = {"url": args.url, "measurements": measurements}
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(rendered + "\n")


if __name__ == "__main__":
    asyncio.run(main())
