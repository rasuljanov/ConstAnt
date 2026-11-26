from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.inference import REVISION, SYSTEM, build_messages
from backend.inference import QwenEngine
from backend.table_queries import PLANNER_SYSTEM


def test_all_roles_use_content_blocks_without_changing_history_or_images():
    image = Image.new("RGB", (64, 64), "red")
    content = [{"type": "text", "text": "Source [test-image]"}, {"type": "image", "image": image}]
    history = [{"role": "user", "content": "What was the PM2.5 peak?"},
               {"role": "assistant", "content": "48 micrograms per cubic metre."}]
    messages = build_messages("Describe this view.", content, history)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert all(isinstance(m["content"], list) for m in messages)
    assert messages[0]["content"] == [{"type": "text", "text": SYSTEM}]
    assert messages[1]["content"] == [{"type": "text", "text": history[0]["content"]}]
    assert messages[-1]["content"][1]["image"] is image
    assert messages[-1]["content"][-1] == {"type": "text", "text": "Describe this view."}
    assert len(content) == 2 and isinstance(history[0]["content"], str)


def test_planner_uses_short_system_prompt_without_changing_normal_chat():
    messages = build_messages("Mean PM2.5?", [], system=PLANNER_SYSTEM)
    assert messages[0]["content"][0]["text"] == PLANNER_SYSTEM
    assert len(PLANNER_SYSTEM) < len(SYSTEM) / 5
    assert build_messages("Describe this image.", [])[0]["content"][0]["text"] == SYSTEM


def test_legacy_collection_labels_are_not_reintroduced_through_history():
    history = [{"role": "assistant", "content": "A recorded peak. [Selected tables]"}]
    messages = build_messages("When was it recorded?", [], history)
    assert messages[1]["content"][0]["text"] == "A recorded peak."
    assert history[0]["content"].endswith("[Selected tables]")


@pytest.fixture(scope="module")
def cached_processor():
    pytest.importorskip("transformers")
    from transformers import AutoProcessor

    root = Path(__file__).resolve().parents[2]
    snapshot = root / "data" / "model-cache" / "models--Qwen--Qwen3-VL-4B-Instruct" / "snapshots" / REVISION
    if not (snapshot / "tokenizer_config.json").exists():
        pytest.skip("Optional integration check requires the locally cached Qwen processor.")
    return AutoProcessor.from_pretrained(str(snapshot), local_files_only=True)


@pytest.mark.parametrize("with_image", [False, True])
@pytest.mark.parametrize("with_history", [False, True])
def test_real_cached_processor_accepts_text_images_and_followups(cached_processor, with_image, with_history):
    content = [{"type": "text", "text": "Source [test]: PM2.5 peak = 48."}]
    if with_image:
        content.append({"type": "image", "image": Image.new("RGB", (64, 64), "red")})
    history = [{"role": "user", "content": "Which measurement?"},
               {"role": "assistant", "content": "PM2.5."}] if with_history else []
    inputs = cached_processor.apply_chat_template(
        build_messages("Explain the evidence.", content, history),
        tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
    assert inputs.input_ids.ndim == 2 and inputs.input_ids.shape[-1] > 0
    assert inputs.input_ids.device.type == "cpu"
    if with_image:
        assert "pixel_values" in inputs and inputs["image_grid_thw"].shape[0] == 1


def test_long_history_drops_old_pairs_preserving_question_and_recent_context(cached_processor, monkeypatch):
    import torch
    engine = QwenEngine("unused-test-cache")
    engine.processor = cached_processor
    seen = []
    class Model:
        device = "cpu"
        config = SimpleNamespace(image_token_id=151655, video_token_id=151656)
        def generate(self, input_ids, **kwargs):
            seen.append(cached_processor.tokenizer.decode(input_ids[0]))
            return torch.cat([input_ids, torch.tensor([[1]])], dim=1)
    engine.model = Model()
    monkeypatch.setattr(engine, "load", lambda: None)
    for name in ("synchronize", "reset_peak_memory_stats", "empty_cache"):
        monkeypatch.setattr(torch.cuda, name, lambda: None)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 0)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda: "TEST STUB CPU")
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn{i} " + "pm " * 1500} for i in range(6)]
    _, metrics = engine.generate("What does the latest turn mean?", [{"type": "text", "text": "Current evidence."}], 64, history=history)
    assert metrics["history_turns_omitted"] >= 2 and metrics["history_turns_used"] >= 2
    assert "turn0" not in seen[0] and "turn5" in seen[0] and "What does the latest turn mean?" in seen[0]
    assert len(history) == 6 and metrics["input_tokens"] + 64 <= 6144
