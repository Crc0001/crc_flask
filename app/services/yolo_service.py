from ultralytics import YOLO
import cv2
import os

model = YOLO(r"C:\Users\Administrator\Desktop\crc_flask\app\weights\best.pt")


def detect_and_draw(image_path, save_dir, confidence_threshold=0.5):

    # 1. 验证输入文件
    if not os.path.exists(image_path):
        return {
            "success": False,
            "error": f"图像文件不存在: {image_path}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": None,
            "inference_time": None
        }

    # 2. 读取图像
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {
                "success": False,
                "error": "无法读取图像文件，可能格式不支持或文件损坏",
                "detections": None,
                "result_path": None,
                "detect_count": 0,
                "image_size": None,
                "inference_time": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"读取图像时出错: {str(e)}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": None,
            "inference_time": None
        }

    # 3. 获取图像尺寸
    img_height, img_width = img.shape[:2]

    # 4. 执行检测
    try:
        results = model(image_path, conf=confidence_threshold)[0]
        inference_time = results.speed  # 获取推理时间（毫秒）
    except Exception as e:
        return {
            "success": False,
            "error": f"模型推理时出错: {str(e)}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": (img_width, img_height),
            "inference_time": None
        }

    # 5. 处理检测结果
    detections = []

    if results.boxes is not None and len(results.boxes) > 0:
        for box in results.boxes:
            # 跳过置信度低于阈值的结果（虽然模型已过滤，但双重保险）
            conf = float(box.conf[0])
            if conf < confidence_threshold:
                continue

            cls_id = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            name = results.names[cls_id]
            if name == '瑞士乳杆菌 Lactobacillus helveticus':
                name = '考克氏菌属  Kocuria sp'

            # 计算归一化坐标（相对于图像尺寸）
            x1_norm = x1 / img_width
            y1_norm = y1 / img_height
            x2_norm = x2 / img_width
            y2_norm = y2 / img_height

            detection_info = {
                "name": name ,
                "class_id": cls_id,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],  # 原始坐标
                "bbox_norm": [x1_norm, y1_norm, x2_norm, y2_norm],  # 归一化坐标
                "bbox_center": [(x1 + x2) // 2, (y1 + y2) // 2],  # 中心点坐标
                "bbox_size": [x2 - x1, y2 - y1]  # 框的宽高
            }
            detections.append(detection_info)

            # 画框和标签
            label = f"{name} {conf:.2f}"

            # 计算文本大小
            (text_width, text_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )

            # 画检测框
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # 画标签背景
            cv2.rectangle(
                img,
                (x1, y1 - text_height - baseline - 5),
                (x1 + text_width, y1),
                (0, 255, 0),
                -1
            )

            # 画标签文本
            cv2.putText(
                img,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),  # 黑色文本
                2
            )

    # 6. 保存结果图像
    os.makedirs(save_dir, exist_ok=True)
    result_filename = f"{os.path.basename(image_path)}"
    result_path = os.path.join(save_dir, result_filename)

    try:
        # 如果没有检测到目标，在图像上添加提示
        if len(detections) == 0:
            # 添加"No detection"提示
            text = "No Detection"
            font_scale = 1.5
            thickness = 3

            # 计算文本位置（居中）
            (text_width, text_height), baseline = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )
            text_x = (img_width - text_width) // 2
            text_y = (img_height + text_height) // 2

            # 添加半透明背景
            overlay = img.copy()
            cv2.rectangle(
                overlay,
                (text_x - 10, text_y - text_height - 10),
                (text_x + text_width + 10, text_y + 10),
                (0, 0, 0),
                -1
            )
            cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

            # 添加文本
            cv2.putText(
                img,
                text,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),  # 白色
                thickness
            )

        cv2.imwrite(result_path, img)

    except Exception as e:
        return {
            "success": False,
            "error": f"保存结果图像时出错: {str(e)}",
            "detections": detections if detections else None,
            "result_path": None,
            "detect_count": len(detections),
            "image_size": (img_width, img_height),
            "inference_time": inference_time
        }

    # 7. 整理返回结果
    response = {
        "success": True,
        "error": None,
        "detections": detections if detections else None,  # 空列表时返回None
        "result_path": result_path,
        "detect_count": len(detections),
        "image_size": (img_width, img_height),
        "inference_time": inference_time,  # 包含预处理、推理、后处理时间
        "confidence_threshold": confidence_threshold,
        "has_detections": len(detections) > 0
    }

    return response
