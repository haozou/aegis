"""File upload and serve routes."""

from __future__ import annotations

import mimetypes
import pathlib
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from ...auth.dependencies import get_current_user
from ...auth.models import User
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["files"])

UPLOAD_ROOT = pathlib.Path("data/uploads")
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming large files


@router.post("/files", status_code=201)
async def upload_file(
    file: UploadFile,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload a file (image, PDF, video, audio, text, etc.) and return its file_id.

    Files are streamed to disk in chunks — no file size limit.
    """
    file_id = uuid.uuid4().hex
    filename = file.filename or "upload"
    media_type = file.content_type or "application/octet-stream"

    # Sanitise filename — strip any path components
    filename = pathlib.Path(filename).name or "upload"

    upload_dir = UPLOAD_ROOT / user.id
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / f"{file_id}_{filename}"

    # Stream to disk in chunks so large video files don't exhaust memory
    total_bytes = 0
    with open(dest, "wb") as fh:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            fh.write(chunk)
            total_bytes += len(chunk)

    logger.info(
        "File uploaded",
        file_id=file_id,
        filename=filename,
        media_type=media_type,
        size=total_bytes,
        user_id=user.id,
    )

    return {
        "file_id": file_id,
        "filename": filename,
        "media_type": media_type,
        "size": total_bytes,
    }


async def _resolve_user_from_token(request: Request, token: str | None) -> User:
    """Resolve user from query-string token (for browser downloads)."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization")
    jwt_secret: str = request.app.state.jwt_secret
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        # Minimal User object — only need id for file lookup
        return User(id=user_id, username="", email="", created_at="", updated_at="")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/files/{file_id}")
async def serve_file(
    file_id: str,
    request: Request,
    token: str | None = Query(default=None),
) -> FileResponse:
    """Return the raw bytes of a previously uploaded file.

    Supports auth via:
    - Authorization: Bearer <token> header
    - ?token=<jwt> query parameter (for browser download links)
    """
    # Try header auth first, fall back to query token
    resolved_user: User | None = None

    # Check Authorization header
    auth_header = request.headers.get("authorization", "")
    header_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
    effective_token = header_token or token

    if not effective_token:
        raise HTTPException(status_code=401, detail="Missing authorization")

    resolved_user = await _resolve_user_from_token(request, effective_token)

    # Search across all user directories for the file
    # (tool-generated files may be in a different user's dir)
    matches: list[pathlib.Path] = []

    # Check the user's own directory first
    user_dir = UPLOAD_ROOT / resolved_user.id
    if user_dir.exists():
        matches = list(user_dir.glob(f"{file_id}_*"))

    # If not found, search all directories (for tool-generated files)
    if not matches and UPLOAD_ROOT.exists():
        for sub in UPLOAD_ROOT.iterdir():
            if sub.is_dir():
                found = list(sub.glob(f"{file_id}_*"))
                if found:
                    matches = found
                    break

    if not matches:
        raise HTTPException(status_code=404, detail="File not found")

    dest = matches[0]
    filename = dest.name[len(file_id) + 1:]  # strip "{file_id}_" prefix

    # Guess media type from extension
    media_type, _ = mimetypes.guess_type(str(dest))
    media_type = media_type or "application/octet-stream"

    return FileResponse(path=str(dest), media_type=media_type, filename=filename)
