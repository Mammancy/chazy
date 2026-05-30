from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    marks: list[tuple[str, float]] = []

    start = time.perf_counter()
    import app.config.settings as settings

    marks.append(("settings import", time.perf_counter() - start))

    start = time.perf_counter()
    settings.get_settings()
    marks.append(("get_settings", time.perf_counter() - start))

    start = time.perf_counter()
    import app.main  # noqa: F401

    marks.append(("app.main import/create_application", time.perf_counter() - start))

    from app.ai.startup_validation import validate_openai_startup_configuration
    from app.config.settings import validate_production_jwt_secret
    from app.database.session import close_db, init_db
    from app.services.health_service import HealthService
    from app.services.startup_validation import validate_smtp_startup_configuration

    timed_steps = [
        ("jwt validation", validate_production_jwt_secret),
        ("smtp validation", validate_smtp_startup_configuration),
    ]
    for name, fn in timed_steps:
        start = time.perf_counter()
        fn()
        marks.append((name, time.perf_counter() - start))

    start = time.perf_counter()
    await validate_openai_startup_configuration()
    marks.append(("openai validation", time.perf_counter() - start))

    start = time.perf_counter()
    await init_db()
    marks.append(("init_db", time.perf_counter() - start))

    start = time.perf_counter()
    HealthService.build_health_response()
    marks.append(("health response", time.perf_counter() - start))

    start = time.perf_counter()
    await close_db()
    marks.append(("close_db", time.perf_counter() - start))

    for name, seconds in marks:
        print(f"{name}: {seconds * 1000:.2f} ms")


if __name__ == "__main__":
    asyncio.run(main())
