#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/ktl/projects/hermes-agent"
VENV_DIR="${REPO_DIR}/venv"
ENV_FILE="${HOME}/.hermes/.env"
LIMIT="${SEC_INTELLIGENCE_DAILY_LIMIT:-100}"
LOG_DIR="${REPO_DIR}/data/logs"
SCRIPT_LOG="${LOG_DIR}/security-intelligence-daily.log"

mkdir -p "${LOG_DIR}"

{
  date -u +"[%Y-%m-%d %H:%M:%S UTC] security_intelligence_daily start"
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  else
    echo "ERROR: missing ${ENV_FILE}" >&2
  fi

  if [[ -f "${VENV_DIR}/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
  fi

  cd "${REPO_DIR}"
  python3 scripts/security_intelligence_daily.py --limit "${LIMIT}"
  echo "security_intelligence_daily completed"
} >> "${SCRIPT_LOG}" 2>&1
