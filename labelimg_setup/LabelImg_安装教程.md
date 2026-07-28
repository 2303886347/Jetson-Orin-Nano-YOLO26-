# LabelImg 独立安装教程

在教程同一文件夹下的 **“资源文件”** 文件夹中找到 `labelimg` 和
`labelimg_setup`，使用 MobaXterm 将两个完整文件夹传入 Jetson 的
`~/Downloads/` 目录。文件夹名称和内部结构必须保持不变；如果目标位置已经存在
同名目录，先核对版本，不要直接混合覆盖。

## 1. 路径

| 路径 | 用途 |
| --- | --- |
| `$HOME/Downloads/labelimg/` | LabelImg 1.8.6 源码。 |
| `$HOME/Downloads/labelimg_setup/install_labelimg.sh` | LabelImg 独立一键安装器。 |
| `$HOME/Downloads/labelimg_setup/logs/` | LabelImg 安装日志。 |
| `$HOME/Software/labelimg/` | LabelImg 安装目录。 |
| `$HOME/Software/labelimg/.venv/` | LabelImg 专用 Python venv。 |
| `$HOME/Software/labelimg/run_labelimg.sh` | 图形界面启动器。 |
由于 AArch64 上 PyQt5 wheel 支持有限，LabelImg venv 通过 `--system-site-packages` 复用 Ubuntu 的 PyQt5 和 lxml。

## 2. 一键安装

在普通用户终端运行：

```bash
chmod +x $HOME/Downloads/labelimg_setup/install_labelimg.sh
bash $HOME/Downloads/labelimg_setup/install_labelimg.sh
```

不要在命令前加 `sudo`。脚本只在 APT 阶段请求 sudo 密码。

安装内容：

```text
python3-venv
python3-pyqt5
python3-lxml
libgl1
libglib2.0-0
libegl1
libxcb-xinerama0
```

| 包 | 作用 |
| --- | --- |
| `python3-pyqt5` | LabelImg 的 Qt 5 图形界面。 |
| `python3-lxml` | Pascal VOC XML 读写。 |
| `python3-venv` | 创建 LabelImg 专用虚拟环境。 |
| 图形运行库 | 提供 OpenGL、EGL 和 xcb 运行支持。 |

脚本不会覆盖已存在的自定义 `data/predefined_classes.txt` 或其他安装目录文件。

## 3. 安装器选项

```bash
# 系统 PyQt5/lxml 已经安装时跳过 APT。
bash $HOME/Downloads/labelimg_setup/install_labelimg.sh --skip-system

# 只验证安装结果。
bash $HOME/Downloads/labelimg_setup/install_labelimg.sh --verify-only
```

验证会使用 `QT_QPA_PLATFORM=offscreen` 构造真实 LabelImg 主窗口并加载预定义类别，不需要显示器。

## 4. 启动

在桌面、VNC 或 NoMachine 图形会话中执行：

```bash
$HOME/Software/labelimg/run_labelimg.sh
```

可以直接打开图片目录：

```bash
$HOME/Software/labelimg/run_labelimg.sh $HOME/my_images
```

若终端没有 `DISPLAY`，Qt xcb 报错表示当前不是图形会话，不代表安装失败。

## 5. YOLO26 单类别和多类别工作流使用 Pascal VOC XML

YOLO26 工作流以 Pascal VOC XML 作为可回溯的源标注，再由数据工具生成 YOLO
TXT。数据集和类别由用户创建，不预置具体识别目标。先确认目标数据集的类别文件：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
cat "datasets/$DATASET_NAME/source/classes.names"
```

单类别文件示例：

```text
target_a
```

多类别文件示例，一行一个类别：

```text
target_a
target_b
target_c
```

如系统尚未安装 Gedit，先执行：

```bash
sudo apt update
sudo apt install -y gedit
```

如需修改 LabelImg 的预定义列表，可编辑：

```bash
gedit "$HOME/Software/labelimg/data/predefined_classes.txt"
```

修改完成后，按 `Ctrl + S` 保存文件，然后关闭 Gedit。

直接打开图片目录：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
$HOME/Software/labelimg/run_labelimg.sh \
  "$YOLO26_ROOT/datasets/$DATASET_NAME/source/JPEGImages"
```

当参数是标准数据集的 `source/JPEGImages` 时，启动器会自动读取同级
`source/classes.names`，将 XML 保存目录设为 `source/Annotations`，并固定使用
`PascalVOC`。路径不存在、类别文件缺失或标注目录缺失时，启动器会直接输出错误并
停止，不会弹出目录选择窗口。

在界面中：

1. 确认页眉格式显示 `PascalVOC`；使用上述启动命令时已经自动设置。
2. 状态栏中的标注保存目录应为对应数据集的 `source/Annotations`，无需再次选择。
3. 使用启动器从 `classes.names` 加载的类别名。
4. 一张图片可以标注多个目标，也可以同时使用多个不同类别。
5. 图片中出现的已声明类别都应标注，不能只标其中一个目标。
6. 每张正样本图片保存后确认 `Annotations` 中出现同名 `.xml`。

类别顺序在同一个数据集中不能随意改变。后期可以在文件末尾增加新类别，但必须回看
已有图片；已有图片中出现的新类别也要补标。重命名已有类别会被训练程序视为新类别。

不包含任何目标类别的图片可以作为负样本保留 JPG 而不创建 XML，转换时必须显式
使用 `--allow-unannotated-negatives`。尚未完成标注的图片不能当作负样本。

完整的数据转换和训练步骤：

```text
$HOME/ros2_ws/src/YOLO26/docs/YOLO26_采集标注训练与ROS识别教程.md
```

## 6. 直接使用 YOLO 标签格式

其他项目如果不需要保留 XML，也可以把工具栏格式切换为 `YOLO`。LabelImg 会生成同名 `.txt` 和 `classes.txt`。不要在同一个数据集中混用两套类别顺序。

本教程中的 YOLO26 工程不采用此方式，应按第 5 节保存 Pascal VOC XML。

## 7. 故障恢复

### 启动时弹出目录选择窗口

检查 `DATASET_NAME` 是否是已经通过 `tools/create_dataset.py` 创建的数据集：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
test -d "$YOLO26_ROOT/datasets/$DATASET_NAME/source/JPEGImages"
test -d "$YOLO26_ROOT/datasets/$DATASET_NAME/source/Annotations"
test -f "$YOLO26_ROOT/datasets/$DATASET_NAME/source/classes.names"
```

三个检查都成功后，再使用第 5 节命令启动。不要在界面中重新选择 `JPEGImages` 作为
XML 保存目录。

查看最新日志：

```bash
latest_log=$(ls -t $HOME/Downloads/labelimg_setup/logs/install-*.log | head -n 1)
tail -n 100 "$latest_log"
```

| 问题 | 处理 |
| --- | --- |
| PyQt5 或 lxml 无法导入 | 不带 `--skip-system` 重跑默认安装器。 |
| venv 不是 Python 3.10 | 先移动备份 `$HOME/Software/labelimg/.venv`，再重跑。 |
| Qt xcb 无法连接显示 | 在图形桌面会话中启动，并检查 `echo $DISPLAY`。 |
| 类别列表需要恢复 | 从 `$HOME/Downloads/labelimg/data/predefined_classes.txt` 手工恢复。 |

成功结束时会显示：

```text
LabelImg installation completed. Start it with:
  $HOME/Software/labelimg/run_labelimg.sh
```
