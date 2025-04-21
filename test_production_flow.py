import os
import json
from services.video_production_service import VideoProductionService

# 设置输出目录
output_dir = "./test_production_output"
os.makedirs(output_dir, exist_ok=True)

# 创建视频生产服务实例
video_service = VideoProductionService(output_dir=output_dir)

# 测试纯视觉脚本
visual_script = """
我需要一个展示理想汽车炫酷外观和高性能的混剪视频，时长30秒左右，需要你帮我写脚本
"""

# 测试有音频的脚本
audio_script = """
特斯拉Model 3是一款集科技与环保于一体的电动车。
它的流线型设计不仅美观，更具有出色的空气动力学性能。
零至百公里加速仅需3.3秒，续航里程可达600公里。
"""

def test_visual_script_production():
    """测试纯视觉脚本视频生产流程"""
    print("开始测试纯视觉脚本处理流程...")
    
    # 设置特殊需求，以便更好地测试素材匹配
    special_requirements = "展示特斯拉车型，注重流线型设计和动态美感"
    
    # 使用纯视觉脚本模式生产视频
    result = video_service.produce_video(
        script=visual_script,
        target_duration=30.0,  
        style="",
        special_requirements=special_requirements,
        script_type="visual"  # 指定为纯视觉脚本
    )
    
    # 打印结果摘要
    print(f"\n视频生产完成，输出文件: {result['final_video']}")
    print(f"项目名称: {result['project_name']}")
    
    # 保存简化的结果摘要，方便查看
    summary = {
        "project_name": result["project_name"],
        "script_type": result["script_type"],
        "final_video": result["final_video"],
        "segments_count": len(result["requirements"]["data"].get("requirements", [])),
        "materials_count": len(result["materials"]["data"].get("results", [])) if "results" in result["materials"]["data"] else 0,
        "editing_segments_count": len(result["editing_plan"]["data"].get("segments", []))
    }
    
    with open(os.path.join(output_dir, f"{result['project_name']}_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return result

def test_audio_script_production():
    """测试有音频的脚本视频生产流程"""
    print("\n开始测试口播脚本处理流程...")
    
    # 设置特殊需求
    special_requirements = "展示特斯拉Model 3，强调科技感和环保理念"
    
    # 使用带音频的脚本模式生产视频
    result = video_service.produce_video(
        script=audio_script,
        target_duration=20.0,  # 预估时长20秒
        style="汽车广告",
        special_requirements=special_requirements,
        script_type="voiceover"  # 默认值，表示口播稿
    )
    
    # 打印结果摘要
    print(f"\n视频生产完成，输出文件: {result['final_video']}")
    print(f"项目名称: {result['project_name']}")
    
    # 保存简化的结果摘要
    summary = {
        "project_name": result["project_name"],
        "script_type": result["script_type"],
        "final_video": result["final_video"],
        "audio_segments_count": len(result["audio_info"]["segments"]) if "audio_info" in result else 0,
        "segments_count": len(result["requirements"]["data"].get("requirements", [])),
        "materials_count": len(result["materials"]["data"].get("results", [])) if "results" in result["materials"]["data"] else 0,
        "editing_segments_count": len(result["editing_plan"]["data"].get("segments", []))
    }
    
    with open(os.path.join(output_dir, f"{result['project_name']}_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return result

if __name__ == "__main__":
    print("=== 视频生产流程测试 ===\n")
    
    # 测试纯视觉脚本
    visual_result = test_visual_script_production()
    
    # 测试有音频的脚本
    # audio_result = test_audio_script_production()
    
    print("\n测试完成!") 