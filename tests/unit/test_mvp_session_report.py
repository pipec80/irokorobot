"""Task 0 (Plan 0080): one row of closed values per turn, read from the server log.

The fixtures mimic ``logs/server.log`` (JSON lines). Every sentence below is an
invented canary: the report must never carry a message text.
"""

import json
from pathlib import Path

from scripts import mvp_session_report
from scripts.mvp_session_report import TurnRow, summarize_turns

_SINCE = "2026-11-09T10:00:00-03:00"
_REQUEST = "11111111-aaaa-bbbb-cccc-000000000001"
_OTHER = "22222222-aaaa-bbbb-cccc-000000000002"
_CANARY = "zorgblat quantum pelican"


def _line(
    ts: str, request_id: str, event: str | None, msg: str = "log text", **fields: object
) -> str:
    """Build one JSON log line shaped like the server's formatter output."""
    record: dict[str, object] = {
        "ts": ts,
        "level": "INFO",
        "logger": "server.test",
        "msg": msg,
        "request_id": request_id,
    }
    if event is not None:
        record["event"] = event
    record.update(fields)
    return json.dumps(record)


def _full_turn(request_id: str, ts: str, *, msg: str = "log text") -> list[str]:
    """Return the three events of a strong recall turn."""
    return [
        _line(ts, request_id, "stt.transcribed", msg, chars=21, hotwords=0),
        _line(
            ts,
            request_id,
            "turn.decision",
            msg,
            channel="stream",
            need="relatives_names",
            status="known",
            source="deterministic",
            tools="-",
            llm_ms=0,
        ),
        _line(
            ts,
            request_id,
            "recall.read",
            msg,
            route="strong",
            outcome="found",
            hits=2,
            best_distance=0.395,
            lexical_only=False,
            windowed=False,
        ),
    ]


def test_a_turn_is_one_row_of_closed_values() -> None:
    lines = _full_turn(_REQUEST, "2026-11-09T10:05:00.100-03:00")

    rows = summarize_turns(lines, since=_SINCE)

    assert rows == [
        TurnRow(
            ts="2026-11-09T10:05:00.100-03:00",
            request_id=_REQUEST,
            stt_chars=21,
            need="relatives_names",
            status="known",
            source="deterministic",
            recall_outcome="found",
            recall_hits=2,
            best_distance=0.395,
        )
    ]


def test_a_turn_without_a_plan_is_generic() -> None:
    ts = "2026-11-09T10:06:00.000-03:00"
    lines = [
        _line(ts, _REQUEST, "stt.transcribed", chars=40, hotwords=0),
        _line(
            ts,
            _REQUEST,
            "turn.decision",
            channel="stream",
            outcome="no-plan-channel-generates",
        ),
    ]

    (row,) = summarize_turns(lines, since=_SINCE)

    assert row.need == "generic_conversation"
    assert row.status is None
    assert row.source is None
    assert row.recall_outcome is None
    assert row.recall_hits is None
    assert row.best_distance is None


def test_lines_before_since_and_other_requests_are_ignored() -> None:
    lines = [
        *_full_turn(_OTHER, "2026-11-09T09:59:59.000-03:00"),
        "this is not json at all",
        "",
        _line("2026-11-09T10:07:00.000-03:00", "-", None, "Retention background job stopped"),
        _line(
            "2026-11-09T10:07:01.000-03:00",
            _OTHER,
            "http.request",
            method="POST",
            path="/transcribe/stream",
            status=200,
            duration_ms=10,
        ),
        *_full_turn(_REQUEST, "2026-11-09T10:08:00.000-03:00"),
    ]

    rows = summarize_turns(lines, since=_SINCE)

    assert [row.request_id for row in rows] == [_REQUEST]


def test_a_row_never_carries_a_message_text(tmp_path: Path) -> None:
    lines = _full_turn(_REQUEST, "2026-11-09T10:09:00.000-03:00", msg=_CANARY)
    log = tmp_path / "server.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written: list[str] = []

    exit_code = mvp_session_report.main(
        ["--log", str(log), "--since", _SINCE], write_text=written.append
    )

    rows = summarize_turns(lines, since=_SINCE)
    assert exit_code == 0
    assert len(rows) == 1
    assert _CANARY not in repr(rows[0])
    output = "".join(written)
    assert "relatives_names" in output
    assert _CANARY not in output
