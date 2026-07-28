#!/usr/bin/env bash

source "$HOME/.venvs/yolo26/bin/activate"

YOLO26_SETUP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

unset PYTHONHOME
export PYTHONNOUSERSITE=1
export CUDA_HOME="/usr/local/cuda-12.6"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if ! /sbin/ldconfig -p 2>/dev/null | grep -q 'libnvdla_compiler.so'; then
    DLA_FALLBACK_DIR="$YOLO26_SETUP_DIR/local-l4t-dla/usr/lib/aarch64-linux-gnu/nvidia"
    DLA_FALLBACK_LIB="$DLA_FALLBACK_DIR/libnvdla_compiler.so"
    DLA_FALLBACK_SHA256="c21986bed8d48a5ef11928aa54a500cd14a997d1d0bed99edf4d161d1c778bec"
    if [[ ! -r "$DLA_FALLBACK_LIB" || "$(sha256sum "$DLA_FALLBACK_LIB" | awk '{print $1}')" != "$DLA_FALLBACK_SHA256" ]]; then
        echo "ERROR: verified local NVIDIA DLA runtime is unavailable." >&2
        return 1 2>/dev/null || exit 1
    fi
    export LD_LIBRARY_PATH="$DLA_FALLBACK_DIR:${LD_LIBRARY_PATH:-}"
    unset DLA_FALLBACK_LIB DLA_FALLBACK_DIR DLA_FALLBACK_SHA256
fi
export YOLO_ENGINE_DIR="$(cd -- "$YOLO26_SETUP_DIR/.." && pwd)"
export YOLO26_PYTHON="$HOME/.venvs/yolo26/bin/python"

if [[ -n "${YOLO26_ROOT:-}" && -r "$YOLO26_ROOT/models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="$(cd -- "$YOLO26_ROOT" && pwd)"
elif [[ -r "$YOLO26_SETUP_DIR/../models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="$(cd -- "$YOLO26_SETUP_DIR/.." && pwd)"
elif [[ -r "$HOME/ros2_ws/src/YOLO26/models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
elif [[ -r "$HOME/YOLO26/models/pretrained/yolo26n.pt" ]]; then
    export YOLO26_ROOT="$HOME/YOLO26"
else
    unset YOLO26_ROOT
    echo "WARNING: YOLO26 project was not found. Set YOLO26_ROOT after placing the project." >&2
fi
unset YOLO26_SETUP_DIR
