# Jetson Orin YOLO26 环境安装教程

本教程安装 YOLO26 训练、推理、导出和 ROS 2 检测节点需要的 Python 与 Jetson GPU
环境。数据采集、标注、训练和部署见：

```text
$HOME/ros2_ws/src/YOLO26/docs/YOLO26_采集标注训练与ROS识别教程.md
```

## 1. 可搬运边界

规范工程位置：

```text
$HOME/ros2_ws/src/YOLO26
```

环境安装材料位于工程内部：

| 路径 | 用途 |
| --- | --- |
| `setup/install_yolo26.sh` | 安装或验证环境。 |
| `setup/activate_yolo26.sh` | 每个新终端加载 YOLO26 环境。 |
| `setup/constraints-yolo26-py310.txt` | 已验证的 Python 版本约束。 |
| `setup/packages`、`setup/local-l4t-dla` | Jetson DLA 后备材料。 |
| `setup/logs` | 安装和验证日志。 |
| `setup/wheels` | 已验证的 AArch64 wheel，随完整工程一同提供。 |

用户迁移时只需搬运整个 `YOLO26` 目录。虚拟环境固定安装到：

```text
$HOME/.venvs/yolo26
```

## 2. 支持的平台

适用平台：

| 项目 | 要求 |
| --- | --- |
| 硬件 | NVIDIA Jetson Orin Nano |
| 架构 | AArch64 |
| 系统 | Ubuntu 22.04 |
| Python | `/usr/bin/python3` 3.10 |
| L4T | R36.4.7 / JetPack 6.2 系列 |
| CUDA | 12.6 |
| cuDNN | 9 |
| TensorRT | 10 |
| ROS 2 | Humble |

此安装器不适用于 x86 主机，也不应通过 `sudo bash` 整体运行。

只读检查：

```bash
uname -m
/usr/bin/python3 --version
dpkg-query -W nvidia-l4t-core
df -h "$HOME"
```

预期架构为 `aarch64`、Python 为 3.10，L4T 版本以 `36.4.7-` 开头。首次安装建议
至少保留 15 GiB 可用空间。

## 3. 迁移工程

在教程同一文件夹下的 **“资源文件”** 文件夹中找到 `YOLO26`，使用 MobaXterm
将完整文件夹传入 Jetson 的 `~/ros2_ws/src/` 目录。传入前先确认用户主目录并创建
工作空间源码目录：

```bash
echo "$HOME"
mkdir -p "$HOME/ros2_ws/src"
test ! -e "$HOME/ros2_ws/src/YOLO26"
```

如果目标位置已经存在同名目录，先核对是否为本教程提供的完整版本，不要把两个版本
直接混合覆盖。传入完成后检查关键文件：

```bash
test -f "$HOME/ros2_ws/src/YOLO26/setup/install_yolo26.sh"
test -f "$HOME/ros2_ws/src/YOLO26/models/pretrained/yolo26n.pt"
test -f "$HOME/ros2_ws/src/YOLO26/setup/wheels/torch-2.7.0-cp310-cp310-linux_aarch64.whl"
```

工程应在安装和编译前放到最终位置。移动后需要重新编译 ROS 工作空间。

## 4. 确认本地 wheel

六个 wheel 已包含在完整 `YOLO26/setup/wheels` 中，不需要再从 **“资源文件”**
文件夹逐个查找或传入。安装器仍保留以下查找顺序，便于维护人员在修复环境时覆盖
默认位置：

1. 环境变量 `YOLO_WHEEL_DIR` 指定的目录。
2. `$YOLO26_ROOT/setup/wheels`。
3. `$HOME/Downloads`。

需要的文件：

```text
torch-2.7.0-cp310-cp310-linux_aarch64.whl
torchvision-0.22.0-cp310-cp310-linux_aarch64.whl
torchaudio-2.7.0-cp310-cp310-linux_aarch64.whl
torchao-0.11.0+git173d38f-cp39-abi3-linux_aarch64.whl
onnxruntime_gpu-1.22.0-cp310-cp310-linux_aarch64.whl
pycuda-2024.1.2-cp310-cp310-linux_aarch64.whl
```

安装器会验证文件名和 SHA256。`--skip-optional` 可以跳过 TorchAO、ONNX Runtime
GPU 和 PyCUDA，但训练核心的三个 PyTorch wheel 仍必须存在。

## 5. 一键安装

首次安装前没有可加载的 YOLO26 环境，因此此步骤不需要 `source`。以普通用户执行：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26

chmod +x "$YOLO26_ROOT/setup/install_yolo26.sh"
bash "$YOLO26_ROOT/setup/install_yolo26.sh"
```

不要执行：

```text
sudo bash $HOME/ros2_ws/src/YOLO26/setup/install_yolo26.sh
```

脚本只在安装系统软件包时单独调用 `sudo`。它会：

1. 检查 AArch64、Python 3.10、L4T 和磁盘空间。
2. 校验 wheel、预训练模型和 DLA 材料。
3. 检查或安装 CUDA 12.6、cuDNN 9、TensorRT 10 和构建依赖。
4. 创建 `$HOME/.venvs/yolo26`。
5. 安装 PyTorch 2.7、Ultralytics 8.4.104、OpenVINO 2025.4.1 等依赖。
6. 运行 CUDA 实算、NMS、YOLO 推理、ONNX Runtime、OpenVINO、TensorRT 和 PyCUDA 验证。

常用选项：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26

# 系统 CUDA、cuDNN、TensorRT 已完整时跳过 APT。
bash "$YOLO26_ROOT/setup/install_yolo26.sh" --skip-system

# 不安装可选的 TorchAO、ONNX Runtime GPU 和 PyCUDA。
bash "$YOLO26_ROOT/setup/install_yolo26.sh" --skip-optional
```

## 6. 新终端加载环境

`source` 只对当前终端有效。每次新开终端、标签页或 SSH 会话，都要重新执行：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

echo "$YOLO26_ROOT"
echo "$YOLO26_PYTHON"
python --version
```

运行 ROS 节点时还需加载 ROS 和工作空间：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash
```

终端 A 中执行过的 `source` 不会传递到终端 B。

## 7. 验证已有环境

`--verify-only` 不安装软件包，也不要求 wheel 仍然存在：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
bash "$YOLO26_ROOT/setup/install_yolo26.sh" --verify-only
```

手工检查：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

python -m pip check
python - <<'PY'
import torch
import ultralytics

print("torch:", torch.__version__)
print("CUDA:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0))
print("ultralytics:", ultralytics.__version__)
PY
```

查看日志：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
ls -lt "$YOLO26_ROOT/setup/logs"
```

## 8. 关键依赖版本

约束文件固定已验证的依赖组合，核心版本包括：

```text
numpy==1.26.4
scipy==1.15.3
opencv-python==4.11.0.86
ultralytics==8.4.104
openvino==2025.4.1
onnx==1.22.0
onnxruntime-gpu==1.22.0
pycuda==2024.1.2
```

不要在激活环境后使用裸 `sudo pip`、`pip --user` 或未经验证的依赖升级。需要安装额外
Python 包时使用：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

python -m pip install package_name
python -m pip check
```

## 9. 常见问题

### 找不到工程

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
test -f "$YOLO26_ROOT/models/pretrained/yolo26n.pt"
```

### 找不到 wheel

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
ls -1 "$YOLO26_ROOT/setup/wheels"
```

如果缺少教程列出的 wheel，说明 `YOLO26` 文件夹传入不完整。重新从教程同一文件夹
下的 **“资源文件”** 文件夹中找到完整 `YOLO26`，核对版本后重新传入，不要从
不明来源补齐同名文件。

### CUDA 可用但 ROS 节点找不到 Ultralytics

新终端必须同时加载三层环境：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash
```
