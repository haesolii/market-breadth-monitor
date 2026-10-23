import types

import anthropic

from app import brief


def test_write_stores_text_and_handles_refusal(monkeypatch):
    calls = []

    def fake_client(stop="end_turn", text="## 한눈에\n- 요약"):
        def create(**kw):
            calls.append(kw)
            return types.SimpleNamespace(stop_reason=stop, stop_details=None, model=kw["model"],
                                         content=[types.SimpleNamespace(type="text", text=text)])
        return lambda: types.SimpleNamespace(beta=types.SimpleNamespace(messages=types.SimpleNamespace(create=create)))

    monkeypatch.setattr(anthropic, "Anthropic", fake_client())
    assert brief.write({"breadth": {}}, "us") == "## 한눈에\n- 요약"
    assert calls[0]["model"] == "claude-opus-5-5" and calls[0]["fallbacks"] == "default"
    assert brief.latest()[0]["slot"] == "us"
    monkeypatch.setattr(anthropic, "Anthropic", fake_client(stop="refusal"))
    try:
        brief.write({}, "kr")
        raise AssertionError("refusal must raise")
    except RuntimeError:
        pass


def test_brief_telegram_html():
    import datetime as dt
    import pandas as pd
    from app import report, store
    store.write("ai_brief", pd.DataFrame([{"date": dt.date(2026, 10, 23), "slot": "kr", "created_at": "2026-10-23T09:00:00+00:00",
                                           "model": "m", "text": "## 한눈에\n- **Bear** < 20"}]))
    t = report.brief_text()
    assert "<b>한눈에</b>" in t and "- Bear &lt; 20" in t and "한국 마감" in t
