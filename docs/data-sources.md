# 데이터 소스와 검증 결과

조사 일자: 2026-10-17.

## 1. public_repo — `github.com/georggatchev87/market-breadth` (재사용)

| 항목 | 확인 결과 |
|---|---|
| 존재 여부 | 존재. `breadth_5d_up20.json`, `breadth_5d_down20.json`, `status.json`, `breadth.py` |
| 스키마 | `[{"date": "YYYY-MM-DD", "value": int}]`, `status.json` = `{date, state: final/preview, updated_utc, up_value, down_value}` |
| 마지막 업데이트 | 2026-10-17 01:20 UTC 커밋 (2026-10-16 final, up=7, down=106) |
| 기간 | 2016-06-24 ~ 현재 (2,593 거래일) |
| 계산식 | `breadth.py` 확인: `C >= C5*1.2` / `C < C5*0.8`, `C >= 5`, `min(V[D-1..D-3]) > 100000` — 지시서 식과 동일 |
| 유니버스 | Massive `/v3/reference/tickers` type=CS, active+inactive(상장폐지 포함), NYSE/NASDAQ/AMEX/Arca/BATS |
| 데이터 | Massive grouped daily, `adjusted=true` |
| 자동 갱신 | GitHub Actions: 매일 23:17 UTC·10:47 UTC 확정, 장중 20분마다 provisional |
| 라이선스 | **LICENSE 파일 없음** → 코드는 복사·재배포하지 않고, 공개 JSON만 개인 용도로 다운로드 |
| 제약 | 종목 수만 제공(티커 목록 없음), Market Monitor 지표 없음 |

본 앱은 장중 provisional 행을 버리고 `state == final`인 날짜만 저장한다. 내려받은 행 수가 기존보다 10% 이상 줄면 덮어쓰지 않는다.

## 2. yahoo — 자체 계산 (무료, 기본 활성)

- **유니버스**: NASDAQ Trader Symbol Directory (`nasdaqlisted.txt`, `otherlisted.txt`) — NASDAQ, NYSE, NYSE American, NYSE Arca, Cboe BZX, IEX 상장 전 종목
  - 제외: `ETF=Y`, `Test Issue=Y`, 심볼 접미사(`$` 우선주, `.W/.WS/.U/.R/.RT/.WI`), 종목명 패턴(warrant, right, unit, preferred, depositary/ADS/ADR, notes, debenture, ETF/ETN, fund, %, bond, beneficial interest, perpetual 등)
  - 결과(2026-10-17): 13,308 심볼 → **보통주 5,264** (NASDAQ 3,224 / NYSE 1,802 / NYSE American 235 / 기타 3)
  - SPAC Class A는 Massive·TC2000과 같이 보통주로 포함
  - ADR은 제외 (Massive `CS` 타입에 ADR이 포함되지 않기 때문)
- **가격**: Yahoo chart API `v8/finance/chart`, 일봉 `close`(분할 보정, 배당 미보정), `volume`(분할 보정)
- **기간**: 최초 5년(`YAHOO_HISTORY`), 이후 매 갱신 시 최근 1개월만 재수집하여 병합
- **분할 처리**: 최근 1개월 안에 분할 이벤트가 있으면 해당 종목 전체 기간 재수집 (첫 증분 갱신에서 51종목)
- **상장폐지**: 디렉터리에서 사라진 종목은 `listed=False`로 남기고 기존 봉은 보존 → 앱을 운영하는 동안에는 생존 편향이 누적되지 않음. 그러나 **최초 5년 백필에는 이미 상장폐지된 종목이 없다 (생존 편향)**
- 확정 시점: 뉴욕 18:00 ET 이후에만 당일 봉 사용, NYSE 캘린더에 없는 날짜 제거

## 3. massive — 자체 계산 (API 키 필요, 생존 편향 없음)

- `MASSIVE_API_KEY` 설정 시 활성. 키 발급·결제는 사용자가 직접 (자동 가입하지 않음)
- 무료 Stocks Basic: 분당 5회, 2년 히스토리, 참조 데이터 포함 ([pricing](https://massive.com/pricing) 확인). 2년 백필 ≈ 500회 호출 ≈ 100분 (최초 1회, 이후 캐시)
- 일봉: `/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false` — **미보정 원본**을 날짜별 Parquet로 영구 캐시
- 분할: `/stocks/v1/splits`로 받아 계산 시점에 소급 보정 (`close × from/to`, `volume × to/from`) → 캐시된 날짜마다 보정 기준이 달라지는 문제 없음
- 유니버스: `/v3/reference/tickers` type=CS, active=true+false, 주 거래소 NYSE/NASDAQ/AMEX/Arca/BATS
- **실키로 테스트하지 않음**: 이 환경에 키가 없어 모의 응답 단위 테스트(`tests/test_store_massive.py`)로만 검증

## 3-1. 코스피 / 코스닥 (자체 계산, 기본 활성 `KR_SCANNER=1`)

- 종목 목록: KRX KIND 상장법인목록 다운로드 (`kind.krx.co.kr/corpgeneral/corpList.do?method=download&marketType=stockMkt|kosdaqMkt`).
  회사당 1행(보통주 코드)이라 우선주·ETF·ETN은 없다. 2026-10-17 기준 코스피 829개, 코스닥 1,819개(Yahoo 시세 없음 7개).
- 시세: Yahoo `종목코드.KS` / `.KQ`, 분할 보정 종가(배당 미보정), 5년 백필 → 이후 1개월 증분
- 거래일: XKRX 달력. 라이브러리에 없는 2026년 임시 휴장일(06-03 지방선거, 07-17 제헌절)과 2022-01-03·2022-05-09는
  Yahoo 데이터에도 봉이 없어 계산에 영향이 없고, 검증 화면에 “누락 거래일”로만 표시된다.
- 알려진 데이터 문제: Yahoo가 일부 액면병합·감자를 보정하지 않음 (예: 224원 → 2,240원 +900%) → 가격제한폭(±30%) 기준으로 단절 처리 (indicator-definitions.md 참조)
- 현재 상장 종목만 → 생존 편향

## 3-2. 나스닥 (종합지수 기준)

미국 전체 유니버스(Yahoo) 중 `exchange == NASDAQ`인 3,221종목. 미국 전체 갱신 시 같은 일봉으로 함께 계산된다.

## 4. 세계 지수 (menu 6)

- Yahoo chart API 일봉 종가, 2000년~ (지수별 상장 시점부터). 기본 19개: 미국(S&P 500, 나스닥, 다우, 러셀 2000, VIX), 아시아(코스피, 코스닥, 닛케이, 항셍, 상해, 대만, 인도 Nifty, 호주), 유럽(Euro Stoxx 50, DAX, FTSE, CAC), 미주(TSX, 보베스파). 화면에서 추가/삭제(추가 시 데이터 조회로 유효성 확인)
- **완성된 일봉만 저장**: 지수의 장이 열려 있으면(`currentTradingPeriod`) 당일 봉을 버리고 “장중” 표시만 함
- 지수별 자국 거래일·통화 기준. 마지막 거래일이 4일 넘게 지나면 “데이터 지연” 표시
- 특이사항 규칙 (`backend/app/world.py`, 참고용이며 매매 신호 아님):
  - 급등/급락: 당일 수익률 ÷ 최근 252거래일 일간 수익률 표준편차 ≥ 기준σ(기본 2, +1σ 이상이면 진한 색)
  - 52주 신고가/신저가: 최근 252봉 최고/최저 종가 도달
  - 조정 국면 / 약세장: 52주 최고 종가 대비 −기준%(기본 10) / −2×기준% 이하
  - 200일선 상향 돌파 / 하향 이탈: 최근 5거래일 안에 종가와 200일 이동평균의 위치가 바뀜
  - VIX(색상 반대): ≥ 20 경계, ≥ 30 공포, 하루 +20% 이상 급등
- 상관관계: 최근 60거래일 일간 수익률, 같은 날짜 기준(시차 때문에 아시아-미국 상관은 낮게 나올 수 있음)

## 5. 벤치마크 (지수 / 시장 모니터용 ETF)

- 과거 통계·차트의 벤치마크는 **지수**: 미국 전체 → S&P 500(^GSPC), 나스닥 → 나스닥 종합(^IXIC), 코스피 → ^KS11, 코스닥 → ^KQ11. 세계 지수와 같은 Yahoo 일봉(가격지수, 배당 미포함).
- 시장 모니터 화면의 아래 비교 패널만 기본이 **ETF**(SPY, QQQ, KODEX 200 069500.KS, KODEX 코스닥150 229200.KS) — “지수” 버튼으로 전환.
  ETF 시세는 지수와 함께 수집되지만 세계 지수 목록·요약에는 나오지 않는다.
- 차트 보드·세계 지수 차트: TradingView 무료 위젯이 지수 자체를 제공하는 경우만 위젯(SSE:000001, XETR:DAX, EURONEXT:PX1, TSX:TSX, BMFBOVESPA:IBOV),
  나머지는 수집한 실제 지수 OHLC로 그린 캔들. 2026-10-17 확인: 위젯은 SP:SPX·NASDAQ:IXIC·DJ:DJI·TVC:*·KRX:*·NSE·ASX·TWSE를 제공하지 않음.

## 검증 결과 (2026-10-17 실측)

| 비교 | 결과 |
|---|---|
| yahoo vs public_repo, 최근 250거래일 | Bull 상관 0.996, 평균 절대차 2.6 · Bear 상관 0.994, 평균 절대차 1.9 |
| 최근 2주 | Bear 완전 일치 (예: 2026-10-16 = 106 / 106), Bull ±1 |
| 5년 전체 | 상관 0.98, Yahoo 합계가 “미국 전체 (상장폐지 포함)”의 약 84% → 생존 편향(상장폐지 종목 누락)과 일치하는 방향 |
| 누락 거래일 | 두 소스 모두 0 |
| 중복 (종목, 날짜) | 0 |

TC2000 원본 수치(예: 원문에서 언급된 110)와는 **직접 비교하지 못했다** — TC2000 접근이 없기 때문이다.
“데이터 관리 → 원본 수치 비교”에서 날짜·지표·원본 값을 입력하면 소스별 계산값과의 차이가 표시된다.

## 차이 발생 시 점검 순서

1. 유니버스: 데이터 관리 화면의 거래소별 구성, 제외 사유별 개수, “의심 이름” 목록
2. 주가 조정: 하루 +300%/−80% 초과 변동 목록 (분할 미반영 의심)
3. 데이터 누락: 누락 거래일, 종목 수가 급감한 날
4. 거래량 조건: 거래량 0/누락 행 수, 최신일 거래량 0 종목 수
