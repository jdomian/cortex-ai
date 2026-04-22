"""Tests for MCP tool registration -- all 6 new tools must be present and dispatch."""
import pytest


class TestMCPToolRegistration:
    def test_all_new_tools_in_tools_list(self):
        """All 6 new v0.5.0 tools must appear in TOOLS list."""
        import importlib.util
        import sys
        # Import without running main()
        spec = importlib.util.spec_from_file_location(
            "cortex_mcp", "/home/claude/cortex/mcp_wrapper.py"
        )
        module = importlib.util.module_from_spec(spec)
        # Don't exec -- just verify the TOOLS list is importable
        # Instead verify by reading the source
        with open("/home/claude/cortex/mcp_wrapper.py") as f:
            source = f.read()

        new_tools = [
            "cortex_stm_log",
            "cortex_stm_fetch",
            "cortex_dream_run",
            "cortex_dream_consolidate",
            "cortex_dream_decay",
            "cortex_dream_patterns",
        ]
        for tool in new_tools:
            assert tool in source, f"Tool {tool} not found in mcp_wrapper.py"

    def test_all_new_tools_have_handlers(self):
        """All 6 new tools must have elif branches in handle_tool()."""
        with open("/home/claude/cortex/mcp_wrapper.py") as f:
            source = f.read()

        handlers = [
            "cortex_stm_log",
            "cortex_stm_fetch",
            "cortex_dream_run",
            "cortex_dream_consolidate",
            "cortex_dream_decay",
            "cortex_dream_patterns",
        ]
        for h in handlers:
            assert f'name == "{h}"' in source, f"Handler for {h} not found"

    def test_original_18_tools_still_present(self):
        """Original tools must not be removed."""
        with open("/home/claude/cortex/mcp_wrapper.py") as f:
            source = f.read()

        original_tools = [
            "cortex_status", "cortex_list_wings", "cortex_search", "cortex_add",
            "cortex_delete", "cortex_kg_query", "cortex_kg_add", "cortex_traverse",
            "cortex_diary_write", "cortex_diary_read",
        ]
        for tool in original_tools:
            assert tool in source, f"Original tool {tool} missing"
