"""단위 테스트."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config_loader import ConfigError, load_config
from src.config_loader import Business
from src.matcher import SearchResultItem, find_business_rank
from src.parser import (
    infer_list_category,
    list_url_for_keyword,
    parse_places_from_apollo_payload,
    parse_places_from_dom_links,
    to_search_results,
)
from src.place_search import (
    PlaceCandidate,
    filter_candidates,
    parse_place_candidates,
    pick_auto_candidate,
    score_candidate,
)
from src.place_url import PlaceUrlError, build_place_url, parse_place_url
from src.storage import Storage
from src.team_config import load_team_watchlist, stable_item_id
from src.team_rankings import load_team_rankings, save_team_rankings, snapshot_from_watchlist
from src.watchlist import (
    WatchlistData,
    WatchlistError,
    WatchlistItem,
    add_item,
    apply_rank_refresh,
    load_watchlist,
    rank_changed,
    remove_item,
    save_watchlist,
)


class ConfigLoaderTests(unittest.TestCase):
    def test_load_valid_config(self) -> None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "test_targets.yaml"
        config = load_config(config_path)
        self.assertEqual(len(config.businesses), 2)
        self.assertEqual(len(config.targets), 2)

    def test_duplicate_business_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(
                """
businesses:
  - id: a
    name: A
    place_id: "1"
  - id: a
    name: B
    place_id: "2"
keywords:
  - test
""",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(path)


class MatcherTests(unittest.TestCase):
    def test_match_by_place_id(self) -> None:
        business = Business(id="x", name="테스트", place_id="123")
        results = [
            SearchResultItem(rank=1, place_id="999", name="다른 업체"),
            SearchResultItem(rank=2, place_id="123", name="테스트"),
        ]
        match = find_business_rank(business, results)
        self.assertTrue(match.found)
        self.assertEqual(match.rank, 2)
        self.assertEqual(match.matched_by, "place_id")

    def test_empty_name_does_not_match_first_result(self) -> None:
        business = Business(id="x", name="", place_id="1934883905")
        results = [
            SearchResultItem(rank=1, place_id="1100344328", name="아낙네의밀가 공주본점"),
            SearchResultItem(rank=2, place_id="31992305", name="피탕김탕"),
        ]
        match = find_business_rank(business, results)
        self.assertFalse(match.found)
        self.assertIsNone(match.rank)


class ParserTests(unittest.TestCase):
    def test_parse_apollo_payload(self) -> None:
        payload = {
            "error": None,
            "total": 7049,
            "places": [
                {"place_id": "2051450000", "name": "도원반점 강남역직영점"},
                {"place_id": "1698724177", "name": "뚜레쥬르 강남직영점"},
            ],
        }
        places, total = parse_places_from_apollo_payload(payload)
        self.assertEqual(total, 7049)
        self.assertEqual(places[0][0], "2051450000")
        results = to_search_results(places)
        self.assertEqual(results[0].rank, 1)

    def test_list_url_for_food_keyword(self) -> None:
        url = list_url_for_keyword("공주시 맛집", 50)
        self.assertIn("/restaurant/list", url)
        self.assertIn("display=50", url)

    def test_list_url_for_general_keyword(self) -> None:
        url = list_url_for_keyword("강남 미용실", 30)
        self.assertIn("/place/list", url)

    def test_list_url_for_medical_keyword(self) -> None:
        url = list_url_for_keyword("강남역 한의원", 50)
        self.assertIn("/hospital/list", url)

    def test_list_url_from_hospital_place_url(self) -> None:
        url = list_url_for_keyword(
            "강남역",
            50,
            place_url="https://m.place.naver.com/hospital/1316635415/home",
        )
        self.assertIn("/hospital/list", url)

    def test_infer_list_category(self) -> None:
        self.assertEqual(infer_list_category("강남역 한의원"), "hospital")
        self.assertEqual(infer_list_category("공주시 맛집"), "restaurant")
        self.assertEqual(
            infer_list_category("강남", "https://m.place.naver.com/hospital/1/home"),
            "hospital",
        )

    def test_parse_hospital_dom_links(self) -> None:
        links = [
            {
                "href": "https://pcmap.place.naver.com/hospital/1316635415/home",
                "text": "테스트한의원",
            }
        ]
        places = parse_places_from_dom_links(links)
        self.assertEqual(places, [("1316635415", "테스트한의원")])


class PlaceUrlTests(unittest.TestCase):
    def test_parse_map_entry_url(self) -> None:
        place_id = parse_place_url("https://map.naver.com/p/entry/place/2051450000")
        self.assertEqual(place_id, "2051450000")

    def test_parse_pcmap_url(self) -> None:
        place_id = parse_place_url(
            "https://pcmap.place.naver.com/restaurant/1476560900/home"
        )
        self.assertEqual(place_id, "1476560900")

    def test_parse_hospital_url(self) -> None:
        place_id = parse_place_url(
            "https://m.place.naver.com/hospital/1316635415/home"
        )
        self.assertEqual(place_id, "1316635415")

    def test_parse_map_search_place_url(self) -> None:
        place_id = parse_place_url(
            "https://map.naver.com/p/search/%EC%B2%9C%EC%95%88%20%EC%A0%9C%EC%8A%A4%ED%8A%B8"
            "/place/1693055805?entry=pll&searchText=test"
        )
        self.assertEqual(place_id, "1693055805")

    def test_invalid_url_raises(self) -> None:
        with self.assertRaises(PlaceUrlError):
            parse_place_url("https://www.naver.com")


class PlaceSearchTests(unittest.TestCase):
    def test_build_place_url_for_hospital(self) -> None:
        url = build_place_url(
            "1316635415",
            category="한의원",
            href="https://pcmap.place.naver.com/hospital/1316635415/home",
        )
        self.assertIn("/hospital/1316635415", url)

    def test_filter_candidates_exact_name_only(self) -> None:
        candidates = [
            PlaceCandidate("1", "아르스킨의원 홍대점", "서울 마포구", "피부과", "url1"),
            PlaceCandidate("2", "나인의원 홍대입구역", "서울 마포구", "피부과", "url2"),
            PlaceCandidate("3", "스타벅스 강남역점", "서울 강남구", "카페", "url3"),
        ]
        filtered = filter_candidates("아르스킨의원 홍대점", candidates)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].name, "아르스킨의원 홍대점")

    def test_filter_candidates_rejects_partial_match(self) -> None:
        candidates = [
            PlaceCandidate("1", "스타벅스 강남역점", "서울 강남구", "카페", "url1"),
            PlaceCandidate("2", "스타벅스 홍대점", "서울 마포구", "카페", "url2"),
        ]
        self.assertEqual(filter_candidates("스타벅스", candidates), [])
        self.assertEqual(filter_candidates("홍대피부과", candidates), [])

    def test_pick_auto_candidate_exact_name(self) -> None:
        candidates = [
            PlaceCandidate("1", "아르스킨의원 홍대점", "서울 마포구", "피부과", "url1"),
            PlaceCandidate("2", "나인의원 홍대입구역", "서울 마포구", "피부과", "url2"),
        ]
        picked = pick_auto_candidate("아르스킨의원 홍대점", candidates)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.place_id, "1")

    def test_pick_auto_candidate_requires_selection_for_duplicates(self) -> None:
        candidates = [
            PlaceCandidate("1", "스타벅스", "서울 강남구", "카페", "url1"),
            PlaceCandidate("2", "스타벅스", "서울 마포구", "카페", "url2"),
        ]
        self.assertIsNone(pick_auto_candidate("스타벅스", candidates))

    def test_parse_place_candidates_payload(self) -> None:
        payload = {
            "candidates": [
                {
                    "place_id": "123",
                    "name": "테스트 업체",
                    "address": "서울 강남구",
                    "category": "카페",
                    "href": "/restaurant/123/home",
                }
            ]
        }
        candidates = parse_place_candidates(payload)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].place_id, "123")
        self.assertIn("/restaurant/123", candidates[0].place_url)

    def test_score_candidate_exact_match(self) -> None:
        candidate = PlaceCandidate("1", "스타벅스", "주소", "카페", "url")
        self.assertEqual(score_candidate("스타벅스", candidate), 100)


class LookupCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        from src.lookup_cache import clear_lookup_cache

        clear_lookup_cache()

    def test_cache_returns_result_within_ttl(self) -> None:
        from src.lookup import RankLookupResult
        from src.lookup_cache import get_cached_lookup, set_cached_lookup

        result = RankLookupResult(
            keyword="강남역 맛집",
            place_id="123",
            place_name="테스트",
            rank=3,
            found=True,
            result_count=20,
            max_rank=50,
            collected_at="2026-05-28T10:00:00+09:00",
        )
        set_cached_lookup("강남역 맛집", "https://map.naver.com/p/entry/place/123", 50, result)
        cached = get_cached_lookup("강남역 맛집", "https://map.naver.com/p/entry/place/123", 50)
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual(cached.rank, 3)

    def test_cache_skips_error_results(self) -> None:
        from src.lookup import RankLookupResult
        from src.lookup_cache import get_cached_lookup, set_cached_lookup

        result = RankLookupResult(
            keyword="강남역 맛집",
            place_id="123",
            place_name=None,
            rank=None,
            found=False,
            result_count=0,
            max_rank=50,
            collected_at="2026-05-28T10:00:00+09:00",
            error="조회 실패",
        )
        set_cached_lookup("강남역 맛집", "https://map.naver.com/p/entry/place/123", 50, result)
        self.assertIsNone(
            get_cached_lookup("강남역 맛집", "https://map.naver.com/p/entry/place/123", 50)
        )


class WatchlistTests(unittest.TestCase):
    def test_add_remove_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watchlist.json"
            data = WatchlistData()
            add_item(
                data,
                place_url="https://map.naver.com/p/entry/place/111",
                keyword="강남역 맛집",
                place_name="테스트 업체",
                place_id="111",
                rank=3,
                found=True,
                updated_at="2026-05-27T09:00:00+09:00",
            )
            save_watchlist(data, path)
            loaded = load_watchlist(path)
            self.assertEqual(len(loaded.items), 1)
            item_id = loaded.items[0].id
            remove_item(loaded, item_id)
            self.assertEqual(len(loaded.items), 0)

    def test_max_items_limit(self) -> None:
        data = WatchlistData()
        for i in range(20):
            add_item(
                data,
                place_url=f"https://map.naver.com/p/entry/place/{1000 + i}",
                keyword=f"키워드{i}",
                place_name=f"업체{i}",
                place_id=str(1000 + i),
                rank=1,
                found=True,
                updated_at="2026-05-27T09:00:00+09:00",
            )
        with self.assertRaises(WatchlistError):
            add_item(
                data,
                place_url="https://map.naver.com/p/entry/place/9999",
                keyword="추가",
                place_name="초과",
                place_id="9999",
                rank=1,
                found=True,
                updated_at="2026-05-27T09:00:00+09:00",
            )

    def test_rank_refresh_detects_change(self) -> None:
        item = WatchlistItem(
            id="1",
            place_id="111",
            place_url="https://map.naver.com/p/entry/place/111",
            place_name="테스트",
            keyword="강남역 맛집",
            rank=5,
            found=True,
            updated_at="2026-05-27T09:00:00+09:00",
        )
        apply_rank_refresh(
            item,
            rank=3,
            found=True,
            place_name="테스트",
            updated_at="2026-05-27T09:05:00+09:00",
        )
        self.assertTrue(item.changed)
        self.assertEqual(item.prev_rank, 5)
        self.assertEqual(item.rank, 3)
        self.assertTrue(rank_changed(5, 3, True, True))


class TeamConfigTests(unittest.TestCase):
    def test_load_team_watchlist(self) -> None:
        path = Path(__file__).resolve().parent.parent / "config" / "team_watchlist.yaml"
        config = load_team_watchlist(path)
        self.assertGreaterEqual(len(config.items), 1)
        self.assertEqual(stable_item_id("2051450000", "강남역 맛집"), stable_item_id("2051450000", "강남역 맛집"))

    def test_team_rankings_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team_rankings.json"
            data = WatchlistData(
                items=[
                    WatchlistItem(
                        id="abc",
                        place_id="111",
                        place_url="https://map.naver.com/p/entry/place/111",
                        place_name="테스트",
                        keyword="키워드",
                        rank=2,
                        found=True,
                    )
                ],
                max_rank=50,
            )
            snapshot = snapshot_from_watchlist(
                data,
                refreshed_at="2026-05-27T10:00:00+09:00",
                refreshed_by="test",
            )
            save_team_rankings(snapshot, path)
            loaded = load_team_rankings(path)
            assert loaded is not None
            self.assertEqual(len(loaded.items), 1)
            self.assertEqual(loaded.refreshed_by, "test")


class SupabaseStoreTests(unittest.TestCase):
    def test_upsert_member_returns_existing_row(self) -> None:
        from unittest.mock import MagicMock

        from src.supabase_store import SupabaseStore

        client = MagicMock()
        table = MagicMock()
        client.table.return_value = table
        select_chain = MagicMock()
        select_chain.execute.return_value = MagicMock(
            data=[
                {
                    "id": "member-1",
                    "display_name": "김민수",
                    "team_code": "trend2026",
                    "max_rank": 80,
                }
            ]
        )
        table.select.return_value.eq.return_value.eq.return_value.limit.return_value = (
            select_chain
        )

        member = SupabaseStore(client=client).upsert_member("김민수", "trend2026")
        self.assertEqual(member.id, "member-1")
        self.assertEqual(member.max_rank, 80)
        table.insert.assert_not_called()

    def test_upsert_member_recovers_after_duplicate_insert(self) -> None:
        from unittest.mock import MagicMock

        from postgrest.exceptions import APIError

        from src.supabase_store import SupabaseStore

        client = MagicMock()
        table = MagicMock()
        client.table.return_value = table

        empty_select = MagicMock()
        empty_select.execute.return_value = MagicMock(data=[])

        found_select = MagicMock()
        found_select.execute.return_value = MagicMock(
            data=[
                {
                    "id": "member-2",
                    "display_name": "안동현",
                    "team_code": "trend2026",
                    "max_rank": 50,
                }
            ]
        )

        table.select.return_value.eq.return_value.eq.return_value.limit.side_effect = [
            empty_select,
            found_select,
        ]
        table.insert.return_value.execute.side_effect = APIError(
            {"message": "duplicate key value violates unique constraint", "code": "23505"}
        )

        member = SupabaseStore(client=client).upsert_member("안동현", "trend2026")
        self.assertEqual(member.id, "member-2")


class StorageTests(unittest.TestCase):
    def test_save_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            storage.sync_businesses(
                [Business(id="biz", name="테스트 업체", place_id="111")]
            )
            storage.save_ranking(
                collected_at="2026-05-27T09:00:00+09:00",
                business_id="biz",
                keyword="강남역 맛집",
                rank=3,
                found=True,
                result_count=20,
            )
            rows = storage.export_rankings()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].rank, 3)


if __name__ == "__main__":
    unittest.main()
