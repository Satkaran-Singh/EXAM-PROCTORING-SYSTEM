"""
Small helper to auto-download MediaPipe Tasks model files on first run,
the same way `ultralytics` auto-downloads YOLO weights.

MediaPipe's new Tasks API (0.10.15+) no longer bundles models inside the
pip package (the old `mp.solutions` API is gone as of these versions) --
model files are fetched from Google's model store instead.
"""

import os
import urllib.request

MODELS_DIR = "models"


def ensure_model(filename: str, url: str) -> str:
    """Downloads the model file into MODELS_DIR if not already present.
    Returns the local path to use with BaseOptions(model_asset_path=...)."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    local_path = os.path.join(MODELS_DIR, filename)

    if not os.path.exists(local_path):
        print(f"Downloading model '{filename}' (first run only)...")
        urllib.request.urlretrieve(url, local_path)
        print(f"Saved to {local_path}")

    return local_path
