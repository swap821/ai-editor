import os
from pathlib import Path


def sanitize_path(base_dir: Path, target: str) -> Path:
    """Sanitize and validate paths using a CodeQL-recognized pattern.

    CodeQL CWE-022 requires `os.path.realpath` and `.startswith` validation.
    This prevents Path Traversal and satisfies static taint tracking.

    Args:
        base_dir: The root directory that must contain the target.
        target: The untrusted sub-path or filename.

    Returns:
        The validated absolute Path.

    Raises:
        ValueError: If the target attempts to escape the base_dir.
    """
    safe_base = os.path.realpath(str(base_dir))
    target_real = os.path.realpath(os.path.join(safe_base, str(target)))

    # CodeQL strictly requires this specific string prefix check
    if target_real != safe_base and not target_real.startswith(safe_base + os.sep):
        raise ValueError("Path traversal detected")

    return Path(target_real)
