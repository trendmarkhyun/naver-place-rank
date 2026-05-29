#!/usr/bin/env python3
"""Supabase 전체 watchlist 순위 갱신 (GitHub Actions용)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import Business
from src.storage import Storage
from src.supabase_store import SupabaseStore
from src.watchlist import WatchlistItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def refresh_all(refreshed_by: str) -> int:
    store = SupabaseStore()
    pairs = store.list_all_items()
    if not pairs:
        logger.info("갱신할 watchlist 항목이 없습니다.")
        return 0

    updated_at = Storage.now_kst_iso()
    keyword_groups: dict[str, list[tuple[str, WatchlistItem, int]]] = defaultdict(list)

    for member, item in pairs:
        keyword_groups[item.keyword].append((member.id, item, member.max_rank))

    from playwright.async_api import async_playwright

    from src.lookup import _create_browser_context
    from src.matcher import find_business_rank
    from src.search import search_keyword_results

    updated_count = 0

    async with async_playwright() as playwright:
        browser, _, page = await _create_browser_context(playwright)
        try:
            for keyword, entries in keyword_groups.items():
                max_rank = max(e[2] for e in entries)
                logger.info("키워드 '%s' (%d개 항목, max_rank=%d)", keyword, len(entries), max_rank)
                sample_url = entries[0][1].place_url
                results = await search_keyword_results(
                    page, keyword, max_rank, place_url=sample_url
                )

                for member_id, item, _ in entries:
                    business = Business(
                        id=item.id,
                        name=item.place_name,
                        place_id=item.place_id,
                    )
                    match = find_business_rank(business, results)
                    place_name = item.place_name
                    if match.found and match.rank is not None:
                        for r in results:
                            if r.place_id == item.place_id:
                                place_name = r.name
                                break

                    store.apply_rank_refresh(
                        item,
                        rank=match.rank,
                        found=match.found,
                        place_name=place_name,
                        updated_at=updated_at,
                    )
                    updated_count += 1
                    logger.info(
                        "  %s / %s → %s",
                        item.place_name,
                        keyword,
                        f"{match.rank}위" if match.found else "순위 없음",
                    )
        finally:
            await browser.close()

    logger.info("갱신 완료: %d개 (by %s)", updated_count, refreshed_by)
    return updated_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Supabase watchlist 순위 갱신")
    parser.add_argument(
        "--by",
        default="manual",
        help="갱신 주체 (github-actions, manual 등)",
    )
    args = parser.parse_args()

    try:
        count = asyncio.run(refresh_all(args.by))
        return 0 if count >= 0 else 1
    except Exception as exc:
        logger.exception("갱신 실패: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
