"""Real file processing and API tests; model responses are stubbed explicitly."""

import io
import logging
import threading
import time

import cv2
import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from PIL import Image
from rasterio.transform import from_origin

from backend import main
from backend.media import sample_video


@pytest.mark.parametrize("path,visible", [
    ("/api/health", False), ("/api/health?check=1", False),
    ("/api/jobs", True), ("/api/assets", True), ("/api/healthcheck", True),
])
def test_health_access_logs_are_suppressed(path, visible):
    entry = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                              '%s - "%s %s HTTP/%s" %d',
                              ("127.0.0.1:12345", "GET", path, "1.1", 200), None)
    assert logging.getLogger("uvicorn.access").filter(entry) is visible
    error = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                              "Application error", (), None)
    assert logging.getLogger("uvicorn.error").filter(error)


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("ASSETS", "JOBS", "CHATS"):
        folder = tmp_path / name
        folder.mkdir()
        monkeypatch.setattr(main, name, folder)
    monkeypatch.setattr(main, "job_slots", threading.BoundedSemaphore(3))
    with TestClient(main.app) as instance:
        yield instance


def upload(client, name, content, role="auto"):
    response = client.post("/api/assets", files={"file": (name, content)}, data={"role": role})
    assert response.status_code == 201, response.text
    return response.json()


def raster_bytes(tmp_path, width=256, height=128):
    path = tmp_path / "source.tif"
    with rasterio.open(path, "w", driver="GTiff", height=height, width=width,
                       count=3, dtype="uint16", crs="EPSG:32652",
                       transform=from_origin(500000, 4100000, 0.1, 0.1), tiled=True) as src:
        plane = np.arange(width * height, dtype=np.uint16).reshape(height, width)
        src.write(np.stack([plane, plane, plane]))
    return path.read_bytes()


def wait_job(client, identifier):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{identifier}").json()
        if job["status"] in ("completed", "failed", "cancelled") and not job.get("title_pending"):
            return job
        time.sleep(0.01)
    pytest.fail("Background job did not finish")


def test_raster_preview_crop_and_source_coordinates(client, tmp_path):
    source = upload(client, "aerial.tiff", raster_bytes(tmp_path), "orthomosaic")
    assert source["info"]["crs"] == "EPSG:32652"
    response = client.get(f"/api/assets/{source['id']}/preview")
    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.content)).size == (256, 128)
    result = client.post(f"/api/assets/{source['id']}/crops", json={"x": 32, "y": 16, "width": 64, "height": 32})
    assert result.status_code == 201, result.text
    crop = result.json()
    assert crop["info"]["parent_id"] == source["id"]
    assert crop["info"]["region"] == [32, 16, 64, 32]
    assert crop["info"]["bounds"] == pytest.approx([500003.2, 4099995.2, 500009.6, 4099998.4])
    assert client.post(f"/api/assets/{source['id']}/crops", json={"x": 250, "y": 0, "width": 64, "height": 32}).status_code == 400
    assert client.get(f"/api/assets/{source['id']}/preview?bands=99").status_code == 400
    assert len(client.get("/api/assets").json()) == 2


@pytest.mark.parametrize("extension,format_name", [(".png", "PNG"), (".jpg", "JPEG")])
def test_oversized_photos_use_bounded_raster_preview_and_crops(client, monkeypatch, extension, format_name):
    buffer = io.BytesIO()
    Image.new("RGB", (5000, 64), "green").save(buffer, format=format_name)
    original = buffer.getvalue()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100_000)
    with pytest.raises(Image.DecompressionBombError):
        Image.open(io.BytesIO(original))
    source = upload(client, "orthophoto" + extension, original, "orthomosaic")
    assert source["kind"] == "raster" and source["extension"] == extension
    assert source["info"]["width"] == 5000 and source["info"]["height"] == 64
    assert source["info"]["crs"] is None
    assert Image.MAX_IMAGE_PIXELS == 100_000
    assert client.get(f"/api/assets/{source['id']}/file").content == original
    response = client.get(f"/api/assets/{source['id']}/preview")
    assert response.status_code == 200, response.text
    assert Image.open(io.BytesIO(response.content)).size == (1280, 16)
    with pytest.raises(ValueError, match="analysis crop first"):
        main.prepare_evidence(main.JobRequest(asset_ids=[source["id"]], question="Count trucks."))
    response = client.post(f"/api/assets/{source['id']}/crops", json={"x": 4096, "y": 16, "width": 128, "height": 32})
    assert response.status_code == 201, response.text
    crop = response.json()
    assert crop["kind"] == "image" and crop["info"]["parent_id"] == source["id"]
    content, evidence = main.prepare_evidence(main.JobRequest(asset_ids=[crop["id"]], question="Count trucks."))
    assert next(part["image"] for part in content if part["type"] == "image").size == (128, 32)
    assert evidence[0]["crop"] == [4096, 16, 128, 32]


def test_small_photos_preserve_normal_image_path_and_exif_orientation(client):
    buffer = io.BytesIO()
    image = Image.new("RGB", (256, 128), "blue")
    exif = image.getexif()
    exif[274] = 6
    image.save(buffer, format="JPEG", exif=exif)
    source = upload(client, "photo.jpg", buffer.getvalue())
    assert source["kind"] == "image"
    response = client.get(f"/api/assets/{source['id']}/preview")
    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.content)).size == (128, 256)


@pytest.mark.parametrize("encoding,delimiter", [("utf-8-sig", ","), ("utf-16", "\t"), ("cp949", ",")])
def test_pm_statistics_units_invalids_and_peak(client, encoding, delimiter):
    text = delimiter.join(["timeStamp", "PM2.5 ug/m3", "Latitude", "Serial No."]) + "\n"
    text += delimiter.join(["2026-11-17T09:00:00+09:00", "12", "37.5", "123"]) + "\n"
    text += delimiter.join(["2026-11-17T09:01:00+09:00", "68", "999", "124"]) + "\n"
    text += delimiter.join(["bad-date", "bad-value", "37.5", "125"]) + "\n"
    item = upload(client, "pm.csv", text.encode(encoding), "pm")
    info = item["info"]
    assert info["rows"] == 3 and info["invalid_timestamps"] == 1
    assert info["statistics"]["PM2.5 ug/m3"] == {"count": 2, "missing_or_invalid": 1, "min": 12, "mean": 40, "max": 68}
    assert "Serial No." not in info["statistics"]
    assert info["invalid_coordinates"]["latitude"] == 1
    assert max(point["value"] for point in info["series"]) == 68
    report = client.post("/api/report", json={"asset_ids": [item["id"]]}).text
    assert item["sha256"] in report and "PM2.5 ug/m3" in report


def test_invalid_uploads_do_not_leave_assets(client, monkeypatch):
    for name, data, role in [("test.exe", b"x", "auto"), ("empty.csv", b"", "pm"),
                             ("bad.tif", b"invalid", "auto"), ("file.txt", b"x", "dem")]:
        assert client.post("/api/assets", files={"file": (name, data)}, data={"role": role}).status_code == 400
    monkeypatch.setattr(main, "MAX_UPLOAD", 4)
    assert client.post("/api/assets", files={"file": ("long.txt", b"12345")}).status_code == 413
    assert client.get("/api/assets").json() == []


def test_model_and_geometry_are_never_executed(client):
    item = upload(client, "not-actually-a-model.joblib", b"this must not be deserialized", "model")
    geometry = upload(client, "cloud.laz", b"stored without a geometry parser", "pointcloud")
    assert item["info"]["stored_only"] and geometry["info"]["stored_only"]
    assert client.post("/api/jobs", json={"asset_ids": [item["id"]], "question": "Execute this"}).status_code == 400
    assert client.get("/api/assets/not-a-valid-id/file").status_code == 404
    assert client.post("/api/assets", files={"file": ("a.txt", b"data")}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400


def test_jobs_record_evidence_metrics_and_report_scope(client, monkeypatch):
    log = upload(client, "flight.log", b"flight=F12 detector=2 trucks confidence=0.78", "log")
    seen = {}
    def fake_generate(question, content, tokens, history=None):
        seen.update(question=question, content=content)
        return "TEST STUB: two predicted trucks, not verified ground truth.", {"input_tokens": 30, "output_tokens": 15}
    monkeypatch.setattr(main.engine, "generate", fake_generate)
    response = client.post("/api/jobs", json={"asset_ids": [log["id"]], "question": "Summarize evidence"})
    assert response.status_code == 202
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "completed", job
    assert job["evidence"][0]["sha256"] == log["sha256"]
    assert job["model"]["revision"] and "system_prompt" in job
    assert log["id"] in str(seen["content"])
    assert client.get(f"/api/jobs/{job['id']}/export").status_code == 200
    report = client.post("/api/report", json={"asset_ids": [log["id"]], "run_ids": [job["id"]]})
    assert report.status_code == 200 and "TEST STUB" in report.text
    other = upload(client, "other.txt", b"unrelated source")
    assert client.post("/api/report", json={"asset_ids": [other["id"]], "run_ids": [job["id"]]}).status_code == 400
    assert client.post("/api/jobs", json={"asset_ids": [], "question": ""}).status_code == 422


def test_video_sampling_interval_and_evidence(client, tmp_path):
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 64))
    assert writer.isOpened()
    for i in range(30):
        writer.write(np.full((64, 64, 3), i * 5, dtype=np.uint8))
    writer.release()
    item = upload(client, "clip.avi", path.read_bytes())
    samples = sample_video(main.asset_path(item), 1, 2, 4)
    assert len(samples) == 4
    assert samples[0][0] >= 1 and samples[-1][0] <= 2
    assert list(t for t, _ in samples) == sorted(t for t, _ in samples)
    with pytest.raises(ValueError):
        sample_video(main.asset_path(item), 2, 4, 4)
    _, evidence = main.prepare_evidence(main.JobRequest(asset_ids=[item["id"]], question="activity?", video_start=1, video_end=2, frame_count=4))
    assert evidence[0]["sampling"]["timestamps"] == [t for t, _ in samples]


def test_failed_job_surfaces_error(client, monkeypatch):
    log = upload(client, "flight.log", b"example")
    def fail(*args, **kwargs):
        raise RuntimeError("CUDA test failure")
    monkeypatch.setattr(main.engine, "generate", fail)
    job = client.post("/api/jobs", json={"asset_ids": [log["id"]], "question": "Summarize"}).json()
    result = wait_job(client, job["id"])
    assert result["status"] == "failed" and result["error"] == "CUDA test failure"


def test_large_rasters_require_crops(client, tmp_path):
    source = upload(client, "wide.tiff", raster_bytes(tmp_path, width=5000, height=32))
    with pytest.raises(ValueError, match="crop first"):
        main.prepare_evidence(main.JobRequest(asset_ids=[source["id"]], question="count?"))


def test_wind_direction_uses_circular_mean(client):
    item = upload(client, "wind.csv", b"wind_Direction degrees,PM2.5\n359,10\n1,20\n", "pm")
    stats = item["info"]["statistics"]["wind_Direction degrees"]
    assert min(abs(stats["mean"]), abs(stats["mean"] - 360)) < 1e-6
    assert "circular" in stats["mean_method"]
    report = client.post("/api/report", json={"asset_ids": [item["id"]]})
    assert report.status_code == 200 and "(circular)" in report.text


def test_polling_does_not_race_atomic_run_writes(tmp_path):
    path = tmp_path / "run.json"
    main.write_json(path, {"step": 0})
    errors = []
    def read_repeatedly():
        try:
            for _ in range(100):
                assert isinstance(main.record(path)["step"], int)
        except Exception as exc:
            errors.append(exc)
    reader = threading.Thread(target=read_repeatedly)
    reader.start()
    for step in range(30):
        main.write_json(path, {"step": step})
    reader.join()
    assert not errors
