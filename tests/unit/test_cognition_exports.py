"""Public cognitive imports for the bounded P0.5-B2 tool seam."""

from server.cognition import HouseholdKnowledgeTools, HouseholdToolName, HouseholdToolResult


def test_household_tool_contracts_are_exported() -> None:
    """Expose the closed tool seam without exporting storage or policy internals."""
    assert HouseholdKnowledgeTools.__name__ == "HouseholdKnowledgeTools"
    assert HouseholdToolName.GET_CHILDREN.value == "get_children"
    assert HouseholdToolResult.__name__ == "HouseholdToolResult"
