# 네이버 플레이스 순위 자동 수집기

여러 업체 × 키워드 조합의 네이버 지도 검색 순위를 자동 수집하고 SQLite에 히스토리를 저장합니다.

## 요구 사항

- Python 3.11+
- Windows (작업 스케줄러 지원)

## 설치

```powershell
cd naver-place-rank
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

## 설정

**순위 정의**
- 네이버 플레이스 검색 결과의 **Apollo placeList 순위** (유료 광고 제외, 일반 업체 목록 기준)
- 키워드 검색 결과 목록에서 **1번째 업체 = 1위**

1. `config/targets.yaml`에 업체(`place_id`, `name`)와 키워드를 등록합니다.
2. 플레이스 ID는 네이버 플레이스 URL에서 확인합니다.  
   예: `https://map.naver.com/p/entry/place/1234567890` → `1234567890`

## 사용법

### 팀 공유 (GitHub + Streamlit Cloud)

직원들이 **같은 URL**로 순위를 함께 보려면 GitHub 연동을 사용합니다.

자세한 설정: [`docs/GITHUB_SETUP.md`](docs/GITHUB_SETUP.md)

**GitHub 저장소:** [github.com/trendmarkhyun/place-rank](https://github.com/trendmarkhyun/place-rank)

**요약**
1. [place-rank](https://github.com/trendmarkhyun/place-rank) 저장소에 코드 push
2. `config/team_watchlist.yaml`에 팀 업체 등록 (최대 20개)
3. Actions **Team Rank Monitor** → 30분마다 `data/team_rankings.json` 갱신
4. [Streamlit Cloud](https://share.streamlit.io)에 `app.py` 배포 → URL 공유
5. 앱 **「팀 공유 (GitHub)」** 탭에서 확인

### 웹 UI (로컬)

키워드 + 플레이스 URL로 순위를 조회하거나, 최대 **20개** 업체를 등록해 모니터링합니다.

```powershell
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 이 열립니다. 자동으로 안 열리면 주소를 직접 입력하세요.

**UI 기능**
- **좌측**: 키워드·URL 입력 → [등록] 또는 [순위 조회]
- **우측**: 등록 업체 목록 (업체명 · 키워드 · 순위)
- **✕ 버튼**: 등록 해제
- **5분마다** 자동 순위 갱신, 변동 시 ✓ 표시
- 등록 목록은 `data/watchlist.json`에 저장 (앱 재시작 후에도 유지)

> 앱이 실행 중일 때만 자동 갱신이 동작합니다. 등록 업체가 많을수록 1회 갱신에 시간이 더 걸릴 수 있습니다.

### CLI (배치 수집 · 스케줄)

```powershell
# 1회 수집
python scripts/run_collector.py --config config/targets.yaml

# CSV 내보내기
python scripts/export_csv.py --from 2026-05-01 --to 2026-05-27

# 매일 오전 9시 자동 실행 등록
powershell -ExecutionPolicy Bypass -File scripts/install_scheduler.ps1
```

## Windows 작업 스케줄러 주의

- PC가 절전/종료 상태면 작업이 실행되지 않습니다.
- Windows 설정 → 전원 → "절전 모드로 전환"을 적절히 조정하세요.
- 작업 스케줄러에서 "사용자가 로그온했는지 여부에 관계없이 실행" 옵션을 검토하세요.

## 주의 사항

네이버 이용약관 및 robots 정책을 확인하세요. 개인/내부 모니터링 용도로 **하루 1~2회** 저빈도 실행을 권장합니다.

## 관련 저장소

블로그 키워드 순위 체커: [github.com/trendmarkhyun/naver-blog-rank](https://github.com/trendmarkhyun/naver-blog-rank)

## 프로젝트 구조

```
config/targets.yaml   # 업체·키워드 설정 (CLI용)
app.py                # Streamlit 플레이스 순위 UI
data/watchlist.json   # UI 등록 업체 (자동 생성)
src/                  # 수집·저장·조회 로직
scripts/              # CLI 및 스케줄러 설치
data/rankings.db      # 순위 히스토리 (자동 생성)
logs/                 # 실행 로그 (자동 생성)
```
