#!/bin/bash
set -e

# Utility script for setting up a new Debian 13 server
# Usage: ./setup-debian13-server.sh [OPTIONS]
# Run as root

DRY_RUN=false
DOCKER=false
NONINTERACTIVE=false

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
    -h, --help          Show this help message

Examples:
    $(basename "$0") -dny          # Install everything non-interactively
    $(basename "$0") --docker      # Interactive mode with Docker option

EOF
    exit 0
}

# Parse arguments
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
if [[ ! "$DEBIAN_VERSION" =~ ^13 ]]; then
    log_warn "Detected Debian version: $DEBIAN_VERSION"
    log_warn "This script is tested for Debian 13"
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

# Add user 'tim' to sudo group if it exists
if id "tim" &>/dev/null; then
    log_info "Adding user 'tim' to sudo group..."
    usermod -aG sudo tim
    log_info "User 'tim' added to sudo group"
fi

# Install base packages
log_info "Installing base packages (sudo, cifs-client, curl, btop, build-essential, linux-headers)..."
apt-get install -y \
    sudo \
    cifs-utils \
    curl \
    btop \
    build-essential \
    linux-headers-$(uname -r)

# Setup Docker if requested
setup_docker() {
    log_info "Setting up Docker..."
    
    # Install Docker using the official script
    log_info "Downloading and running Docker installation script..."
    curl -fsSL https://get.docker.com | sh
    
    # Start and enable Docker service
    log_info "Starting Docker service..."
    systemctl start docker
    systemctl enable docker
    
    # Add user 'tim' to docker group if it exists
    if id "tim" &>/dev/null; then
        log_info "Adding user 'tim' to docker group..."
        usermod -aG docker tim
        log_info "User 'tim' added to docker group"
    else
        log_warn "User 'tim' not found - skipping group additions"
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
