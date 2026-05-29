"""Supabase watchlist 저장소."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from postgrest.exceptions import APIError
from supabase import Client, create_client

from src.place_url import PlaceUrlError, parse_place_url
from src.storage import Storage
from src.watchlist import MAX_ITEMS, WatchlistError, WatchlistItem, rank_changed


class SupabaseStoreError(Exception):
    pass


@dataclass
class Member:
    id: str
    display_name: str
    team_code: str
    max_rank: int


def _get_secret(key: str) -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass

    value = os.getenv(key, "").strip()
    if not value:
        raise SupabaseStoreError(f"{key}가 설정되지 않았습니다.")
    return value


def get_client() -> Client:
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_SERVICE_KEY")
    return create_client(url, key)


class SupabaseStore:
    def __init__(self, client: Client | None = None) -> None:
        self.client = client or get_client()

    @staticmethod
    def _member_from_row(row: dict) -> Member:
        return Member(
            id=str(row["id"]),
            display_name=str(row["display_name"]),
            team_code=str(row["team_code"]),
            max_rank=int(row.get("max_rank") or 50),
        )

    @staticmethod
    def _wrap_db_error(exc: Exception) -> SupabaseStoreError:
        if isinstance(exc, APIError):
            message = str(exc)
            lowered = message.lower()
            if "max_rank" in lowered or "42703" in message:
                return SupabaseStoreError(
                    "members 테이블에 max_rank 컬럼이 없습니다. "
                    "Supabase SQL Editor에서 supabase/schema.sql을 다시 실행해 주세요."
                )
            if "23505" in message or "duplicate" in lowered or "unique" in lowered:
                return SupabaseStoreError(
                    "이미 등록된 팀원입니다. 잠시 후 다시 시도해 주세요."
                )
            return SupabaseStoreError(f"Supabase 오류: {message}")
        return SupabaseStoreError(str(exc))

    def _fetch_member_row(self, display_name: str, team_code: str) -> dict | None:
        response = (
            self.client.table("members")
            .select("*")
            .eq("display_name", display_name)
            .eq("team_code", team_code)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def upsert_member(self, display_name: str, team_code: str) -> Member:
        display_name = display_name.strip()
        team_code = team_code.strip()

        existing = self._fetch_member_row(display_name, team_code)
        if existing:
            return self._member_from_row(existing)

        try:
            inserted = (
                self.client.table("members")
                .insert(
                    {
                        "display_name": display_name,
                        "team_code": team_code,
                    }
                )
                .execute()
            )
            if inserted.data:
                return self._member_from_row(inserted.data[0])
        except APIError as exc:
            existing = self._fetch_member_row(display_name, team_code)
            if existing:
                return self._member_from_row(existing)
            raise self._wrap_db_error(exc) from exc
        except Exception as exc:
            existing = self._fetch_member_row(display_name, team_code)
            if existing:
                return self._member_from_row(existing)
            raise self._wrap_db_error(exc) from exc

        existing = self._fetch_member_row(display_name, team_code)
        if existing:
            return self._member_from_row(existing)

        raise SupabaseStoreError("팀원 등록에 실패했습니다.")

    def update_member_max_rank(self, member_id: str, max_rank: int) -> None:
        self.client.table("members").update({"max_rank": max_rank}).eq("id", member_id).execute()

    def list_items(self, member_id: str) -> list[WatchlistItem]:
        response = (
            self.client.table("watchlist_items")
            .select("*")
            .eq("member_id", member_id)
            .order("created_at")
            .execute()
        )
        return [_row_to_item(row) for row in (response.data or [])]

    def list_all_items(self) -> list[tuple[Member, WatchlistItem]]:
        members_resp = self.client.table("members").select("*").execute()
        members = {
            str(row["id"]): Member(
                id=str(row["id"]),
                display_name=str(row["display_name"]),
                team_code=str(row["team_code"]),
                max_rank=int(row.get("max_rank") or 50),
            )
            for row in (members_resp.data or [])
        }

        items_resp = self.client.table("watchlist_items").select("*").execute()
        result: list[tuple[Member, WatchlistItem]] = []
        for row in items_resp.data or []:
            member = members.get(str(row["member_id"]))
            if member is None:
                continue
            result.append((member, _row_to_item(row)))
        return result

    def add_item(
        self,
        member_id: str,
        *,
        place_url: str,
        keyword: str,
        place_name: str = "",
    ) -> WatchlistItem:
        keyword = keyword.strip()
        place_url = place_url.strip()

        if not keyword:
            raise WatchlistError("키워드를 입력해 주세요.")

        try:
            place_id = parse_place_url(place_url)
        except PlaceUrlError as exc:
            raise WatchlistError(str(exc)) from exc

        current = self.list_items(member_id)
        if len(current) >= MAX_ITEMS:
            raise WatchlistError(f"최대 {MAX_ITEMS}개까지 등록할 수 있습니다.")

        for item in current:
            if item.place_id == place_id and item.keyword == keyword:
                raise WatchlistError("이미 등록된 업체·키워드 조합입니다.")

        item_id = str(uuid.uuid4())
        payload = {
            "id": item_id,
            "member_id": member_id,
            "place_id": place_id,
            "place_url": place_url,
            "place_name": place_name or f"place_{place_id}",
            "keyword": keyword,
            "rank": None,
            "prev_rank": None,
            "found": False,
            "changed": False,
            "updated_at": None,
        }
        inserted = self.client.table("watchlist_items").insert(payload).execute()
        if not inserted.data:
            raise SupabaseStoreError("등록에 실패했습니다.")
        return _row_to_item(inserted.data[0])

    def delete_item(self, member_id: str, item_id: str) -> None:
        self.client.table("watchlist_items").delete().eq("member_id", member_id).eq(
            "id", item_id
        ).execute()

    def update_item(self, item: WatchlistItem) -> None:
        self.client.table("watchlist_items").update(
            {
                "place_name": item.place_name,
                "rank": item.rank,
                "prev_rank": item.prev_rank,
                "found": item.found,
                "changed": item.changed,
                "updated_at": item.updated_at,
            }
        ).eq("id", item.id).execute()

    def apply_rank_refresh(
        self,
        item: WatchlistItem,
        *,
        rank: int | None,
        found: bool,
        place_name: str | None,
        updated_at: str,
    ) -> None:
        item.prev_rank = item.rank
        prev_found = item.found
        item.rank = rank
        item.found = found
        item.changed = rank_changed(item.prev_rank, rank, prev_found, found)
        if place_name:
            item.place_name = place_name
        item.updated_at = updated_at
        self.update_item(item)

    def refresh_member_items(self, items: list[WatchlistItem]) -> None:
        for item in items:
            self.update_item(item)

    def update_item_ranks(self, items: list[WatchlistItem]) -> None:
        """GitHub Actions용 일괄 순위 저장 (plan API alias)."""
        self.refresh_member_items(items)

    def find_item(self, member_id: str, place_id: str, keyword: str) -> WatchlistItem | None:
        response = (
            self.client.table("watchlist_items")
            .select("*")
            .eq("member_id", member_id)
            .eq("place_id", place_id)
            .eq("keyword", keyword.strip())
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return _row_to_item(rows[0])

    @staticmethod
    def now_iso() -> str:
        return Storage.now_kst_iso()


def _row_to_item(row: dict) -> WatchlistItem:
    return WatchlistItem(
        id=str(row["id"]),
        place_id=str(row["place_id"]),
        place_url=str(row["place_url"]),
        place_name=str(row.get("place_name") or ""),
        keyword=str(row["keyword"]),
        rank=row.get("rank"),
        prev_rank=row.get("prev_rank"),
        found=bool(row.get("found", False)),
        changed=bool(row.get("changed", False)),
        updated_at=row.get("updated_at"),
    )
