"""Conversion helpers for standard vision_msgs detection messages."""

from __future__ import annotations

from std_msgs.msg import Header
from vision_msgs.msg import Detection2D, ObjectHypothesisWithPose


def detection_from_xyxy(
    header: Header,
    class_name: str,
    score: float,
    xyxy: tuple[float, float, float, float],
    detection_id: str,
) -> Detection2D:
    x1, y1, x2, y2 = xyxy
    detection = Detection2D()
    detection.header = header
    detection.id = detection_id
    detection.bbox.center.position.x = (x1 + x2) / 2.0
    detection.bbox.center.position.y = (y1 + y2) / 2.0
    detection.bbox.center.theta = 0.0
    detection.bbox.size_x = x2 - x1
    detection.bbox.size_y = y2 - y1

    hypothesis = ObjectHypothesisWithPose()
    hypothesis.hypothesis.class_id = class_name
    hypothesis.hypothesis.score = float(score)
    hypothesis.pose.pose.orientation.w = 1.0
    detection.results.append(hypothesis)
    return detection
