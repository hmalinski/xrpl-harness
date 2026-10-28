"""xrpl-explain: decode an XRPL transaction result into a typed state diff + a plain-language explanation."""
from .explain import explain, render, Explanation
from .diff import decode_meta, StateDiff, ObjectChange, FieldChange
from .results import explain_result

__all__ = [
    "explain", "render", "Explanation",
    "decode_meta", "StateDiff", "ObjectChange", "FieldChange",
    "explain_result",
]
__version__ = "0.0.1"
