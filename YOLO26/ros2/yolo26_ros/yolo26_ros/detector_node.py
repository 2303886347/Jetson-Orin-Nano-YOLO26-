"""Subscribe to ROS images and publish YOLO26 detections and annotations."""

from __future__ import annotations

import copy
import queue
import threading
import time
from pathlib import Path

import cv2
import rclpy
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_srvs.srv import Trigger
from vision_msgs.msg import Detection2DArray

from .detections import detection_from_xyxy
from .runtime import ensure_yolo_runtime


class Yolo26Detector(Node):
    def __init__(self) -> None:
        super().__init__("detector")
        default_model = (
            Path(get_package_share_directory("yolo26_ros")) / "models/yolo26n.pt"
        )
        self.declare_parameter("model_path", str(default_model))
        self.declare_parameter("image_topic", "/image_raw")
        self.declare_parameter("annotated_topic", "/yolo26/annotated_image")
        self.declare_parameter("detections_topic", "/yolo26/detections")
        self.declare_parameter("confidence", 0.25)
        self.declare_parameter("iou", 0.45)
        self.declare_parameter("imgsz", 640)
        self.declare_parameter("device", "0")
        self.declare_parameter("enabled", True)

        self.model_path = Path(str(self.get_parameter("model_path").value)).expanduser()
        self.image_topic = str(self.get_parameter("image_topic").value)
        self.annotated_topic = str(self.get_parameter("annotated_topic").value)
        self.detections_topic = str(self.get_parameter("detections_topic").value)
        self.confidence = float(self.get_parameter("confidence").value)
        self.iou = float(self.get_parameter("iou").value)
        self.imgsz = int(self.get_parameter("imgsz").value)
        self.device = str(self.get_parameter("device").value)
        self.enabled = bool(self.get_parameter("enabled").value)

        self._validate_parameters()
        from ultralytics import YOLO

        self.get_logger().info(f"Loading YOLO26 model: {self.model_path}")
        self.model = YOLO(str(self.model_path), task="detect")
        self.bridge = CvBridge()
        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.smoothed_fps = 0.0

        self.annotated_publisher = self.create_publisher(
            Image, self.annotated_topic, qos_profile_sensor_data
        )
        self.detections_publisher = self.create_publisher(
            Detection2DArray, self.detections_topic, 10
        )
        self.subscription = self.create_subscription(
            Image, self.image_topic, self.image_callback, qos_profile_sensor_data
        )
        self.create_service(Trigger, "/yolo26/start", self.start_callback)
        self.create_service(Trigger, "/yolo26/stop", self.stop_callback)
        self.worker = threading.Thread(target=self.process_frames, daemon=True)
        self.worker.start()
        self.get_logger().info(
            f"Subscribed to {self.image_topic}; publishing {self.annotated_topic} "
            f"and {self.detections_topic}"
        )

    def _validate_parameters(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"YOLO26 model does not exist: {self.model_path}")
        if self.model_path.suffix.lower() not in {".pt", ".engine"}:
            raise ValueError("model_path must end in .pt or .engine")
        for topic in (self.image_topic, self.annotated_topic, self.detections_topic):
            if not topic.startswith("/"):
                raise ValueError(f"ROS topic must be absolute: {topic}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.iou <= 1.0:
            raise ValueError("iou must be between 0 and 1")
        if self.imgsz <= 0:
            raise ValueError("imgsz must be positive")

    def start_callback(self, request, response):
        del request
        with self.state_lock:
            self.enabled = True
        response.success = True
        response.message = "YOLO26 detection started"
        self.get_logger().info(response.message)
        return response

    def stop_callback(self, request, response):
        del request
        with self.state_lock:
            self.enabled = False
        response.success = True
        response.message = "YOLO26 detection stopped"
        self.get_logger().info(response.message)
        return response

    def image_callback(self, message: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"Unable to convert input image: {exc}")
            return
        item = (frame, copy.deepcopy(message.header))
        if self.frame_queue.full():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self.frame_queue.put_nowait(item)
        except queue.Full:
            pass

    def process_frames(self) -> None:
        while not self.stop_event.is_set():
            try:
                frame, header = self.frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.state_lock:
                enabled = self.enabled
            annotated = frame.copy()
            detection_array = Detection2DArray()
            detection_array.header = header
            started = time.perf_counter()
            if enabled:
                try:
                    result = self.model.predict(
                        frame,
                        imgsz=self.imgsz,
                        conf=self.confidence,
                        iou=self.iou,
                        device=self.device,
                        verbose=False,
                    )[0]
                    annotated = result.plot()
                    if result.boxes is not None:
                        for index, box in enumerate(result.boxes):
                            class_id = int(box.cls[0].item())
                            class_name = str(result.names.get(class_id, class_id))
                            score = float(box.conf[0].item())
                            coordinates = tuple(
                                float(value) for value in box.xyxy[0].cpu().tolist()
                            )
                            detection_array.detections.append(
                                detection_from_xyxy(
                                    header,
                                    class_name,
                                    score,
                                    coordinates,
                                    str(index),
                                )
                            )
                except Exception as exc:
                    self.get_logger().error(f"YOLO26 inference failed: {exc}")

            elapsed = time.perf_counter() - started
            if elapsed > 0:
                current_fps = 1.0 / elapsed
                self.smoothed_fps = (
                    current_fps
                    if self.smoothed_fps == 0.0
                    else self.smoothed_fps * 0.9 + current_fps * 0.1
                )
            status = f"YOLO26 {'ON' if enabled else 'OFF'}  FPS {self.smoothed_fps:.1f}"
            cv2.putText(
                annotated,
                status,
                (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 255),
                2,
                cv2.LINE_AA,
            )
            output = self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8")
            output.header = header
            if self.stop_event.is_set() or not rclpy.ok(context=self.context):
                break
            self.annotated_publisher.publish(output)
            self.detections_publisher.publish(detection_array)

    def destroy_node(self):
        self.stop_event.set()
        if hasattr(self, "worker") and self.worker.is_alive():
            self.worker.join(timeout=3.0)
        return super().destroy_node()


def main(args=None) -> None:
    ensure_yolo_runtime()
    rclpy.init(args=args)
    node = None
    try:
        node = Yolo26Detector()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
