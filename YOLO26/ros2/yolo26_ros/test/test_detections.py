from std_msgs.msg import Header

from yolo26_ros.detections import detection_from_xyxy


def test_detection_from_xyxy():
    header = Header()
    header.frame_id = "camera"
    detection = detection_from_xyxy(
        header, "target_a", 0.9, (10.0, 20.0, 50.0, 80.0), "0"
    )
    assert detection.header.frame_id == "camera"
    assert detection.bbox.center.position.x == 30.0
    assert detection.bbox.center.position.y == 50.0
    assert detection.bbox.size_x == 40.0
    assert detection.bbox.size_y == 60.0
    assert detection.results[0].hypothesis.class_id == "target_a"
    assert detection.results[0].hypothesis.score == 0.9
