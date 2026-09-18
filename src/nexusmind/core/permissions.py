from fastapi import HTTPException, status

# 与 00-Meta/知识库架构说明.md 保持一致。
STRICT_READ_ONLY = ("00-Meta", "25-Routines", "60-References")
RESTRICTED_DOMAIN = "40-Domain"
CONTROLLED_WORLD = "50-World"
CONDITIONAL_OCC = "20-Projects"


def _under(rel_path: str, folder: str) -> bool:
    norm = rel_path.replace("\\", "/").strip("/")
    return norm == folder or norm.startswith(f"{folder}/")


def requires_occ(rel_path: str) -> bool:
    """项目目录是显式 OCC 区；其他已有文件也由 patch_note 强制 OCC。"""
    return _under(rel_path, CONDITIONAL_OCC)


def check_write_permission(
    rel_path: str,
    *,
    actor: str = "agent",
    privileged: bool = False,
    force: bool | None = None,
) -> None:
    """按知识库权限矩阵校验写入边界。

    privileged 仅供进程内部受控能力（compiler/indexer/ingest）使用，
    HTTP/MCP 客户端不能直接申请该权限。force 仅保留给旧内部调用兼容。
    """
    if force is not None:
        privileged = privileged or force
    if privileged:
        return
    for folder in STRICT_READ_ONLY:
        if _under(rel_path, folder):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{folder}' is read-only for agents.",
            )

    if _under(rel_path, RESTRICTED_DOMAIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "40-Domain is a reviewed knowledge layer. "
                "Write drafts to 90-AI-Workspace/drafts or use vault_compile."
            ),
        )

    if _under(rel_path, CONTROLLED_WORLD) and actor != "radar":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="50-World only accepts controlled writes from the Radar agent.",
        )
