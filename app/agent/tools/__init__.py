"""工具注册表。新增工具 → 在这里登记即可被 Agent Loop 使用。"""
from .recall_playbook import RecallPlaybookTool
from .project_search import ProjectSearchTool
from .owner_cases import OwnerCasesTool
from .handoff import HandoffTool


def build_registry() -> dict:
    tools = [
        RecallPlaybookTool(),
        ProjectSearchTool(),
        OwnerCasesTool(),
        HandoffTool(),
    ]
    return {t.name: t for t in tools}
