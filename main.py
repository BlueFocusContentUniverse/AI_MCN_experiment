# main.py
import os
import sys
import json
import argparse
from dotenv import load_dotenv
from services.video_info_extractor import VideoInfoExtractor
from services.video_production_service import VideoProductionService

# 加载环境变量
load_dotenv()

def extract_video_info(video_path, output_dir="./output", skip_mongodb=False):
    """提取视频信息"""
    extractor = VideoInfoExtractor(output_dir=output_dir, skip_mongodb=skip_mongodb)
    result = extractor.extract_video_info(video_path)
    
    # 保存结果
    os.makedirs(output_dir, exist_ok=True)
    result_file = os.path.join(output_dir, f"video_info_{os.path.basename(video_path)}.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"视频信息提取完成，结果已保存到: {result_file}")
    return result

def produce_video(script, target_duration=60.0, style="汽车广告", output_dir="./output"):
    """生产视频"""
    producer = VideoProductionService(output_dir=output_dir)
    result = producer.produce_video(script, target_duration, style)
    
    print(f"视频生产完成，最终视频: {result['final_video']}")
    return result

def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description="视频处理工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 提取视频信息命令
    extract_parser = subparsers.add_parser("extract", help="提取视频信息")
    extract_parser.add_argument("video_path", help="视频文件路径")
    extract_parser.add_argument("--output", "-o", default="./output", help="输出目录")
    extract_parser.add_argument("--skip-mongodb", action="store_true", help="跳过MongoDB连接")
    
    # 生产视频命令
    produce_parser = subparsers.add_parser("produce", help="生产视频")
    produce_parser.add_argument("script_file", help="口播稿文件路径")
    produce_parser.add_argument("--duration", "-d", type=float, default=60.0, help="目标视频时长（秒）")
    produce_parser.add_argument("--style", "-s", default="汽车广告", help="视频风格")
    produce_parser.add_argument("--output", "-o", default="./output", help="输出目录")
    
    args = parser.parse_args()
    
    if args.command == "extract":
        extract_video_info(args.video_path, args.output, args.skip_mongodb)
    elif args.command == "produce":
        # 读取口播稿文件
        with open(args.script_file, 'r', encoding='utf-8') as f:
            script = f.read()
        
        produce_video(script, args.duration, args.style, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    # if len(sys.argv) == 1:
    #     # 设置调试参数
    #     video_path = "temp1.mp4"
    #     output_dir = "./debug_output"  # 可以设置一个专门用于调试的输出目录
    #     skip_mongodb = False  # 调试时可能想跳过数据库连接

    #     # 调用提取函数
    #     result = extract_video_info(video_path, output_dir, skip_mongodb)

    #     # 可以在这里添加额外的调试代码
    #     print("调试信息:")
    #     print(f"处理的视频: {video_path}")
    #     print(f"输出目录: {output_dir}")
    #     print("提取结果摘要:")
    #     # 打印结果的一部分关键信息，避免输出过多
    #     for key in result:
    #         if isinstance(result[key], dict):
    #             print(f"  {key}: {len(result[key])} 项")
    #         elif isinstance(result[key], list):
    #             print(f"  {key}: {len(result[key])} 个元素")
    #         else:
    #             print(f"  {key}: {result[key]}")
    # 调试模式
    if len(sys.argv) == 1:
        # 设置调试参数 - 视频生产
        script_file = "./debug_script.txt"  # 口播稿文件路径
        target_duration = 60.0  # 目标视频时长（秒）
        style = "汽车广告"  # 视频风格
        output_dir = "./debug_output"  # 可以设置一个专门用于调试的输出目录
        
        # 读取口播稿文件
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                script = f.read()
        except FileNotFoundError:
            # 如果文件不存在，创建一个示例口播稿
            script = "这是一个测试口播稿，用于调试视频生产功能。这款车型设计优雅，性能卓越，是驾驶者的理想选择。"
            os.makedirs(os.path.dirname(script_file) or '.', exist_ok=True)
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script)
            print(f"已创建示例口播稿文件: {script_file}")

        # 调用视频生产函数
        result = produce_video(script, target_duration, style, output_dir)

        # 可以在这里添加额外的调试代码
        print("调试信息:")
        print(f"口播稿: {script[:50]}..." if len(script) > 50 else script)
        print(f"目标时长: {target_duration}秒")
        print(f"视频风格: {style}")
        print(f"输出目录: {output_dir}")
        print("生产结果摘要:")
        # 打印结果的一部分关键信息，避免输出过多
        for key in result:
            if isinstance(result[key], dict):
                print(f"  {key}: {len(result[key])} 项")
            elif isinstance(result[key], list):
                print(f"  {key}: {len(result[key])} 个元素")
            else:
                print(f"  {key}: {result[key]}")
    else:
        main()
