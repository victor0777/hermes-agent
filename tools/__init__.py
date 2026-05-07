#!/usr/bin/env python3
"""
Tools Package

This package contains specific tool implementations for Hermes Agent. Tool modules
are imported by model_tools.py for discovery; package-level exports are loaded
lazily so optional tool dependencies are not required for unrelated imports.
"""

_EXPORTS = {
    # Web tools
    "web_search_tool": "web_tools",
    "web_extract_tool": "web_tools",
    "web_crawl_tool": "web_tools",
    "check_firecrawl_api_key": "web_tools",
    # Terminal tools
    "terminal_tool": "terminal_tool",
    "check_terminal_requirements": "terminal_tool",
    "cleanup_vm": "terminal_tool",
    "cleanup_all_environments": "terminal_tool",
    "get_active_environments_info": "terminal_tool",
    "register_task_env_overrides": "terminal_tool",
    "clear_task_env_overrides": "terminal_tool",
    "TERMINAL_TOOL_DESCRIPTION": "terminal_tool",
    # Vision tools
    "vision_analyze_tool": "vision_tools",
    "check_vision_requirements": "vision_tools",
    # MoA tools
    "mixture_of_agents_tool": "mixture_of_agents_tool",
    "check_moa_requirements": "mixture_of_agents_tool",
    # Image generation tools
    "image_generate_tool": "image_generation_tool",
    "check_image_generation_requirements": "image_generation_tool",
    # Skills tools
    "skills_list": "skills_tool",
    "skill_view": "skills_tool",
    "check_skills_requirements": "skills_tool",
    "SKILLS_TOOL_DESCRIPTION": "skills_tool",
    # Skill management
    "skill_manage": "skill_manager_tool",
    "check_skill_manage_requirements": "skill_manager_tool",
    "SKILL_MANAGE_SCHEMA": "skill_manager_tool",
    # Browser automation tools
    "browser_navigate": "browser_tool",
    "browser_snapshot": "browser_tool",
    "browser_click": "browser_tool",
    "browser_type": "browser_tool",
    "browser_scroll": "browser_tool",
    "browser_back": "browser_tool",
    "browser_press": "browser_tool",
    "browser_close": "browser_tool",
    "browser_get_images": "browser_tool",
    "browser_vision": "browser_tool",
    "cleanup_browser": "browser_tool",
    "cleanup_all_browsers": "browser_tool",
    "get_active_browser_sessions": "browser_tool",
    "check_browser_requirements": "browser_tool",
    "BROWSER_TOOL_SCHEMAS": "browser_tool",
    # Cronjob management tools (CLI-only)
    "cronjob": "cronjob_tools",
    "schedule_cronjob": "cronjob_tools",
    "list_cronjobs": "cronjob_tools",
    "remove_cronjob": "cronjob_tools",
    "check_cronjob_requirements": "cronjob_tools",
    "get_cronjob_tool_definitions": "cronjob_tools",
    "CRONJOB_SCHEMA": "cronjob_tools",
    # RL Training tools
    "rl_list_environments": "rl_training_tool",
    "rl_select_environment": "rl_training_tool",
    "rl_get_current_config": "rl_training_tool",
    "rl_edit_config": "rl_training_tool",
    "rl_start_training": "rl_training_tool",
    "rl_check_status": "rl_training_tool",
    "rl_stop_training": "rl_training_tool",
    "rl_get_results": "rl_training_tool",
    "rl_list_runs": "rl_training_tool",
    "rl_test_inference": "rl_training_tool",
    "check_rl_api_keys": "rl_training_tool",
    "get_missing_keys": "rl_training_tool",
    # File manipulation tools
    "read_file_tool": "file_tools",
    "write_file_tool": "file_tools",
    "patch_tool": "file_tools",
    "search_tool": "file_tools",
    "get_file_tools": "file_tools",
    "clear_file_ops_cache": "file_tools",
    # Text-to-speech tools
    "text_to_speech_tool": "tts_tool",
    "check_tts_requirements": "tts_tool",
    # Planning & task management tool
    "todo_tool": "todo_tool",
    "check_todo_requirements": "todo_tool",
    "TODO_SCHEMA": "todo_tool",
    "TodoStore": "todo_tool",
    # Clarifying questions tool
    "clarify_tool": "clarify_tool",
    "check_clarify_requirements": "clarify_tool",
    "CLARIFY_SCHEMA": "clarify_tool",
    # Code execution sandbox
    "execute_code": "code_execution_tool",
    "check_sandbox_requirements": "code_execution_tool",
    "EXECUTE_CODE_SCHEMA": "code_execution_tool",
    # Subagent delegation
    "delegate_task": "delegate_tool",
    "check_delegate_requirements": "delegate_tool",
    "DELEGATE_TASK_SCHEMA": "delegate_tool",
    # Collaboration PM tool
    "collaboration_tool": "collaboration_tool",
    "check_collaboration_requirements": "collaboration_tool",
    "COLLABORATION_SCHEMA": "collaboration_tool",
}


def __getattr__(name):
    if name == "check_file_requirements":
        def check_file_requirements():
            from .terminal_tool import check_terminal_requirements
            return check_terminal_requirements()
        return check_file_requirements

    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [*_EXPORTS, "check_file_requirements"]
