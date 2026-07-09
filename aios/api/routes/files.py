import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from aios import config

router = APIRouter(tags=["Files"])

class ReadFileRequest(BaseModel):
    path: str = Field(..., description="Absolute path to the file to read")

class EditFileRequest(BaseModel):
    path: str = Field(..., description="Absolute path to the file to edit")
    content: str = Field(..., description="Proposed new content")
    # This hits the gate, so we just stub it out as a proposal here for Phase 1.
    
def _build_tree(root_dir: Path) -> List[Dict[str, Any]]:
    tree = []
    try:
        for entry in os.scandir(root_dir):
            if entry.name.startswith('.') or entry.name == '__pycache__' or entry.name == 'node_modules':
                continue
            node = {
                "name": entry.name,
                "path": str(Path(entry.path).resolve()).replace('\\', '/'),
                "type": "directory" if entry.is_dir() else "file",
                "status": "normal"
            }
            if entry.is_dir():
                # Don't recurse deeply to avoid massive payloads, just one level or handle carefully
                # We'll just do shallow children for directories that we expand
                node["children"] = []
            tree.append(node)
    except Exception as e:
        pass
    
    return sorted(tree, key=lambda x: (x["type"] == "file", x["name"]))

@router.get("/api/v1/files/tree")
def get_file_tree(root: Optional[str] = None):
    """Returns the AST structure of the workspace."""
    base_dir = Path(root) if root else Path(config.PROJECT_ROOT)
    if not base_dir.exists() or not base_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    
    return _build_tree(base_dir)

@router.post("/api/v1/files/read")
def read_file(req: ReadFileRequest):
    """Returns file content."""
    p = Path(req.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        content = p.read_text(encoding='utf-8')
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/v1/files/edit")
def edit_file(req: EditFileRequest):
    """Proposes diff, hits gate."""
    # In Phase 1, we just return success to simulate proposing an edit
    return {"status": "proposed", "message": "Edit proposed for approval."}
