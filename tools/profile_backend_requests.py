from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    from app.database.session import close_db, init_db
    from app.main import app
    from app.services.health_service import HealthService

    await init_db()

    timings: list[tuple[str, float]] = []
    for label, fn in [
        ("health first", HealthService.build_health_response),
        ("health cached", HealthService.build_health_response),
        ("openapi first", app.openapi),
        ("openapi cached", app.openapi),
    ]:
        start = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - start
        if label.startswith("openapi"):
            extra = f" paths={len(result.get('paths', {}))}"
        else:
            extra = ""
        timings.append((label + extra, elapsed))

    await close_db()

    for label, seconds in timings:
        print(f"{label}: {seconds * 1000:.2f} ms")


if __name__ == "__main__":
    asyncio.run(main())
