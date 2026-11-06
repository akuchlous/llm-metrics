#!/usr/bin/env bash
# setup.sh — Bootstrap Docker and Docker Compose for llm-metrics.
#
# Checks whether Docker Engine and Docker Compose v2 are installed and the
# Docker daemon is accessible.  If Docker is missing on a supported platform,
# offers to install it via the official package manager — with explicit
# confirmation before every system change.
#
# NEVER:
#   - uses curl-pipe-shell (curl ... | bash/sh) installers
#   - installs PostgreSQL, Python, pip, or any application service
#   - changes host permissions without explicit confirmation
#   - uses Google Cloud or any cloud provider
#
# SUPPORTED PLATFORMS:
#   Ubuntu / Debian     — Docker's official apt repository
#   RHEL / Fedora /
#   CentOS / Rocky /
#   AlmaLinux           — Docker's official dnf repository
#   macOS (Homebrew)    — brew install --cask docker  (Docker Desktop)
#   WSL2                — Docker Desktop for Windows handles daemon access;
#                         enable WSL integration in Docker Desktop settings,
#                         then re-run setup.sh from WSL
#   Other               — Displays official install URL; no auto-install
#
# Usage:
#   ./setup.sh           Check status and offer to install if missing
#   ./setup.sh --check   Report status only; never install or change anything
#   ./setup.sh --help    Show this message

cd "$(dirname "$0")"

CHECK_ONLY=0
if [[ "${1:-}" == "--help" ]]; then
    sed -n '2,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
    exit 0
fi
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=1
fi

# --- Terminal colours (only when stdout is a TTY) ---
if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; BOLD=''; NC=''
fi

pass() { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }
info() { echo "  $*"; }
header() { echo -e "\n${BOLD}$*${NC}"; }
ask() {
    # ask PROMPT — prints prompt, reads Y/N; returns 0 for yes, 1 for no
    local prompt="$1"
    local reply
    echo -en "  ${YELLOW}?${NC} ${prompt} [y/N] "
    read -r reply
    [[ "${reply,,}" == "y" ]]
}

# --- Platform detection ---
OS=""        # linux | macos | windows_wsl | unknown
DISTRO=""    # ubuntu | debian | rhel | fedora | centos | rocky | alma | other
PKG_MGR=""   # apt | dnf | brew | none

detect_platform() {
    local kernel
    kernel="$(uname -s)"
    case "$kernel" in
        Linux)
            # WSL2 / WSL1
            if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
                OS="windows_wsl"
                return
            fi
            OS="linux"
            if [ -f /etc/os-release ]; then
                # shellcheck source=/dev/null
                . /etc/os-release
                local id="${ID:-}"
                local id_like="${ID_LIKE:-}"
                case "$id $id_like" in
                    *ubuntu*) DISTRO="ubuntu"; PKG_MGR="apt" ;;
                    *debian*) DISTRO="debian"; PKG_MGR="apt" ;;
                    *fedora*) DISTRO="fedora"; PKG_MGR="dnf" ;;
                    *rhel*)   DISTRO="rhel";   PKG_MGR="dnf" ;;
                    *centos*) DISTRO="centos"; PKG_MGR="dnf" ;;
                    *rocky*)  DISTRO="rocky";  PKG_MGR="dnf" ;;
                    *alma*)   DISTRO="alma";   PKG_MGR="dnf" ;;
                    *)        DISTRO="other";  PKG_MGR="none" ;;
                esac
            else
                DISTRO="other"; PKG_MGR="none"
            fi
            ;;
        Darwin)
            OS="macos"
            command -v brew &>/dev/null && PKG_MGR="brew" || PKG_MGR="none"
            ;;
        *)
            OS="unknown"; PKG_MGR="none"
            ;;
    esac
}

# --- Docker state ---
DOCKER_BIN=""         # path to docker binary or ""
DOCKER_VERSION=""     # version string
COMPOSE_OK=0          # 1 if docker compose v2 works
DAEMON_OK=0           # 1 if daemon is accessible
DAEMON_PERM_ERR=0     # 1 if daemon running but user lacks socket access

check_all() {
    # Docker binary
    if command -v docker &>/dev/null; then
        DOCKER_BIN="$(command -v docker)"
        DOCKER_VERSION="$(docker --version 2>/dev/null | head -1)" || DOCKER_VERSION="(version unavailable)"
    fi

    # Docker Compose v2
    if [ -n "$DOCKER_BIN" ]; then
        docker compose version &>/dev/null 2>&1 && COMPOSE_OK=1 || COMPOSE_OK=0
    fi

    # Daemon access
    if [ -n "$DOCKER_BIN" ]; then
        if docker info &>/dev/null 2>&1; then
            DAEMON_OK=1
        else
            local err
            err="$(docker info 2>&1)"
            if echo "$err" | grep -qiE "permission denied|connect.*unix.*docker\.sock"; then
                DAEMON_PERM_ERR=1
            fi
        fi
    fi
}

# --- Helpers that require sudo ---

_require_sudo() {
    if ! command -v sudo &>/dev/null; then
        fail "'sudo' is required but was not found."
        info "Re-run as root, or install sudo first."
        return 1
    fi
    if ! sudo -n true 2>/dev/null; then
        warn "Some steps require sudo.  You may be prompted for your password."
    fi
    return 0
}

_install_docker_apt() {
    # Install Docker Engine via Docker's official apt repository.
    # Uses curl to download the GPG key to a file (NOT curl-pipe-shell).
    # https://docs.docker.com/engine/install/ubuntu/
    # https://docs.docker.com/engine/install/debian/
    local apt_distro_id
    . /etc/os-release 2>/dev/null || true
    case "${ID:-}" in
        ubuntu) apt_distro_id="ubuntu" ;;
        *)      apt_distro_id="debian" ;;
    esac
    local version_codename="${VERSION_CODENAME:-}"
    if [ -z "$version_codename" ]; then
        fail "Could not determine VERSION_CODENAME from /etc/os-release."
        info "Install Docker manually: https://docs.docker.com/engine/install/${apt_distro_id}/"
        return 1
    fi

    _require_sudo || return 1

    echo ""
    info "--- 1/4: install prerequisites ---"
    sudo apt-get update -qq
    sudo apt-get install -y ca-certificates curl

    info "--- 2/4: add Docker's GPG signing key ---"
    info "    (file download, not a curl-pipe-shell installer)"
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL "https://download.docker.com/linux/${apt_distro_id}/gpg" \
        -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    info "--- 3/4: add Docker apt repository ---"
    local arch
    arch="$(dpkg --print-architecture)"
    echo \
        "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc]" \
        "https://download.docker.com/linux/${apt_distro_id}" \
        "${version_codename} stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq

    info "--- 4/4: install Docker Engine and Compose plugin ---"
    sudo apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    pass "Docker Engine and Compose plugin installed."
}

_install_docker_dnf() {
    # https://docs.docker.com/engine/install/fedora/
    _require_sudo || return 1

    echo ""
    info "--- 1/2: add Docker dnf repository ---"
    sudo dnf -y install dnf-plugins-core
    sudo dnf config-manager --add-repo \
        https://download.docker.com/linux/fedora/docker-ce.repo

    info "--- 2/2: install Docker Engine and Compose plugin ---"
    sudo dnf -y install \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    pass "Docker Engine and Compose plugin installed."
}

_install_docker_brew() {
    brew install --cask docker
    pass "Docker Desktop installed via Homebrew."
    warn "Start Docker Desktop from Applications before running ./run.sh."
}

_add_user_to_docker_group() {
    _require_sudo || return 1
    sudo usermod -aG docker "${USER}"
    pass "Added '${USER}' to the docker group."
    warn "Log out and back in (or run 'newgrp docker') for the change to take effect."
    warn "Re-run ./setup.sh to verify daemon access after re-login."
}

_start_docker_daemon() {
    if ! command -v systemctl &>/dev/null; then
        warn "Cannot determine how to start the Docker daemon on this platform."
        info "Start Docker manually, then re-run ./setup.sh."
        return 1
    fi
    _require_sudo || return 1
    sudo systemctl enable --now docker
    pass "Docker daemon started and enabled."
}

# --- Installation descriptions (shown before confirmation) ---

_describe_apt_install() {
    info "Will install Docker Engine via Docker's official apt repository:"
    info "  sudo apt-get install  ca-certificates curl"
    info "  curl (file download)  https://download.docker.com/linux/debian/gpg"
    info "                        → /etc/apt/keyrings/docker.asc  (GPG key, not a script)"
    info "  Adds Docker apt repository to /etc/apt/sources.list.d/docker.list"
    info "  sudo apt-get install  docker-ce docker-ce-cli containerd.io"
    info "                        docker-buildx-plugin docker-compose-plugin"
}

_describe_dnf_install() {
    info "Will install Docker Engine via Docker's official dnf repository:"
    info "  sudo dnf install  dnf-plugins-core"
    info "  sudo dnf config-manager --add-repo  (Docker dnf repo)"
    info "  sudo dnf install  docker-ce docker-ce-cli containerd.io"
    info "                    docker-buildx-plugin docker-compose-plugin"
}

_describe_brew_install() {
    info "Will run:  brew install --cask docker"
    info "Docker Desktop for macOS will be installed."
    info "Start Docker Desktop from Applications after installation."
}

# --- Main ---

main() {
    header "LLM Metrics — Docker setup check"
    if [[ $CHECK_ONLY -eq 1 ]]; then
        info "(check-only mode: reporting status only, no changes)"
    fi

    # 1. Detect platform
    detect_platform
    echo ""
    case "$OS" in
        linux)       info "Platform: Linux ($DISTRO, installer: $PKG_MGR)" ;;
        macos)       info "Platform: macOS (installer: ${PKG_MGR:-none})" ;;
        windows_wsl) info "Platform: WSL (Windows Subsystem for Linux)" ;;
        *)           info "Platform: unknown ($(uname -s))" ;;
    esac

    # WSL: Docker Desktop owns the daemon
    if [ "$OS" = "windows_wsl" ]; then
        echo ""
        warn "WSL2 detected.  Docker Desktop for Windows provides the daemon."
        info "  1. Install Docker Desktop for Windows:"
        info "     https://docs.docker.com/desktop/wsl/"
        info "  2. Enable WSL integration: Settings → Resources → WSL Integration"
        info "  3. Re-run ./setup.sh from WSL to verify."
        exit 1
    fi

    # 2. Check all three components now
    check_all

    # 3. Report current state
    header "Docker Engine"
    if [ -n "$DOCKER_BIN" ]; then
        pass "Docker binary:  $DOCKER_BIN"
        info "  $DOCKER_VERSION"
    else
        fail "Docker binary not found in PATH."
    fi

    header "Docker Compose v2"
    if [[ $COMPOSE_OK -eq 1 ]]; then
        pass "'docker compose' is available."
        docker compose version 2>/dev/null | head -1 | sed 's/^/  /'
    else
        if [ -n "$DOCKER_BIN" ]; then
            fail "'docker compose' (Compose v2) not available."
            info "The standalone 'docker-compose' v1 binary is NOT compatible with ./run.sh."
        else
            warn "Compose check skipped (Docker binary not found)."
        fi
    fi

    header "Docker daemon"
    if [[ $DAEMON_OK -eq 1 ]]; then
        pass "Daemon is accessible."
    elif [[ $DAEMON_PERM_ERR -eq 1 ]]; then
        fail "Daemon is running but '${USER}' cannot access the Docker socket."
    else
        if [ -n "$DOCKER_BIN" ]; then
            fail "Daemon is not running or not accessible."
        else
            warn "Daemon check skipped (Docker binary not found)."
        fi
    fi

    # 4. If everything is fine, we're done
    if [ -n "$DOCKER_BIN" ] && [[ $COMPOSE_OK -eq 1 ]] && [[ $DAEMON_OK -eq 1 ]]; then
        header "Summary"
        pass "Docker Engine, Compose v2, and daemon access are all ready."
        echo ""
        info "Run the full workflow:  ./run.sh"
        info "Run tests only:         ./run.sh test"
        info "Clean up after SIGKILL: ./run.sh down"
        exit 0
    fi

    # 5. In check-only mode, report what's missing and exit
    if [[ $CHECK_ONLY -eq 1 ]]; then
        header "Summary"
        warn "One or more checks did not pass (check-only mode; no changes made)."
        echo ""
        if [ -z "$DOCKER_BIN" ]; then
            case "$PKG_MGR" in
                apt)  _describe_apt_install ;;
                dnf)  _describe_dnf_install ;;
                brew) _describe_brew_install ;;
                none)
                    info "Install Docker manually: https://docs.docker.com/get-docker/"
                    ;;
            esac
        fi
        if [[ $DAEMON_PERM_ERR -eq 1 ]]; then
            info "To fix daemon access:  sudo usermod -aG docker ${USER}"
            info "Then log out and back in, or run:  newgrp docker"
        elif [ -n "$DOCKER_BIN" ] && [[ $DAEMON_OK -eq 0 ]]; then
            command -v systemctl &>/dev/null && \
                info "To start the daemon:  sudo systemctl enable --now docker"
        fi
        echo ""
        info "Re-run without --check to apply fixes:"
        info "  ./setup.sh"
        exit 1
    fi

    # 6. Interactive: offer to fix each issue
    echo ""

    # 6a. Install Docker if missing
    if [ -z "$DOCKER_BIN" ]; then
        case "$PKG_MGR" in
            apt|dnf|brew)
                echo ""
                case "$PKG_MGR" in
                    apt)  _describe_apt_install ;;
                    dnf)  _describe_dnf_install ;;
                    brew) _describe_brew_install ;;
                esac
                echo ""
                if ask "Install Docker now?"; then
                    case "$PKG_MGR" in
                        apt)  _install_docker_apt  ;;
                        dnf)  _install_docker_dnf  ;;
                        brew) _install_docker_brew ;;
                    esac
                    # Re-check after install
                    check_all
                else
                    warn "Installation cancelled."
                fi
                ;;
            none)
                echo ""
                fail "Automatic installation is not supported on this platform."
                info "Install Docker manually: https://docs.docker.com/get-docker/"
                case "$OS" in
                    macos)
                        info "macOS without Homebrew: https://docs.docker.com/desktop/install/mac-install/"
                        info "Or install Homebrew (https://brew.sh) then re-run ./setup.sh."
                        ;;
                esac
                exit 1
                ;;
        esac
    fi

    # 6b. Fix daemon permission issue
    if [[ $DAEMON_PERM_ERR -eq 1 ]]; then
        echo ""
        warn "Docker daemon is running but '${USER}' cannot access the socket."
        info "This will run:  sudo usermod -aG docker ${USER}"
        echo ""
        if ask "Add '${USER}' to the docker group?"; then
            _add_user_to_docker_group
        else
            warn "Skipped.  Run manually:  sudo usermod -aG docker ${USER}"
            warn "Then log out and back in, or run:  newgrp docker"
        fi
    fi

    # 6c. Start daemon if not running
    if [ -n "$DOCKER_BIN" ] && [[ $DAEMON_OK -eq 0 ]] && [[ $DAEMON_PERM_ERR -eq 0 ]]; then
        echo ""
        warn "Docker is installed but the daemon does not appear to be running."
        if command -v systemctl &>/dev/null; then
            info "This will run:  sudo systemctl enable --now docker"
            echo ""
            if ask "Enable and start the Docker daemon?"; then
                _start_docker_daemon
                check_all  # re-check daemon
            else
                warn "Skipped.  Run manually:  sudo systemctl enable --now docker"
            fi
        else
            info "Start Docker Desktop or the Docker daemon for your platform."
            info "Then re-run ./setup.sh to verify."
        fi
    fi

    # 7. Final status
    header "Summary"
    local all_ok=1
    [ -n "$DOCKER_BIN" ]    || all_ok=0
    [[ $COMPOSE_OK -eq 1 ]] || all_ok=0
    [[ $DAEMON_OK -eq 1 ]]  || all_ok=0

    if [[ $all_ok -eq 1 ]]; then
        pass "Docker Engine, Compose v2, and daemon access are all ready."
        echo ""
        info "Run the full workflow:  ./run.sh"
        info "Run tests only:         ./run.sh test"
        info "Clean up after SIGKILL: ./run.sh down"
    else
        echo ""
        warn "One or more checks did not pass.  Resolve the issues above, then re-run:"
        info "  ./setup.sh"
        echo ""
        if [[ $DAEMON_PERM_ERR -eq 1 ]] || ([ -n "$DOCKER_BIN" ] && [[ $DAEMON_OK -eq 0 ]]); then
            info "If Docker was just installed or permissions just changed, log out and"
            info "back in (or run 'newgrp docker'), then re-run ./setup.sh."
        fi
        exit 1
    fi
}

main
