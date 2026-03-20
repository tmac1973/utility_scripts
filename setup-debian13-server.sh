#!/bin/bash
set -e

# Utility script for setting up a new Debian 13 server
# Usage: ./setup-debian13-server.sh [OPTIONS]
# Run as root

DOCKER=false
NONINTERACTIVE=false
SETUP_USER="${SUDO_USER:-tim}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Setup script for a new Debian 13 server.

Options:
    -d, --docker        Install and configure Docker
    -n, --non-interactive   Run non-interactively (assume yes to all prompts)
    -y                  Alias for --non-interactive
    -u, --user USER     User to configure (default: \$SUDO_USER or tim)
    -h, --help          Show this help message

Examples:
    $(basename "$0") -d -n -y      # Install everything non-interactively
    $(basename "$0") --docker      # Interactive mode with Docker option
    $(basename "$0") -d -u alice   # Install Docker, configure for user alice

EOF
    exit 0
}

# Expand combined short flags (e.g. -dny -> -d -n -y)
expand_flags() {
    local expanded=()
    for arg in "$@"; do
        if [[ "$arg" =~ ^-[a-zA-Z]{2,}$ ]]; then
            local flags="${arg#-}"
            for (( i=0; i<${#flags}; i++ )); do
                expanded+=("-${flags:$i:1}")
            done
        else
            expanded+=("$arg")
        fi
    done
    printf '%s\n' "${expanded[@]}"
}

# Parse arguments
mapfile -t ARGS < <(expand_flags "$@")
set -- "${ARGS[@]}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--docker)
            DOCKER=true
            shift
            ;;
        -n|--non-interactive)
            NONINTERACTIVE=true
            shift
            ;;
        -y)
            NONINTERACTIVE=true
            shift
            ;;
        -u|--user)
            SETUP_USER="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root"
    exit 1
fi

# Check if Debian 13
if [[ ! -f /etc/debian_version ]]; then
    log_error "This script is designed for Debian systems"
    exit 1
fi

DEBIAN_VERSION=$(cat /etc/debian_version)
if [[ ! "$DEBIAN_VERSION" =~ ^13 && ! "$DEBIAN_VERSION" =~ trixie ]]; then
    log_warn "Detected Debian version: $DEBIAN_VERSION"
    log_warn "This script is tested for Debian 13 (trixie)"
fi

# Function to prompt for yes/no
ask_yes_no() {
    local prompt="$1"
    local default="${2:-y}"
    
    if [[ "$NONINTERACTIVE" == "true" ]]; then
        return 0
    fi
    
    local answer
    local hint="Y/n"
    [[ "$default" == "n" ]] && hint="y/N"
    
    read -rp "$prompt [$hint]: " answer
    [[ -z "$answer" ]] && answer="$default"
    [[ "$answer" =~ ^[Yy]$ ]] && return 0 || return 1
}

# Update package lists
log_info "Updating package lists..."
apt-get update

# Add user to sudo group if it exists
if id "$SETUP_USER" &>/dev/null; then
    log_info "Adding user '$SETUP_USER' to sudo group..."
    usermod -aG sudo "$SETUP_USER"
    log_info "User '$SETUP_USER' added to sudo group"
else
    log_warn "User '$SETUP_USER' not found — skipping sudo group addition"
fi

# Install base packages
log_info "Installing base packages..."
apt-get install -y \
    sudo \
    cifs-utils \
    curl \
    btop \
    build-essential

# linux-headers may not match running kernel on fresh installs; don't abort if unavailable
if apt-get install -y "linux-headers-$(uname -r)" 2>/dev/null; then
    log_info "Installed linux-headers-$(uname -r)"
else
    log_warn "linux-headers-$(uname -r) not available — install manually or reboot and re-run"
fi

# Setup Docker if requested
setup_docker() {
    log_info "Setting up Docker..."
    
    # Install Docker using the official script
    log_info "Downloading Docker installation script..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    log_info "Running Docker installation script..."
    sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh

    # Start and enable Docker service
    log_info "Starting Docker service..."
    systemctl start docker
    systemctl enable docker

    # Add user to docker group if it exists
    if id "$SETUP_USER" &>/dev/null; then
        log_info "Adding user '$SETUP_USER' to docker group..."
        usermod -aG docker "$SETUP_USER"
        log_info "User '$SETUP_USER' added to docker group"
    else
        log_warn "User '$SETUP_USER' not found — skipping docker group addition"
    fi
    
    log_info "Docker installation complete!"
}

# Main logic
if [[ "$DOCKER" == "true" ]]; then
    log_info "Docker installation requested"
    if ! ask_yes_no "Install Docker?" y; then
        log_info "Skipping Docker installation"
    else
        setup_docker
    fi
else
    if [[ "$NONINTERACTIVE" != "true" ]]; then
        if ask_yes_no "Install Docker as well?" n; then
            setup_docker
        fi
    fi
fi

log_info "Server setup complete!"
