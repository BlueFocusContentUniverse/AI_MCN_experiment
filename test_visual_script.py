import os
from services.video_production_service import VideoProductionService

# 创建输出目录
output_dir = "./visual_script_test_output"
os.makedirs(output_dir, exist_ok=True)

# 创建视频生产服务
video_service = VideoProductionService(output_dir=output_dir)

# 测试视觉脚本
test_script = """
第一场景：车辆远景展示（10秒）
特斯拉Model 3停放在现代化的城市街道上，阳光照射下车身线条流畅优美。

第二场景：车内视角（8秒）
展示车内宽敞的空间和简约的中控台设计，突出大屏幕和无按键界面。

第三场景：驾驶场景（12秒）
车辆在城市道路上行驶，展示驾驶的流畅性和操控感。
"""

def test_parse_visual_script():
    """测试纯视觉脚本解析功能"""
    print("测试纯视觉脚本解析...")
    
    try:
        # 调用纯视觉脚本解析方法
        segments = video_service._parse_visual_script(
            script=test_script,
            target_duration=30.0,
            style="汽车广告"
        )
        
        # 打印解析结果
        print(f"\n成功解析视觉脚本，共找到 {len(segments)} 个场景:")
        for i, segment in enumerate(segments):
            print(f"\n场景 {i+1}:")
            print(f"  内容: {segment.get('content', '')}")
            print(f"  时长: {segment.get('duration', 0)} 秒")
            print(f"  情感: {segment.get('emotion', '')}")
            print(f"  场景类型: {segment.get('scene_type', '')}")
            
        return segments
        
    except Exception as e:
        print(f"解析视觉脚本失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_parse_visual_script() 