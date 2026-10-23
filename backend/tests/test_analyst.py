import datetime as dt

import pandas as pd

from app import analyst


def test_parse_and_enrich_reaction():
    items = [{"nid": "2", "writeDate": "2026-10-07", "brokerName": "A증권", "itemCode": "000001", "itemName": "가", "title": "t&amp;s",
              "content": "<p><strong>요약</strong></p><p>- 하나<br>- 둘</p>", "goalPrice": "12,000", "opinionText": "Buy"},
             {"nid": "1", "writeDate": "2026-10-03", "brokerName": "A증권", "itemCode": "000001", "itemName": "가", "title": "x",
              "content": "", "goalPrice": None, "opinionText": "Buy"},
             {"nid": "0", "writeDate": "2026-10-01", "brokerName": "A증권", "itemCode": "000001", "itemName": "가", "title": "x",
              "content": "", "goalPrice": "10000", "opinionText": "Buy"}]
    rep = analyst.parse(items)
    assert rep.loc[0, "title"] == "t&s" and rep.loc[0, "summary"] == "" and rep.loc[0, "goal"] == 12000
    d = [dt.date(2026, 10, x) for x in (1, 2, 5, 6, 7, 8)]  # 10-03 (Sat) is not a session
    bars = pd.DataFrame({"date": d, "ticker": "000001", "close": [100.0, 100, 100, 100, 110, 120]})
    e = analyst.enrich(rep, bars).set_index("nid")
    assert e.loc[2, "prev_goal"] == 10000 and round(e.loc[2, "goal_chg"], 6) == 20  # target-less report skipped
    assert round(e.loc[2, "react1d"], 6) == 10 and round(e.loc[2, "ret_since"], 6) == 20 and e.loc[2, "upside"] == 9900
    assert pd.isna(e.loc[1, "react1d"]) and round(e.loc[1, "ret_since"], 6) == 20                # weekend report: no same-day reaction
