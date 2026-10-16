"""Generate a self-contained, escaped HTML report from the JSONL event log."""

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from canarynet.attack.rules import ATTACK_VERSION, TECHNIQUES


def _escape(value):
    return html.escape(str(value), quote=True)


def _validate(event):
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    for field in ("session_id", "timestamp", "src", "input", "output", "answered_by"):
        if not isinstance(event.get(field), str):
            raise ValueError("missing or invalid text field")
    latency = event.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)):
        raise ValueError("latency must be numeric")
    if latency < 0 or not math.isfinite(latency):
        raise ValueError("latency must be finite and nonnegative")
    if not isinstance(event.get("tags"), list) or not all(isinstance(t, str) for t in event["tags"]):
        raise ValueError("tags must be a list of strings")
    timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must contain a timezone")
    return timestamp.astimezone(timezone.utc)


def read_events(path):
    """Return chronologically sorted valid events, malformed count, missing flag."""
    events, skipped = [], 0
    try:
        stream = Path(path).open("rb")
    except FileNotFoundError:
        return [], 0, True
    with stream:
        for number, raw in enumerate(stream, start=1):
            try:
                event = json.loads(raw)
                event["_time"] = _validate(event)
                event["_line"] = number
                events.append(event)
            except (ValueError, TypeError, UnicodeError, OverflowError):
                skipped += 1
    events.sort(key=lambda event: (event["_time"], event["_line"]))
    return events, skipped, False


_STYLE = """
body{font:15px system-ui,sans-serif;background:#f5f7fb;color:#18243a;margin:0}
main{max-width:1200px;margin:auto;padding:32px 20px}h1{margin-bottom:6px}
.muted{color:#536079}.summary,.notice,section{background:white;border:1px solid #dce2ed;
border-radius:12px;padding:18px;margin:18px 0}.notice{border-left:5px solid #a36b00}
.summary{display:flex;gap:24px;flex-wrap:wrap}.metric strong{display:block;font-size:25px}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}
th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e2e7ef;padding:10px;
overflow-wrap:anywhere}th{font-size:12px;color:#536079}pre{white-space:pre-wrap;
overflow-wrap:anywhere;margin:0;font:13px ui-monospace,monospace}.tags{font-size:12px}
caption{text-align:left;margin-bottom:12px;color:#536079}h2{overflow-wrap:anywhere}
.time{width:16%}.command{width:22%}.output{width:27%}.meta{width:15%}
"""


def generate_report(log_path="logs/events.jsonl", output_path="report.html"):
    """Write the report; all paths are trusted developer arguments, not visitors'."""
    events, skipped, missing = read_events(log_path)
    sessions = {}
    for event in events:
        sessions.setdefault(event["session_id"], []).append(event)
    code_count = sum(event["answered_by"] == "code" for event in events)
    model_count = sum(event["answered_by"] == "model" for event in events)
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
        '<title>CanaryNet Lite — Activity report</title><style>', _STYLE,
        '</style></head><body><main><h1>CanaryNet Lite</h1>',
        '<p class="muted">Private lab activity report · ATT&amp;CK v', _escape(ATTACK_VERSION), '</p>',
        '<div class="notice">Technique matches describe observed attempts and rule matches. ',
        'They do not establish successful compromise.</div><div class="summary">',
    ]
    for label, value in [("Sessions", len(sessions)), ("Events", len(events)),
                         ("Code answers", code_count), ("Model answers", model_count),
                         ("Malformed lines skipped", skipped)]:
        parts.append(f'<div class="metric"><strong>{value}</strong>{_escape(label)}</div>')
    parts.append('</div>')
    if missing:
        parts.append('<p>No log file found. Run the decoy to record activity, then regenerate this report.</p>')
    elif not events:
        parts.append('<p>No valid events found.</p>')
    for session_id, rows in sessions.items():
        parts.append(f'<section><h2>Session {_escape(session_id)}</h2><div class="scroll"><table>')
        parts.append('<caption>UTC time order; ties preserve log order.</caption>')
        parts.append('<thead><tr><th class="time">UTC time / source</th><th class="command">Input</th>'
                     '<th class="output">Output</th><th class="meta">Answer / latency</th>'
                     '<th>ATT&amp;CK attempts</th></tr></thead><tbody>')
        for event in rows:
            stamp = event["_time"].isoformat().replace("+00:00", "Z")
            tags = '<br>'.join(
                f'{_escape(tag)} — {_escape(TECHNIQUES.get(tag, "VERIFY: unknown technique"))}'
                for tag in event["tags"]
            ) or 'None'
            parts.append(
                '<tr>'
                f'<td>{_escape(stamp)}<br>{_escape(event["src"])}</td>'
                f'<td><pre>{_escape(event["input"])}</pre></td>'
                f'<td><pre>{_escape(event["output"])}</pre></td>'
                f'<td>{_escape(event["answered_by"])}<br>{_escape(event["latency_ms"])} ms</td>'
                f'<td class="tags">{tags}</td></tr>'
            )
        parts.append('</tbody></table></div></section>')
    parts.append('</main></body></html>')
    Path(output_path).write_text(''.join(parts), encoding="utf-8")
    return {"events": len(events), "sessions": len(sessions), "skipped": skipped}


def main():
    counts = generate_report()
    print(f"Wrote report.html: {counts['events']} events, {counts['skipped']} malformed lines skipped.")


if __name__ == "__main__":
    main()
