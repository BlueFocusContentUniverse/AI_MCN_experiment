# utils/helpers.py
import os
import json
import cv2

def save_metadata(metadata, filepath):
    """将元数据保存为 JSON 文件"""
    with open(filepath, 'w') as f:
        json.dump(metadata, f, indent=2)

def load_metadata(filepath):
    """从 JSON 文件加载元数据"""
    with open(filepath, 'r') as f:
        return json.load(f)

def create_video_thumbnail(video_path, output_path, position=0.5):
    """
    从视频中提取缩略图
    
    参数:
    video_path: 视频文件路径
    output_path: 输出缩略图路径
    position: 视频位置（0-1 之间的百分比）
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False
    
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_pos = int(frame_count * position)
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
    ret, frame = cap.read()
    
    if ret:
        cv2.imwrite(output_path, frame)
        cap.release()
        return True
    else:
        cap.release()
        return False