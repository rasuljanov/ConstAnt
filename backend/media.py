"""Bounded previews, raster windows, and timestamped video samples."""

from io import BytesIO
import os
import math
from pathlib import Path

import cv2
import numpy as np
import rasterio
from PIL import Image, ImageOps
from rasterio.enums import Resampling
from rasterio.windows import Window, bounds

# PostGIS can set a global PROJ path incompatible with Rasterio's bundled GDAL.
_proj_data = Path(rasterio.__file__).parent / "proj_data"
if _proj_data.is_dir():
    from rasterio._env import set_proj_data_search_path
    os.environ["PROJ_DATA"] = os.environ["PROJ_LIB"] = str(_proj_data)
    set_proj_data_search_path(str(_proj_data))
_gdal_data = Path(rasterio.__file__).parent / "gdal_data"
if _gdal_data.is_dir():
    os.environ["GDAL_DATA"] = str(_gdal_data)


def raster_info(path: Path) -> dict:
    with rasterio.open(path) as src:
        return {
            "width": src.width, "height": src.height, "bands": src.count,
            "dtype": src.dtypes[0], "crs": str(src.crs) if src.crs else None,
            "bounds": list(src.bounds), "transform": list(src.transform)[:6],
            "color_interpretation": [c.name for c in src.colorinterp],
            "nodata": str(src.nodata), "block_shapes": src.block_shapes,
        }


def raster_image(path: Path, region=None, bands=None, max_edge=1280):
    with rasterio.open(path) as src:
        window = Window(*(region or [0, 0, src.width, src.height]))
        if (window.col_off < 0 or window.row_off < 0 or window.width < 1
                or window.height < 1 or window.col_off + window.width > src.width
                or window.row_off + window.height > src.height):
            raise ValueError("Crop must fit inside the source raster.")
        bands = bands or ([1, 2, 3] if src.count >= 3 else [1])
        if len(bands) not in (1, 3) or min(bands) < 1 or max(bands) > src.count:
            raise ValueError("Choose one band or three RGB bands present in the raster.")
        scale = min(1, max_edge / max(window.width, window.height))
        height, width = max(1, round(window.height * scale)), max(1, round(window.width * scale))
        data = src.read(bands, window=window, out_shape=(len(bands), height, width),
                        masked=True, resampling=Resampling.nearest)
        rgb = []
        for channel in data:
            values = channel.compressed()
            values = values[np.isfinite(values)]
            output = np.zeros(channel.shape, dtype=np.uint8)
            if values.size:
                low, high = (0, 255) if channel.dtype == np.uint8 else np.percentile(values, [2, 98])
                if high > low:
                    filled = np.nan_to_num(channel.filled(float(low)).astype(float), nan=low)
                    output = np.clip((filled - low) * 255 / (high - low), 0, 255).astype(np.uint8)
            rgb.append(output)
        if len(rgb) == 1:
            rgb *= 3
        details = {"region": [int(v) for v in (window.col_off, window.row_off, window.width, window.height)],
                   "bands": bands, "bounds": list(bounds(window, src.transform)),
                   "crs": str(src.crs) if src.crs else None,
                   "source_transform": list(src.window_transform(window))[:6],
                   "rendered_size": [width, height],
                   "display_stretch": "uint8 unchanged; other types per-band 2–98 percentile"}
        return Image.fromarray(np.stack(rgb, axis=-1)), details


def ordinary_image(path: Path, max_edge=1280):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((max_edge, max_edge))
        return image


def png_bytes(image: Image.Image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def video_info(path: Path):
    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not capture.isOpened() or not np.isfinite(fps) or fps <= 0 or frames < 1:
            raise ValueError("Video cannot be decoded. Try an MP4/H.264 or AVI file.")
        return {"fps": fps, "frames": frames, "duration_seconds": frames / fps,
                "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    finally:
        capture.release()


def video_sample_indexes(info, start, end, count):
    if start < 0 or end <= start or end > info["duration_seconds"] + 0.01:
        raise ValueError("Choose a valid video interval inside the clip.")
    if not 1 <= count <= 120:
        raise ValueError("Choose between 1 and 120 sampled frames.")
    first, last = math.ceil(start * info["fps"]), min(info["frames"] - 1, math.floor(end * info["fps"]))
    if first > last:
        raise ValueError("No video frame falls within this interval. Select a wider range.")
    return np.unique(np.linspace(first, last, count).astype(int))


def iter_video_samples(path: Path, start: float, end: float, count: int, max_edge=640):
    info = video_info(path)
    indexes = video_sample_indexes(info, start, end, count)
    # shortcut: ordered images represent video; add native video tokens for temporal-model comparisons.
    capture = cv2.VideoCapture(str(path))
    try:
        for index in indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Could not decode video frame {index}. Re-encode the clip.")
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((max_edge, max_edge))
            yield round(index / info["fps"], 3), image
    finally:
        capture.release()


def sample_video(path: Path, start: float, end: float, count: int, max_edge=640):
    return list(iter_video_samples(path, start, end, count, max_edge))
