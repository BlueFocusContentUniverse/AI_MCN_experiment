import json
import os
from agents.editing_planning_agent import EditingPlanningAgent, EditingPlanTool

# 创建测试分段数据
test_segments = [
    {
        "segment_id": 1,
        "text": "这是一个测试音频分段",
        "duration": 10.0,
        "audio_file": None
    },
    {
        "segment_id": 2,
        "text": "这是第二个测试音频分段",
        "duration": 15.0,
        "audio_file": None
    }
]

# 创建测试视觉场景分段
test_visual_segments = [
    {
        "segment_id": 1,
        "content": "城市天际线全景",
        "text": "城市天际线全景",
        "description": "现代化城市天际线的全景镜头，展示城市的繁华与现代感",
        "visual_elements": ["城市", "高楼", "天际线"],
        "start_time": 0,
        "end_time": 8,
        "duration": 8,
        "emotion": "壮观",
        "scene_type": "场景展示"
    },
    {
        "segment_id": 2,
        "content": "车辆行驶在城市道路上",
        "text": "车辆行驶在城市道路上",
        "description": "车辆行驶在宽阔的城市道路上，展示车辆的动态美感",
        "visual_elements": ["道路", "车辆", "城市"],
        "start_time": 8,
        "end_time": 16,
        "duration": 8,
        "emotion": "流畅",
        "scene_type": "产品展示"
    }
]

# 创建测试素材数据 - 列表格式
test_materials_list = [
    {
        "video_path": "/videos/city_view.mp4",
        "shot_type": "全景",
        "description": "城市全景镜头，展示现代化城市风貌",
        "duration": 15.0,
        "start_time": 0.0,
        "end_time": 15.0,
        "similarity_score": 0.85
    },
    {
        "video_path": "/videos/car_driving.mp4",
        "shot_type": "跟踪镜头",
        "description": "跟踪拍摄行驶中的汽车，展示车辆动态",
        "duration": 12.0,
        "start_time": 5.0,
        "end_time": 17.0,
        "similarity_score": 0.78
    }
]

# 创建测试素材数据 - 基于MongoDB的结构
test_materials_mongo = {
    "results": [
        {
            "requirement": {
                "description": "城市场景",
                "scene_type": "场景展示"
            },
            "matching_videos": [
                {
                    "video_path": "/videos/city_aerial.mp4",
                    "video_title": "城市航拍",
                    "segments": [
                        {
                            "start_time": 10.0,
                            "end_time": 20.0,
                            "duration": 10.0,
                            "shot_type": "航拍",
                            "description": "城市建筑航拍镜头",
                            "match_reason": "场景类型匹配"
                        }
                    ]
                }
            ]
        },
        {
            "requirement": {
                "description": "车辆行驶",
                "scene_type": "产品展示"
            },
            "matching_videos": [
                {
                    "video_path": "/videos/car_road.mp4",
                    "video_title": "汽车道路行驶",
                    "segments": [
                        {
                            "start_time": 3.0,
                            "end_time": 13.0,
                            "duration": 10.0,
                            "shot_type": "跟踪",
                            "description": "车辆在道路上行驶",
                            "match_reason": "内容与需求匹配"
                        }
                    ]
                }
            ]
        }
    ]
}

def test_editing_plan_tool():
    """测试EditingPlanTool能否正确处理各种格式的素材数据"""
    # 创建工具实例
    tool = EditingPlanTool()
    
    print("=== 测试处理列表格式素材 ===")
    result1 = tool._run(test_segments, test_materials_list, has_audio=True)
    print(f"提取到 {len(result1['available_materials'])} 个素材")
    
    print("\n=== 测试处理MongoDB格式素材（有音频） ===")
    result2 = tool._run(test_segments, test_materials_mongo, has_audio=True)
    print(f"提取到 {len(result2['available_materials'])} 个素材")
    
    print("\n=== 测试处理MongoDB格式素材（纯视觉） ===")
    result3 = tool._run(test_visual_segments, test_materials_mongo, has_audio=False)
    print(f"提取到 {len(result3['available_materials'])} 个素材")
    
    return result1, result2, result3

def main():
    # 设置测试输出目录
    os.makedirs("test_output", exist_ok=True)
    
    print("测试EditingPlanningAgent组件...")
    
    # 测试EditingPlanTool
    result1, result2, result3 = test_editing_plan_tool()
    
    # 保存结果以便分析
    with open("test_output/result_list_format.json", "w", encoding="utf-8") as f:
        json.dump(result1, f, ensure_ascii=False, indent=2)
        
    with open("test_output/result_mongo_format_audio.json", "w", encoding="utf-8") as f:
        json.dump(result2, f, ensure_ascii=False, indent=2)
        
    with open("test_output/result_mongo_format_visual.json", "w", encoding="utf-8") as f:
        json.dump(result3, f, ensure_ascii=False, indent=2)
    
    print("\n测试结果已保存到 test_output 目录")
    
    # 打印提示词分析
    print("\n=== 有音频的提示词 ===")
    print(result1["message"][:200] + "...")
    
    print("\n=== 纯视觉的提示词 ===")
    print(result3["message"][:200] + "...")
    
    print("\n测试完成!")

if __name__ == "__main__":
    main() 