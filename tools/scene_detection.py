# tools/scene_detection.py
import os
import cv2
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector, ThresholdDetector
from scenedetect.scene_manager import save_images
import tempfile
from typing import Optional, Type, List
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool

class SceneDetectionInput(BaseModel):
    """场景检测工具的输入模式"""
    video_path: str = Field(..., description="视频文件的路径")
    threshold: float = Field(27.0, description="检测阈值，越小越敏感,阈值范围为5-30")
    min_scene_len: int = Field(15, description="最小场景长度（帧数）")
    detector_type: str = Field("content", description="检测器类型 - 'content' 或 'threshold'")

class ExtractSceneFramesInput(BaseModel):
    """提取场景关键帧工具的输入模式"""
    video_path: str = Field(..., description="视频文件的路径")
    scenes_info: dict = Field(..., description="场景信息（来自 detect_scenes 工具）")
    output_dir: Optional[str] = Field(None, description="关键帧输出目录")

class DetectScenesTool(BaseTool):
    name: str = "DetectScenes"
    description: str = "使用 PySceneDetect 检测视频中的场景，可调整阈值,阈值范围为5-30"
    args_schema: Type[BaseModel] = SceneDetectionInput
    
    def _run(self, video_path: str, threshold: float = 27.0, min_scene_len: int = 15, detector_type: str = 'content') -> dict:
        """
        使用 PySceneDetect 检测视频中的场景
        
        参数:
        video_path: 视频文件路径
        threshold: 检测阈值，越小越敏感
        min_scene_len: 最小场景长度（帧数）
        detector_type: 检测器类型 - 'content' 或 'threshold'
        
        返回:
        场景列表，每个场景包含开始和结束帧号
        """
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        try:
            # 创建视频管理器
            video_manager = VideoManager([video_path])
            scene_manager = SceneManager()
            
            # 添加检测器
            if detector_type.lower() == 'content':
                scene_manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
            elif detector_type.lower() == 'threshold':
                scene_manager.add_detector(ThresholdDetector(threshold=threshold, min_scene_len=min_scene_len))
            else:
                return f"Error: Unknown detector type '{detector_type}'"
            
            # 启动视频管理器
            video_manager.start()
            
            # 检测场景
            scene_manager.detect_scenes(frame_source=video_manager)
            
            # 获取场景列表
            scene_list = scene_manager.get_scene_list()
            
            # 获取视频信息
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            
            # 转换场景列表为时间格式
            scenes = []
            for i, scene in enumerate(scene_list):
                start_frame = scene[0].frame_num
                end_frame = scene[1].frame_num
                start_time = start_frame / fps
                end_time = end_frame / fps
                duration = end_time - start_time
                
                scenes.append({
                    "scene_number": i + 1,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "start_time": f"{int(start_time // 60):02d}:{start_time % 60:06.3f}",
                    "end_time": f"{int(end_time // 60):02d}:{end_time % 60:06.3f}",
                    "duration": f"{duration:.3f}",
                })
            
            return {"scenes": scenes, "total_scenes": len(scenes)}
            
        except Exception as e:
            return f"Error detecting scenes: {str(e)}"

class ExtractSceneFramesTool(BaseTool):
    name: str = "ExtractSceneFrames"
    description: str = "从检测到的视频场景中提取关键帧"
    args_schema: Type[BaseModel] = ExtractSceneFramesInput
    
    def _run(self, video_path: str, scenes_info: dict, output_dir: Optional[str] = None) -> dict:
        """
        为每个检测到的场景提取关键帧
        
        参数:
        video_path: 视频文件路径
        scenes_info: 场景信息（来自 detect_scenes 工具）
        output_dir: 关键帧输出目录
        
        返回:
        关键帧路径列表
        """
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        if output_dir is None:
            output_dir = tempfile.mkdtemp()
        elif not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            scenes = scenes_info.get('scenes', [])
            if not scenes:
                return "Error: No scenes provided in scenes_info"
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return f"Error: Could not open video: {video_path}"
            
            frame_paths = []
            
            # 为每个场景提取中间帧作为代表帧
            for scene in scenes:
                scene_num = scene['scene_number']
                start_frame = scene['start_frame']
                end_frame = scene['end_frame']
                
                # 获取场景中间的帧
                middle_frame = (start_frame + end_frame) // 2
                
                # 设置位置并读取帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
                ret, frame = cap.read()
                
                if ret:
                    # 保存帧
                    frame_path = os.path.join(output_dir, f"scene_{scene_num:03d}_frame_{middle_frame}.jpg")
                    cv2.imwrite(frame_path, frame)
                    
                    # 还可以保存场景的起始和结束帧
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                    ret, start_frame_img = cap.read()
                    if ret:
                        start_frame_path = os.path.join(output_dir, f"scene_{scene_num:03d}_start.jpg")
                        cv2.imwrite(start_frame_path, start_frame_img)
                        frame_paths.append(start_frame_path)
                    
                    # 确保结束帧不超出视频范围
                    if end_frame > 0:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, end_frame - 1)
                        ret, end_frame_img = cap.read()
                        if ret:
                            end_frame_path = os.path.join(output_dir, f"scene_{scene_num:03d}_end.jpg")
                            cv2.imwrite(end_frame_path, end_frame_img)
                            frame_paths.append(end_frame_path)
                    
                    frame_paths.append(frame_path)
            
            cap.release()
            
            return {
                "frame_paths": frame_paths,
                "output_directory": output_dir,
                "total_frames_extracted": len(frame_paths)
            }
            
        except Exception as e:
            return f"Error extracting scene frames: {str(e)}"