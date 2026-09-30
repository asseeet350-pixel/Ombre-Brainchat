import hmac
import os
import re

from starlette.requests import Request
from starlette.responses import Response

from . import _shared as sh
from utils import strip_wikilinks


def register(mcp):

    @mcp.custom_route("/api/bucket-preview/{bucket_id}", methods=["GET"])
    async def api_bucket_preview(request: Request) -> Response:
        from starlette.responses import JSONResponse

        configured = os.environ.get("OMBRE_MCP_SERVICE_TOKEN", "").strip()
        auth = request.headers.get("Authorization", "")
        supplied = auth[7:].strip() if auth.startswith("Bearer ") else ""

        if len(configured) < 32 or len(supplied) != len(configured) or not hmac.compare_digest(supplied, configured):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        bucket_id = str(request.path_params.get("bucket_id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", bucket_id):
            return JSONResponse({"error": "invalid id"}, status_code=400)

        bucket = await sh.bucket_mgr.get(bucket_id)
        if not bucket or (bucket.get("metadata") or {}).get("deleted_at"):
            return JSONResponse({"error": "not found"}, status_code=404)

        source = strip_wikilinks(str(bucket.get("content") or ""))
        all_lines = [line.strip() for line in source.splitlines() if line.strip()]
        lines = all_lines[:7]

        return JSONResponse({
            "id": str(bucket.get("id") or bucket_id),
            "preview": "\n".join(lines)[:1400],
            "lineCount": len(lines),
            "truncated": len(all_lines) > len(lines),
        })

    @mcp.custom_route("/api/bucket-map", methods=["GET"])
    async def api_bucket_map(request: Request) -> Response:
        from starlette.responses import JSONResponse

        configured = os.environ.get("OMBRE_MCP_SERVICE_TOKEN", "").strip()
        auth = request.headers.get("Authorization", "")
        supplied = auth[7:].strip() if auth.startswith("Bearer ") else ""

        if len(configured) < 32 or len(supplied) != len(configured) or not hmac.compare_digest(supplied, configured):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            all_buckets = await sh.bucket_mgr.list_all(include_archive=True)
            stars = []
            stats = {"pinned": 0, "dynamic": 0, "archived": 0}

            for b in all_buckets:
                meta = b.get("metadata", {})
                if meta.get("deleted_at"):
                    continue

                btype = meta.get("type", "dynamic")

                if meta.get("pinned") or btype == "permanent":
                    stats["pinned"] += 1
                elif btype == "archive":
                    stats["archived"] += 1
                else:
                    stats["dynamic"] += 1

                stars.append({
                    "id": b["id"],
                    "name": meta.get("name", b["id"]),
                    "type": btype,
                    "domain": meta.get("domain", []),
                    "tags": meta.get("tags", []),
                    "valence": meta.get("valence", 0.5),
                    "arousal": meta.get("arousal", 0.3),
                    "importance": meta.get("importance", 5),
                    "resolved": meta.get("resolved", False),
                    "pinned": meta.get("pinned", False),
                    "created_at": meta.get("created", ""),
                    "last_active": meta.get("last_active", ""),
                    "activation_count": meta.get("activation_count", 0),
                    "score": sh.decay_engine.calculate_score(meta),
                })

            stars.sort(key=lambda x: x["score"], reverse=True)

            return JSONResponse({
                "stats": stats,
                "total": len(stars),
                "stars": stars[:800],
            })

        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
