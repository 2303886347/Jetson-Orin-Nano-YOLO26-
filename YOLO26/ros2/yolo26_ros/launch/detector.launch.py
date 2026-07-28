"""Launch the YOLO26 detector for an existing /image_raw publisher."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default_model = str(
        Path(get_package_share_directory("yolo26_ros")) / "models/yolo26n.pt"
    )
    arguments = [
        DeclareLaunchArgument("model_path", default_value=default_model),
        DeclareLaunchArgument("image_topic", default_value="/image_raw"),
        DeclareLaunchArgument(
            "annotated_topic", default_value="/yolo26/annotated_image"
        ),
        DeclareLaunchArgument(
            "detections_topic", default_value="/yolo26/detections"
        ),
        DeclareLaunchArgument("confidence", default_value="0.25"),
        DeclareLaunchArgument("iou", default_value="0.45"),
        DeclareLaunchArgument("imgsz", default_value="640"),
        DeclareLaunchArgument("device", default_value="0"),
        DeclareLaunchArgument("enabled", default_value="true"),
        DeclareLaunchArgument("show_rqt", default_value="true"),
    ]
    detector = Node(
        package="yolo26_ros",
        executable="detector_node",
        namespace="yolo26",
        name="detector",
        output="screen",
        emulate_tty=True,
        additional_env={"PYTHONNOUSERSITE": "1"},
        parameters=[
            {
                "model_path": LaunchConfiguration("model_path"),
                "image_topic": LaunchConfiguration("image_topic"),
                "annotated_topic": LaunchConfiguration("annotated_topic"),
                "detections_topic": LaunchConfiguration("detections_topic"),
                "confidence": ParameterValue(
                    LaunchConfiguration("confidence"), value_type=float
                ),
                "iou": ParameterValue(LaunchConfiguration("iou"), value_type=float),
                "imgsz": ParameterValue(
                    LaunchConfiguration("imgsz"), value_type=int
                ),
                "device": ParameterValue(
                    LaunchConfiguration("device"), value_type=str
                ),
                "enabled": ParameterValue(
                    LaunchConfiguration("enabled"), value_type=bool
                ),
            }
        ],
    )
    viewer = Node(
        package="rqt_image_view",
        executable="rqt_image_view",
        name="yolo26_image_view",
        arguments=[LaunchConfiguration("annotated_topic")],
        output="screen",
        condition=IfCondition(LaunchConfiguration("show_rqt")),
    )
    return LaunchDescription([*arguments, detector, viewer])
