"""Launch a CSI/USB camera, YOLO26 detection, and optional rqt viewer."""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default_model = str(
        Path(get_package_share_directory("yolo26_ros")) / "models/yolo26n.pt"
    )
    camera_launch = os.path.join(
        get_package_share_directory("camera_usb_and_csi"), "launch", "camera.launch.py"
    )
    argument_defaults = {
        "camera_type": "CSI",
        "image_topic": "/image_raw",
        "frame_id": "camera_optical_frame",
        "frame_limit": "0",
        "csi_sensor_id": "0",
        "csi_capture_width": "1280",
        "csi_capture_height": "720",
        "csi_output_width": "640",
        "csi_output_height": "480",
        "csi_framerate": "60",
        "csi_flip_method": "0",
        "usb_device": "/dev/usb_cam",
        "usb_width": "640",
        "usb_height": "480",
        "usb_framerate": "30",
        "usb_pixel_format": "MJPEG",
        "model_path": default_model,
        "annotated_topic": "/yolo26/annotated_image",
        "detections_topic": "/yolo26/detections",
        "confidence": "0.25",
        "iou": "0.45",
        "imgsz": "640",
        "device": "0",
        "enabled": "true",
        "show_rqt": "true",
    }
    arguments = [
        DeclareLaunchArgument(name, default_value=value)
        for name, value in argument_defaults.items()
    ]
    camera_argument_names = (
        "camera_type",
        "image_topic",
        "frame_id",
        "frame_limit",
        "csi_sensor_id",
        "csi_capture_width",
        "csi_capture_height",
        "csi_output_width",
        "csi_output_height",
        "csi_framerate",
        "csi_flip_method",
        "usb_device",
        "usb_width",
        "usb_height",
        "usb_framerate",
        "usb_pixel_format",
    )
    camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(camera_launch),
        launch_arguments={
            name: LaunchConfiguration(name) for name in camera_argument_names
        }.items(),
    )
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
    return LaunchDescription([*arguments, camera, detector, viewer])
