"""Small Streamlit-only model library used by the UI skeleton.

This module does **not** parse SBML or call ShapCRN. It only keeps the raw files
that the user selected so the interface can support multiple models at once.

When you implement the real loader, use the active model bytes exposed through
``st.session_state['shapcrn_model_bytes']`` and keep the scientific logic in
``logic/model.py``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

import streamlit as st

MODEL_LIBRARY_KEY = "shapcrn_model_library"
ACTIVE_MODEL_KEY = "shapcrn_active_model_id"
UPLOAD_BATCH_KEY = "_shapcrn_upload_batch_ids"
UPLOAD_GENERATION_FRESH_KEY = "_shapcrn_upload_generation_fresh"
UPLOAD_WIDGET_KEY = "shapcrn_model_upload_queue"


def ensure_model_library() -> dict[str, dict[str, Any]]:
    """Create the persistent raw-file registry used by the UI shell."""
    if MODEL_LIBRARY_KEY not in st.session_state:
        st.session_state[MODEL_LIBRARY_KEY] = {}
    if UPLOAD_BATCH_KEY not in st.session_state:
        st.session_state[UPLOAD_BATCH_KEY] = []
    if UPLOAD_GENERATION_FRESH_KEY not in st.session_state:
        st.session_state[UPLOAD_GENERATION_FRESH_KEY] = True
    _repair_active_model()
    _sync_compatibility_keys()
    return st.session_state[MODEL_LIBRARY_KEY]


def begin_uploader_generation() -> None:
    """Mark a recreated uploader as a new batch without deleting saved models.

    Streamlit may discard page-local widget state while the user visits another
    page. The independent model library must survive that cleanup. When the
    uploader comes back, its first new file is therefore *added* to the library
    rather than interpreted as a replacement for files uploaded previously.
    """
    ensure_model_library()
    if UPLOAD_WIDGET_KEY not in st.session_state:
        st.session_state[UPLOAD_BATCH_KEY] = []
        st.session_state[UPLOAD_GENERATION_FRESH_KEY] = True


def sync_uploaded_models(uploaded_files: Iterable[Any] | None) -> None:
    """Merge the current multi-file uploader batch into the model library.

    Behaviour:
    - pressing Streamlit's ``+`` adds files to the current batch;
    - pressing the uploader ``×`` removes that file from the current batch;
    - models uploaded in an earlier page visit remain in the library;
    - the newest newly-added model becomes active.
    """
    ensure_model_library()
    library = st.session_state[MODEL_LIBRARY_KEY]
    files = list(uploaded_files or [])
    previous_batch = list(st.session_state.get(UPLOAD_BATCH_KEY, []))
    fresh_generation = bool(st.session_state.get(UPLOAD_GENERATION_FRESH_KEY, True))

    current_ids: list[str] = []
    newly_added_ids: list[str] = []

    for uploaded in files:
        raw = uploaded.getvalue()
        model_id = _model_id(raw)
        current_ids.append(model_id)
        if model_id not in library:
            newly_added_ids.append(model_id)
        library[model_id] = {
            "id": model_id,
            "name": uploaded.name,
            "bytes": raw,
            "size": len(raw),
            "mime": getattr(uploaded, "type", None),
        }

    # Only files belonging to the *current uploader generation* are removed by
    # its × buttons. Older library entries may not be represented by a recreated
    # page-local uploader and must therefore be preserved.
    if not fresh_generation:
        for model_id in previous_batch:
            if model_id not in current_ids:
                library.pop(model_id, None)

    if files:
        st.session_state[UPLOAD_GENERATION_FRESH_KEY] = False
        st.session_state[UPLOAD_BATCH_KEY] = current_ids
    elif not fresh_generation:
        # The user explicitly removed the last file from this live uploader.
        for model_id in previous_batch:
            library.pop(model_id, None)
        st.session_state[UPLOAD_BATCH_KEY] = []

    if newly_added_ids:
        st.session_state[ACTIVE_MODEL_KEY] = newly_added_ids[-1]

    _repair_active_model()
    _sync_compatibility_keys()


def set_active_model(model_id: str | None) -> None:
    ensure_model_library()
    library = st.session_state[MODEL_LIBRARY_KEY]
    st.session_state[ACTIVE_MODEL_KEY] = model_id if model_id in library else None
    _repair_active_model()
    _sync_compatibility_keys()


def remove_model(model_id: str) -> None:
    ensure_model_library()
    library = st.session_state[MODEL_LIBRARY_KEY]
    library.pop(model_id, None)

    batch = list(st.session_state.get(UPLOAD_BATCH_KEY, []))
    if model_id in batch:
        st.session_state[UPLOAD_BATCH_KEY] = [
            item for item in batch if item != model_id
        ]

    _repair_active_model()
    _sync_compatibility_keys()


def get_active_model() -> dict[str, Any] | None:
    ensure_model_library()
    active_id = st.session_state.get(ACTIVE_MODEL_KEY)
    if active_id is None:
        return None
    return st.session_state[MODEL_LIBRARY_KEY].get(active_id)


def _repair_active_model() -> None:
    library = st.session_state.get(MODEL_LIBRARY_KEY, {})
    active_id = st.session_state.get(ACTIVE_MODEL_KEY)
    if active_id not in library:
        st.session_state[ACTIVE_MODEL_KEY] = (
            next(reversed(library), None) if library else None
        )


def _sync_compatibility_keys() -> None:
    """Keep the old single-model keys pointing at the currently active model."""
    library = st.session_state.get(MODEL_LIBRARY_KEY, {})
    active_id = st.session_state.get(ACTIVE_MODEL_KEY)
    active = library.get(active_id) if active_id else None
    if active is None:
        st.session_state.pop("shapcrn_model_bytes", None)
        st.session_state.pop("shapcrn_model_name", None)
        return
    st.session_state["shapcrn_model_bytes"] = active["bytes"]
    st.session_state["shapcrn_model_name"] = active["name"]


def _model_id(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
