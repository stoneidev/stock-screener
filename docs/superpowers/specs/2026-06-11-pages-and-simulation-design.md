# 설계: 스캔 리포트 GitHub Pages + Top3 매매 시뮬레이션

작성일: 2026-06-11

## 배경 / 문제

`stock-screener`는 매일 GitHub Actions로 전체 미국 주식을 스캔하고
`data/daily_scans/optimized_scan_*.txt` 리포트를 생성한다. 그러나 이 리포트는
**GitHub Actions artifact로만** 업로드되어(보관 90일), 매번 zip을 내려받아 txt를
풀어봐야 하는 불편함이 있다. 또한 신호의 실제 성과(매매했다면 수익률)를 추적하는
수단이 없다.

세 가지를 추가한다.

1. 리포트를 보기 좋은 **GitHub Pages 대시보드**로 제공
2. 매일 점수 상위 **Top3 BUY 신호 매매 시뮬레이션** (손익절 자동, 일별 수익률)
3. 위 결과를 매일 자동으로 레포에 **반영(커밋/푸시) + Pages 배포**

## 확정된 결정 사항 (사용자 합의)

- **손익절 정책**: 리포트에 들어 있는 종목별 값을 그대로 사용
  (손절 = `Stop Loss`, 목표가 = `Breakout + Reward`)
- **보유 모델**: 손절가 또는 목표가에 도달할 때까지 보유 (동시 보유 종목 누적 허용)
- **진입가**: 스캔 **다음 거래일 시가** (look-ahead 방지, 현실적 가정)
- **데이터 출처**: 리포트 JSON을 레포에 커밋해 신호 기록을 남기고, 손익절 도달 판정은
  실제 일봉 가격(yfinance)으로 계산
- **Pages 구성**: 리포트 뷰 + 시뮬레이션 대시보드 통합 한 페이지
- **시작일**: GitHub Actions artifact가 남아있는 가장 빠른 날부터.
  현재 만료 안 된 artifact는 7개, 가장 빠른 Scan Date는 **2026-06-03**
  (artifact 라벨 2026-06-02). 만료된 과거 데이터는 복구 불가.

## 데이터 현황 (조사 결과)

- 레포에 scan 결과(txt/json)가 커밋된 이력 없음. artifact만 존재.
- 남아있는 artifact: `screening-results-2026-06-02` ~ `-2026-06-10` (7개, 영업일 기준)
- artifact 내부 txt 형식 (파싱 가능):
  - `Scan Date: YYYY-MM-DD` (artifact 라벨 날짜와 다를 수 있음 → **내부 Scan Date 신뢰**)
  - BUY 블록: `BUY #N: TICKER | Score: X/125`, `Phase:`, `Stop Loss: $X`,
    `Risk/Reward: R:1 (Risk $X, Reward $Y)`, `Breakout: $X`, `Entry Quality:`,
    `RS:`, `Volume:`, `Key Reasons:` 목록
  - SELL 블록: `SELL #N: TICKER | Score: X/110`, `Severity:`, `Breakdown: $X`

## 아키텍처

네 개의 독립 컴포넌트로 분리한다.

```
[스캐너] --txt--> [파서/JSON 출력] --json--> [시뮬레이션 엔진] --json--> [Pages 대시보드]
                                  \                                    /
                                   ---------- data/ (git) -------------
                                          [워크플로가 커밋/푸시/배포]
```

### 컴포넌트 1: 리포트 JSON 출력 (`run_optimized_scan.py` 수정 + 백필 스크립트)

**목적**: 머신리더블한 스캔 결과를 레포에 누적한다.

- `save_report()`에 JSON 출력 추가:
  - `data/daily_scans/scan_<YYYY-MM-DD>.json`, `data/daily_scans/latest.json`
  - 스키마:
    ```json
    {
      "scan_date": "2026-06-03",
      "generated_at": "2026-06-03 00:03:12",
      "market": { "spy_phase": 2, "regime": "RISK-ON", "breadth_quality": "Good" },
      "counts": { "buy": 433, "sell": 384 },
      "buys": [
        {
          "rank": 1, "ticker": "D", "score": 113.0, "phase": 2,
          "entry_quality": "Good",
          "stop_loss": 64.23, "breakout": 64.96,
          "risk_amount": 2.24, "reward_amount": 19.94, "rr_ratio": 8.9,
          "target": 84.90,
          "rs_slope": 0.351, "volume_ratio": null,
          "reasons": ["..."]
        }
      ],
      "sells": [ { "rank": 1, "ticker": "...", "score": 0, "severity": "high" } ]
    }
    ```
  - `target = breakout + reward_amount`. breakout 없으면 stop_loss + risk + reward로 역산.
    필수값(stop_loss, breakout/target) 누락 종목은 시뮬레이션에서 제외하고 로그로 남긴다.
- **백필 스크립트** `scripts/backfill_scans.py`:
  - `gh api`로 만료 안 된 artifact 목록 조회 → 각 zip 다운로드 → txt 파싱 →
    `scan_<scan_date>.json` 생성. 이미 있으면 스킵(멱등).
  - txt 파서는 `src/simulation/report_parser.py`에 두고 라이브 출력과 공유.
- 파서/JSON 생성 로직은 `src/simulation/report_parser.py` 한 곳에 두어
  라이브 스캔과 백필이 동일 코드를 쓴다.

### 컴포넌트 2: 시뮬레이션 엔진 (`src/simulation/`)

**목적**: 매일 Top3를 정책대로 매매했을 때의 일별 수익률을 계산한다.

- 모듈 구성:
  - `report_parser.py` — txt → dict (컴포넌트1과 공유)
  - `price_provider.py` — yfinance 일봉 조회 + 디스크 캐시 (`data/simulation/price_cache/`)
  - `engine.py` — 매매 시뮬레이션 핵심
  - `run_simulation.py` (repo root 또는 scripts/) — CLI 진입점
- **규칙**:
  1. 각 `scan_<date>.json`에서 score 상위 Top3 BUY 선택
     (필수값 누락 종목은 건너뛰고 다음 순위로 보충하지 않음 — 그날 유효 Top3만)
  2. 진입: scan_date의 **다음 거래일 시가**에 매수
  3. 자본: 초기자본 기본 `$100,000`. 1포지션 = `초기자본 / 3` 고정 금액
     (동시 보유가 누적되면 현금이 마이너스가 될 수 있음 → 단순 수익률 추적이 목적이므로
     레버리지 제한 없이 각 트레이드 독립 손익을 합산하는 방식. equity = 초기자본 + 누적 실현손익 + 미실현손익)
  4. 청산 판정 (진입일 다음 날부터 매일):
     - 일봉 `low <= stop_loss` → 손절가에 청산
     - 일봉 `high >= target` → 목표가에 청산
     - 같은 날 둘 다 충족 → **손절 우선**(보수적)
  5. 보유 종목이 다시 Top3에 떠도 **중복 진입 안 함** (이미 열린 포지션 유지)
- **출력** (`data/simulation/`):
  - `trades.json` — 모든 체결: `ticker, entry_date, entry_price, exit_date, exit_price, shares, pnl, pnl_pct, exit_reason(stop/target/open)`
  - `equity_curve.json` — 일별 `{date, realized, unrealized, equity, return_pct}`
  - `open_positions.json` — 미청산 포지션 현재가 기준 평가
  - `summary.json` — 총수익률, 승률, 평균손익, 최대낙폭(MDD), 트레이드 수
- **멱등성/증분**: 이미 시뮬레이션된 마지막 날짜 이후만 추가 계산.
  전체 재계산 옵션(`--rebuild`)도 둔다.
- **시작일**: 존재하는 가장 빠른 `scan_*.json`부터 자동 시작.

### 컴포넌트 3: GitHub Pages 대시보드 (`docs/site/`)

**목적**: 빌드 없는 정적 사이트. `data/`의 JSON을 fetch로 읽어 표시.

- 순수 HTML + JS (경량 차트 라이브러리 1개: Chart.js CDN). 빌드 스텝 없음.
- 페이지 구성 (단일 페이지, 탭/섹션):
  - **시뮬레이션 대시보드**: equity curve 차트, 요약 카드(총수익률/승률/MDD/평균손익),
    청산 트레이드 테이블, 현재 열린 포지션 테이블
  - **리포트 뷰**: 날짜 드롭다운 → 그날 BUY Top(점수/phase/손익절/목표가/사유 카드) + SELL Top
  - 데이터 인덱스: `data/daily_scans/index.json`(존재하는 scan 날짜 목록)을 만들어
    드롭다운이 읽게 한다.
- Pages는 레포 루트 기준 상대경로로 `../../data/...`를 fetch하면 깨지므로,
  배포 워크플로에서 `docs/site/` + 필요한 `data/*.json`을 한 아티팩트로 묶어 배포한다
  (사이트 내부에 `data/` 복사). 상세는 컴포넌트4.

### 컴포넌트 4: 워크플로 (반영 + 배포)

**목적**: 매일 자동으로 스캔→JSON→시뮬레이션→커밋→Pages 배포.

- 기존 `daily_screening_git_storage.yml` 수정:
  - 스캔 후 `data/daily_scans/scan_*.json`, `latest.json`, `index.json` 생성 확인
  - 시뮬레이션 스텝 추가: `python scripts/run_simulation.py`
  - 커밋 대상에 `data/daily_scans/*.json`, `data/simulation/*.json` 추가
    (txt는 용량 크므로 레포에 안 넣고 기존대로 artifact만)
- 신규 `pages.yml` (또는 같은 워크플로 잡 추가):
  - main push 시 `docs/site/` + `data/` 의 JSON을 모아 Pages artifact로 빌드,
    `actions/deploy-pages`로 배포
  - `.gitignore` 조정: `data/simulation/*.json`, `data/daily_scans/*.json` 추적 허용
    (현재 `data/daily_scans/**`는 이미 허용됨, simulation 디렉터리 예외 추가 필요)
- **일회성**: 백필 스크립트는 로컬에서 한 번 실행(또는 수동 트리거 워크플로)해
  06-03부터의 JSON과 초기 시뮬레이션 결과를 만들어 커밋한다.

## 테스트 전략

- `report_parser.py`: 실제 artifact txt 샘플을 픽스처로 두고 파싱 단위 테스트
  (BUY/SELL 개수, 필드 값, target 역산, 필수값 누락 처리)
- `engine.py`: 합성 가격 시리즈로 손절/목표/동시충족(손절우선)/미청산 케이스 테스트
- `price_provider.py`: 캐시 히트/미스, 거래일 보정 로직 테스트 (네트워크는 모킹)
- 기존 테스트 스위트(`tests/`)에 합류시키고 깨지지 않게 유지

## 에러 처리

- artifact 다운로드 실패/만료 → 스킵 + 경고 로그, 나머지 진행
- yfinance 조회 실패/상장폐지/데이터 공백 → 해당 트레이드 `open`으로 두고 경고,
  시뮬레이션 전체는 중단하지 않음
- 필수 필드 누락 종목 → 시뮬레이션 제외 + 로그
- 미래 날짜/진입일 가격 미존재 → 아직 진입 안 한 pending으로 보류

## 범위 밖 (YAGNI)

- 실거래 연동, 슬리피지/수수료 모델(초기엔 0 가정, 추후 옵션)
- 분봉 단위 정밀 청산 (일봉 high/low로 충분)
- 포지션 사이징 최적화, 켈리 등
- 인증/다중 사용자 Pages
```
