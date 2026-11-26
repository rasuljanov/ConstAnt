import json

import pytest

from backend import main
from backend.inference import SYSTEM, response_system
from backend.table_queries import PLANNER_SYSTEM, TableQuery, format_table_answer, query_tables
from backend.visual_analysis import visual_count_table
from test_chat_tables import sniffer_data, table
from test_workbench import client, upload, wait_job


@pytest.mark.parametrize("language,name", [("en", "English"), ("uz", "Uzbek"), ("ko", "Korean")])
def test_selected_reply_language_reaches_model_and_saved_prompt(client, monkeypatch, language, name):
    seen = []
    def generate(question, content, tokens, history=None, system=None):
        seen.append(system)
        return "TEST ANSWER", {"input_tokens": 10}
    monkeypatch.setattr(main.engine, "generate", generate)
    response = client.post("/api/jobs", json={"question": "English question", "language": language})
    run = wait_job(client, response.json()["id"])
    assert run["status"] == "completed"
    assert f"Respond in {name}" in seen[0]
    assert run["system_prompt"] == seen[0] and run["request"]["language"] == language
    assert run["request"]["question"] == "English question"
    assert response_system() == SYSTEM
    assert client.post("/api/jobs", json={"question": "TEST", "language": "invalid"}).status_code == 422


@pytest.mark.parametrize("language,header", [("uz", "mos qator"), ("ko", "일치 행")])
def test_computed_table_reply_is_localized_without_an_extra_model_call(client, monkeypatch, language, header):
    item = upload(client, "Mean.csv", sniffer_data(), "pm")
    calls = []
    def generate(question, content, tokens, history=None, system=None):
        assert system == PLANNER_SYSTEM
        calls.append(1)
        return json.dumps({"operation": "rows", "columns": ["timeStamp", "PM2.5 μg/m³"], "sort_by": "PM2.5 μg/m³", "limit": 1, "explain": False}), {}
    monkeypatch.setattr(main.engine, "generate", generate)
    response = client.post("/api/jobs", json={"question": "Show the highest PM2.5 record.", "asset_ids": [item["id"]], "language": language})
    run = wait_job(client, response.json()["id"])
    assert run["status"] == "completed", run
    assert len(calls) == 1 and run["response_mode"] == "computed"
    assert header in run["answer"] and "PM2.5 μg/m³" in run["answer"]
    assert "70" in run["answer"] and "2025-03-26 11:19:11" in run["answer"]
    assert "Mean.csv" in run["answer"]


def test_summary_localizes_authored_labels_without_changing_data_columns(tmp_path):
    result = query_tables([table(tmp_path)], TableQuery(columns=["PM2.5 μg/m³"]))
    answer = format_table_answer(result, language="ko")
    assert "평균" in answer and "PM2.5 μg/m³" in answer
    assert "56" in answer and "상관" not in answer


def test_visual_table_localizes_labels_without_translating_filename_or_counts():
    result = {"sources": [{"id": "TEST", "name": "Trucks.mp4", "kind": "video", "unit_count": 1,
                           "units": [{"status": "observed", "counts": {"truck": 2}}]}]}
    answer = visual_count_table(result, language="ko")
    assert "트럭" in answer and "Trucks.mp4" in answer and "2–2" in answer
