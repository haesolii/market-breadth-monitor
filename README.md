# 시장 폭 모니터 (Market Breadth Monitor)

**20% Bull/Bear Study**와 **Market Monitor**를 재현하는 개인 연구용 로컬 대시보드.
`http://localhost:3000` · 한국어 UI · 투자 권유 아님.

- 20% Bull/Bear: “미국 전체 (상장폐지 포함)” = 외부 GitHub 데이터(georggatchev87/market-breadth, 2016~) + 자체 계산(Yahoo 무료 / Massive 유료·무료 키)
- Market Monitor: 4% 일간, 5/10일 비율, 분기·월간 25%/50%, 34/13, T2108 — **미국 전체 · 나스닥(종합지수 기준) · 코스피 · 코스닥** 시장 탭으로 전환
- 벤치마크 지수 비교 차트, 날짜 클릭 상세, 과거 이벤트 통계, 종목 스캐너, 데이터 검증, 자동 갱신
- 세계 주요 지수 19개 모니터링 + 특이사항(급등락·신고가/신저가·조정/약세장·200일선 돌파/이탈·VIX 공포·데이터 지연) 색상 강조
- 크립토(바이낸스 USDT 현물, 상장폐지 포함) 시장 폭, 시장 간 비교(T2108·10일 비율·Bear 비중·4% 순상승 비중)
- 섹터 히트맵(미국·나스닥·코스피·코스닥·크립토), 액티브 ETF 보유 종목 변화(국내 주식형 액티브 + ARK), 증권사 리포트(목표가·발간일 반응), 미국 실적(서프라이즈·반응)
- 매크로 발표 감지 + 발표일 시장 반응, Claude가 쓰는 AI 시장 브리핑, 텔레그램 알림(시장 폭 극단값·일일 보고·브리핑)

계산식은 [docs/indicator-definitions.md](docs/indicator-definitions.md), 데이터 출처·유니버스·검증 결과는 [docs/data-sources.md](docs/data-sources.md).

## 1. 설치 (최초 1회, Windows)

필요: **Python 3.12+**, **Node.js 20+** (Docker 불필요)

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id OpenJS.NodeJS.LTS
```

프로젝트 폴더에서:

```bat
scripts\setup.bat
```

`backend\.venv` 생성 → Python 패키지 설치 → `.env.example`을 `.env`로 복사 → 프론트엔드 `npm install` + 빌드.

선택: Massive(구 Polygon.io) API 키가 있으면 `.env`에 `MASSIVE_API_KEY=...`를 넣는다. 키가 없어도 모든 화면이 실제 데이터로 동작한다
(“미국 전체 (상장폐지 포함)” + Yahoo 소스).

## 2. 실행

```bat
start.bat
```

백엔드(127.0.0.1:8000)와 대시보드(127.0.0.1:3000) 콘솔 창 두 개가 뜨고, 브라우저가 `http://localhost:3000`을 연다.
종료하려면 두 콘솔 창을 닫는다. `start.bat`은 설치가 안 되어 있으면 `setup.bat`을 자동 실행한다.

**최초 실행**: 데이터가 없으면 서버가 즉시 수집을 시작한다 (공개 JSON·세계 지수 수 초, Yahoo 5년 백필 약 1~2분, 5,000여 종목).
수집이 끝나기 전에는 화면에 “데이터가 아직 없습니다” 안내만 표시되며(가상 수치는 표시하지 않음), 상단 상태바에서 진행을 확인할 수 있다.

수동 실행(개발용):

```bat
cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000
cd frontend && npm run dev        :: 또는 npx next start -p 3000 (빌드 후)
```

## 3. 메뉴

| 메뉴 | 내용 |
|---|---|
| 1. 종합 시장 현황 | KPI(Bull/Bear/Net/비율/전일 대비/최신 날짜/소스), 시장 모니터 핵심 지표, 차트 + 날짜 상세 |
| 2. 20% 급등락 분석 | Bull(녹색)/Bear(빨강, 아래쪽) 히스토그램, 1M~ALL, Bear 기준선 50/100/150/사용자, 벤치마크 지수 패널, 비교 소스 겹쳐 보기, 클릭 시 상세 |
| 3. 시장 모니터 | 시장 탭(미국 전체/나스닥/코스피/코스닥), 날짜×지표 히스토리 테이블 (색상 강조, 수식 툴팁, 기간 필터, CSV), 헤더 클릭 시 해당 지표 + 시장별 벤치마크(SPY/나스닥 종합/코스피/코스닥 지수) 시계열 |
| 4. 지표 흐름·과거 통계 | **지표 흐름**: 종합 점수(16개 지표의 1년 백분위 평균, 0~100) 추이, 16개 지표 동기화 소형 차트·백분위, 지표×지수 수익률·지표 간 순위상관, **선행·후행 분석**(시차 -20~+20일 상관, 60일 이동 상관). **극단값 이후 성과**: 임계값(50/75/100/150/사용자) 이후 벤치마크(시장별 자동 또는 선택) 1/3/5/10/20일 수익률: n, 평균, 중앙값, 상승 비율, 최대/최소, 분포, 기준 대비 p값, 독립/묶음 이벤트. 두 번째 조건(AND, 예: Bear ≥ 100 그리고 T2108 ≤ 20), 이후 20거래일 최대 낙폭(MAE)·최대 상승폭(MFE) |
| 5. 조건 충족 종목 검색 | 날짜별 조건 충족 종목 (Ticker, Company, Exchange, Close, 5D %, Volume, Signal), 검색·정렬·CSV |
| 6. 세계 지수 | 지수별 1일/1주/1개월/3개월/연초 대비, 52주 고점 대비, 50·200일선, 변동성, 특이사항 색상 강조(기준 σ·조정폭 선택), 지수 비교 차트(=100, 아래 미국 Bear 수), 60일 상관관계 히트맵, 지수 추가/삭제 |
| 7. 매크로 | 미국 매크로 20개(물가·고용·금리·신용·경기·유동성, FRED): 카드별 최신값·직전/1년 전 대비·추이(1·3·10년), 특이사항 강조(경기침체 신호, 금리 역전, 스프레드 급등, 고물가 등), 카드 클릭 시 전체 기간 차트 + S&P 500 / 20% Bear 비교 |
| 8. 차트 보드 | 세계 지수·유가·금리 차트를 가로 4열(3·2열 선택)로 한눈에. **6개월·1년·3년 버튼**이 모든 칸에 동일 적용. 칸은 모두 수집한 실제 지수 일봉 캔들 + 50·200일선 (ETF·CFD 대체 없음). 이름 클릭 시 크게 보기 — 무료 위젯이 지수 자체를 제공하는 상해·DAX·CAC·TSX·보베스파는 TradingView로 열림 (TradingView 위젯은 6개월·3년 일봉 범위를 지원하지 않아 격자에는 쓰지 않음) |
| 9. 섹터 히트맵 | 시장별 트리맵(칸 크기 = 시가총액, 크립토는 거래대금 · 색 = 1일/1주/1개월/3개월/연초 대비 수익률), 섹터별 가중 수익률·중앙값·상승 종목 비율·최고/최저 종목, 섹터 지수 추이(=100)·변동성·베타·상관, 섹터별 40일선 위 종목 비율, 섹터 순환 지도(RRG). 종목 더블클릭 → 종목 상세. 미국 섹터 = Nasdaq 스크리너, 한국 = 네이버 업종 |
| 10. 액티브 ETF | 국내 주식형 액티브 ETF 상위 60개(채권·금리·커버드콜 제외) + ARK 6개: 일별 구성 종목 스냅샷, 편입/편출/증가/감소 내역, 여러 펀드가 함께 사고판 종목, 펀드별 구성·변화 이력, 종목 당일 등락 |
| 11. 리포트·실적 | 증권사 기업 리포트(네이버 리서치, 180일): 목표가·이전 목표가 대비 변경·의견·요약, 발간일 반응·이후 수익률·상승여력, 종목별 컨센서스. 미국 실적(Nasdaq): EPS vs 예상, 서프라이즈, 발표 시각별 반응, 발표 예정 14일. 한국 잠정실적(DART, 키 필요): 공시·2일 반응 |
| 12. 한국 수급 | 오늘 코스피·코스닥 투자자별 순매수, 전 종목(약 2,600개) 외국인·기관·개인 누적 순매수(+코스피 지수), 업종별 5/20일 순매수, 외국인·기관 순매수/순매도 상위 종목(지분율 변화) |
| 13. 종목 상세 | 종목 검색 → 기간별 수익률·업종 내 순위·시장 백분위, 미국 차트(TradingView), 투자자별 누적 순매수(한국), 같은 업종 대형주, 액티브 ETF 보유·매매, 증권사 리포트·컨센서스, 잠정실적/실적 |
| 데이터 관리 (`/data`, 메뉴 숨김 · 상태바 오류 링크) | 소스 상태·오류·수동 갱신, 원본 수치(TC2000/원본) 입력 비교, 데이터 품질 리포트, 로그 |

종합 화면 맨 위에는 최신 AI 시장 브리핑(접힘), 맨 아래에는 시장 간 비교 차트가 있다. 매크로 화면 아래에는 최근 발표와 발표일 S&P 500·10년물 반응이 있다.

미래 지수 수익률은 **4번 화면에서만** 표시한다 (실시간 판단 화면에는 표시하지 않음).
강조 색상 기준은 사용자 설정이며 원본 공식 매매 신호가 아니다.

## 4. 자동 갱신

- 서버 실행 중: 15분마다(`REFRESH_INTERVAL_MIN`) “최신 완료 거래일”을 계산 (NYSE 캘린더: 휴장일·조기폐장·서머타임 반영, 뉴욕 18:00 ET 이후 당일 확정)
  → 그보다 늦은 소스만 수집. 세계 지수는 나라마다 장 마감 시각이 달라 1시간마다 갱신(장 중인 지수의 당일 봉은 저장하지 않음). 소스가 아직 갱신되지 않았으면(공개 저장소는 보통 19:17 ET 이후) 60분 뒤 재시도.
- HTTP 429/5xx는 지수 백오프로 최대 4회 재시도. 실패 시 기존 데이터 유지, 오류는 상태바·데이터 관리 화면·로그에 표시.
- 저장은 `(source, date)` 키 upsert(중복 날짜 방지), 임시 파일 → 원자적 교체. 새 다운로드가 기존보다 10% 이상 작으면 저장 거부.
- 서버가 꺼져 있을 때도 갱신하려면 Windows 작업 스케줄러 등록 (3시간마다, 오래된 소스만):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1          # 등록
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Remove  # 제거
```

로그: `data\refresh_task.log`. 명령행 수동 갱신: `cd backend && .venv\Scripts\python -m app.refresh [--source yahoo] [--only-stale]`

## 5. 구조

```
stockbee-breadth/
├── backend/app/
│   ├── main.py              FastAPI (/api/*)
│   ├── indicators.py        20% + Market Monitor 계산 (DuckDB 윈도 쿼리 1회)
│   ├── refresh.py           수집→검증→계산→저장, 자동 갱신 루프, CLI
│   ├── research.py          이벤트 스터디 (look-ahead 없음), 지표 상관·종합 점수·선행/후행
│   ├── validation.py        품질 검사, 소스 간 비교, 원본 수치 비교
│   ├── world.py             세계 지수 수집·지표·특이사항·상관관계
│   ├── macro.py             미국 매크로 (FRED) 수집·변환·특이사항·발표 감지와 시장 반응
│   ├── sectors.py           섹터 히트맵 (시장별 수익률·시가총액·섹터)
│   ├── etf.py               액티브 ETF 구성 스냅샷·변화
│   ├── analyst.py           증권사 리포트 수집·목표가 변경·반응
│   ├── earnings.py          미국 실적 캘린더·서프라이즈·반응
│   ├── flows.py             한국 투자자별 순매수 (네이버)
│   ├── dart.py              한국 잠정실적 공시 (DART, DART_API_KEY)
│   ├── stock.py             종목 상세·검색 (모든 데이터 묶음)
│   ├── brief.py             AI 시장 브리핑 (Claude, `python -m app.brief`)
│   ├── report.py            텔레그램: 일일 보고, 시장 폭 신호(`--signals`), 브리핑(`--brief`), 경보
│   ├── publish.py · remote.py · usage.py   Supabase 게시/읽기, 방문 기록 (배포용)
│   ├── universes.py         시장별 종목·달력·기준값·벤치마크 (미국/나스닥/코스피/코스닥/크립토)
│   ├── market_calendar.py   NYSE 거래일/ET
│   ├── store.py             Parquet 테이블 + status.json
│   └── collectors/          public.py · yahoo.py · massive.py · korea.py (KRX KIND) · crypto.py (Binance)
├── backend/tests/           pytest
├── frontend/                Next.js 15 App Router, TypeScript, Tailwind v4, shadcn/ui, ECharts
├── data/                    Parquet 저장소 (git 제외)
├── scripts/                 setup.bat, refresh.bat, register_task.ps1
├── docs/                    지표 정의, 데이터 소스·검증
├── .env.example
└── start.bat
```

주요 테이블 (`data/*.parquet`): `breadth20`, `market_monitor_daily`, `bars_yahoo`, `universe_yahoo`,
`universe_massive`, `bars_kospi`, `bars_kosdaq`, `universe_kospi`, `universe_kosdaq`, `bars_crypto`, `universe_crypto`, `manual_reference`, `indices`(세계 지수 종가), `macro`, `macro_releases`,
`sector_map`, `etf_snapshots`·`etf_latest`·`etf_changes`·`etf_funds`, `analyst_reports`, `earnings`, `ai_brief`, `sector_daily`(섹터 일간 수익률·40일선 위 비율), `kr_flow`, `kr_flow_market`, `dart_prelim`, `massive/<date>.parquet`(원본 일봉 캐시). 지수 목록: `data/indices.json`.

## 5-1. 배포 (선택)

- **GitHub Actions** (`.github/workflows/refresh.yml`): 수집·계산 후 Supabase에 게시. 장중에는 한 번 실행이 5분마다 잠정값을 갱신하고, 미국(23:15 UTC)·한국(09:40 UTC) 마감 후 확정.
  섹터·지수는 매 회, 매크로 30분, 리포트 1시간, ETF 3시간, 실적 6시간, 수급·DART 30분마다.
- **Vercel**: `vercel.json` services (frontend + backend), 읽기 전용 API가 Supabase를 읽음. 배포는 `vercel deploy --prod` (push로 자동 배포되지 않음).
- **Secrets**: `SUPABASE_DB_URL`, `TELEGRAM_BOT_TOKEN`(+선택 `TELEGRAM_CHAT_ID`), `ANTHROPIC_API_KEY`(AI 브리핑, 없으면 건너뜀), `DART_API_KEY`(잠정실적, 선택), `MASSIVE_API_KEY`(선택). Vercel: `DASHBOARD_PASSWORD`, `STORE=supabase`.
- 텔레그램: 마감 후 시장 폭 극단값(Bear·4% 하락 극단 기준, 10일 비율 ≤0.5/≥2, T2108 <20/>80)이 **새로** 나타나면 알림, 아침 일일 보고, 브리핑.
- 다시 받을 수 없는 누적 이력(ETF 변화·실적 발표 시각·매크로 발표·브리핑·시장 전체 수급)은 러너 캐시가 지워지면 Supabase에서 복원한다.

## 6. 테스트

```bat
cd backend && .venv\Scripts\python -m pytest -q
cd frontend && npx tsc --noEmit && npm run build
```

## 7. 문제 해결

| 증상 | 확인 |
|---|---|
| 상단 “백엔드 연결 실패” | 백엔드 콘솔 창 오류 확인, 8000 포트 사용 중인지 (`netstat -ano | findstr :8000`) |
| “데이터가 아직 없습니다”가 계속 표시됨 | 데이터 관리 → 소스 상태의 “마지막 오류”, 실행 로그 |
| 날짜가 노란색(지연) | 소스가 아직 해당 거래일을 게시하지 않음 → 자동 재시도. 수동 갱신 버튼 |
| 회사 방화벽/TLS 검사 | `pip install pip-system-certs` (backend venv) |
| 데이터 초기화 | 서버 종료 후 `data\` 폴더 삭제 → 재시작하면 재수집 |

## 8. 알려진 제약

- Yahoo 소스는 **생존 편향**(현재 상장 종목만) → 과거 수치가 “미국 전체 (상장폐지 포함)”보다 평균 약 16% 작음. 정확한 과거 비교는 “미국 전체 (상장폐지 포함)”(20%만) 또는 Massive 키 사용.
- Market Monitor 히스토리는 Yahoo 기준 2021-10 이후(5년). Massive 무료 키는 2년.
- 코스피·코스닥 기준값(₩1,000 / 10만 주 / ₩3.5억)은 원본 미국 기준을 환산·조정한 자체 값이며, 원본 수치와 비교할 대상이 없다.
- 나스닥은 ADR을 제외한 NASDAQ 상장 보통주 기준이라 공식 종합지수 구성과 다르다.
- 벤치마크·차트는 지수 기준(S&P 500 ^GSPC 등). 예외로 시장 모니터 아래 패널은 기본이 ETF(SPY·QQQ·KODEX 200·KODEX 코스닥150)이며 “지수” 버튼으로 전환.
- TradingView 무료 위젯은 한국거래소(코스피·코스닥·개별 종목), 미국 공식 지수, 일본·홍콩·인도·대만·호주 지수를 제공하지 않는다 → 해당 지수는 자체 차트, 한국 개별 종목은 TradingView 사이트 링크.
- Massive 연동은 실키로 테스트하지 못함(모의 테스트만).
- TC2000/원본 원본 수치와의 직접 대조는 하지 못함 → 화면에서 수동 입력 비교 기능 제공.
- 액티브 ETF·매크로 발표는 제공처가 과거 이력을 주지 않아 **수집을 시작한 날부터** 쌓인다. 국내 ETF는 CU당 수량 기준이고 일부 해외 종목은 비중이 비어 있다.
- 매크로 발표일은 FRED에 새 값이 처음 보인 시각 기준(무료 CSV에 발표 시각 없음). 미국 실적의 과거 발표 시각은 예정일 수집분만 정확하고, 모르면 2일 반응으로 표시.
- 한국 잠정실적은 DART 목록 API 기준이라 수치(매출·영업이익)는 공시 원문 링크로만 제공. 공시 시각을 몰라 반응은 2거래일.
- 한국 수급의 시장 전체 값은 네이버가 당일 값만 주므로 수집 시작일부터 쌓이고, 종목별 누적은 순매수 주식 수 × 그날 종가로 환산한 근사치이며 매일 18시(KST) 이후 하루 한 번 갱신 (배포 API는 게시 때 미리 계산한 요약과 종목별 DB 조회를 씀).
- 종합 점수는 각 지표의 최근 1년 백분위 평균(하락형 지표는 뒤집음)으로 만든 자체 지표이며 매매 신호가 아니다. 섹터 지수·RRG는 현재 구성 종목·현재 시가총액 기준 근사(상장폐지 종목 없음, JdK RRG 공식 비공개).
- 월간 50% 상승·하락의 원문 기준(미국 20)은 어느 시장에서나 약 75%의 날에 충족돼 극단값이 아니다. 그래서 '과열'·'극단적 하락' 판정은 시장별 자체 90백분위(2021-10~2026-10 측정)를 쓰고, 원문 기준은 '평소 수준'으로 표시.
- 증권사 리포트·섹터·ETF·수급은 네이버/WiseReport 비공식 엔드포인트라 예고 없이 바뀔 수 있음.
- AI 브리핑은 대시보드 수치만 근거로 쓰도록 지시하지만 요약·해석이 틀릴 수 있다. 투자 권유 아님.
- Yahoo 비공식 API는 예고 없이 바뀔 수 있음 (실패 시 기존 데이터 유지, 오류 표시).
- 공개 저장소(georggatchev87/market-breadth)는 라이선스가 없어 데이터만 개인 용도로 사용.
