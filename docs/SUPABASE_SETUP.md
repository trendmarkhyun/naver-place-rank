# Supabase + Streamlit Cloud 배포 가이드

팀원이 **URL 하나**로 접속해, **개인별** 업체를 등록하고 순위를 확인합니다.

## 구조

```
팀원 → Streamlit Cloud (app.py)
         ↕ Supabase (members + watchlist_items)
GitHub Actions (30분) → Playwright 순위 수집 → Supabase 갱신
```

---

## 1. Supabase 설정

1. [supabase.com](https://supabase.com) → New project (Seoul)
2. **SQL Editor** → [`supabase/schema.sql`](../supabase/schema.sql) 실행
3. **Project Settings → API** 에서 복사:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` key → `SUPABASE_SERVICE_KEY`

---

## 2. GitHub Secrets (Actions용)

저장소 `trendmarkhyun/naver-place-rank` → **Settings → Secrets → Actions**

| Name | Value |
|------|-------|
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_SERVICE_KEY` | service_role key |

---

## 3. GitHub Actions 실행

**Actions → Supabase Rank Monitor → Run workflow**

등록된 watchlist가 있으면 Supabase `watchlist_items`의 `rank`, `updated_at`이 채워집니다.

---

## 4. Streamlit Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io) → GitHub 연결
2. Repository: `trendmarkhyun/naver-place-rank`
3. Main file: `app.py`
4. **Secrets:**

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_SERVICE_KEY = "eyJ..."
TEAM_ACCESS_CODE = "trend2026"
```

5. Deploy → `https://naver-place-rank.streamlit.app` 같은 URL 생성

---

## 5. 팀원 사용법

1. Streamlit URL 접속
2. **이름** + **팀원코드** 로그인 (팀원코드는 관리자가 `TEAM_ACCESS_CODE`로 설정)
3. 키워드 + 플레이스 URL → **등록**
4. 30분 이내 순위 자동 갱신 (또는 Actions 수동 실행)

---

## 로컬 개발

```powershell
cd C:\Users\User\naver-place-rank
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# secrets.toml 편집
pip install -r requirements.txt
streamlit run app.py
```

---

## 문제 해결

| 증상 | 확인 |
|------|------|
| 로그인 실패 | `TEAM_ACCESS_CODE` 일치 여부 |
| 연결 오류 | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` |
| 순위 없음 | Actions 실행 여부, 등록 후 30분 대기 |
| 다른 사람 목록 보임 | 버그 — member_id 필터 확인 (정상이면 안 보임) |
