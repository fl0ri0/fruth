#!/bin/bash
# Starts the manager that discovers and launches dedicated model servers
# and then starts the Flask webserver for the UI.
# Usage: run from the fruth repo root: ./start_multi_models.sh

cd "$(dirname "$0")" # Ensure we are in the fruth repo root.

OLLAMA_CLI="/opt/homebrew/bin/ollama"
MAIN_VENV_DIR=".venv"
REPO_PYTHON=""
REQUIREMENTS_FILE="requirements.txt" # In the fruth repo root.
BOOTSTRAP_PREFLIGHT="scripts/bootstrap_preflight.py"
UNIFIED_STARTUP_SCRIPT="scripts/startup_model_manager.py"
WEBSERVER_SCRIPT="fruth_webserver.py"
WEBSERVER_PORT="5011"

# Keep reviewed-rebase credentials out of every model/backend process. They
# are re-exported only for the Flask control plane, which immediately removes
# them from its process environment after startup.
GRAPH_REBASE_OPERATOR_TOKEN="${FRUTH_GRAPH_REBASE_OPERATOR_TOKEN:-}"
GRAPH_REBASE_OPERATOR_IDENTITY="${FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY:-}"
export -n GRAPH_REBASE_OPERATOR_TOKEN
export -n GRAPH_REBASE_OPERATOR_IDENTITY
unset FRUTH_GRAPH_REBASE_OPERATOR_TOKEN
unset FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY

: "${FRUTH_MULTI_MATERIALIZATION_MAX_PARALLEL_WORKERS:=4}"
: "${FRUTH_GRAPH_REPAIR_AUTONOMY=apply_enforced}"
: "${FRUTH_APPLY_ENFORCED_POLICY=safe_v1}"
export FRUTH_MULTI_MATERIALIZATION_MAX_PARALLEL_WORKERS
export FRUTH_GRAPH_REPAIR_AUTONOMY
export FRUTH_APPLY_ENFORCED_POLICY

# Colors
SYSTEM_COLOR="\033[90m"
RESET_COLOR="\033[0m"

run_repo_python() {
    "$REPO_PYTHON" "$@"
}

bootstrap_repair_message() {
    echo "   Startup does not repair existing environments automatically."
    echo "   See README.md (Python environment recovery). With a valid main interpreter,"
    echo "   explicitly repair while Fruth is stopped:"
    echo "     .venv/bin/python3 -m pip install -r requirements.txt"
    echo "     .venv/bin/python3 -I -B scripts/bootstrap_preflight.py --venv .venv --requirements requirements.txt"
}

preflight_ollama_service_ownership() {
    if [ "${FRUTH_ALLOW_BREW_OLLAMA_SERVICE:-0}" = "1" ]; then
        echo "⚠️  FRUTH_ALLOW_BREW_OLLAMA_SERVICE=1 is set. Skipping the Homebrew Ollama ownership check."
        return 0
    fi

    if ! command -v brew >/dev/null 2>&1; then
        return 0
    fi

    local service_line
    local service_status

    service_line=$(brew services list 2>/dev/null | awk '$1=="ollama"{print; exit}')
    if [ -z "$service_line" ]; then
        return 0
    fi

    service_status=$(printf '%s\n' "$service_line" | awk '{print $2}')
    if [ "$service_status" != "started" ]; then
        return 0
    fi

    echo "❌ Homebrew service 'ollama' is already running."
    echo "   Fruth should be the only owner of 'ollama serve'."
    echo "   Run this first: brew services stop ollama"
    echo "   If you want to override this intentionally: FRUTH_ALLOW_BREW_OLLAMA_SERVICE=1 ./start_multi_models.sh"
    return 1
}

echo -e "${SYSTEM_COLOR}--- Full startup: models + web UI ---${RESET_COLOR}"

# --- Virtual environment & dependencies ---
echo -e "\n${SYSTEM_COLOR}--- Step 1: check/activate virtual environment ---${RESET_COLOR}"
if [ ! -f "$REQUIREMENTS_FILE" ] || [ ! -r "$REQUIREMENTS_FILE" ]; then
    echo "❌ Missing or unreadable $REQUIREMENTS_FILE. Restore it from the matching Fruth source before startup."
    exit 1
fi
if [ ! -f "$BOOTSTRAP_PREFLIGHT" ]; then
    echo "❌ Missing $BOOTSTRAP_PREFLIGHT. Restore the complete Fruth source before startup."
    exit 1
fi
if [ ! -e "$MAIN_VENV_DIR" ] && [ ! -L "$MAIN_VENV_DIR" ]; then
    BOOTSTRAP_PYTHON=$(type -P python3)
    if [ -z "$BOOTSTRAP_PYTHON" ] || ! "$BOOTSTRAP_PYTHON" -I -B "$BOOTSTRAP_PREFLIGHT" --requirements "$REQUIREMENTS_FILE" --interpreter-only; then
        echo "❌ Select a working Python 3.11+ linked to OpenSSL 1.1.1+ on PATH before creating .venv. See README.md."
        exit 1
    fi
    echo "🔧 Creating virtual environment ($MAIN_VENV_DIR)..."
    "$BOOTSTRAP_PYTHON" -I -m venv "$MAIN_VENV_DIR"
    if [ $? -ne 0 ]; then echo "❌ Failed to create the virtual environment."; exit 1; fi
    NEEDS_INSTALL=true
else
    NEEDS_INSTALL=false
fi
# Never fall back to PATH Python or a backend environment for an existing venv.
REPO_PYTHON="$PWD/$MAIN_VENV_DIR/bin/python3"
if [ ! -x "$REPO_PYTHON" ] || [ ! -f "$MAIN_VENV_DIR/bin/activate" ]; then
    echo "❌ Missing/broken main venv interpreter or activate script: $REPO_PYTHON"
    bootstrap_repair_message
    exit 1
fi
if ! "$REPO_PYTHON" -I -B "$BOOTSTRAP_PREFLIGHT" --venv "$MAIN_VENV_DIR" --requirements "$REQUIREMENTS_FILE" --interpreter-only; then
    bootstrap_repair_message
    exit 1
fi

# Bootstrap only a newly created environment. Existing environments are managed
# explicitly by the user; startup/restart must not install or update packages.
if $NEEDS_INSTALL; then
     echo "🔧 Installing dependencies from $REQUIREMENTS_FILE..."
    "$REPO_PYTHON" -m pip --disable-pip-version-check install -r "$REQUIREMENTS_FILE"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies. The partial .venv is retained for explicit repair."
        bootstrap_repair_message
        exit 1
    fi
fi
if ! "$REPO_PYTHON" -I -B "$BOOTSTRAP_PREFLIGHT" --venv "$MAIN_VENV_DIR" --requirements "$REQUIREMENTS_FILE"; then
    bootstrap_repair_message
    exit 1
fi
source "$MAIN_VENV_DIR/bin/activate"
echo "🐍 Virtual environment validated and activated."
# --- End virtual environment & dependencies ---

echo -e "\n${SYSTEM_COLOR}--- Step 1.5: check Ollama ownership ---${RESET_COLOR}"
if ! preflight_ollama_service_ownership; then
    exit 1
fi

# --- Discover/start models together ---
echo -e "\n${SYSTEM_COLOR}--- Step 2: discover and start model instances ---${RESET_COLOR}"
if [ ! -f "$UNIFIED_STARTUP_SCRIPT" ]; then
     echo "❌ Could not find $UNIFIED_STARTUP_SCRIPT."
     exit 1
fi
"$REPO_PYTHON" "$UNIFIED_STARTUP_SCRIPT"
if [ $? -ne 0 ]; then
    echo "❌ Failed while running $UNIFIED_STARTUP_SCRIPT."
    exit 1
fi
echo "✅ Model startup finished."

# --- Start Flask webserver ---
echo -e "\n${SYSTEM_COLOR}--- Step 3: start the webserver for the UI ---${RESET_COLOR}"
echo "ℹ️  External provider projections are not refreshed during startup. Run './fruth sync' manually if needed."
if [ ! -f "$WEBSERVER_SCRIPT" ]; then
     echo "❌ Could not find $WEBSERVER_SCRIPT."
     exit 1;
fi

# Port occupancy is discovery only. A foreign/ambiguous listener is a failure.
run_repo_python -B -m fruth_core.process_ownership check-webserver --root "$PWD" --port "$WEBSERVER_PORT"
WEBSERVER_CHECK=$?
if [[ "$WEBSERVER_CHECK" -eq 0 ]]; then
    echo "✅ This checkout's verified Fruth webserver is already running on port $WEBSERVER_PORT."
    echo "   Dashboard:       http://127.0.0.1:$WEBSERVER_PORT/"
    echo "   Dashboard alias: http://127.0.0.1:$WEBSERVER_PORT/dashboard"
elif [[ "$WEBSERVER_CHECK" -eq 3 ]]; then
    echo "🚀 Starting $WEBSERVER_SCRIPT in the background on port $WEBSERVER_PORT..."
    LOG_DIR="logs"; mkdir -p "$LOG_DIR"
    FLASK_LOG="${LOG_DIR}/flask_webserver.log"
    run_repo_python - <<'PY'
from pathlib import Path

from fruth_runtime.runtime_log_hygiene import prepare_clean_global_log

prepare_clean_global_log(
    Path("logs/flask_webserver.log"),
    metadata={
        'service': 'flask_webserver',
        'port': 5011,
    },
)
PY
    export FRUTH_GRAPH_REBASE_OPERATOR_TOKEN="$GRAPH_REBASE_OPERATOR_TOKEN"
    export FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY="$GRAPH_REBASE_OPERATOR_IDENTITY"
    run_repo_python -B -m fruth_core.process_ownership launch-webserver --root "$PWD" --port "$WEBSERVER_PORT"
    WEBSERVER_LAUNCH=$?
    unset FRUTH_GRAPH_REBASE_OPERATOR_TOKEN
    unset FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY
    GRAPH_REBASE_OPERATOR_TOKEN=""
    GRAPH_REBASE_OPERATOR_IDENTITY=""
    if [[ "$WEBSERVER_LAUNCH" -eq 0 ]]; then
        echo "✅ Verified Fruth webserver started successfully."
        echo "   Dashboard:       http://127.0.0.1:$WEBSERVER_PORT/"
        echo "   Dashboard alias: http://127.0.0.1:$WEBSERVER_PORT/dashboard"
        echo "   (The server is running in the background, logs in $FLASK_LOG)"
    else
        echo "❌ Failed to start the webserver. See $FLASK_LOG."
        exit 1
    fi
else
    echo "❌ Webserver port $WEBSERVER_PORT has unresolved ownership; Fruth startup failed."
    exit 1
fi
# --- End webserver start ---

echo -e "\n${SYSTEM_COLOR}--- Startup complete ---${RESET_COLOR}"
# The virtual environment stays active for this terminal session unless you call 'deactivate'.
