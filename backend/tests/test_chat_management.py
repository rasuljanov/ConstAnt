import pytest

from backend import main
from test_workbench import client, upload


def seed_chat(identifier, title, created, asset_ids=None, status="completed"):
    run_id = ("1" if identifier == "a" * 32 else "2") * 32
    request = main.JobRequest(chat_id=identifier, question=title, asset_ids=asset_ids or [])
    main.write_json(main.JOBS / (run_id + ".json"), {"id": run_id, "created_at": created,
                    "status": status, "request": request.model_dump(), "answer": "TEST STUB"})
    return run_id


def test_rename_and_pin_persist_without_changing_messages(client):
    first, second = "a" * 32, "b" * 32
    run_id = seed_chat(first, "Original question", "2026-11-17T01:00:00Z")
    seed_chat(second, "Newer chat", "2026-11-17T02:00:00Z")
    assert client.get("/api/chats").json()[0]["id"] == second
    updated = client.patch(f"/api/chats/{first}", json={"title": "  Site review  ", "pinned": True})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Site review" and updated.json()["pinned"]
    assert client.get("/api/chats").json()[0]["id"] == first
    assert main.record(main.JOBS / (run_id + ".json"))["request"]["question"] == "Original question"
    assert main.record(main.CHATS / (first + ".json"))["title"] == "Site review"
    client.patch(f"/api/chats/{first}", json={"pinned": False})
    assert client.get("/api/chats").json()[0]["id"] == second
    assert next(c for c in client.get("/api/chats").json() if c["id"] == first)["title"] == "Site review"


@pytest.mark.parametrize("update", [{}, {"title": " "}, {"title": None}, {"title": "x" * 121}, {"pinned": None}, {"pinned": "false"}, {"unknown": True}])
def test_invalid_chat_changes_are_rejected(client, update):
    seed_chat("a" * 32, "Original", "1")
    assert client.patch("/api/chats/" + "a" * 32, json=update).status_code == 422
    assert not list(main.CHATS.glob("*.json"))


def test_delete_chat_removes_only_its_history_and_metadata(client):
    source = upload(client, "notes.txt", b"Keep this original file.")
    first, second = "a" * 32, "b" * 32
    run_id = seed_chat(first, "Delete this chat", "1", [source["id"]])
    other = seed_chat(second, "Keep this chat", "2")
    client.patch(f"/api/chats/{first}", json={"pinned": True})
    assert client.delete(f"/api/chats/{first}").status_code == 200
    assert not (main.JOBS / (run_id + ".json")).exists()
    assert not (main.CHATS / (first + ".json")).exists()
    assert (main.JOBS / (other + ".json")).is_file()
    assert main.asset_path(source).read_bytes() == b"Keep this original file."
    assert client.delete(f"/api/chats/{first}").status_code == 404


def test_active_chat_cannot_be_deleted_but_can_be_renamed(client):
    run_id = seed_chat("a" * 32, "Running chat", "1", status="running")
    assert client.delete("/api/chats/" + "a" * 32).status_code == 409
    assert (main.JOBS / (run_id + ".json")).exists()
    assert client.patch("/api/chats/" + "a" * 32, json={"title": "Renamed while running"}).status_code == 200
    assert client.patch("/api/chats/not-an-id", json={"title": "Invalid"}).status_code == 404
