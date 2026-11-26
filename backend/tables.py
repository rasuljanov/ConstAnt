"""Calculate measurement summaries before sending evidence to the language model."""

import csv
import io
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

MAX_ROWS = 200_000


def read_table(path: Path):
    raw = path.read_bytes()
    text = None
    encodings = ("utf-16",) if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "cp949")
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            break
        except UnicodeError:
            continue
    if text is None or "\x00" in text:
        raise ValueError("Use a UTF-8, UTF-16, or Korean CP949 CSV/TSV file.")
    text = text.replace("\ufeff", "")
    skipped = 0
    if text.startswith("#Created by: Sniffer4DMapper"):
        lines = text.splitlines()
        skipped = next((i for i, line in enumerate(lines[:20]) if line.startswith("timeStamp,")), -1)
        if skipped < 0:
            raise ValueError("Sniffer4D export has no timeStamp header in its first 20 lines.")
        text = "\n".join(lines[skipped:])
    try:
        delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    frame = pd.read_csv(io.StringIO(text), sep=delimiter, nrows=MAX_ROWS + 1)
    frame = frame.drop(columns=[c for c in frame if str(c).startswith("Unnamed:") and frame[c].isna().all()])
    if frame.empty or len(frame) > MAX_ROWS or len(frame.columns) > 100:
        raise ValueError("Tables must contain 1–200,000 rows and at most 100 columns. Split larger tables.")
    frame.columns = [str(c).strip() for c in frame.columns]
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("Column names must be unique after removing surrounding whitespace.")
    frame.attrs["preamble_lines_skipped"] = skipped
    return frame


def experiment_from_name(name):
    match = re.search(r"Speed_(\d+)_Alt_(\d+)m_trial_(\d+)", name, flags=re.IGNORECASE)
    if not match:
        return {}
    return dict(zip(("speed_setting", "altitude_setting_m", "trial"), map(int, match.groups())))


def summarize_table(path: Path):
    frame = read_table(path)
    normalized = {c: unicodedata.normalize("NFKC", c).lower().replace(" ", "") for c in frame.columns}
    time_col = next((c for c, n in normalized.items() if n in ("timestamp", "time", "datetime", "date")), None)
    times = pd.to_datetime(frame[time_col], errors="coerce", format="mixed") if time_col else None
    summary = {"rows": len(frame), "columns": list(frame.columns), "statistics": {},
               "preamble_lines_skipped": frame.attrs["preamble_lines_skipped"],
               "time_column": time_col, "time_range": None, "invalid_timestamps": None,
               "timezone_note": "No site timezone inferred. Verify time alignment before combining sources.",
               "series": [], "series_column": None,
               "preview": frame.head(8).astype(object).where(frame.head(8).notna(), None).to_dict("records")}
    if times is not None:
        valid_times = times.dropna()
        summary["invalid_timestamps"] = int(times.isna().sum())
        try:
            if len(valid_times):
                summary["time_range"] = [str(valid_times.min()), str(valid_times.max())]
        except TypeError:
            raise ValueError("Use consistent timestamp formats and timezone offsets within a table.")
    numeric = {}
    for column in frame:
        if column == time_col or normalized[column] in ("serialno.", "serialno", "serialnumber", "id"):
            continue
        values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
        valid = values.dropna()
        if valid.empty:
            continue
        numeric[column] = values
        summary["statistics"][column] = {
            "count": int(valid.count()), "missing_or_invalid": int(values.isna().sum()),
            "min": float(valid.min()), "mean": float(valid.mean()), "max": float(valid.max()),
        }
        if "direction" in normalized[column] and ("degree" in normalized[column] or "°" in column):
            radians = np.deg2rad(valid)
            sine, cosine = float(np.sin(radians).mean()), float(np.cos(radians).mean())
            summary["statistics"][column]["mean"] = (
                float(np.rad2deg(np.arctan2(sine, cosine)) % 360) if np.hypot(sine, cosine) > 1e-8 else None)
            summary["statistics"][column]["mean_method"] = "circular mean in degrees; null when undefined"
    pm_column = next((c for c in numeric if "pm2.5" in normalized[c]), None)
    series_column = pm_column or next(iter(numeric), None)
    if series_column:
        summary["series_column"] = series_column
        # Preserve bucket minima/maxima so a display downsample does not hide PM peaks.
        values = numeric[series_column]
        indices = set()
        for bucket in np.array_split(np.arange(len(frame)), min(100, len(frame))):
            valid = values.iloc[bucket].dropna()
            if not valid.empty:
                indices.update((int(valid.idxmin()), int(valid.idxmax())))
        summary["series"] = [{"row": i, "time": str(frame.iloc[i][time_col]) if time_col else str(i + 1),
                              "value": float(values.iloc[i])} for i in sorted(indices)]
    for label, limit in (("latitude", 90), ("longitude", 180)):
        col = next((c for c in numeric if normalized[c] == label), None)
        if col:
            summary.setdefault("invalid_coordinates", {})[label] = int((numeric[col].abs() > limit).sum())
    # Convert preview values through pandas JSON to remove numpy scalars/nonfinite numbers.
    import json
    summary["preview"] = json.loads(frame.head(8).to_json(orient="records", date_format="iso"))
    return summary
