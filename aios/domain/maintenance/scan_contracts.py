"""Contracts for bounded maintenance scans."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BoundedScanContract(BaseModel):
    """Resource boundaries for executing a maintenance scanner."""
    model_config = ConfigDict(frozen=True)
    
    allowed_root: str
    max_files: int
    max_total_bytes: int
    max_file_bytes: int
    deadline: int  # milliseconds or seconds timestamp
    max_findings: int
    
    # Strictly enforced safety limits
    network_allowed: Literal[False] = Field(default=False)
    git_history_allowed: bool
