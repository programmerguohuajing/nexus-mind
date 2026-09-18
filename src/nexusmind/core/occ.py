import hashlib
from typing import Optional

from fastapi import HTTPException, status


def get_file_hash(content: str) -> str:
    """计算内容前 12 位 SHA-256 指纹。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def verify_occ(
    current_version: Optional[str],
    expected_version: Optional[str],
    *,
    exists: bool,
) -> None:
    """执行 OCC：已有文件必须带 ifMatch；新文件可用 NEW 或空值。"""
    if not exists:
        if expected_version not in (None, "", "NEW"):
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail={"error": "Target does not exist", "expected_version": expected_version},
            )
        return

    if expected_version in (None, "", "NEW"):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Existing files require ifMatch. Re-read the note and retry.",
        )
    if expected_version != current_version:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "error": "Conflict: file changed since it was read",
                "current_version": current_version,
                "expected_version": expected_version,
                "retry_guidance": "Re-read, reconcile changes, then retry with the latest version.",
            },
        )
