import json
import threading

import pytest

from backend import main
from backend.chat_titles import TITLE_SYSTEM, generate_title
from test_workbench import client, upload, wait_job


@pytest.mark.parametrize("with_file", [False, True])
def test_title_follows_first_reply_without_delaying_it_or_renaming_followups(client, monkeypatch, with_file):
    entered, release, naming, finish = (threading.Event() for _ in range(4))
    title_calls = []
    def generate(question, content, tokens, **kwargs):
        if kwargs.get("system", "").startswith(TITLE_SYSTEM):
            title_calls.append(json.loads(content[0]["text"]))
            assert tokens == 48 and "Uzbek" in kwargs["system"]
            naming.set()
            assert finish.wait(3)
            return "Qurilish Changini Kuzatish", {"output_tokens": 8}
        entered.set()
        assert release.wait(3)
        return "TEST STUB: dust monitoring supports site review.", {"inference_seconds": 0.25}
    monkeypatch.setattr(main.engine, "generate", generate)
    chat_id = "1" * 32
    ids = [upload(client, "site.txt", b"Recorded site observations.")["id"]] if with_file else []
    first = client.post("/api/jobs", json={"chat_id": chat_id, "question": "What is this useful for?", "asset_ids": ids, "language": "uz"}).json()
    try:
        assert entered.wait(2)
        assert client.get("/api/chats").json()[0]["title"] is None
        release.set()
        assert naming.wait(2)
        ready = client.get(f"/api/jobs/{first['id']}").json()
        assert ready["status"] == "completed" and ready["answer"].startswith("TEST STUB:")
        assert ready["title_pending"] and ready["model_calls"] == 1
        assert ready["metrics"]["inference_seconds"] == 0.25
        assert client.get("/api/chats").json()[0]["title"] is None
        assert client.patch(f"/api/chats/{chat_id}", json={"pinned": True}).status_code == 200
    finally:
        release.set()
        finish.set()
    done = wait_job(client, first["id"])
    assert done["wall_seconds"] == ready["wall_seconds"] and not done["title_pending"]
    chat = client.get("/api/chats").json()[0]
    assert chat["title"] == "Qurilish Changini Kuzatish" and chat["pinned"]
    metadata = main.record(main.CHATS / (chat_id + ".json"))
    assert metadata["title_run_id"] == first["id"] and metadata["title_metrics"]["output_tokens"] == 8
    assert title_calls == [{"request": "What is this useful for?", "response": done["answer"]}]
    follow = client.post("/api/jobs", json={"chat_id": chat_id, "question": "Explain the next step."}).json()
    assert wait_job(client, follow["id"])["status"] == "completed"
    assert len(title_calls) == 1
    assert client.get("/api/chats").json()[0]["title"] == chat["title"]


@pytest.mark.parametrize("action", ["rename", "delete"])
def test_manual_changes_during_naming_are_preserved(client, monkeypatch, action):
    naming, finish = threading.Event(), threading.Event()
    def generate(question, content, tokens, **kwargs):
        if kwargs.get("system", "").startswith(TITLE_SYSTEM):
            naming.set()
            assert finish.wait(3)
            return "Generated Site Title", {}
        return "TEST STUB: first reply.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    chat_id = "2" * 32
    submitted = client.post("/api/jobs", json={"chat_id": chat_id, "question": "Review the site."}).json()
    try:
        assert naming.wait(2)
        if action == "rename":
            assert client.patch(f"/api/chats/{chat_id}", json={"title": "My own title"}).status_code == 200
        else:
            assert client.delete(f"/api/chats/{chat_id}").status_code == 200
    finally:
        finish.set()
        # Wait for the worker, including its post-reply title cleanup.
        future = main.job_futures.get(submitted["id"])
        if future is not None:
            future.result(timeout=3)
    if action == "rename":
        assert client.get("/api/chats").json()[0]["title"] == "My own title"
    else:
        assert client.get("/api/chats").json() == []
        assert not (main.CHATS / (chat_id + ".json")).exists()
        assert not (main.JOBS / (submitted["id"] + ".json")).exists()


def test_naming_failure_does_not_fail_a_reply_and_retries_from_first_pair(client, monkeypatch):
    seen = []
    def generate(question, content, tokens, **kwargs):
        if kwargs.get("system", "").startswith(TITLE_SYSTEM):
            seen.append(json.loads(content[0]["text"]))
            if len(seen) == 1:
                raise RuntimeError("TEST STUB: naming unavailable")
            return "Site Dust Review", {}
        return "TEST STUB: " + question, {}
    monkeypatch.setattr(main.engine, "generate", generate)
    chat_id = "3" * 32
    first = client.post("/api/jobs", json={"chat_id": chat_id, "question": "First question"}).json()
    assert wait_job(client, first["id"])["status"] == "completed"
    assert client.get("/api/chats").json()[0]["title"] is None
    follow = client.post("/api/jobs", json={"chat_id": chat_id, "question": "Follow-up question"}).json()
    assert wait_job(client, follow["id"])["status"] == "completed"
    assert seen[0] == seen[1] == {"request": "First question", "response": "TEST STUB: First question"}
    assert client.get("/api/chats").json()[0]["title"] == "Site Dust Review"


@pytest.mark.parametrize("raw,expected", [
    ('"Site Dust Review"', "Site Dust Review"),
    ("Title: Site Equipment Counting And Safety\nMore text", "Site Equipment Counting And"),
    ("**Qurilish Changini Kuzatish**", "Qurilish Changini Kuzatish"),
    ("현장 장비 분석.", "현장 장비 분석"),
])
def test_generated_titles_are_bounded_and_clean(raw, expected):
    run = {"id": "test", "request": {"question": "Q" * 3000}, "answer": "A" * 6000}
    def generate(question, content, tokens, **kwargs):
        data = json.loads(content[0]["text"])
        assert len(data["request"]) == 2000 and len(data["response"]) == 4000
        return raw, {}
    title = generate_title(run, generate)["title"]
    assert title == expected and len(title.split()) <= 4


def test_blank_title_is_rejected():
    with pytest.raises(ValueError, match="empty chat title"):
        generate_title({"id": "test", "request": {"question": "Q"}, "answer": "A"}, lambda *args, **kwargs: ("   ", {}))
