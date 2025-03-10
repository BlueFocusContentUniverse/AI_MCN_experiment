import os
import sys
from tools.vision_analysis_enhanced import ExtractVideoFramesTool
from pathlib import Path

def test_extract_frames():
    """测试视频帧提取功能"""
    # 创建工具实例
    extract_frames_tool = ExtractVideoFramesTool()
    
    # 设置测试参数
    video_path = "./debug_video.mp4"  # 替换为实际的测试视频路径
    output_dir = "./debug_output/frames"
    frame_interval = 1  # 每秒提取1帧
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"开始测试视频帧提取功能...")
    print(f"视频路径: {video_path}")
    print(f"输出目录: {output_dir}")
    print(f"帧间隔: {frame_interval}秒")
    
    # 检查视频文件是否存在
    if not os.path.exists(video_path):
        print(f"错误: 视频文件 {video_path} 不存在!")
        return False
    
    try:
        # 调用提取工具
        result = extract_frames_tool._run(
            video_path=video_path,
            output_dir=output_dir,
            frame_interval=frame_interval
        )
        
        # 验证结果
        if isinstance(result, dict) and "frames_dir" in result and "frame_count" in result:
            frames_dir = result["frames_dir"]
            frame_count = result["frame_count"]
            
            # 检查是否有帧被提取
            if frame_count > 0:
                print(f"成功提取 {frame_count} 帧!")
                print(f"帧保存在: {frames_dir}")
                
                # 检查帧文件是否存在
                frames_path = Path(frames_dir)
                frame_files = list(frames_path.glob("*.jpg"))
                if len(frame_files) == frame_count:
                    print(f"验证通过: 所有 {frame_count} 帧文件都存在")
                else:
                    print(f"验证失败: 预期 {frame_count} 帧，但找到 {len(frame_files)} 个文件")
                
                # 打印前5个帧的文件名
                if frame_files:
                    print("前5个帧文件:")
                    for i, frame in enumerate(sorted(frame_files)[:5]):
                        print(f"  {i+1}. {frame.name}")
                
                return True
            else:
                print("警告: 没有帧被提取!")
                return False
        else:
            print(f"错误: 工具返回了意外的结果格式: {result}")
            return False
    
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 如果命令行提供了视频路径，使用它
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        test_extract_frames(video_path)
    else:
        test_extract_frames() 