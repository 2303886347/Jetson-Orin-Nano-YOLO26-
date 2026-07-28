#!/usr/bin/env bash
# Install the CUDA 12.6 YOLO26 environment for this Jetson host.
set -Eeuo pipefail
export LC_ALL=C.utf8
# Do not let a previously activated Python environment affect pip resolution.
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1

readonly SETUP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${YOLO26_VENV_DIR:-$HOME/.venvs/yolo26}"
readonly YOLO_ENGINE_DIR="$(cd "$SETUP_DIR/.." && pwd)"
readonly SYSTEM_PYTHON="/usr/bin/python3"
readonly PRIMARY_INDEX="${YOLO_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
readonly FALLBACK_INDEX="https://pypi.org/simple"
readonly DLA_FALLBACK_DIR="$SETUP_DIR/local-l4t-dla/usr/lib/aarch64-linux-gnu/nvidia"
readonly DLA_FALLBACK_LIB="$DLA_FALLBACK_DIR/libnvdla_compiler.so"
readonly DLA_FALLBACK_SHA256="c21986bed8d48a5ef11928aa54a500cd14a997d1d0bed99edf4d161d1c778bec"
readonly DLA_PACKAGE="$SETUP_DIR/packages/nvidia-l4t-dla-compiler_36.4.7-20250918154033_arm64.deb"
readonly DLA_PACKAGE_SHA256="676e43d47472a7d486e4dac0ae8e0924c62910d1a2dd4be3acfdb65f75f26564"

SKIP_SYSTEM=false
SKIP_OPTIONAL=false
VERIFY_ONLY=false
YOLO26_PROJECT_DIR=""
YOLO_MODEL_PATH=""
WHEEL_DIR=""

usage() {
    cat <<'EOF'
Usage: bash install_yolo26.sh [option]

Default: install the Jetson GPU runtime, create/update the YOLO26 Python
environment, and run verification.

Options:
  --skip-system    Do not run apt. Requires CUDA/cuDNN/TensorRT and system/local DLA.
  --skip-optional  Skip torchao, PyCUDA, and onnxruntime-gpu.
  --verify-only    Verify an already installed environment without changing packages.
  -h, --help       Show this help.

Wheel lookup order:
  1. YOLO_WHEEL_DIR
  2. <YOLO26>/setup/wheels
  3. $HOME/Downloads
EOF
}

while (($#)); do
    case "$1" in
        --skip-system) SKIP_SYSTEM=true ;;
        --skip-optional) SKIP_OPTIONAL=true ;;
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

warn() {
    echo "WARNING: $*" >&2
}

resolve_wheel_dir() {
    local candidate
    if [[ -n "${YOLO_WHEEL_DIR:-}" ]]; then
        candidate="$(cd -- "$YOLO_WHEEL_DIR" 2>/dev/null && pwd)" \
            || fail "YOLO_WHEEL_DIR does not exist: $YOLO_WHEEL_DIR"
        WHEEL_DIR="$candidate"
        return
    fi

    for candidate in "$SETUP_DIR/wheels" "$HOME/Downloads"; do
        if [[ -r "$candidate/torch-2.7.0-cp310-cp310-linux_aarch64.whl" ]]; then
            WHEEL_DIR="$candidate"
            return
        fi
    done

    WHEEL_DIR="$SETUP_DIR/wheels"
}

resolve_yolo_paths() {
    local root
    if [[ -n "${YOLO26_ROOT:-}" ]]; then
        root="$(cd -- "$YOLO26_ROOT" 2>/dev/null && pwd)" \
            || fail "YOLO26_ROOT does not exist: $YOLO26_ROOT"
        [[ -r "$root/models/pretrained/yolo26n.pt" ]] \
            || fail "YOLO26_ROOT has no models/pretrained/yolo26n.pt: $root"
        YOLO26_PROJECT_DIR="$root"
        YOLO_MODEL_PATH="$root/models/pretrained/yolo26n.pt"
        return
    fi

    for root in \
        "$SETUP_DIR/.." \
        "$HOME/ros2_ws/src/YOLO26" \
        "$HOME/YOLO26"
    do
        if [[ -r "$root/models/pretrained/yolo26n.pt" ]]; then
            YOLO26_PROJECT_DIR="$root"
            YOLO_MODEL_PATH="$root/models/pretrained/yolo26n.pt"
            return
        fi
    done

    fail "Unable to find YOLO26. Set YOLO26_ROOT or place the project at $HOME/ros2_ws/src/YOLO26."
}

if ((EUID == 0)); then
    fail "Run this script as a regular user, not through sudo. It asks for sudo only for apt."
fi

mkdir -p "$SETUP_DIR/logs"
LOG_FILE="$SETUP_DIR/logs/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'printf "\nInstallation failed at line %s. See %s\n" "$LINENO" "$LOG_FILE" >&2' ERR

echo "YOLO26 installer log: $LOG_FILE"
echo "Host: $(uname -a)"

if [[ "$(uname -m)" != "aarch64" ]]; then
    fail "This installer is for the supplied aarch64 wheels, but this host is $(uname -m)."
fi

[[ -x "$SYSTEM_PYTHON" ]] || fail "System Python was not found at $SYSTEM_PYTHON."
PYTHON_MAJOR_MINOR="$($SYSTEM_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYTHON_MAJOR_MINOR" != "3.10" ]]; then
    fail "This installer requires Python 3.10 for the supplied cp310 wheels; found Python $PYTHON_MAJOR_MINOR."
fi

if ! dpkg-query -W -f='${Status}' nvidia-l4t-core 2>/dev/null | grep -q 'install ok installed'; then
    fail "NVIDIA L4T is not installed. This script is intended for the Jetson host that supplied the wheels."
fi
L4T_VERSION="$(dpkg-query -W -f='${Version}' nvidia-l4t-core)"
[[ "$L4T_VERSION" == 36.4.7-* ]] || fail "This installer supports L4T R36.4.7; found $L4T_VERSION."

if [[ "$VERIFY_ONLY" == false ]]; then
    REQUIRED_KB=15728640
    REQUIRED_GIB=15
    if [[ -x "$VENV_DIR/bin/python" && -x /usr/local/cuda-12.6/bin/nvcc ]] \
        && "$VENV_DIR/bin/python" -c 'import torch; assert torch.__version__.split("+")[0] == "2.7.0"' >/dev/null 2>&1; then
        # A repaired/repeated install reuses the multi-gigabyte CUDA and torch payloads.
        REQUIRED_KB=2097152
        REQUIRED_GIB=2
    fi
    AVAILABLE_KB="$(df -Pk "$HOME" | awk 'NR == 2 {print $4}')"
    if ((AVAILABLE_KB < REQUIRED_KB)); then
        fail "At least $REQUIRED_GIB GiB of free disk space is required; only $((AVAILABLE_KB / 1024 / 1024)) GiB is available."
    fi
fi

declare -Ar WHEEL_SHA256=(
    ["onnxruntime_gpu-1.22.0-cp310-cp310-linux_aarch64.whl"]="869e41abdc35e09345876f047fce49267d699df3e44b67c2518b0469739484ff"
    ["pycuda-2024.1.2-cp310-cp310-linux_aarch64.whl"]="97de894e562ead63d6fa3aa79d4c947ed7cd9fd75cc8920b712475cc6ff69b7f"
    ["torch-2.7.0-cp310-cp310-linux_aarch64.whl"]="6eff643c0a7acda92734cc798338f733ff35c7df1a4434576f5ff7c66fc97319"
    ["torchao-0.11.0+git173d38f-cp39-abi3-linux_aarch64.whl"]="12dea2023c3d1b73fa8df77427db1459e2a201aa9af0043c327752ecc7b813f5"
    ["torchaudio-2.7.0-cp310-cp310-linux_aarch64.whl"]="c59026d500c573666ae0437c4202ac312ac8ebe38fa12dbb37250a07c1e826f9"
    ["torchvision-0.22.0-cp310-cp310-linux_aarch64.whl"]="daabff3a0725996886b92e4b5dd143f5750ef4b181b5c7d01371a9185e8f0402"
)

check_wheels() {
    echo "Checking supplied wheel files and SHA256 values in: $WHEEL_DIR"
    local filename expected actual
    for filename in "${!WHEEL_SHA256[@]}"; do
        if [[ "$SKIP_OPTIONAL" == true ]]; then
            case "$filename" in
                onnxruntime_gpu-*|pycuda-*|torchao-*) continue ;;
            esac
        fi
        [[ -r "$WHEEL_DIR/$filename" ]] || fail "Missing wheel: $WHEEL_DIR/$filename"
        expected="${WHEEL_SHA256[$filename]}"
        actual="$(sha256sum "$WHEEL_DIR/$filename" | awk '{print $1}')"
        [[ "$actual" == "$expected" ]] || fail "SHA256 mismatch for $filename. Do not install a changed file without auditing it."
    done
}

check_yolo_model() {
    [[ -n "$YOLO_MODEL_PATH" ]] || resolve_yolo_paths
    [[ -r "$YOLO_MODEL_PATH" ]] || fail "Missing YOLO26 model: $YOLO_MODEL_PATH"
    echo "YOLO26 project: $YOLO26_PROJECT_DIR"
    echo "YOLO26 verification model: $YOLO_MODEL_PATH"
}

readonly SYSTEM_PACKAGES=(
    cuda-toolkit-12-6
    libcudnn9-cuda-12
    libcudnn9-dev-cuda-12
    tensorrt
    nvidia-l4t-dla-compiler
    python3-venv
    python3-dev
    build-essential
    libopenblas-dev
    libjpeg-dev
    zlib1g-dev
    libsox-dev
    libgl1
    libglib2.0-0
    libegl1
    libxcb-xinerama0
)

configure_cuda_environment() {
    if [[ -x /usr/local/cuda-12.6/bin/nvcc ]]; then
        export CUDA_HOME="/usr/local/cuda-12.6"
    elif [[ -x /usr/local/cuda/bin/nvcc ]]; then
        export CUDA_HOME="/usr/local/cuda"
    else
        fail "CUDA Toolkit 12.6 was not found under /usr/local/cuda or /usr/local/cuda-12.6."
    fi
    export PATH="$CUDA_HOME/bin:$PATH"
    export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    "$CUDA_HOME/bin/nvcc" --version | grep -q 'release 12\.6' || fail "CUDA at $CUDA_HOME is not release 12.6."
}

dla_fallback_is_valid() {
    [[ -r "$DLA_FALLBACK_LIB" && -r "$DLA_PACKAGE" ]] || return 1
    [[ "$(sha256sum "$DLA_FALLBACK_LIB" | awk '{print $1}')" == "$DLA_FALLBACK_SHA256" ]] || return 1
    [[ "$(sha256sum "$DLA_PACKAGE" | awk '{print $1}')" == "$DLA_PACKAGE_SHA256" ]]
}

system_packages_present() {
    local package
    for package in "${SYSTEM_PACKAGES[@]}"; do
        if [[ "$package" == "nvidia-l4t-dla-compiler" ]] && dla_fallback_is_valid; then
            continue
        fi
        if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
            return 1
        fi
    done
}

configure_dla_environment() {
    if ldconfig -p | grep 'libnvdla_compiler.so' >/dev/null; then
        return 0
    fi

    dla_fallback_is_valid || fail "Jetson DLA compiler runtime is unavailable and the local NVIDIA fallback is missing or invalid."

    export LD_LIBRARY_PATH="$DLA_FALLBACK_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    echo "Using the verified local NVIDIA DLA runtime fallback: $DLA_FALLBACK_LIB"
}

check_system_stack() {
    configure_cuda_environment
    configure_dla_environment
    command -v nvcc >/dev/null || fail "nvcc is unavailable. Install cuda-toolkit-12-6."
    ldconfig -p | grep 'libcudart.so.12' >/dev/null || fail "CUDA runtime 12 is unavailable."
    ldconfig -p | grep 'libcudnn.so.9' >/dev/null || fail "cuDNN 9 is unavailable."
    ldconfig -p | grep 'libnvinfer.so.10' >/dev/null || fail "TensorRT 10 is unavailable."
}

install_system_packages() {
    echo "Installing the Jetson CUDA 12.6, cuDNN 9, and TensorRT 10 runtime..."
    sudo -v
    sudo apt-get update

    local simulation
    simulation="$(apt-get -s install --no-install-recommends "${SYSTEM_PACKAGES[@]}")"
    if grep -q '^The following packages will be REMOVED:' <<<"$simulation"; then
        echo "$simulation" >&2
        fail "The selected package set would remove installed packages. Stop and inspect apt before continuing."
    fi

    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${SYSTEM_PACKAGES[@]}"
    check_system_stack
}

pip_online() {
    if "$PYTHON" -m pip install --disable-pip-version-check --prefer-binary --only-binary=:all: --index-url "$PRIMARY_INDEX" "$@"; then
        return 0
    fi
    warn "The Tsinghua mirror failed for this request; retrying with PyPI."
    "$PYTHON" -m pip install --disable-pip-version-check --prefer-binary --only-binary=:all: --index-url "$FALLBACK_INDEX" "$@"
}

create_or_check_venv() {
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        echo "Creating Jetson system-package-visible virtual environment: $VENV_DIR"
        "$SYSTEM_PYTHON" -m venv --system-site-packages "$VENV_DIR"
    fi
    PYTHON="$VENV_DIR/bin/python"
    [[ "$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.10" ]] || fail "Existing virtual environment is not Python 3.10."
    if ! grep -q '^include-system-site-packages = true$' "$VENV_DIR/pyvenv.cfg"; then
        fail "Existing virtual environment does not expose Jetson system Python packages such as TensorRT. Move $VENV_DIR aside and rerun."
    fi
}

write_constraints() {
    CONSTRAINTS_FILE="$SETUP_DIR/constraints-yolo26-py310.txt"
    cat > "$CONSTRAINTS_FILE" <<'EOF'
pip==26.1.2
setuptools==79.0.1
wheel==0.47.0
packaging==26.2
cffi==1.17.1
pycparser==3.0
numpy==1.26.4
scipy==1.15.3
opencv-python==4.11.0.86
ultralytics==8.4.104
openvino==2025.4.1
filelock==3.32.0
typing-extensions==4.16.0
sympy==1.14.0
mpmath==1.3.0
networkx==3.4.2
jinja2==3.1.6
fsspec==2026.6.0
pillow==12.3.0
polars==1.43.0
polars-runtime-32==1.43.0
nvidia-ml-py==13.610.43
ultralytics-thop==2.0.20
openvino-telemetry==2025.2.0
onnx==1.22.0
onnxslim==0.1.94
protobuf==7.35.1
ml-dtypes==0.5.4
scikit-learn==1.7.2
joblib==1.5.3
threadpoolctl==3.6.0
onnxruntime-gpu==1.22.0
coloredlogs==15.0.1
flatbuffers==25.12.19
humanfriendly==10.0
pycuda==2024.1.2
pytools==2026.1.1
platformdirs==4.11.0
siphash24==1.8
EOF
}

install_python_packages() {
    echo "Installing Python packages into $VENV_DIR..."
    pip_online --upgrade \
        'pip==26.1.2' \
        'setuptools==79.0.1' \
        'wheel==0.47.0' \
        'packaging==26.2' \
        'cffi==1.17.1' \
        'pycparser==3.0'

    # Install runtime requirements first, then keep local torch wheels isolated from the resolver.
    pip_online --upgrade -c "$CONSTRAINTS_FILE" \
        'numpy==1.26.4' \
        'filelock==3.32.0' \
        'typing-extensions==4.16.0' \
        'sympy==1.14.0' \
        'packaging==26.2' \
        'cffi==1.17.1' \
        'scipy==1.15.3' \
        'networkx==3.4.2' \
        'jinja2==3.1.6' \
        'fsspec==2026.6.0' \
        'pillow==12.3.0'

    "$PYTHON" -m pip install --disable-pip-version-check --upgrade --no-deps \
        "$WHEEL_DIR/torch-2.7.0-cp310-cp310-linux_aarch64.whl" \
        "$WHEEL_DIR/torchvision-0.22.0-cp310-cp310-linux_aarch64.whl" \
        "$WHEEL_DIR/torchaudio-2.7.0-cp310-cp310-linux_aarch64.whl"

    # Do not use --no-deps here: this is the corrected form of the command from yolo_engine/README.md.
    pip_online --upgrade -c "$CONSTRAINTS_FILE" \
        'opencv-python==4.11.0.86' \
        'ultralytics==8.4.104' \
        'openvino==2025.4.1' \
        'onnx==1.22.0' \
        'onnxslim==0.1.94' \
        'scikit-learn==1.7.2'

    if [[ "$SKIP_OPTIONAL" == false ]]; then
        pip_online --upgrade -c "$CONSTRAINTS_FILE" \
            "$WHEEL_DIR/onnxruntime_gpu-1.22.0-cp310-cp310-linux_aarch64.whl" \
            "$WHEEL_DIR/pycuda-2024.1.2-cp310-cp310-linux_aarch64.whl"
        "$PYTHON" -m pip install --disable-pip-version-check --upgrade --no-deps \
            "$WHEEL_DIR/torchao-0.11.0+git173d38f-cp39-abi3-linux_aarch64.whl"
    fi

    check_python_dependencies
}

check_python_dependencies() {
    echo "Checking Python package dependency metadata..."
    "$PYTHON" -m pip check
}

write_activation_script() {
    local activation_script="$SETUP_DIR/activate_yolo26.sh"
    cat > "$activation_script" <<EOF
#!/usr/bin/env bash

source "$VENV_DIR/bin/activate"

YOLO26_SETUP_DIR="\$(cd -- "\$(dirname -- "\${BASH_SOURCE[0]}")" && pwd)"

unset PYTHONHOME
export PYTHONNOUSERSITE=1
export CUDA_HOME="$CUDA_HOME"
export PATH="\$CUDA_HOME/bin:\$PATH"
export LD_LIBRARY_PATH="\$CUDA_HOME/lib64\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
if ! /sbin/ldconfig -p 2>/dev/null | grep -q 'libnvdla_compiler.so'; then
    DLA_FALLBACK_DIR="\$YOLO26_SETUP_DIR/local-l4t-dla/usr/lib/aarch64-linux-gnu/nvidia"
    DLA_FALLBACK_LIB="\$DLA_FALLBACK_DIR/libnvdla_compiler.so"
    DLA_FALLBACK_SHA256="$DLA_FALLBACK_SHA256"
    if [[ ! -r "\$DLA_FALLBACK_LIB" || "\$(sha256sum "\$DLA_FALLBACK_LIB" | awk '{print \$1}')" != "\$DLA_FALLBACK_SHA256" ]]; then
        echo "ERROR: verified local NVIDIA DLA runtime is unavailable." >&2
        return 1 2>/dev/null || exit 1
    fi
    export LD_LIBRARY_PATH="\$DLA_FALLBACK_DIR:\${LD_LIBRARY_PATH:-}"
    unset DLA_FALLBACK_LIB DLA_FALLBACK_DIR DLA_FALLBACK_SHA256
fi
export YOLO_ENGINE_DIR="\$(cd -- "\$YOLO26_SETUP_DIR/.." && pwd)"
export YOLO26_PYTHON="$VENV_DIR/bin/python"

if [[ -n "\${YOLO26_ROOT:-}" && -r "\$YOLO26_ROOT/models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="\$(cd -- "\$YOLO26_ROOT" && pwd)"
elif [[ -r "\$YOLO26_SETUP_DIR/../models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="\$(cd -- "\$YOLO26_SETUP_DIR/.." && pwd)"
elif [[ -r "\$HOME/ros2_ws/src/YOLO26/models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="\$HOME/ros2_ws/src/YOLO26"
elif [[ -r "\$HOME/YOLO26/models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="\$HOME/YOLO26"
else
    unset YOLO26_ROOT
    echo "WARNING: YOLO26 project was not found. Set YOLO26_ROOT after placing the project." >&2
fi
unset YOLO26_SETUP_DIR
EOF
    chmod 0755 "$activation_script"
}

verify_activation_script() {
    local activation_script="$SETUP_DIR/activate_yolo26.sh"
    [[ -x "$activation_script" ]] || fail "Activation script is missing: $activation_script"
    bash -n "$activation_script"
}

verify_environment_once() {
    echo "Verifying CUDA, PyTorch, Ultralytics, OpenVINO, and the supplied YOLO26 model..."
    YOLO_VERIFY_OPTIONAL="$([[ "$SKIP_OPTIONAL" == false ]] && echo 1 || echo 0)" \
        YOLO_MODEL_PATH="$YOLO_MODEL_PATH" \
        "$PYTHON" - <<'PY'
import os

import numpy as np
import openvino as ov
import scipy
import torch
import torchaudio
import torchvision
from openvino import opset13
from packaging.version import Version
from ultralytics import YOLO

print(f"torch={torch.__version__}, torch CUDA={torch.version.cuda}")
assert torch.__version__.split("+")[0] == "2.7.0", "unexpected torch version"
assert torch.version.cuda == "12.6", "unexpected torch CUDA build"
assert torch.cuda.is_available(), "PyTorch cannot access CUDA"
print(f"GPU={torch.cuda.get_device_name(0)}")

x = torch.randn((256, 256), device="cuda")
torch.cuda.synchronize()
print(f"CUDA matmul mean={(x @ x).mean().item():.6f}")

boxes = torch.tensor([[0, 0, 10, 10], [1, 1, 9, 9]], dtype=torch.float32, device="cuda")
scores = torch.tensor([0.9, 0.8], device="cuda")
print(f"torchvision NMS={torchvision.ops.nms(boxes, scores, 0.5).tolist()}")
print(f"torchvision={torchvision.__version__}, torchaudio={torchaudio.__version__}")
assert scipy.__version__ == "1.15.3", "unexpected scipy version"
print(f"numpy={np.__version__}, scipy={scipy.__version__}")

import ultralytics
assert Version(ultralytics.__version__) >= Version("8.4.0"), "Ultralytics is too old for YOLO26"
print(f"ultralytics={ultralytics.__version__}")

model = YOLO(os.environ["YOLO_MODEL_PATH"])
result = model.predict(np.zeros((64, 64, 3), dtype=np.uint8), imgsz=64, device=0, verbose=False)
print(f"YOLO26 smoke prediction count={len(result)}")

ov_core = ov.Core()
ov_parameter = opset13.parameter([1, 2], np.float32, name="x")
ov_model = ov.Model([opset13.relu(ov_parameter)], [ov_parameter], "openvino_smoke")
ov_compiled = ov_core.compile_model(ov_model, "CPU")
ov_result = ov_compiled([np.array([[-1.0, 2.0]], dtype=np.float32)])[0]
assert np.allclose(ov_result, [[0.0, 2.0]]), ov_result
print(f"openvino={ov.__version__}, devices={ov_core.available_devices}, CPU ReLU=OK")

if os.environ["YOLO_VERIFY_OPTIONAL"] == "1":
    import onnxruntime as ort
    import pycuda.driver as cuda
    from onnx import TensorProto, helper

    providers = ort.get_available_providers()
    assert "CUDAExecutionProvider" in providers, f"ONNX Runtime CUDA provider is missing: {providers}"
    print(f"onnxruntime={ort.__version__}, providers={providers}")
    node = helper.make_node("MatMul", ["x", "w"], ["y"])
    graph = helper.make_graph(
        [node],
        "cuda_smoke",
        [
            helper.make_tensor_value_info("x", TensorProto.FLOAT, [2, 2]),
            helper.make_tensor_value_info("w", TensorProto.FLOAT, [2, 2]),
        ],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [2, 2])],
    )
    onnx_model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    onnx_model.ir_version = 10
    session = ort.InferenceSession(
        onnx_model.SerializeToString(), providers=["CUDAExecutionProvider"]
    )
    assert session.get_providers()[0] == "CUDAExecutionProvider", session.get_providers()
    ort_result = session.run(
        None,
        {"x": np.eye(2, dtype=np.float32), "w": np.ones((2, 2), dtype=np.float32)},
    )[0]
    assert np.allclose(ort_result, 1.0), ort_result
    print("ONNX Runtime CUDA MatMul: OK")
    cuda.init()
    print(f"pycuda device={cuda.Device(0).name()}")
    try:
        import torchao
        print(f"torchao={torchao.__version__}")
    except Exception as exc:
        print(f"torchao warning: optional package could not import: {exc}")

try:
    import tensorrt as trt
    print(f"tensorrt={trt.__version__}")
except Exception as exc:
    raise RuntimeError(f"TensorRT Python import failed: {exc}") from exc

PY
}

verify_environment() {
    local attempt
    for attempt in 1 2; do
        if verify_environment_once; then
            return 0
        fi
        if ((attempt < 2)); then
            warn "GPU verification failed on the first attempt; retrying after 3 seconds."
            sleep 3
        fi
    done
    fail "Environment verification failed twice. Inspect the log above for the original error."
}

if [[ "$VERIFY_ONLY" == true ]]; then
    resolve_yolo_paths
    check_yolo_model
    [[ -x "$VENV_DIR/bin/python" ]] || fail "No environment found at $VENV_DIR. Run the installer without --verify-only first."
    PYTHON="$VENV_DIR/bin/python"
    check_system_stack
    check_python_dependencies
    verify_activation_script
    verify_environment
    echo "Verification completed."
    exit 0
fi

resolve_wheel_dir
check_wheels
resolve_yolo_paths
check_yolo_model

if [[ "$SKIP_SYSTEM" == false ]]; then
    if system_packages_present; then
        echo "Required system packages are already present; skipping apt."
        check_system_stack
    else
        install_system_packages
    fi
else
    echo "Skipping apt as requested. Checking the existing CUDA/cuDNN/TensorRT/DLA installation..."
    check_system_stack
fi

create_or_check_venv
write_constraints
install_python_packages
write_activation_script
verify_activation_script
verify_environment

echo
echo "Installation completed. Activate the environment with:"
echo "  source $SETUP_DIR/activate_yolo26.sh"
echo "Then work in: $YOLO26_PROJECT_DIR"
