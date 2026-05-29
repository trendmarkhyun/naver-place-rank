"""네이버 플레이스 순위 모니터 — Supabase 팀원별 UI (Streamlit Cloud)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.app_common import inject_base_css, render_brand_header, require_member
from src.auth import MemberSession
from src.place_url import PlaceUrlError, parse_place_url
from src.supabase_store import SupabaseStore, SupabaseStoreError
from src.ui_helpers import format_change, format_rank
from src.watchlist import WatchlistError, WatchlistItem

st.set_page_config(
    page_title="시월기획 플레이스 순위 모니터링",
    page_icon=str(PROJECT_ROOT / "assets" / "siwol_logo.png"),
    layout="wide",
)

BRAND_TITLE = "시월기획 플레이스 순위 모니터링"

inject_base_css()
st.markdown(
    """
    <style>
    .result-card {
        background: linear-gradient(135deg, #f8fff9 0%, #ffffff 100%);
        border: 1px solid #d4edda; border-radius: 12px;
        padding: 1rem 1.25rem; margin: 0.75rem 0;
    }
    .rank-number { font-size: 2.2rem; font-weight: 800; color: #03C75A; }
    .watch-card {
        border: 1px solid #e8ece9; border-radius: 10px;
        padding: 0.55rem 0.6rem 0.65rem; margin-bottom: 0.65rem;
        background: #fff; min-height: 132px;
    }
    .watch-card.changed { background: #fffbe6; border-color: #f0d96b; }
    .watch-card .watch-name {
        font-weight: 600; color: #222; font-size: 0.88rem;
        line-height: 1.35; margin-bottom: 0.2rem;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
        overflow: hidden; word-break: keep-all;
    }
    .watch-card .watch-meta {
        color: #666; font-size: 0.76rem; line-height: 1.3;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .watch-card .watch-rank {
        font-weight: 700; color: #03C75A; font-size: 1rem; margin-top: 0.35rem;
    }
    .watch-card .watch-changed {
        color: #b8860b; font-weight: 600; font-size: 0.74rem; margin-top: 0.15rem;
    }
    .watch-card .watch-updated {
        color: #888; font-size: 0.68rem; margin-top: 0.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

WATCHLIST_KEY = "watchlist_items"
ITEMS_PER_ROW = 5
PLACE_SESSION_KEYS = (WATCHLIST_KEY,)


def _store() -> SupabaseStore:
    return SupabaseStore()


def _get_watchlist() -> list[WatchlistItem] | None:
    return st.session_state.get(WATCHLIST_KEY)


def _set_watchlist(items: list[WatchlistItem]) -> None:
    st.session_state[WATCHLIST_KEY] = items


def load_items(member_id: str) -> list[WatchlistItem]:
    return _store().list_items(member_id)


def ensure_items(member_id: str) -> list[WatchlistItem]:
    cached = _get_watchlist()
    if cached is None:
        cached = load_items(member_id)
        _set_watchlist(cached)
    return cached


def render_db_lookup_result(item: WatchlistItem, member: MemberSession) -> None:
    pending = item.rank is None and not item.updated_at
    rank_text = format_rank(item.rank, item.found, member.max_rank, pending=pending)

    if pending:
        st.info("순위 조회 전입니다. GitHub Actions가 30분마다 갱신합니다.")
    elif item.found and item.rank is not None:
        st.markdown(
            f'<div class="result-card"><div class="rank-number">{item.rank}위</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"{member.max_rank}위 이내에 노출되지 않습니다.")

    st.markdown(f"**업체명:** {item.place_name}")
    st.caption(f"키워드: `{item.keyword}` · 플레이스 ID: `{item.place_id}`")
    if item.updated_at:
        st.caption(f"마지막 갱신: {item.updated_at}")
    else:
        st.caption(f"표시 순위: {rank_text}")


def register_item(
    store: SupabaseStore,
    member: MemberSession,
    *,
    keyword: str,
    place_url: str,
    place_name: str,
) -> None:
    item = store.add_item(
        member.id,
        place_url=place_url.strip(),
        keyword=keyword.strip(),
        place_name=place_name.strip(),
    )
    updated_items = load_items(member.id)
    _set_watchlist(updated_items)
    st.success(
        f"등록 완료: {item.place_name} ({len(updated_items)}/20)\n\n"
        "순위는 GitHub Actions가 최대 30분마다 자동 갱신합니다."
    )
    st.rerun()


def lookup_registered_item(
    store: SupabaseStore,
    member: MemberSession,
    *,
    keyword: str,
    place_url: str,
) -> None:
    place_id = parse_place_url(place_url.strip())
    item = store.find_item(member.id, place_id, keyword.strip())
    if item is None:
        st.warning(
            "등록된 업체가 없습니다. 먼저 [등록]을 눌러 추가한 뒤, "
            "Actions 갱신 후 다시 [순위 조회]를 눌러 주세요."
        )
        return

    st.markdown("**조회 결과 (저장된 순위)**")
    render_db_lookup_result(item, member)


def render_item_card(item: WatchlistItem, member: MemberSession) -> None:
    pending = item.rank is None and not item.updated_at
    row_class = "watch-card changed" if item.changed else "watch-card"
    change_text = format_change(item)
    rank_text = format_rank(item.rank, item.found, member.max_rank, pending=pending)

    if st.button("✕", key=f"del_{item.id}", help="등록 해제"):
        _store().delete_item(member.id, item.id)
        _set_watchlist(load_items(member.id))
        st.rerun()

    st.markdown(f'<div class="{row_class}">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="watch-name">{item.place_name}</div>'
        f'<div class="watch-meta">키워드: {item.keyword}</div>'
        f'<div class="watch-rank">{rank_text}</div>'
        + (f'<div class="watch-changed">✓ {change_text}</div>' if change_text else ""),
        unsafe_allow_html=True,
    )
    if item.updated_at:
        st.markdown(
            f'<div class="watch-updated">갱신: {item.updated_at}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_items_grid(items: list[WatchlistItem], member: MemberSession) -> None:
    for row_start in range(0, len(items), ITEMS_PER_ROW):
        row_items = items[row_start : row_start + ITEMS_PER_ROW]
        columns = st.columns(ITEMS_PER_ROW)
        for column, item in zip(columns, row_items):
            with column:
                render_item_card(item, member)


@st.fragment(run_every=timedelta(minutes=5))
def auto_reload_items() -> None:
    member: MemberSession = st.session_state.member
    try:
        _set_watchlist(load_items(member.id))
    except SupabaseStoreError:
        if _get_watchlist() is None:
            _set_watchlist([])


def on_max_rank_change() -> None:
    member: MemberSession = st.session_state.member
    max_rank = st.session_state.max_rank_slider
    _store().update_member_max_rank(member.id, max_rank)
    member.max_rank = max_rank
    st.session_state.member = member


def render_dashboard(member: MemberSession) -> None:
    items: list[WatchlistItem] = ensure_items(member.id)
    store = _store()
    left, right = st.columns([2, 5])

    with left:
        st.subheader("등록 / 조회")
        max_rank = st.slider(
            "탐색할 최대 순위",
            min_value=10,
            max_value=100,
            value=member.max_rank,
            step=10,
            key="max_rank_slider",
            on_change=on_max_rank_change,
        )

        with st.form("input_form"):
            keyword = st.text_input("검색 키워드", placeholder="예: 신부동 맛집")
            place_url = st.text_input(
                "플레이스 URL",
                placeholder="https://map.naver.com/p/entry/place/1234567890",
            )
            place_name = st.text_input("업체명 (선택)", placeholder="표시용 이름")
            col_reg, col_lookup = st.columns(2)
            register_clicked = col_reg.form_submit_button("등록", use_container_width=True)
            lookup_clicked = col_lookup.form_submit_button(
                "순위 조회", type="primary", use_container_width=True
            )

        if register_clicked or lookup_clicked:
            if not keyword.strip() or not place_url.strip():
                st.error("키워드와 플레이스 URL을 모두 입력해 주세요.")
            else:
                try:
                    parse_place_url(place_url.strip())
                    if register_clicked:
                        register_item(
                            store,
                            member,
                            keyword=keyword,
                            place_url=place_url,
                            place_name=place_name,
                        )
                    else:
                        lookup_registered_item(
                            store,
                            member,
                            keyword=keyword,
                            place_url=place_url,
                        )
                except (WatchlistError, PlaceUrlError) as exc:
                    st.error(str(exc))
                except SupabaseStoreError as exc:
                    st.error(f"저장 오류: {exc}")

        st.caption(
            "순위 수집은 GitHub Actions가 30분마다 실행합니다. "
            "급한 경우 관리자에게 Actions 수동 실행을 요청하세요."
        )

    with right:
        st.subheader(f"내 등록 업체 ({len(items)}/20)")

        col_reload, col_refresh = st.columns(2)
        with col_reload:
            if st.button("목록 새로고침", key="reload", use_container_width=True):
                _set_watchlist(load_items(member.id))
                st.rerun()
        with col_refresh:
            if st.button("갱신 안내", key="refresh_info", use_container_width=True):
                st.info(
                    "전체 순위 갱신은 GitHub Actions → **Supabase Rank Monitor** → "
                    "**Run workflow** 로 실행합니다. 완료 후 [목록 새로고침]을 눌러 주세요."
                )

        auto_reload_items()

        if not items:
            st.info("좌측에서 키워드와 URL을 입력한 뒤 [등록]을 눌러 주세요.")
        else:
            latest = max((i.updated_at for i in items if i.updated_at), default=None)
            if latest:
                st.caption(f"마지막 순위 갱신: {latest}")
            render_items_grid(items, member)


member = require_member(extra_session_keys=PLACE_SESSION_KEYS)

render_brand_header(
    member,
    title=BRAND_TITLE,
    extra_session_keys=PLACE_SESSION_KEYS,
)

render_dashboard(member)

st.divider()
st.caption("순위 기준: Apollo placeList 일반 목록 (유료 광고 제외).")
