import pytest
from fastapi import HTTPException

from nexusmind.core.permissions import check_write_permission


@pytest.mark.parametrize("path", [
    "00-Meta/AGENTS.md",
    "25-Routines/Routines.md",
    "40-Domain/Architecture/TestCard.md",
    "60-References/Articles/paper.md",
])
def test_protected_folders_reject_agent_write(path):
    with pytest.raises(HTTPException) as exc_info:
        check_write_permission(path)
    assert exc_info.value.status_code == 403


def test_workspace_is_writable():
    check_write_permission("90-AI-Workspace/drafts/test.md")


def test_internal_privileged_override():
    check_write_permission(
        "60-References/Articles/paper.md",
        actor="gateway",
        privileged=True,
    )
