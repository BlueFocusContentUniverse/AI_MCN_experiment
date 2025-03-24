#!/usr/bin/env python3
# batch_extract.py - 批量处理视频文件的脚本

import os
import sys
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from main import extract_video_info

# 常见视频文件扩展名
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp', '.ts']

def is_video_file(filename):
    """检查文件是否为视频文件"""
    _, ext = os.path.splitext(filename.lower())
    return ext in VIDEO_EXTENSIONS

def find_all_videos(root_dir):
    """遍历目录找到所有视频文件"""
    video_files = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if is_video_file(file):
                full_path = os.path.join(root, file)
                video_files.append(full_path)
    return video_files

def process_video(video_path, output_base_dir, preserve_structure, skip_mongodb, special_requirements):
    """处理单个视频文件"""
    try:
        if preserve_structure:
            # 保留原始目录结构
            rel_path = os.path.relpath(os.path.dirname(video_path), start=args.input_dir)
            output_dir = os.path.join(output_base_dir, rel_path)
        else:
            output_dir = output_base_dir
            
        os.makedirs(output_dir, exist_ok=True)
        
        # 调用主程序中的视频信息提取函数
        result = extract_video_info(video_path, output_dir, skip_mongodb, special_requirements)
        return (video_path, True, "处理成功")
    except Exception as e:
        return (video_path, False, str(e))

def main():
    parser = argparse.ArgumentParser(description="批量处理视频文件")
    parser.add_argument("--input-dir", "-i", default="/home/jinpeng/multi-agent/李想公关",
                      help="输入视频目录")
    parser.add_argument("--output-dir", "-o", default="./batch_output",
                      help="输出目录")
    parser.add_argument("--preserve-structure", "-p", action="store_true",
                      help="保留原始目录结构")
    parser.add_argument("--parallel", "-j", type=int, default=1,
                      help="并行处理的视频数量")
    parser.add_argument("--skip-mongodb", action="store_true",
                      help="跳过MongoDB连接")
    parser.add_argument("--special-requirements", "-r", default="",
                      help="特殊分析需求，将添加到任务描述中")
    
    global args
    args = parser.parse_args()
    
    # 确保输出目录存在
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 查找所有视频文件
    print(f"正在扫描 {args.input_dir} 中的视频文件...")
    video_files = find_all_videos(args.input_dir)
    
    if not video_files:
        print(f"在 {args.input_dir} 中未找到视频文件")
        return
    
    print(f"找到 {len(video_files)} 个视频文件")
    
    # 记录开始时间
    start_time = time.time()
    
    # 创建日志文件
    log_file = os.path.join(args.output_dir, "batch_process.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"批量处理开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入目录: {args.input_dir}\n")
        f.write(f"输出目录: {args.output_dir}\n")
        f.write(f"视频文件数量: {len(video_files)}\n")
        if args.special_requirements:
            f.write(f"特殊需求: {args.special_requirements}\n")
        f.write("\n")
    
    # 处理视频文件
    results = []
    if args.parallel > 1:
        print(f"使用 {args.parallel} 个进程并行处理视频...")
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(
                    process_video, 
                    video_path, 
                    args.output_dir, 
                    args.preserve_structure, 
                    args.skip_mongodb,
                    args.special_requirements
                ): video_path for video_path in video_files
            }
            
            for i, future in enumerate(as_completed(futures), 1):
                video_path = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(f"[{i}/{len(video_files)}] 处理: {os.path.basename(video_path)} - {'成功' if result[1] else '失败'}")
                except Exception as e:
                    results.append((video_path, False, str(e)))
                    print(f"[{i}/{len(video_files)}] 处理: {os.path.basename(video_path)} - 出错: {e}")
    else:
        print("按顺序处理视频...")
        for i, video_path in enumerate(video_files, 1):
            print(f"[{i}/{len(video_files)}] 处理: {os.path.basename(video_path)}")
            result = process_video(video_path, args.output_dir, args.preserve_structure, args.skip_mongodb, args.special_requirements)
            results.append(result)
            print(f"  状态: {'成功' if result[1] else '失败 - ' + result[2]}")
    
    # 计算处理时间
    total_time = time.time() - start_time
    minutes, seconds = divmod(total_time, 60)
    hours, minutes = divmod(minutes, 60)
    
    # 统计结果
    success_count = sum(1 for _, success, _ in results if success)
    
    # 写入日志文件
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n处理结果汇总:\n")
        f.write(f"总视频数: {len(video_files)}\n")
        f.write(f"成功处理: {success_count}\n")
        f.write(f"处理失败: {len(video_files) - success_count}\n")
        f.write(f"总耗时: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}\n\n")
        
        f.write("详细处理记录:\n")
        for video_path, success, message in results:
            status = "成功" if success else "失败"
            f.write(f"{video_path}: {status}")
            if not success:
                f.write(f" - {message}")
            f.write("\n")
    
    # 打印最终摘要
    print("\n处理完成!")
    print(f"总视频数: {len(video_files)}")
    print(f"成功处理: {success_count}")
    print(f"处理失败: {len(video_files) - success_count}")
    print(f"总耗时: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
    print(f"详细日志已保存至: {log_file}")

if __name__ == "__main__":
    main() 