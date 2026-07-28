#!/usr/bin/env bash
# Install the provided LabelImg source independently from the YOLO environment.
set -Eeuo pipefail
export LC_ALL=C.utf8
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1

readonly SETUP_DIR="$HOME/Downloads/labelimg_setup"
readonly SOURCE_DIR="$HOME/Downloads/labelimg"
readonly INSTALL_DIR="$HOME/Software/labelimg"
readonly VENV_DIR="$INSTALL_DIR/.venv"
readonly SYSTEM_PYTHON="/usr/bin/python3"

SKIP_SYSTEM=false
VERIFY_ONLY=false

usage() {
    cat <<EOF
Usage: bash install_labelimg.sh [option]

Default: install LabelImg system dependencies, deploy the provided source to
$INSTALL_DIR, create its own venv, and verify the GUI offscreen.

Options:
  --skip-system  Skip apt after PyQt5 and lxml are already installed.
  --verify-only  Verify the existing LabelImg installation without changing it.
  -h, --help     Show this help.
EOF
}

while (($#)); do
    case "$1" in
        --skip-system) SKIP_SYSTEM=true ;;
        --verify-only) VERIFY_ONLY=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

if ((EUID == 0)); then
    fail "Run this script as a regular user, not through sudo. It asks for sudo only for apt."
fi

mkdir -p "$SETUP_DIR/logs"
LOG_FILE="$SETUP_DIR/logs/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'printf "\nInstallation failed at line %s. See %s\n" "$LINENO" "$LOG_FILE" >&2' ERR

[[ -x "$SYSTEM_PYTHON" ]] || fail "System Python was not found at $SYSTEM_PYTHON."
[[ "$($SYSTEM_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.10" ]] \
    || fail "LabelImg installer expects Ubuntu Python 3.10."

readonly SYSTEM_PACKAGES=(
    python3-venv
    python3-pyqt5
    python3-lxml
    libgl1
    libglib2.0-0
    libegl1
    libxcb-xinerama0
)

check_source() {
    [[ -r "$SOURCE_DIR/labelImg.py" ]] || fail "Missing LabelImg source: $SOURCE_DIR/labelImg.py"
    [[ -r "$SOURCE_DIR/libs/resources.py" ]] || fail "Missing generated Qt resources: $SOURCE_DIR/libs/resources.py"
    [[ -r "$SOURCE_DIR/data/predefined_classes.txt" ]] || fail "Missing predefined class file."
}

install_system_packages() {
    echo "Installing LabelImg Qt and XML dependencies..."
    sudo -v
    sudo apt-get update

    local simulation
    simulation="$(apt-get -s install --no-install-recommends "${SYSTEM_PACKAGES[@]}")"
    if grep -q '^The following packages will be REMOVED:' <<<"$simulation"; then
        echo "$simulation" >&2
        fail "The LabelImg package set would remove installed packages."
    fi

    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${SYSTEM_PACKAGES[@]}"
}

write_launcher() {
    cat > "$INSTALL_DIR/run_labelimg.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1

LABELIMG_FORMAT="${LABELIMG_FORMAT:-PascalVOC}"

if (($# == 1)); then
    IMAGE_DIR="$(realpath -m -- "$1")"
    if [[ ! -d "$IMAGE_DIR" ]]; then
        echo "ERROR: image directory does not exist: $IMAGE_DIR" >&2
        exit 1
    fi
    if [[ "$(basename -- "$IMAGE_DIR")" == "JPEGImages" ]]; then
        SOURCE_DIR="$(dirname -- "$IMAGE_DIR")"
        CLASS_FILE="$SOURCE_DIR/classes.names"
        SAVE_DIR="$SOURCE_DIR/Annotations"
        [[ -r "$CLASS_FILE" ]] || {
            echo "ERROR: class list does not exist: $CLASS_FILE" >&2
            exit 1
        }
        [[ -d "$SAVE_DIR" ]] || {
            echo "ERROR: annotation directory does not exist: $SAVE_DIR" >&2
            exit 1
        }
        set -- "$IMAGE_DIR" "$CLASS_FILE" "$SAVE_DIR"
    fi
fi

exec "$APP_DIR/.venv/bin/python" "$APP_DIR/labelImg.py" \
    --format "$LABELIMG_FORMAT" "$@"
EOF
    chmod 0755 "$INSTALL_DIR/run_labelimg.sh"
}

verify_labelimg() {
    local python="$VENV_DIR/bin/python"
    [[ -x "$python" ]] || fail "LabelImg venv is missing: $python"
    [[ -x "$INSTALL_DIR/run_labelimg.sh" ]] || fail "LabelImg launcher is missing."
    [[ -r "$INSTALL_DIR/libs/resources.py" ]] || fail "LabelImg Qt resources are missing."

    (
        cd "$INSTALL_DIR"
        QT_QPA_PLATFORM=offscreen env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 "$python" - <<'PY'
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.QtWidgets import QApplication
from labelImg import MainWindow
from libs import __version__
import lxml.etree

app = QApplication([])
window = MainWindow(default_prefdef_class_file="data/predefined_classes.txt")
assert window.label_hist, "LabelImg did not load predefined classes"
print(f"LabelImg={__version__}, Qt={QT_VERSION_STR}, lxml={lxml.etree.LXML_VERSION}")
print(f"predefined classes={len(window.label_hist)}")
window.close()
app.quit()
PY
    )
    echo "LabelImg offscreen window verification: OK"
}

if [[ "$VERIFY_ONLY" == true ]]; then
    verify_labelimg
    echo "Verification completed."
    exit 0
fi

check_source

if [[ "$SKIP_SYSTEM" == false ]]; then
    install_system_packages
fi

mkdir -p "$INSTALL_DIR"
# Preserve an existing customized predefined_classes.txt and other local changes.
cp -an "$SOURCE_DIR/." "$INSTALL_DIR/"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    "$SYSTEM_PYTHON" -m venv --system-site-packages "$VENV_DIR"
fi
[[ "$("$VENV_DIR/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.10" ]] \
    || fail "Existing LabelImg venv is not Python 3.10. Move $VENV_DIR aside and rerun."
grep -q '^include-system-site-packages = true$' "$VENV_DIR/pyvenv.cfg" \
    || fail "LabelImg venv must expose system PyQt5 and lxml packages."

write_launcher
verify_labelimg

echo
echo "LabelImg installation completed. Start it with:"
echo "  $INSTALL_DIR/run_labelimg.sh"
