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
#                         (Ubuntu ≥ 20.04 focal; Debian ≥ 11 bullseye)
#   RHEL / Fedora /
#   CentOS / Rocky /
#   AlmaLinux           — Docker's official dnf repository
#                         (Fedora repo for Fedora; RHEL repo for the rest)
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

ask_yes() {
    # ask_yes PROMPT — requires the user to type the word 'yes'; returns 0 for yes, 1 for no.
    # Use this for operations that grant elevated or root-equivalent access.
    local prompt="$1"
    local reply
    echo -en "  ${YELLOW}?${NC} ${prompt} (type 'yes' to confirm): "
    read -r reply
    [[ "$reply" == "yes" ]]
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
            # WSL2 / WSL1 — check before other Linux detection
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
    DOCKER_BIN=""; DOCKER_VERSION=""; COMPOSE_OK=0; DAEMON_OK=0; DAEMON_PERM_ERR=0

    # Docker binary
    if command -v docker &>/dev/null; then
        DOCKER_BIN="$(command -v docker)"
        DOCKER_VERSION="$(docker --version 2>/dev/null | head -1)" \
            || DOCKER_VERSION="(version unavailable)"
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

# --- Prerequisite: sudo ---

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

# --- apt-based installation helpers ---

# Docker's apt repository supports these release codenames.
# A codename not in this list may not have packages yet; installation will
# likely fail.  Add new releases as Docker publishes them.
_APT_KNOWN_CODENAMES=(
    # Ubuntu
    focal jammy mantic noble oracular
    # Debian
    bullseye bookworm trixie
)

_apt_distro_id() {
    # Returns the Docker repository path identifier for this distro.
    . /etc/os-release 2>/dev/null || true
    case "${ID:-}" in
        ubuntu) echo "ubuntu" ;;
        *)      echo "debian" ;;
    esac
}

_apt_check_codename() {
    # Validates VERSION_CODENAME; sets version_codename in caller's scope.
    . /etc/os-release 2>/dev/null || true
    version_codename="${VERSION_CODENAME:-}"
    if [ -z "$version_codename" ]; then
        fail "Could not determine VERSION_CODENAME from /etc/os-release."
        info "Install Docker manually: https://docs.docker.com/engine/install/$(_apt_distro_id)/"
        return 1
    fi
    local known=0
    local c
    for c in "${_APT_KNOWN_CODENAMES[@]}"; do
        [[ "$c" == "$version_codename" ]] && known=1 && break
    done
    if [[ $known -eq 0 ]]; then
        warn "Release codename '${version_codename}' is not in the list of"
        warn "known-supported Docker apt releases.  Installation may fail."
        info "Known Ubuntu: focal/20.04 jammy/22.04 noble/24.04 oracular/24.10"
        info "Known Debian: bullseye/11 bookworm/12 trixie/13"
        if [[ $CHECK_ONLY -eq 1 ]]; then
            warn "Cannot verify compatibility in check-only mode."
        elif ! ask "Continue installation for '${version_codename}' anyway?"; then
            warn "Installation cancelled."
            return 1
        fi
    fi
    return 0
}

_install_docker_apt() {
    # Install Docker Engine via Docker's official apt repository.
    # GPG key downloaded to file with curl (NOT curl-pipe-shell).
    # https://docs.docker.com/engine/install/ubuntu/
    # https://docs.docker.com/engine/install/debian/
    local apt_distro_id version_codename
    apt_distro_id="$(_apt_distro_id)"
    _apt_check_codename || return 1
    _require_sudo || return 1

    echo ""
    info "--- 1/4: install prerequisites ---"
    # Wrap each install phase in a subshell with set -e so any command
    # failure stops immediately and is caught as a whole-step failure.
    (set -e
        sudo apt-get update -qq
        sudo apt-get install -y ca-certificates curl
    ) || { fail "Step 1/4 failed: could not install prerequisites."; return 1; }

    info "--- 2/4: add Docker's GPG signing key ---"
    info "    (curl downloads key to file; NOT a curl-pipe-shell installer)"
    (set -e
        sudo install -m 0755 -d /etc/apt/keyrings
        sudo curl -fsSL "https://download.docker.com/linux/${apt_distro_id}/gpg" \
            -o /etc/apt/keyrings/docker.asc
        sudo chmod a+r /etc/apt/keyrings/docker.asc
    ) || { fail "Step 2/4 failed: could not add Docker GPG key."; return 1; }

    info "--- 3/4: add Docker apt repository ---"
    (set -e
        local arch
        arch="$(dpkg --print-architecture)"
        echo \
            "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc]" \
            "https://download.docker.com/linux/${apt_distro_id}" \
            "${version_codename} stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update -qq
    ) || { fail "Step 3/4 failed: could not add Docker apt repository."; return 1; }

    info "--- 4/4: install Docker Engine and Compose plugin ---"
    (set -e
        sudo apt-get install -y \
            docker-ce \
            docker-ce-cli \
            containerd.io \
            docker-buildx-plugin \
            docker-compose-plugin
    ) || { fail "Step 4/4 failed: could not install Docker Engine packages."; return 1; }

    pass "Docker Engine and Compose plugin installed."
}

_install_compose_plugin_apt() {
    _require_sudo || return 1
    (set -e
        sudo apt-get update -qq
        sudo apt-get install -y docker-compose-plugin
    ) || { fail "Could not install docker-compose-plugin."; return 1; }
    pass "Docker Compose plugin installed."
}

# --- dnf-based installation helpers ---

_dnf_docker_repo_url() {
    # Fedora has its own Docker repository; RHEL-compatible distros use the RHEL repo.
    # https://docs.docker.com/engine/install/fedora/
    # https://docs.docker.com/engine/install/rhel/
    if [ "$DISTRO" = "fedora" ]; then
        echo "https://download.docker.com/linux/fedora/docker-ce.repo"
    else
        echo "https://download.docker.com/linux/rhel/docker-ce.repo"
    fi
}

_install_docker_dnf() {
    # Install Docker Engine via Docker's official dnf repository.
    local repo_url
    repo_url="$(_dnf_docker_repo_url)"
    _require_sudo || return 1

    echo ""
    info "--- 1/2: add Docker dnf repository ---"
    info "    Repository: $repo_url"
    (set -e
        sudo dnf -y install dnf-plugins-core
        sudo dnf config-manager --add-repo "$repo_url"
    ) || { fail "Step 1/2 failed: could not add Docker dnf repository."; return 1; }

    info "--- 2/2: install Docker Engine and Compose plugin ---"
    (set -e
        sudo dnf -y install \
            docker-ce \
            docker-ce-cli \
            containerd.io \
            docker-buildx-plugin \
            docker-compose-plugin
    ) || { fail "Step 2/2 failed: could not install Docker Engine packages."; return 1; }

    pass "Docker Engine and Compose plugin installed."
}

_install_compose_plugin_dnf() {
    _require_sudo || return 1
    (set -e
        sudo dnf -y install docker-compose-plugin
    ) || { fail "Could not install docker-compose-plugin."; return 1; }
    pass "Docker Compose plugin installed."
}

# --- macOS installation helper ---

_install_docker_brew() {
    (set -e
        brew install --cask docker
    ) || { fail "brew install --cask docker failed."; return 1; }
    pass "Docker Desktop installed via Homebrew."
    warn "Start Docker Desktop from Applications before running ./run.sh."
}

# --- Docker group: requires explicit security acknowledgement ---

_add_user_to_docker_group() {
    echo ""
    warn "SECURITY: The 'docker' group grants root-equivalent access."
    warn "Group members can run containers that mount the host filesystem or"
    warn "bypass container isolation, with the same effect as unrestricted sudo."
    info "Only add users who already have unrestricted sudo access on this host."
    echo ""
    info "This will run:  sudo usermod -aG docker ${USER}"
    echo ""
    if [[ $CHECK_ONLY -eq 1 ]]; then
        warn "Check-only mode: group change skipped."
        info "Run 'sudo usermod -aG docker ${USER}' manually after reviewing the"
        info "security implications above."
        return 1
    fi
    if ! ask_yes "Add '${USER}' to the docker group (acknowledging root-equivalent access)?"; then
        warn "Skipped."
        info "Run manually when ready:  sudo usermod -aG docker ${USER}"
        info "Then log out and back in, or run:  newgrp docker"
        return 1
    fi
    _require_sudo || return 1
    (set -e
        sudo usermod -aG docker "${USER}"
    ) || { fail "Failed to add '${USER}' to the docker group."; return 1; }
    pass "Added '${USER}' to the docker group."
    warn "Log out and back in (or run 'newgrp docker') for the change to take effect."
    warn "Re-run ./setup.sh to verify daemon access after re-login."
}

# --- Daemon start helper ---

_start_docker_daemon() {
    if ! command -v systemctl &>/dev/null; then
        warn "Cannot determine how to start the Docker daemon on this platform."
        info "Start Docker manually, then re-run ./setup.sh."
        return 1
    fi
    _require_sudo || return 1
    (set -e
        sudo systemctl enable --now docker
    ) || { fail "Failed to start the Docker daemon."; return 1; }
    pass "Docker daemon started and enabled."
}

# --- Installation descriptions shown before confirmation ---

_describe_apt_install() {
    local apt_distro_id
    apt_distro_id="$(_apt_distro_id)"
    info "Will install Docker Engine via Docker's official apt repository:"
    info "  sudo apt-get install  ca-certificates curl"
    info "  curl (file download only, not a script):"
    info "    https://download.docker.com/linux/${apt_distro_id}/gpg"
    info "    → /etc/apt/keyrings/docker.asc"
    info "  Adds Docker ${apt_distro_id} repository to /etc/apt/sources.list.d/docker.list"
    info "  sudo apt-get install  docker-ce docker-ce-cli containerd.io"
    info "                        docker-buildx-plugin docker-compose-plugin"
}

_describe_dnf_install() {
    local repo_url
    repo_url="$(_dnf_docker_repo_url)"
    info "Will install Docker Engine via Docker's official dnf repository:"
    info "  sudo dnf install  dnf-plugins-core"
    info "  sudo dnf config-manager --add-repo  $repo_url"
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

    # WSL: Docker Desktop for Windows owns the daemon
    if [ "$OS" = "windows_wsl" ]; then
        echo ""
        warn "WSL2 detected.  Docker Desktop for Windows provides the daemon to WSL."
        info "  1. Install Docker Desktop for Windows:"
        info "     https://docs.docker.com/desktop/wsl/"
        info "  2. Enable WSL integration: Settings → Resources → WSL Integration"
        info "  3. Re-run ./setup.sh from WSL to verify daemon access."
        exit 1
    fi

    # 2. Check all three components
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
    elif [ -n "$DOCKER_BIN" ]; then
        fail "'docker compose' (Compose v2) not available."
        info "The standalone 'docker-compose' v1 binary is NOT compatible with ./run.sh."
        case "$PKG_MGR" in
            apt) info "To install:  sudo apt-get install docker-compose-plugin" ;;
            dnf) info "To install:  sudo dnf install docker-compose-plugin" ;;
        esac
    else
        warn "Compose check skipped (Docker binary not found)."
    fi

    header "Docker daemon"
    if [[ $DAEMON_OK -eq 1 ]]; then
        pass "Daemon is accessible."
    elif [[ $DAEMON_PERM_ERR -eq 1 ]]; then
        fail "Daemon is running but '${USER}' cannot access the Docker socket."
        warn "SECURITY: The 'docker' group grants root-equivalent access."
        info "Only proceed if '${USER}' already has unrestricted sudo on this host."
    elif [ -n "$DOCKER_BIN" ]; then
        fail "Daemon is not running or not accessible."
    else
        warn "Daemon check skipped (Docker binary not found)."
    fi

    # 4. If everything is fine, report and exit
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
                    case "$OS" in
                        macos)
                            info "macOS without Homebrew: https://docs.docker.com/desktop/install/mac-install/"
                            ;;
                    esac
                    ;;
            esac
        elif [[ $COMPOSE_OK -eq 0 ]]; then
            case "$PKG_MGR" in
                apt) info "To install Compose plugin:  sudo apt-get install docker-compose-plugin" ;;
                dnf) info "To install Compose plugin:  sudo dnf install docker-compose-plugin" ;;
            esac
        fi
        if [[ $DAEMON_PERM_ERR -eq 1 ]]; then
            echo ""
            warn "SECURITY: The 'docker' group grants root-equivalent access."
            info "Only add '${USER}' if they already have unrestricted sudo on this host."
            info "Command:  sudo usermod -aG docker ${USER}"
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

    # 6. Interactive: offer to fix each issue in order

    # 6a. Install Docker Engine if missing
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
                    esac || {
                        echo ""
                        fail "Docker installation failed.  Resolve the error above and re-run:"
                        info "  ./setup.sh"
                        exit 1
                    }
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
                    linux)
                        info "Linux without a supported package manager: see the Docker docs"
                        info "for your distribution at https://docs.docker.com/engine/install/"
                        ;;
                esac
                exit 1
                ;;
        esac
    fi

    # 6b. Install Compose plugin if Docker present but Compose missing
    if [ -n "$DOCKER_BIN" ] && [[ $COMPOSE_OK -eq 0 ]]; then
        echo ""
        warn "Docker is installed but 'docker compose' (Compose v2) is not available."
        case "$PKG_MGR" in
            apt)
                info "This will run:  sudo apt-get install docker-compose-plugin"
                echo ""
                if ask "Install the Docker Compose plugin now?"; then
                    _install_compose_plugin_apt || {
                        fail "Compose plugin installation failed.  Resolve the error and re-run:"
                        info "  ./setup.sh"
                        exit 1
                    }
                    check_all
                else
                    warn "Skipped.  Run manually:  sudo apt-get install docker-compose-plugin"
                fi
                ;;
            dnf)
                info "This will run:  sudo dnf install docker-compose-plugin"
                echo ""
                if ask "Install the Docker Compose plugin now?"; then
                    _install_compose_plugin_dnf || {
                        fail "Compose plugin installation failed.  Resolve the error and re-run:"
                        info "  ./setup.sh"
                        exit 1
                    }
                    check_all
                else
                    warn "Skipped.  Run manually:  sudo dnf install docker-compose-plugin"
                fi
                ;;
            *)
                info "Install the Compose plugin for your platform and re-run ./setup.sh."
                ;;
        esac
    fi

    # 6c. Fix daemon socket permission error
    if [[ $DAEMON_PERM_ERR -eq 1 ]]; then
        _add_user_to_docker_group || true
    fi

    # 6d. Start daemon if not running (and no permission error)
    if [ -n "$DOCKER_BIN" ] && [[ $DAEMON_OK -eq 0 ]] && [[ $DAEMON_PERM_ERR -eq 0 ]]; then
        echo ""
        warn "Docker is installed but the daemon does not appear to be running."
        if command -v systemctl &>/dev/null; then
            info "This will run:  sudo systemctl enable --now docker"
            echo ""
            if ask "Enable and start the Docker daemon?"; then
                _start_docker_daemon || {
                    fail "Failed to start the daemon.  Resolve the error and re-run:"
                    info "  ./setup.sh"
                    exit 1
                }
                check_all
            else
                warn "Skipped.  Run manually:  sudo systemctl enable --now docker"
            fi
        else
            info "Start Docker Desktop or the Docker daemon for your platform."
            info "Then re-run ./setup.sh to verify."
        fi
    fi

    # 7. Final summary
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

# Run only when executed directly, not when sourced (e.g. from tests).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi
