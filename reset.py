"""Drop and re-seed the Sample Data Mode org (refuses to touch non-sample orgs)."""

from __future__ import annotations

import asyncio

from overclouded.repos.client import close_client, get_db
from overclouded.repos.migrate import migrate
from overclouded.services.demo import reset
from overclouded.settings import get_settings


async def main() -> None:
    settings = get_settings()
    db = await get_db(settings)
    await migrate(db)
    summary = await reset(db, settings)
    print(
        f"Sample org reset; {summary.open_problems} open problems; "
        f"{len(summary.historic_missions)} historic verified missions"
    )
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
