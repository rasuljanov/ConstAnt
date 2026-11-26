"""Tests never open or recover the user's live upload/job directory."""

import atexit
import os
import tempfile

runtime = tempfile.TemporaryDirectory(prefix="const-vlm-tests-")
os.environ["CONST_VLM_DATA"] = runtime.name
os.environ["CONST_VLM_ENGINE"] = "transformers"
atexit.register(runtime.cleanup)
