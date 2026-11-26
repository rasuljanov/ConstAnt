import io

from PIL import Image

from backend import main
from test_workbench import client, upload


def test_table_viewer_returns_actual_paginated_rows_and_validates_limits(client):
    source = upload(client, "flight.csv", b"timeStamp,PM2.5\n2025-03-26 11:00:00,10\n2025-03-26 11:01:00,80\n")
    path = f"/api/assets/{source['id']}/content"
    first = client.get(path + "?limit=1").json()
    assert first["rows"] == [{"timeStamp": "2025-03-26 11:00:00", "PM2.5": 10}]
    assert first["total"] == 2 and first["next_offset"] == 1
    second = client.get(path + "?offset=1&limit=1").json()
    assert second["rows"][0]["PM2.5"] == 80 and second["next_offset"] is None
    for suffix in ("?offset=-1", "?limit=0", "?limit=101"):
        assert client.get(path + suffix).status_code == 422
    assert client.get("/api/assets/invalid/content").status_code == 404


def test_log_viewer_pages_text_and_never_serves_it_as_executable_html(client):
    text = "<script>alert(1)</script>" + "x" * 13_000
    source = upload(client, "notes.txt", text.encode())
    path = f"/api/assets/{source['id']}/content"
    first = client.get(path)
    assert first.headers["content-type"].startswith("application/json")
    assert first.json()["text"] == text[:12_000]
    assert client.get(path + "?offset=12000").json()["text"] == text[12_000:]
    assert client.get(f"/api/assets/{source['id']}/media").status_code == 400


def test_media_is_inline_and_supports_range_requests_without_changing_downloads(client):
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, format="PNG")
    source = upload(client, "photo.png", buffer.getvalue())
    path = f"/api/assets/{source['id']}"
    inline = client.get(path + "/media")
    assert inline.headers["content-type"] == "image/png"
    assert inline.headers["content-disposition"].startswith("inline;")
    assert inline.headers["x-content-type-options"] == "nosniff"
    head = client.head(path + "/media")
    assert head.status_code == 200 and head.content == b""
    assert head.headers["content-type"] == "image/png"
    assert int(head.headers["content-length"]) == len(buffer.getvalue())
    ranged = client.get(path + "/media", headers={"Range": "bytes=0-7"})
    assert ranged.status_code == 206 and ranged.content == buffer.getvalue()[:8]
    assert client.get(path + "/file").headers["content-disposition"].startswith("attachment;")
    assert client.get(path + "/content").status_code == 400


def test_video_media_uses_playable_mime_and_byte_ranges(client, monkeypatch):
    monkeypatch.setattr(main, "inspect_file", lambda *_: {"duration_seconds": 10})
    source = upload(client, "site.mp4", b"TEST FIXTURE: not a decodable video")
    response = client.get(f"/api/assets/{source['id']}/media", headers={"Range": "bytes=5-11"})
    assert response.status_code == 206 and response.headers["content-type"] == "video/mp4"
    assert response.content == b"FIXTURE"
