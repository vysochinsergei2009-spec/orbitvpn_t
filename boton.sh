#!/bin/bash

# ====================================
# OrbitVPN Bot Startup Script
# ====================================

# Constants
readonly PROJECT_DIR="/root/orbitvpn"
readonly VENV_PATH="${PROJECT_DIR}/venv"
readonly PYTHON_SCRIPT="${PROJECT_DIR}/run.py"
readonly TMUX_SESSION="orbitvpn_bot"
readonly LOG_FILE="${PROJECT_DIR}/bot.log"

# Colors for terminal output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color
readonly BOLD='\033[1m'

# ====================================
# Helper Functions
# ====================================

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔════════════════════════════════════════╗"
    echo "║        OrbitVPN Bot Manager            ║"
    echo "║            Starting Bot...             ║"
    echo "╚════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# ====================================
# Main Script
# ====================================

print_banner

# Check if tmux session already exists
if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
    print_warning "Bot session '${TMUX_SESSION}' is already running!"
    echo -e "\n${CYAN}Options:${NC}"
    echo "  1. Attach to existing session: tmux attach -t ${TMUX_SESSION}"
    echo "  2. Stop the bot first: ./botoff.sh"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "${VENV_PATH}" ]; then
    print_error "Virtual environment not found at ${VENV_PATH}"
    print_info "Please create it with: python3 -m venv ${VENV_PATH}"
    exit 1
fi

# Check if run.py exists
if [ ! -f "${PYTHON_SCRIPT}" ]; then
    print_error "Bot script not found at ${PYTHON_SCRIPT}"
    exit 1
fi

print_info "Project directory: ${PROJECT_DIR}"
print_info "Virtual environment: ${VENV_PATH}"
print_info "Session name: ${TMUX_SESSION}"

# Create tmux session and start bot
print_info "Creating tmux session and starting bot..."

tmux new-session -d -s "${TMUX_SESSION}" -c "${PROJECT_DIR}" \
    "source '${VENV_PATH}/bin/activate' && \
     echo -e '${CYAN}${BOLD}OrbitVPN Bot Started${NC}' && \
     echo -e '${GREEN}Session: ${TMUX_SESSION}${NC}' && \
     echo -e '${YELLOW}Press Ctrl+B then D to detach${NC}\n' && \
     python3 '${PYTHON_SCRIPT}' 2>&1 | tee -a '${LOG_FILE}'"

# Check if session was created successfully
if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
    sleep 1
    print_success "Bot started successfully in tmux session '${TMUX_SESSION}'"
    echo ""
    print_info "Useful commands:"
    echo -e "  ${CYAN}Attach to session:${NC}  tmux attach -t ${TMUX_SESSION}"
    echo -e "  ${CYAN}View logs:${NC}          tail -f ${LOG_FILE}"
    echo -e "  ${CYAN}Stop bot:${NC}           ./botoff.sh"
    echo ""
else
    print_error "Failed to create tmux session"
    exit 1
fi
