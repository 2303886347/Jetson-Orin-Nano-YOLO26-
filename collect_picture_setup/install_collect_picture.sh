#!/usr/bin/env bash
# Install the provided collect_picture application for ROS 2 Humble.
set -Eeuo pipefail

export LC_ALL=C.UTF-8

readonly DOWNLOADS_DIR="$HOME/Downloads"
readonly SETUP_DIR="$DOWNLOADS_DIR/collect_picture_setup"
readonly SOURCE_DIR="$DOWNLOADS_DIR/collect_picture"
readonly INSTALL_DIR="$HOME/Software/collect_picture"
readonly LOG_DIR="$SETUP_DIR/logs"
readonly SYSTEM_PYTHON="/usr/bin/python3"
readonly DEFAULT_ROS_SETUP="/opt/ros/humble/setup.bash"
readonly DESKTOP_ENTRY="$HOME/.local/share/applications/collect-picture.desktop"

SKIP_SYSTEM=false
VERIFY_ONLY=false
INSTALL_DESKTOP=true

usage() {
    cat <<EOF
Usage: bash install_collect_picture.sh [option]

Default: check/install system dependencies, deploy collect_picture to
$INSTALL_DIR, create a ROS 2 launcher, add an
application-menu entry, and run an offscreen verification.

Options:
  --skip-system  Do not use apt; fail if required packages are missing.
  --verify-only  Verify the existing installation without changing it.
  --no-desktop   Do not create or update the application-menu entry.
  -h, --help     Show this help.
EOF
}

while (($#)); do
    case "$1" in
        --skip-system) SKIP_SYSTEM=true ;;
        --verify-only) VERIFY_ONLY=true ;;
        --no-desktop) INSTALL_DESKTOP=false ;;
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
    fail "Run this installer as a regular user, not through sudo. It asks for sudo only for apt."
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'printf "\nInstallation failed at line %s. See %s\n" "$LINENO" "$LOG_FILE" >&2' ERR

readonly SYSTEM_PACKAGES=(
    python3-numpy
    python3-opencv
    python3-pyqt5
    libgl1
    libegl1
    libglib2.0-0
    libxcb-xinerama0
    libxkbcommon-x11-0
    ros-humble-rclpy
    ros-humble-sensor-msgs
    ros-humble-cv-bridge
)

check_source() {
    [[ -d "$SOURCE_DIR" ]] || fail "Source directory does not exist: $SOURCE_DIR"
    [[ -r "$SOURCE_DIR/main.py" ]] || fail "Missing application entry point: $SOURCE_DIR/main.py"
    [[ -r "$SOURCE_DIR/ui.py" ]] || fail "Missing generated Qt UI: $SOURCE_DIR/ui.py"
    [[ -r "$SOURCE_DIR/config.ini" ]] || fail "Missing application configuration: $SOURCE_DIR/config.ini"
    [[ -r "$SOURCE_DIR/resources/app.png" ]] || fail "Missing application icon."
}

find_missing_packages() {
    local package
    MISSING_PACKAGES=()
    for package in "${SYSTEM_PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${db:Status-Status}\n' "$package" 2>/dev/null | grep -qx installed; then
            MISSING_PACKAGES+=("$package")
        fi
    done
}

install_missing_packages() {
    find_missing_packages
    if ((${#MISSING_PACKAGES[@]} == 0)); then
        echo "System dependencies: already installed"
        return
    fi

    echo "Missing system packages: ${MISSING_PACKAGES[*]}"
    if [[ "$SKIP_SYSTEM" == true ]]; then
        fail "Required packages are missing and --skip-system was selected."
    fi

    sudo -v
    sudo apt-get update

    local simulation
    simulation="$(apt-get -s install --no-install-recommends "${MISSING_PACKAGES[@]}")"
    if grep -q '^The following packages will be REMOVED:' <<<"$simulation"; then
        echo "$simulation" >&2
        fail "Installing dependencies would remove existing packages."
    fi

    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${MISSING_PACKAGES[@]}"
}

load_ros_environment() {
    local ros_setup="${COLLECT_PICTURE_ROS_SETUP:-$DEFAULT_ROS_SETUP}"
    [[ -r "$ros_setup" ]] || fail "ROS 2 setup file was not found: $ros_setup"

    set +u
    # shellcheck disable=SC1090
    source "$ros_setup"
    if [[ -n "${COLLECT_PICTURE_ROS_OVERLAY:-}" ]]; then
        [[ -r "$COLLECT_PICTURE_ROS_OVERLAY" ]] \
            || fail "ROS 2 overlay setup file was not found: $COLLECT_PICTURE_ROS_OVERLAY"
        # shellcheck disable=SC1090
        source "$COLLECT_PICTURE_ROS_OVERLAY"
    fi
    set -u
}

check_python_dependencies() {
    (
        unset PYTHONHOME PYTHONPATH
        export PYTHONNOUSERSITE=1
        load_ros_environment
        "$SYSTEM_PYTHON" - <<'PY'
modules = ("PyQt5", "cv2", "numpy", "rclpy", "cv_bridge", "sensor_msgs")
for name in modules:
    __import__(name)
print("Python and ROS 2 imports: OK")
PY
    )
}

write_camera_adapter() {
    if [[ -r "$SOURCE_DIR/camera.py" ]]; then
        echo "Using camera.py supplied by the source package."
        return
    fi

    cat > "$INSTALL_DIR/camera.py" <<'PY'
#!/usr/bin/env python3
"""ROS 2 image-topic adapter expected by collect_picture/main.py."""

import os
import queue

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


CAM1 = os.environ.get(
    "COLLECT_PICTURE_CAMERA_TOPIC",
    "/image_raw",
)
CAM2 = os.environ.get("COLLECT_PICTURE_CAMERA_TOPIC_2", "")

_native_spin = rclpy.spin


def _spin_without_shutdown_traceback(node, executor=None):
    try:
        _native_spin(node, executor=executor)
    except ExternalShutdownException:
        pass


rclpy.spin = _spin_without_shutdown_traceback


class CameraNode(Node):
    def __init__(self, name):
        if not rclpy.ok():
            rclpy.init(args=None)
        super().__init__(name)
        self.bridge = CvBridge()
        self.image_queue = queue.Queue(maxsize=2)
        self.image_sub = None

    def create_sub(self, image_topic):
        if not image_topic:
            raise ValueError("The camera image topic is empty.")
        self.destroy_sub()
        self.image_sub = self.create_subscription(
            Image,
            image_topic,
            self._image_callback,
            qos_profile_sensor_data,
        )
        self.get_logger().info("Subscribed to camera topic: %s" % image_topic)

    def destroy_sub(self):
        if self.image_sub is not None:
            self.destroy_subscription(self.image_sub)
            self.image_sub = None

    def _image_callback(self, ros_image):
        try:
            image = self.bridge.imgmsg_to_cv2(ros_image, desired_encoding="rgb8")
            image = np.asarray(image, dtype=np.uint8)
            if self.image_queue.full():
                try:
                    self.image_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self.image_queue.put_nowait(image)
            except queue.Full:
                pass
        except Exception as exc:
            self.get_logger().error("Unable to convert camera image: %s" % exc)

    def shutdown(self):
        self.destroy_sub()
        if rclpy.ok():
            rclpy.shutdown()
PY
    chmod 0644 "$INSTALL_DIR/camera.py"
    echo "Installed ROS 2 camera adapter: $INSTALL_DIR/camera.py"
}

write_camera_environment() {
    if [[ -e "$INSTALL_DIR/camera.env" ]]; then
        echo "Preserving existing camera configuration: $INSTALL_DIR/camera.env"
        return
    fi

    cat > "$INSTALL_DIR/camera.env" <<'EOF'
# The environment can override each value at launch time.
COLLECT_PICTURE_CAMERA_TOPIC="${COLLECT_PICTURE_CAMERA_TOPIC:-/image_raw}"
COLLECT_PICTURE_CAMERA_TOPIC_2="${COLLECT_PICTURE_CAMERA_TOPIC_2:-}"
COLLECT_PICTURE_ROS_OVERLAY="${COLLECT_PICTURE_ROS_OVERLAY:-}"
export COLLECT_PICTURE_CAMERA_TOPIC
export COLLECT_PICTURE_CAMERA_TOPIC_2
export COLLECT_PICTURE_ROS_OVERLAY
EOF
    chmod 0644 "$INSTALL_DIR/camera.env"
}

write_launcher() {
    cat > "$INSTALL_DIR/run_collect_picture.sh" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_PYTHON="/usr/bin/python3"
ROS_SETUP="${COLLECT_PICTURE_ROS_SETUP:-/opt/ros/humble/setup.bash}"

[[ -r "$APP_DIR/camera.env" ]] || {
    echo "Missing camera configuration: $APP_DIR/camera.env" >&2
    exit 1
}
[[ -r "$ROS_SETUP" ]] || {
    echo "Missing ROS 2 setup file: $ROS_SETUP" >&2
    exit 1
}

unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

# shellcheck disable=SC1091
source "$APP_DIR/camera.env"
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
if [[ -n "${COLLECT_PICTURE_ROS_OVERLAY:-}" ]]; then
    [[ -r "$COLLECT_PICTURE_ROS_OVERLAY" ]] || {
        echo "Missing ROS 2 overlay: $COLLECT_PICTURE_ROS_OVERLAY" >&2
        exit 1
    }
    # shellcheck disable=SC1090
    source "$COLLECT_PICTURE_ROS_OVERLAY"
fi
set -u

cd "$APP_DIR"
exec "$SYSTEM_PYTHON" "$APP_DIR/main.py" "$@"
EOF
    chmod 0755 "$INSTALL_DIR/run_collect_picture.sh"
}

write_desktop_entry() {
    [[ "$INSTALL_DESKTOP" == true ]] || return

    cat > "$INSTALL_DIR/collect-picture.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Collect Picture
Name[zh_CN]=图片采集
Comment=Collect images from a ROS 2 camera topic
Comment[zh_CN]=从 ROS 2 相机话题采集图片
Exec=$INSTALL_DIR/run_collect_picture.sh
Icon=$INSTALL_DIR/resources/app.png
Terminal=false
Categories=Graphics;Photography;
StartupNotify=true
EOF
    chmod 0644 "$INSTALL_DIR/collect-picture.desktop"

    mkdir -p "$(dirname -- "$DESKTOP_ENTRY")"
    install -m 0644 "$INSTALL_DIR/collect-picture.desktop" "$DESKTOP_ENTRY"
    echo "Application-menu entry: $DESKTOP_ENTRY"
}

deploy_application() {
    check_source
    [[ ! -L "$INSTALL_DIR" ]] || fail "Refusing to install through a symbolic-link directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"

    # Update program files while preserving settings written by the application.
    rsync -a --exclude 'config.ini' --exclude '__pycache__/' "$SOURCE_DIR/" "$INSTALL_DIR/"
    if [[ ! -e "$INSTALL_DIR/config.ini" ]]; then
        install -m 0644 "$SOURCE_DIR/config.ini" "$INSTALL_DIR/config.ini"
    else
        echo "Preserving existing application settings: $INSTALL_DIR/config.ini"
    fi

    write_camera_adapter
    write_camera_environment
    write_launcher
    write_desktop_entry
}

verify_installation() {
    [[ -r "$INSTALL_DIR/main.py" ]] || fail "Installed main.py is missing."
    [[ -r "$INSTALL_DIR/ui.py" ]] || fail "Installed ui.py is missing."
    [[ -r "$INSTALL_DIR/camera.py" ]] || fail "Installed camera adapter is missing."
    [[ -r "$INSTALL_DIR/camera.env" ]] || fail "Camera configuration is missing."
    [[ -x "$INSTALL_DIR/run_collect_picture.sh" ]] || fail "Launcher is missing or not executable."

    "$SYSTEM_PYTHON" -m py_compile \
        "$INSTALL_DIR/main.py" \
        "$INSTALL_DIR/ui.py" \
        "$INSTALL_DIR/camera.py"

    (
        unset PYTHONHOME PYTHONPATH
        export PYTHONNOUSERSITE=1
        # shellcheck disable=SC1090
        source "$INSTALL_DIR/camera.env"
        load_ros_environment

        COLLECT_PICTURE_INSTALL_DIR="$INSTALL_DIR" \
        QT_QPA_PLATFORM=offscreen \
        "$SYSTEM_PYTHON" - <<'PY'
import os
import sys

import numpy as np

app_dir = os.environ["COLLECT_PICTURE_INSTALL_DIR"]
sys.path.insert(0, app_dir)

import camera
import ui
from PyQt5.QtWidgets import QApplication, QWidget

assert camera.CAM1, "The primary camera topic is empty"
node = camera.CameraNode("collect_picture_install_check")
node.create_sub(camera.CAM1)
test_bgr = np.array([[[10, 20, 30]]], dtype=np.uint8)
test_message = node.bridge.cv2_to_imgmsg(test_bgr, encoding="bgr8")
node._image_callback(test_message)
test_rgb = node.image_queue.get_nowait()
assert test_rgb.tolist() == [[[30, 20, 10]]], "BGR-to-RGB conversion failed"
node.destroy_sub()
node.destroy_node()
if camera.rclpy.ok():
    camera.rclpy.shutdown()

qt_app = QApplication([])
widget = QWidget()
form = ui.Ui_Form()
form.setupUi(widget)
assert form.label_display.width() == 640
assert form.label_display.height() == 480
widget.close()
qt_app.quit()

print("ROS 2 node construction: OK")
print("ROS image conversion: OK")
print("Qt offscreen UI construction: OK")
print("Primary camera topic: %s" % camera.CAM1)
print("Secondary camera topic: %s" % (camera.CAM2 or "disabled"))
PY
    )

    if [[ "$INSTALL_DESKTOP" == true && -r "$DESKTOP_ENTRY" ]] \
        && command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$DESKTOP_ENTRY"
    fi

    echo "Installation verification: OK"
}

if [[ "$VERIFY_ONLY" == true ]]; then
    check_python_dependencies
    verify_installation
    echo "Verification completed."
    exit 0
fi

install_missing_packages
check_python_dependencies
deploy_application
verify_installation

echo
echo "collect_picture installation completed."
echo "Start the camera publisher first, then run:"
echo "  $INSTALL_DIR/run_collect_picture.sh"
echo "Installation log: $LOG_FILE"
