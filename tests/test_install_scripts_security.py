"""Static security checks for installer scripts."""

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPTS = [
    REPO_ROOT / "scripts" / "install.sh",
    REPO_ROOT / "setup-hermes.sh",
]


PIPE_TO_SHELL_RE = re.compile(
    r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b",
    re.IGNORECASE,
)


def _script_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_installers_do_not_pipe_remote_content_to_shell():
    for path in INSTALL_SCRIPTS:
        text = _script_text(path)
        assert not PIPE_TO_SHELL_RE.search(text), f"{path} must not contain curl/wget piped to shell"


def test_main_installer_exposes_safe_mode():
    text = _script_text(REPO_ROOT / "scripts" / "install.sh")
    assert "SAFE_MODE=${HERMES_INSTALL_SAFE:-false}" in text
    assert "--safe)" in text
    assert "RUN_SETUP=false" in text


def test_main_installer_safe_mode_gates_optional_actions():
    text = _script_text(REPO_ROOT / "scripts" / "install.sh")
    required_messages = [
        "safe mode skips Node.js auto-install",
        "Safe mode: skipping optional system package installation.",
        "Safe mode: skipping build tool package-manager install.",
        "Safe mode: skipping npm and Playwright installs.",
        "Safe mode: not editing shell config files.",
        "Safe mode: skipping gateway service offer/start.",
    ]
    for message in required_messages:
        assert message in text


def test_setup_script_safe_mode_gates_optional_actions():
    text = _script_text(REPO_ROOT / "setup-hermes.sh")
    assert "SAFE_MODE=${HERMES_INSTALL_SAFE:-false}" in text
    assert "--safe)" in text
    assert "RUN_SETUP=false" in text

    required_messages = [
        "safe mode skips package-manager auto-install",
        "Safe mode: not editing shell config files.",
        "Setup wizard skipped",
    ]
    for message in required_messages:
        assert message in text
