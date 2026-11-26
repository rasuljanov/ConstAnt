import json
import threading

import cv2
import numpy as np
import pytest

from backend import main
from backend.chat_titles import TITLE_SYSTEM
from backend.visual_analysis import VISUAL_SYSTEM, analyze_visuals, plan_sources, visual_evidence
from backend.media import video_sample_indexes
from test_workbench import client, raster_bytes, upload, wait_job


def observation_response(question, content, tokens, history=None, system=None):
    if system and system.startswith(TITLE_SYSTEM):
        return "Site Vehicle Counts", {}
    if system == VISUAL_SYSTEM:
        views = json.loads(content[0]["text"])["views"]
        return json.dumps({"observations": [{"unit_id": unit["unit_id"], "summary": "TEST STUB: visible vehicles.",
                                             "counts": {"car": 2, "truck": 1}, "uncertainty": "TEST STUB: boundary uncertainty."}
                                            for unit in views]}), {"input_tokens": 20}
    assert "Visual analysis evidence" in str(content)
    return "TEST STUB: Review the full scan and its estimated counts.", {"input_tokens": 30}


def test_full_raster_scan_covers_edges_and_reuses_observations_for_followups(client, tmp_path, monkeypatch):
    source = upload(client, "ortho.tif", raster_bytes(tmp_path, width=5000, height=64))
    calls = []
    def generate(*args, **kwargs):
        calls.append(kwargs.get("system"))
        return observation_response(*args, **kwargs)
    monkeypatch.setattr(main.engine, "generate", generate)
    chat_id = "a" * 32
    submitted = client.post("/api/jobs", json={"chat_id": chat_id, "asset_ids": [source["id"]], "question": "Count cars and trucks."}).json()
    job = wait_job(client, submitted["id"])
    assert job["status"] == "completed", job
    result = job["visual_result"]
    assert result["sources"][0]["sha256"] == source["sha256"]
    assert result["completed"] == result["total"] == 5
    units = result["sources"][0]["units"]
    assert [unit["region"][0] for unit in units] == [0, 1024, 2048, 3072, 4096]
    assert units[-1]["region"] == [4096, 0, 904, 64]
    assert sum(u["region"][2] * u["region"][3] for u in units) == 5000 * 64
    assert all(max(u["rendered_size"]) <= 768 for u in units)
    assert job["model_calls"] == 4 and calls.count(VISUAL_SYSTEM) == 3
    compact = json.loads(visual_evidence(result).split("\n", 1)[1])[0]
    assert compact["counts"]["car"]["estimated_visible_count"] == 10
    assert compact["counts"]["truck"]["estimated_visible_count"] == 5
    assert compact["counts"]["car"]["unreported_or_uncertain_views"] == 0
    assert "| Cars | 10 | 5 / 5 |" in job["answer"]
    assert "sources" not in client.get("/api/jobs").json()[0]["visual_result"]
    follow = client.post("/api/jobs", json={"chat_id": chat_id, "question": "What does this mean?"}).json()
    answer = wait_job(client, follow["id"])
    assert answer["status"] == "completed", answer
    assert answer["request"]["asset_ids"] == [] and answer["context_asset_ids"] == [source["id"]]
    assert answer["reused_visual_run_id"] == job["id"] and answer["model_calls"] == 1
    assert len(answer["request"]["history"]) == 2
    assert len(calls) == 6  # Five analysis calls, plus one first-reply title.
    wrong_scope = client.post("/api/report", json={"asset_ids": [], "run_ids": [answer["id"]]})
    assert wrong_scope.status_code == 422
    assert client.post("/api/report", json={"asset_ids": [source["id"]], "run_ids": [answer["id"]]}).status_code == 200


def test_multiple_small_images_respect_vllm_two_view_batches(client, monkeypatch):
    import io
    from PIL import Image
    sources = []
    for color in ("red", "green", "blue"):
        output = io.BytesIO()
        Image.new("RGB", (64, 64), color).save(output, format="PNG")
        sources.append(upload(client, color + ".png", output.getvalue())["id"])
    calls = []
    def generate(question, content, *args, **kwargs):
        views = sum(block["type"] == "image" for block in content)
        assert views <= 2
        calls.append(views)
        return observation_response(question, content, *args, **kwargs)
    monkeypatch.setattr(main.engine, "max_images", 2, raising=False)
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": sources, "question": "Compare these views."}).json()
    job = wait_job(client, submitted["id"])
    assert job["status"] == "completed", job
    assert calls == [2, 1, 0] and job["visual_result"]["completed"] == 3


def test_long_video_spans_full_duration_and_counts_are_per_frame(client, tmp_path, monkeypatch):
    path = tmp_path / "long.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 1, (64, 64))
    assert writer.isOpened()
    for i in range(181):
        writer.write(np.full((64, 64, 3), i, dtype=np.uint8))
    writer.release()
    source = upload(client, "long.avi", path.read_bytes())
    monkeypatch.setattr(main.engine, "generate", observation_response)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "Count cars in the video.", "frame_count": 6}).json()
    job = wait_job(client, submitted["id"])
    assert job["status"] == "completed", job
    video = job["visual_result"]["sources"][0]
    assert video["end"] == 181 and video["unit_count"] == 6
    timestamps = [u["timestamp_seconds"] for u in video["units"]]
    assert timestamps == sorted(timestamps) and timestamps[0] == 0 and timestamps[-1] == 180
    compact = json.loads(visual_evidence(job["visual_result"]).split("\n", 1)[1])[0]
    assert compact["counts"]["car"]["min_per_sampled_frame"] == 2
    assert compact["counts"]["car"]["max_per_sampled_frame"] == 2
    assert "estimated_visible_count" not in compact["counts"]["car"]
    assert "Min–max per sampled frame" in job["answer"] and "| Cars | 2–2 | 6 / 6 |" in job["answer"]


def test_invalid_visual_observations_are_bounded_and_not_counted(tmp_path):
    from PIL import Image
    path = tmp_path / "view.png"
    Image.new("RGB", (64, 64), "red").save(path)
    item = {"id": "a" * 32, "name": "view.png", "kind": "image", "path": path, "info": {"width": 64, "height": 64}}
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        return '{"observations":[{"unit_id":"wrong","summary":"bad","counts":{"car":99}}]}', {}
    result = analyze_visuals([item], main.JobRequest(question="Count cars."), generate, lambda r: None, lambda: False)
    assert len(calls) == 2 and result["completed"] == 1
    assert result["sources"][0]["units"][0]["status"] == "failed"
    compact = json.loads(visual_evidence(result).split("\n", 1)[1])[0]
    assert compact["counts"] == {} and compact["failed_views"] == 1


def test_stop_and_delete_guard_keep_active_files_intact(client, monkeypatch):
    source = upload(client, "notes.txt", b"Recorded flight notes.")
    entered, release = threading.Event(), threading.Event()
    def generate(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return "TEST STUB: interrupted work.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    submitted = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "Describe this."}).json()
    try:
        assert entered.wait(2)
        assert client.delete(f"/api/assets/{source['id']}").status_code == 409
        assert main.asset_path(source).is_file()
        assert client.post(f"/api/jobs/{submitted['id']}/cancel").json()["status"] == "stopping"
    finally:
        release.set()
    assert wait_job(client, submitted["id"])["status"] == "cancelled"
    assert client.delete(f"/api/assets/{source['id']}").status_code == 200
    assert not (main.ASSETS / source["id"]).exists()
    assert client.delete("/api/assets/../model-cache").status_code in (404, 405)


def test_queued_job_cancels_without_waiting_for_the_running_model(client, monkeypatch):
    source = upload(client, "notes.txt", b"Recorded notes.")
    entered, release = threading.Event(), threading.Event()
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return "TEST STUB: completed work.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    running = client.post("/api/jobs", json={"asset_ids": [source["id"]], "question": "First request."}).json()
    try:
        assert entered.wait(2)
        queued = client.post("/api/jobs", json={"question": "Waiting request."}).json()
        assert client.post(f"/api/jobs/{queued['id']}/cancel").json()["status"] == "cancelled"
        assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "cancelled"
    finally:
        release.set()
    assert wait_job(client, running["id"])["status"] == "completed"
    assert len(calls) == 1


def test_chat_context_survives_deleted_files_but_does_not_leak_to_new_chat(client, monkeypatch):
    source = upload(client, "notes.txt", b"Recorded flight notes.")
    seen = []
    def generate(question, content, tokens, history=None, **kwargs):
        if kwargs.get("system", "").startswith(TITLE_SYSTEM):
            return "Recorded Flight Notes", {}
        seen.append((content, history))
        return "TEST STUB: saved reply.", {}
    monkeypatch.setattr(main.engine, "generate", generate)
    chat_id = "b" * 32
    first = client.post("/api/jobs", json={"chat_id": chat_id, "asset_ids": [source["id"]], "question": "Review these notes."}).json()
    wait_job(client, first["id"])
    assert client.delete(f"/api/assets/{source['id']}").status_code == 200
    follow = client.post("/api/jobs", json={"chat_id": chat_id, "question": "What about that flight?"}).json()
    follow = wait_job(client, follow["id"])
    assert follow["status"] == "completed" and follow["context_missing"] == [source["id"]]
    assert seen[-1][1][0]["content"] == "Review these notes."
    assert "deleted" in str(seen[-1][0])
    report = client.post("/api/report", json={"asset_ids": [source["id"]], "run_ids": [first["id"]]})
    assert report.status_code == 200 and source["sha256"] in report.text and "Original file deleted" in report.text
    fresh = client.post("/api/jobs", json={"chat_id": "c" * 32, "question": "Hello."}).json()
    fresh = wait_job(client, fresh["id"])
    assert fresh["effective_asset_ids"] == [] and seen[-1][1] == []
    chats = client.get("/api/chats").json()
    assert {c["id"] for c in chats} == {chat_id, "c" * 32}
    assert next(c for c in chats if c["id"] == chat_id)["title"] == "Recorded Flight Notes"
    assert len(client.get(f"/api/jobs?chat_id={chat_id}").json()) == 2


def test_chat_list_keeps_history_older_than_latest_hundred_jobs(client):
    for i in range(105):
        identifier = f"{i:032x}"
        request = main.JobRequest(chat_id="d" * 32 if i == 0 else "e" * 32, question=f"Question {i}")
        main.write_json(main.JOBS / (identifier + ".json"), {"id": identifier, "created_at": f"2026-11-17T00:{i:03d}",
                        "status": "completed", "request": request.model_dump(), "answer": "TEST STUB"})
    assert len(client.get("/api/jobs").json()) == 100
    assert len(client.get("/api/chats").json()) == 2
    assert client.get("/api/jobs?chat_id=" + "d" * 32).json()[0]["request"]["question"] == "Question 0"


def test_visual_scan_stop_preserves_completed_units(tmp_path):
    path = tmp_path / "ortho.tif"
    path.write_bytes(raster_bytes(tmp_path, width=5000, height=64))
    item = {"id": "f" * 32, "name": "ortho.tif", "kind": "raster", "path": path,
            "info": {"width": 5000, "height": 64, "crs": "EPSG:32652"}}
    stopped = False
    def progress(result):
        nonlocal stopped
        stopped = result["completed"] >= 2
    result = analyze_visuals([item], main.JobRequest(question="Count cars."), observation_response, progress, lambda: stopped)
    assert result["cancelled"] and result["completed"] == 2 and result["total"] == 5
    assert sum(u.get("status") == "observed" for u in result["sources"][0]["units"]) == 2


def test_video_sampling_keeps_frames_inside_fractional_intervals():
    info = {"fps": 10, "frames": 100, "duration_seconds": 10}
    indexes = video_sample_indexes(info, 1.01, 1.39, 16)
    assert indexes.tolist() == [11, 12, 13]
    with pytest.raises(ValueError, match="No video frame"):
        video_sample_indexes(info, 1.01, 1.09, 4)


def test_video_upload_has_a_separate_streamed_size_limit(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD", 4)
    monkeypatch.setattr(main, "MAX_VIDEO_UPLOAD", 16)
    monkeypatch.setattr(main, "inspect_file", lambda path, kind: {"fps": 1, "frames": 10, "duration_seconds": 10})
    video = client.post("/api/assets", files={"file": ("site.mp4", b"12345678")})
    assert video.status_code == 201
    assert client.post("/api/assets", files={"file": ("large.mp4", b"1" * 17)}).status_code == 413
    assert client.post("/api/assets", files={"file": ("large.txt", b"12345")}).status_code == 413
