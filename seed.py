"""Seed the Sample Data Mode org into the database named by MONGODB_URI / MONGODB_DB.
Idempotent: an existing sample org is left as is (use reset.py to start over)."""

from __future__ import annotations

import asyncio

from overclouded.demo.seed import seed_sample_org
from overclouded.repos.client import close_client, get_db
from overclouded.repos.migrate import migrate
from overclouded.settings import get_settings


async def main() -> None:
    settings = get_settings()
    db = await get_db(settings)
    await migrate(db)
    summary = await seed_sample_org(db, settings)
    state = "created" if summary.created else "already present"
    print(f"Sample org {summary.org_id} {state}; demo clock {summary.clock.isoformat()}")
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
