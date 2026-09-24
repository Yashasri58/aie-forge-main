"""
Cache API Routes

Endpoints for the demo cache:
  GET  /cache              — list all entries
  GET  /cache/stats        — summary counts
  GET  /cache/{id}         — fetch one entry (input + output)
  DELETE /cache/{id}       — delete one entry
  DELETE /cache            — clear all (or ?type=impact|codegen|reverse_engineer)
  POST /cache/{id}/label   — rename label
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/cache", tags=["cache"])

# Injected by main.py
_cache = None


def set_cache(c):
    global _cache
    _cache = c


# ─── Models ──────────────────────────────────────────────────────────────────

class LabelRequest(BaseModel):
    label: str


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_cache(type: Optional[str] = Query(None, description="Filter by pipeline_type")):
    """List all cached demo entries."""
    if not _cache:
        return []
    entries = _cache.list(pipeline_type=type)
    # Omit large output blob from list view — only return metadata
    return [
        {
            "id":            e["id"],
            "pipeline_type": e["pipeline_type"],
            "label":         e["label"],
            "created_at":    e["created_at"],
            "last_used_at":  e["last_used_at"],
            "use_count":     e["use_count"],
            "has_output":    bool(e.get("output")),
            "token_usage":   e.get("token_usage", {}),
        }
        for e in entries
    ]


@router.get("/stats")
async def cache_stats():
    """Return cache summary statistics."""
    if not _cache:
        return {"total": 0, "by_type": {}}
    return _cache.stats()


@router.get("/{cache_id}")
async def get_cache_entry(cache_id: str):
    """Fetch a single cache entry including full input and output."""
    if not _cache:
        raise HTTPException(status_code=503, detail="Cache not initialised")
    entry = _cache.get(cache_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Cache entry {cache_id!r} not found")
    return entry


@router.delete("/{cache_id}")
async def delete_cache_entry(cache_id: str):
    """Delete a single cache entry."""
    if not _cache:
        raise HTTPException(status_code=503, detail="Cache not initialised")
    deleted = _cache.delete(cache_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Cache entry {cache_id!r} not found")
    return {"status": "deleted", "id": cache_id}


@router.delete("")
async def clear_cache(type: Optional[str] = Query(None, description="Pipeline type to clear")):
    """Clear all (or filtered) cache entries."""
    if not _cache:
        raise HTTPException(status_code=503, detail="Cache not initialised")
    count = _cache.clear(pipeline_type=type)
    return {"status": "cleared", "count": count}


@router.post("/{cache_id}/label")
async def rename_label(cache_id: str, request: LabelRequest):
    """Rename the label of a cache entry."""
    if not _cache:
        raise HTTPException(status_code=503, detail="Cache not initialised")
    entry = _cache.get(cache_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Cache entry {cache_id!r} not found")
    # Re-save with updated label (input/output unchanged)
    _cache.save(
        cache_id=cache_id,
        pipeline_type=entry["pipeline_type"],
        label=request.label,
        input_data=entry["input"],
        output_data=entry["output"],
    )
    return {"status": "updated", "id": cache_id, "label": request.label}
