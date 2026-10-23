import datetime as dt

from app import calendar_


def test_parse_ir_both_forms():
    a = calendar_.parse_ir("1. 일시 및 장소 일시 2026-10-30 15:30 장소 - 2. 참가 대상자 기관 3. 개최목적 투자자 이해도 제고 4. 개최방법 Conference Call "
                           "5. 후원기관 - 6. 주요 설명회내용(요약) 2026년 3분기 영업실적 7. 결정일자 2026-10-23 8. IR 자료 게재일시 2026-10-30")
    assert a == {"ir_date": dt.date(2026, 10, 30), "ir_time": "15:30", "summary": "2026년 3분기 영업실적", "earnings": True}
    b = calendar_.parse_ir("1. 일시 행사일 시간(현지시간) 시작일 종료일 시작시간 종료시간 2026-10-20 2026-10-20 14:00 15:00 2. 장소 본사 "
                           "4. 실시목적 2026년 2분기 경영실적 설명 5. 실시방법 NDR 6. 주요내용 - 사업 현황 - 질의응답 7. 후원기관 자사주관 "
                           "10. IR 자료게재 게재일시 2026-08-20")
    assert b["ir_date"] == dt.date(2026, 10, 20) and b["ir_time"] == "14:00" and b["summary"] == "- 사업 현황 - 질의응답" and b["earnings"]


def test_parse_fomc_and_bea():
    page = ('2026 FOMC Meetings</a></h4><div class="fomc-meeting__month col"><strong>October</strong></div>'
            '<div class="fomc-meeting__date col">27-28</div><div class="fomc-meeting__month col"><strong>Dec</strong></div>'
            '<div class="fomc-meeting__date col">8-9*</div>')
    f = calendar_.parse_fomc(page)
    assert [x["date"] for x in f] == [dt.date(2026, 10, 28), dt.date(2026, 12, 9)] and "경제전망" in f[1]["title"]
    bea = ('<table><th>Year 2026</th><tr class="scheduled-releases-type-press"><div class="release-date">October 29</div>'
           '<small class="text-muted">8:30 AM</small><td class="release-title x">GDP (Advance Estimate), 3rd Quarter 2026 </td></tr>'
           '<tr class="scheduled-releases-type-press"><div class="release-date">December 2</div><small>8:30 AM</small>'
           '<td class="release-title x">GDP by County, 2025</td></tr></table>')
    assert [(x["date"], x["title"]) for x in calendar_.parse_bea(bea)] == [(dt.date(2026, 10, 29), "GDP")]


def test_cboe_monthly_only():
    from app import term
    csv = "Product,Symbol,Expiration Date,Price\nVX,VX44/X6,2026-11-04,19.4\nVX,VX/X6,2026-11-18,19.38\nVX,VX/Z6,2026-12-16,19.23\nVXM,VXM/X6,2026-11-18,19.4"
    f = term.parse_cboe(csv, dt.date(2026, 10, 22))
    assert f["expiry"].tolist() == [dt.date(2026, 11, 18), dt.date(2026, 12, 16)] and f["price"].tolist() == [19.38, 19.23]
