import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.table_queries import PLANNER_SYSTEM, TablePlan, TableQuery, describe_tables, format_table_answer, format_table_evidence, needs_table_explanation, parse_plan, parse_query, query_instructions, query_tables
from backend.tables import read_table, summarize_table
from scripts.import_pm import import_files
from test_workbench import client, upload, wait_job


def sniffer_data():
    return ("#Created by: Sniffer4DMapper 2.4.05.07\nProjectName : Organization :\n"
            "timeStamp,Altitude m,PM2.5 μg/m³,PM10 μg/m³,,Serial No.\n"
            "\ufeff2025-03-26 11:19:09,19,48,60,,sensor-1\n"
            "\ufeff2025-03-26 11:19:10,22,50,65,,sensor-1\n"
            "\ufeff2025-03-26 11:19:11,25,70,90,,sensor-1\n").encode("utf-8-sig")


def table(tmp_path, altitude=50, trial=1):
    name = f"Activity_1_2_Mar_26_2025_Speed_3_Alt_{altitude}m_trial_{trial}.CSV"
    path = tmp_path / name
    path.write_bytes(sniffer_data())
    return {"id": str(altitude), "name": name, "path": path, "info": summarize_table(path)}


def test_sniffer_import_handles_preamble_bom_empty_column_and_preserves_original(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    item = table(source)
    original = item["path"].read_bytes()
    info = item["info"]
    assert info["rows"] == 3 and info["preamble_lines_skipped"] == 2
    assert info["invalid_timestamps"] == 0
    assert info["columns"] == ["timeStamp", "Altitude m", "PM2.5 μg/m³", "PM10 μg/m³", "Serial No."]
    destination = tmp_path / "assets"
    first, second = import_files(source, destination), import_files(source, destination)
    assert first["imported"] == 1 and second["already_present"] == 1
    saved = json.loads(next(destination.glob("*/metadata.json")).read_text(encoding="utf-8"))
    assert saved["info"]["experiment"] == {"speed_setting": 3, "altitude_setting_m": 50, "trial": 1}
    assert next(destination.glob("*/original.csv")).read_bytes() == original == item["path"].read_bytes()


def test_grouped_summary_separates_filename_setting_from_measured_altitude(tmp_path):
    tables = [table(tmp_path, 50), table(tmp_path, 70)]
    query = TableQuery(columns=["PM2.5 μg/m³", "Altitude m"], group_by="altitude_setting_m")
    result = query_tables(tables, query)
    assert result["matched_rows"] == 6
    assert [row["group"] for row in result["result"]] == ["50", "70"]
    for row in result["result"]:
        assert row["statistics"]["PM2.5 μg/m³"]["mean"] == 56
        assert row["statistics"]["Altitude m"]["mean"] == 22


def test_peak_rows_time_filter_and_correlations(tmp_path):
    tables = [table(tmp_path)]
    result = query_tables(tables, TableQuery(operation="rows", columns=["timeStamp", "PM2.5 μg/m³"],
                         sort_by="PM2.5 μg/m³", limit=1))
    assert result["matched_rows"] == 3 and result["displayed_rows"] == 1
    assert result["result"][0]["PM2.5 μg/m³"] == 70
    assert result["result"][0]["timeStamp"] == "2025-03-26 11:19:11"
    filtered = query_tables(tables, TableQuery(columns=["PM2.5 μg/m³"],
                           filters=[{"column": "timeStamp", "op": "ge", "value": "2025-03-26 11:19:10"}]))
    assert filtered["matched_rows"] == 2
    assert filtered["result"][0]["statistics"]["PM2.5 μg/m³"]["mean"] == 60
    corr = query_tables(tables, TableQuery(operation="correlation", columns=["PM2.5 μg/m³", "PM10 μg/m³"]))
    frame = read_table(tables[0]["path"])
    assert corr["result"]["PM2.5 μg/m³"]["PM10 μg/m³"] == pytest.approx(frame["PM2.5 μg/m³"].corr(frame["PM10 μg/m³"]))
    assert corr["pairwise_valid_counts"]["PM2.5 μg/m³"]["PM10 μg/m³"] == 3


def test_each_measurement_peak_has_its_own_timestamp_and_altitude(tmp_path):
    item = table(tmp_path)
    item["path"].write_text("timeStamp,Altitude m,PM2.5 μg/m³,PM10 μg/m³\n2025-03-26 11:00:00,20,90,10\n2025-03-26 11:01:00,25,30,100\n", encoding="utf-8")
    item["info"] = summarize_table(item["path"])
    result = query_tables([item], TableQuery(columns=["PM2.5 μg/m³", "PM10 μg/m³"]))
    peaks = {p["measurement"]: p for p in result["peak_records"]}
    assert peaks["PM2.5 μg/m³"]["timeStamp"] == "2025-03-26 11:00:00"
    assert peaks["PM10 μg/m³"]["timeStamp"] == "2025-03-26 11:01:00"
    assert peaks["PM2.5 μg/m³"]["value"] == 90
    assert peaks["PM10 μg/m³"]["value"] == 100
    assert peaks["PM2.5 μg/m³"]["altitude_setting_m"] == 50
    assert peaks["PM10 μg/m³"]["Altitude m"] == 25


def test_statistical_evidence_keeps_narration_within_computed_columns_and_scope(tmp_path):
    result = query_tables([table(tmp_path)], TableQuery(columns=["PM2.5 μg/m³"]))
    context = format_table_evidence(result)
    assert "within its query filters and matched_rows" in context
    assert "Do not compare unqueried columns" in context
    assert "cannot confirm an anomaly or determine its cause" in context
    payload = context.split("\n", 2)[1]
    supplied = json.loads(payload)
    assert supplied["query"] == result["query"]
    assert supplied["matched_rows"] == result["matched_rows"]
    assert supplied["result"] == result["result"]


def test_missing_rows_invalid_plan_unknown_columns_and_nonfinite_values(tmp_path):
    tables = [table(tmp_path)]
    empty = query_tables(tables, TableQuery(columns=["PM2.5 μg/m³"],
                        filters=[{"column": "PM2.5 μg/m³", "op": "gt", "value": 1000}]))
    assert empty["matched_rows"] == 0 and empty["result"] == []
    with pytest.raises(ValueError, match="Unknown"):
        query_tables(tables, TableQuery(columns=["invented"]))
    with pytest.raises(ValueError):
        parse_query('{"operation":"execute","code":"import os"}')
    with pytest.raises(ValueError):
        parse_query('{"operation":"rows","filters":[{"column":"x","op":"gt","value":NaN}]}')
    parsed = parse_query('{"operation":"summary","columns":["PM2.5 μg/m³"]}')
    assert parsed.operation == "summary"
    with pytest.raises(ValueError, match="Grouping"):
        query_tables(tables, TableQuery(operation="rows", group_by="altitude_setting_m"))
    with pytest.raises(ValueError, match="Sorting"):
        query_tables(tables, TableQuery(operation="summary", sort_by="PM2.5 μg/m³"))
    with pytest.raises(ValueError, match="unique"):
        query_tables(tables, TableQuery(columns=["PM2.5 μg/m³", "PM2.5 μg/m³"]))


def test_chat_passes_history_and_records_computed_table_evidence(client, monkeypatch):
    source = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_50m_trial_1.CSV", sniffer_data(), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append({"question": question, "content": content, "history": history})
        if len(calls) == 1:
            assert system == PLANNER_SYSTEM
            return '{"operation":"summary","columns":["PM2.5 μg/m³"],"group_by":"altitude_setting_m","explain":true}', {"input_tokens": 10}
        return "TEST STUB: mean PM2.5 is 56 μg/m³ for the 50 m setting.", {"input_tokens": 20}
    monkeypatch.setattr(main.engine, "generate", generate)
    history = [{"role": "user", "content": "Compare the altitude settings."},
               {"role": "assistant", "content": "Which pollutant?"}]
    submitted = client.post("/api/jobs", json={"chat_id": "a" * 32, "asset_ids": [source["id"]],
                           "question": "PM2.5 please.", "history": history})
    assert submitted.status_code == 202
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert job["table_result"]["result"][0]["statistics"]["PM2.5 μg/m³"]["mean"] == 56
    assert calls[0]["history"] == calls[1]["history"] == history
    assert "Verified Python table query result" in str(calls[1]["content"])
    assert source["name"] in str(calls[1]["content"]) and "peak_records" in str(calls[1]["content"])
    assert job["evidence"][0]["id"] == source["id"] and job["planner_metrics"]["input_tokens"] == 10
    assert job["model_calls"] == 2 and job["response_mode"] == "qwen"


def test_text_only_chat_is_allowed(client, monkeypatch):
    monkeypatch.setattr(main.engine, "generate", lambda *args, **kwargs: ("TEST STUB: text reply", {}))
    submitted = client.post("/api/jobs", json={"asset_ids": [], "question": "Explain this project.", "chat_id": "b" * 32})
    assert submitted.status_code == 202
    assert wait_job(client, submitted.json()["id"])["status"] == "completed"


def test_file_overview_has_real_schema_counts_and_settings_without_a_statistical_query(tmp_path):
    tables = [table(tmp_path, 50), table(tmp_path, 70)]
    result = query_tables(tables, TableQuery(operation="none"))
    manifest = result["dataset"]
    assert manifest["source_count"] == 2 and manifest["total_rows"] == 6
    assert "PM2.5 μg/m³" in manifest["columns"] and "timeStamp" in manifest["columns"]
    assert manifest["filename_settings"] == {"speed_setting": [3], "altitude_setting_m": [50, 70], "trial": [1]}
    assert manifest["schema_count"] == 1
    assert manifest["recorded_date_range"] == ["2025-03-26", "2025-03-26"]
    assert manifest["numeric_missing_or_invalid"]["PM2.5 μg/m³"] == 0
    assert "not all cells" in manifest["quality_scope"]
    context = format_table_evidence(result)
    assert '"source_count": 2' in context and "PM2.5 μg/m³" in context
    assert "numeric_missing_or_invalid" not in context and "source_time_ranges" not in context


def test_manifest_missing_numeric_column_is_not_reported_as_zero_missing(tmp_path):
    first, second = table(tmp_path, 50), table(tmp_path, 70)
    second["path"].write_text("timeStamp,PM2.5 μg/m³\n2025-03-26 12:00:00,10\n", encoding="utf-8")
    second["info"] = summarize_table(second["path"])
    manifest = describe_tables([first, second])
    assert manifest["source_count"] == 2 and manifest["total_rows"] == 4
    assert manifest["schema_count"] == 2
    assert manifest["numeric_missing_or_invalid"]["PM10 μg/m³"] == 1


def test_file_description_chat_returns_verified_manifest_with_one_call(client, monkeypatch):
    source = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_50m_trial_1.CSV", sniffer_data(), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append(content)
        return '{"operation":"none"}', {}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "What do these files store?"})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert job["table_result"]["dataset"]["source_count"] == 1
    assert len(calls) == job["model_calls"] == 1
    assert "**1 CSV file**" in job["answer"] and "**3 recorded environmental sensor measurements**" in job["answer"]
    assert "PM2.5" in job["answer"] and "Altitude" in job["answer"]


@pytest.mark.parametrize("bad_plan", [
    '{"operation":"summary","columns":["PM2.5 μg/m³"],"sort_by":"PM2.5 μg/m³"}',
    '{"operation":"none","sort_by":"PM2.5 μg/m³"}',
    '{"operation":"none","filters":[{"column":"speed_setting","op":"eq","value":3}]}',
    'This is not JSON.',
])
def test_invalid_planner_query_gets_one_correction_without_changing_scope(client, monkeypatch, bad_plan):
    source = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_50m_trial_1.CSV", sniffer_data(), "pm")
    calls = []
    filters = [{"column": "speed_setting", "op": "eq", "value": 3},
               {"column": "altitude_setting_m", "op": "eq", "value": 50},
               {"column": "trial", "op": "eq", "value": 1}]
    corrected = json.dumps({"operation": "summary", "columns": ["PM2.5 μg/m³"], "filters": filters, "explain": True})
    def generate(question, content, tokens, history=None, system=None):
        calls.append((question, content, history))
        if len(calls) == 1:
            return bad_plan, {"input_tokens": 10}
        if len(calls) == 2:
            repair_text = "\n".join(part["text"] for part in content)
            assert "validation_error" in repair_text
            assert "Preserve the user's question, filters, dataset scope" in repair_text
            return corrected, {"input_tokens": 12}
        return "TEST STUB: PM2.5 mean 56, minimum 48, maximum 70.", {"input_tokens": 20}
    monkeypatch.setattr(main.engine, "generate", generate)
    history = [{"role": "user", "content": "Use speed 3, altitude 50, trial 1."}]
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "What is unusual?", "history": history})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert len(job["planner_attempts"]) == 2
    assert job["planner_attempts"][0]["response"] == bad_plan
    assert job["planner_attempts"][0]["validation_error"]
    assert job["planner_attempts"][1]["query"]["operation"] == "summary"
    assert job["table_result"]["matched_rows"] == 3
    assert job["table_result"]["result"][0]["statistics"]["PM2.5 μg/m³"]["mean"] == 56
    assert job["planner_metrics"]["input_tokens"] == 12
    assert all(call[0] == "What is unusual?" and call[2] == history for call in calls)


def test_repeated_invalid_plans_stop_and_remain_in_run_export(client, monkeypatch):
    source = upload(client, "pm.csv", sniffer_data(), "pm")
    calls = []
    def generate(*args, **kwargs):
        calls.append(args)
        return '{"operation":"summary","sort_by":"PM2.5 μg/m³"}', {}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "What is unusual?"})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "failed"
    assert "after one correction" in job["error"]
    assert len(calls) == len(job["planner_attempts"]) == 2
    exported = client.get(f"/api/jobs/{job['id']}/export").json()
    assert all(attempt["response"] and attempt["validation_error"] for attempt in exported["planner_attempts"])
    assert "answer" not in job


@pytest.mark.parametrize("plan,expected", [
    ({"columns": ["PM2.5 μg/m³"]}, "56"),
    ({"columns": ["PM2.5 μg/m³"], "group_by": "altitude_setting_m"}, "Altitude setting (m)"),
    ({"operation": "rows", "columns": ["timeStamp", "PM2.5 μg/m³"], "sort_by": "PM2.5 μg/m³", "limit": 1}, "2025-03-26 11:19:11"),
    ({"operation": "correlation", "columns": ["PM2.5 μg/m³", "PM10 μg/m³"]}, "Pearson r"),
])
def test_basic_table_answers_use_one_model_call_and_preserve_exports(client, monkeypatch, plan, expected):
    source = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_50m_trial_1.CSV", sniffer_data(), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append(system)
        assert len(calls) == 1, "A simple query must not trigger prose generation."
        return json.dumps(plan), {"input_tokens": 20}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "Show the calculated values."})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert calls == [PLANNER_SYSTEM] and job["model_calls"] == 1
    assert job["response_mode"] == "computed" and job["metrics"] == {}
    assert expected in job["answer"] and "[Selected tables]" not in job["answer"]
    assert job["table_result"]["matched_rows"] == 3
    assert job["evidence"][0]["sha256"] == source["sha256"]
    exported = client.get(f"/api/jobs/{job['id']}/export").json()
    assert exported["planner_metrics"] == {"input_tokens": 20}
    assert exported["system_prompt"] == PLANNER_SYSTEM
    report = client.post("/api/report", json={"asset_ids": [source["id"]], "run_ids": [job["id"]]})
    assert report.status_code == 200 and expected in report.text


def test_mixed_sources_keep_qwen_answer_even_when_table_plan_is_basic(client, monkeypatch):
    source = upload(client, "pm.csv", sniffer_data(), "pm")
    log = upload(client, "flight.log", b"Flight observation: north area inspected.")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append(content)
        if len(calls) == 1:
            return '{"columns":["PM2.5 μg/m³"]}', {}
        assert "north area inspected" in str(content)
        return "TEST STUB: Combined evidence answer.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"], log["id"]], "question": "Summarize this flight."})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert job["model_calls"] == len(calls) == 2 and job["response_mode"] == "qwen"
    assert len(job["evidence"]) == 2


def test_requested_interpretation_keeps_answer_call_when_planner_omits_flag(client, monkeypatch):
    source = upload(client, "pm.csv", sniffer_data(), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append(content)
        if len(calls) == 1:
            return '{"columns":["PM2.5 μg/m³"]}', {}
        return "TEST STUB: Observed variation; the cause is not established.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "What is weird about these measurements?"})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert job["model_calls"] == len(calls) == 2 and job["response_mode"] == "qwen"


@pytest.mark.parametrize("question,operation,expected", [
    ("Mean and standard deviation for PM2.5", "summary", False),
    ("Give summary statistics", "summary", False),
    ("What do these files store?", "none", False),
    ("What do these files store?", "summary", True),
    ("Show the five highest records", "rows", False),
    ("Compare means by altitude", "summary", False),
    ("Explain these PM2.5 values", "summary", True),
    ("What stands out?", "summary", True),
    ("Write a narrative report", "summary", True),
    ("WHY is it unusual?", "summary", True),
    ("is there any case to use them for site safety manager", "summary", True),
    ("this is datasets useful for what for site monitoring?", "none", True),
    ("What can I do with these?", "summary", True),
    ("Can the PM2.5 mean show a safety problem?", "summary", True),
    ("Tell me about these datasets overall, and when and at which altitude was PM2.5 highest?", "none", True),
])
def test_explanation_intent_keeps_routine_calculations_fast(question, operation, expected):
    assert needs_table_explanation(question, TableQuery(operation=operation)) is expected
    assert needs_table_explanation(question, TableQuery(operation=operation, explain=True))


@pytest.mark.parametrize("plan", [
    '{"columns":["PM2.5 μg/m³"],"filters":[{"column":"trial","op":"ge","value":2}],"explain":false}',
    '{"operation":"none","explain":false}',
])
def test_safety_manager_question_does_not_return_only_a_filtered_statistics_table(client, monkeypatch, plan):
    source = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_50m_trial_1.CSV", sniffer_data(), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append(content)
        if len(calls) == 1:
            return plan, {}
        assert "PM2.5 μg/m³" in str(content)
        assert "Use factual_lead as the opening sentence" not in str(content)
        return "TEST STUB: A safety manager can use recorded PM measurements to plan follow-up checks.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]],
                                             "question": "is there any case to use them for site safety manager"})
    job = wait_job(client, submitted.json()["id"])
    assert job["status"] == "completed", job
    assert len(calls) == job["model_calls"] == 2
    assert job["response_mode"] == "qwen" and "A safety manager" in job["answer"]


def test_direct_answer_preserves_unavailable_values_and_does_not_invent_anomalies(tmp_path):
    item = table(tmp_path)
    item["path"].write_text("PM2.5 μg/m³,PM10 μg/m³\n10,20\n", encoding="utf-8")
    item["info"] = summarize_table(item["path"])
    result = query_tables([item], TableQuery(columns=["PM2.5 μg/m³"]))
    answer = format_table_answer(result)
    assert "Std dev" in answer and "| 10 | 10 | 10 | 10 | — |" in answer
    assert "anomaly" not in answer and "sensor error" not in answer
    missing = query_tables([item], TableQuery(columns=["PM2.5 μg/m³"],
                           filters=[{"column": "PM2.5 μg/m³", "op": "gt", "value": 100}]))
    assert "No measurements matched" in format_table_answer(missing)
    correlation = query_tables([item], TableQuery(operation="correlation", columns=["PM2.5 μg/m³", "PM10 μg/m³"]))
    assert "| — | 1 |" in format_table_answer(correlation)


def test_compact_planner_sources_preserve_exact_names_ids_and_settings(tmp_path):
    tables = [table(tmp_path, 50), table(tmp_path, 70)]
    instructions = query_instructions(tables)
    data = json.loads(instructions.split("\n", 1)[1])
    assert data["query_schema"] == TablePlan.model_json_schema() and "explain=true" in instructions
    for item, row in zip(tables, data["sources"]):
        assert row[0] == item["id"]
        assert data["name_prefix"] + row[1] == item["name"]
        assert row[2:] == [3, int(item["id"]), 1]
    with pytest.raises(ValueError):
        parse_query('{"explain":"false"}')
    with pytest.raises(ValueError, match='"field": "summary"'):
        parse_query('{"summary":{"stats":{"mean":56}}}')


def test_direct_answer_handles_generic_schema_circular_mean_and_literal_source_names(tmp_path):
    item = table(tmp_path)
    item["name"] = "flight|[link](example).csv"
    item["path"].write_text("wind_Direction degrees,Temperature ℃\n350,10\n10,20\n", encoding="utf-8")
    item["info"] = summarize_table(item["path"])
    overview = format_table_answer(query_tables([item], TableQuery(operation="none")))
    assert "tabular records" in overview and "Temperature ℃" in overview
    assert "Air quality" not in overview
    summary = format_table_answer(query_tables([item], TableQuery(columns=["wind_Direction degrees"])))
    assert "uses a circular mean" in summary and "standard deviation is not calculated" in summary
    records = format_table_answer(query_tables([item], TableQuery(operation="rows", columns=["Temperature ℃"])))
    assert r"flight\|\[link\](example).csv" in records


def test_multi_query_plan_is_bounded_and_all_queries_are_validated():
    queries = parse_plan('{"queries":[{"operation":"summary"},{"operation":"rows","limit":3}]}')
    assert [q.operation for q in queries] == ["summary", "rows"]
    assert parse_plan('{"operation":"none"}')[0].operation == "none"
    for payload in ({"queries": []}, {"queries": [{}] * 4}, {"queries": [{"operation": "execute", "code": "print(1)"}]},
                    {"queries": [{}], "code": "import os"}):
        with pytest.raises(ValueError):
            parse_plan(json.dumps(payload))


def test_question_gets_altitude_comparison_and_peak_time_in_one_plan(client, monkeypatch):
    first = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_50m_trial_1.CSV", sniffer_data(), "pm")
    second = upload(client, "Activity_1_2_Mar_26_2025_Speed_3_Alt_70m_trial_1.CSV",
                    sniffer_data().replace(b",70,90,", b",170,190,"), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        calls.append((question, content, system))
        if system == PLANNER_SYSTEM:
            return json.dumps({"queries": [
                {"operation": "summary", "columns": ["PM2.5 μg/m³"], "group_by": "altitude_setting_m", "explain": True},
                {"operation": "rows", "columns": ["timeStamp", "altitude_setting_m", "Altitude m", "PM2.5 μg/m³"], "sort_by": "PM2.5 μg/m³", "limit": 1}
            ]}), {}
        evidence = next(p["text"] for p in content if "Verified Python results" in p.get("text", ""))
        data = json.loads(evidence.split("\n", 2)[1])
        assert "Do not provide example, hypothetical" in evidence
        assert len(data["results"]) == 2
        peak = data["results"][1]["result"][0]
        assert peak["PM2.5 μg/m³"] == 170 and peak["altitude_setting_m"] == 70 and peak["Altitude m"] == 25
        assert peak["timeStamp"] == "2025-03-26 11:19:11"
        assert data["dataset"]["source_count"] == 2
        return "TEST STUB: PM2.5 peaked at 170 μg/m³ at 11:19:11, in the 70 m flight. [Selected tables]", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    question = "Tell me about these datasets overall, any eco-safety issue, when and at which altitude?"
    response = client.post("/api/jobs", json={"asset_ids": [first["id"], second["id"]], "question": question})
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "completed", job
    assert job["model_calls"] == 2 and job["table_result"]["operation"] == "multiple"
    assert calls[0][0] == calls[1][0] == question
    assert "[Selected tables]" not in job["answer"]
    assert "[Selected tables]" not in format_table_answer(query_tables([
        {**first, "path": main.asset_path(first)}], TableQuery(operation="none")))
