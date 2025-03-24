#!/usr/bin/env python3
# batch_produce.py - 批量生产视频的脚本

import os
import sys
import time
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from main import produce_video

# 支持的口播稿文件扩展名
SCRIPT_EXTENSIONS = ['.txt', '.md', '.json']

def is_script_file(filename):
    """检查文件是否为口播稿文件"""
    _, ext = os.path.splitext(filename.lower())
    return ext in SCRIPT_EXTENSIONS

def find_all_scripts(root_dir):
    """遍历目录找到所有口播稿文件"""
    script_files = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if is_script_file(file):
                full_path = os.path.join(root, file)
                script_files.append(full_path)
    return script_files

def read_script(script_path):
    """读取口播稿文件内容"""
    _, ext = os.path.splitext(script_path.lower())
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            if ext == '.json':
                # 如果是JSON文件，尝试提取script字段
                data = json.load(f)
                if isinstance(data, dict) and 'script' in data:
                    return data['script']
                else:
                    # 如果没有script字段，将整个JSON转为字符串
                    return json.dumps(data, ensure_ascii=False)
            else:
                # 如果是文本文件，直接读取
                return f.read()
    except Exception as e:
        raise ValueError(f"读取口播稿文件失败: {str(e)}")

def process_script(script_path, output_base_dir, preserve_structure, target_duration, style, special_requirements, input_dir=None):
    """处理单个口播稿文件"""
    try:
        # 读取口播稿
        script = read_script(script_path)
        
        if preserve_structure and input_dir:
            # 保留原始目录结构
            rel_path = os.path.relpath(os.path.dirname(script_path), start=input_dir)
            output_dir = os.path.join(output_base_dir, rel_path)
        else:
            output_dir = output_base_dir
            
        os.makedirs(output_dir, exist_ok=True)
        
        # 调用主程序中的视频生产函数
        result = produce_video(script, target_duration, style, special_requirements)
        
        # 返回处理结果
        return (script_path, True, result.get('final_video', '未知'), "处理成功")
    except Exception as e:
        return (script_path, False, None, str(e))

def main():
    # 设置特定参数
    input_dir = "./list"
    output_dir = "./batch_videos"  # 使用默认输出目录
    preserve_structure = True  # 保留目录结构
    parallel = 3  # 默认单进程处理
    duration = 60.0  # 默认视频时长60秒
    style = "搞笑"  # 设置视频风格为搞笑
    special_requirements = """这次生产任务将用于理想创始人李想的个人营销，目的是扩大李想的影响力，**必须使用李想公关文件夹下的视频！！！**"""
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 查找所有口播稿文件
    print(f"正在扫描 {input_dir} 中的口播稿文件...")
    script_files = find_all_scripts(input_dir)
    
    if not script_files:
        print(f"在 {input_dir} 中未找到口播稿文件")
        return
    
    print(f"找到 {len(script_files)} 个口播稿文件")
    
    # 记录开始时间
    start_time = time.time()
    
    # 创建日志文件
    log_file = os.path.join(output_dir, "batch_produce.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"批量生产开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入目录: {input_dir}\n")
        f.write(f"输出目录: {output_dir}\n")
        f.write(f"口播稿文件数量: {len(script_files)}\n")
        f.write(f"目标视频时长: {duration}秒\n")
        f.write(f"视频风格: {style}\n")
        f.write(f"特殊需求: {special_requirements}\n")
        f.write("\n")
    
    # 处理口播稿文件
    results = []
    if parallel > 1:
        print(f"使用 {parallel} 个进程并行处理口播稿...")
        with ProcessPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(
                    process_script, 
                    script_path, 
                    output_dir, 
                    preserve_structure, 
                    duration,
                    style,
                    special_requirements,
                    input_dir  # 传入input_dir参数
                ): script_path for script_path in script_files
            }
            
            for i, future in enumerate(as_completed(futures), 1):
                script_path = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    status = '成功' if result[1] else '失败'
                    print(f"[{i}/{len(script_files)}] 处理: {os.path.basename(script_path)} - {status}")
                    if result[1]:  # 如果成功
                        print(f"  生成视频: {result[2]}")
                except Exception as e:
                    results.append((script_path, False, None, str(e)))
                    print(f"[{i}/{len(script_files)}] 处理: {os.path.basename(script_path)} - 出错: {e}")
    else:
        print("按顺序处理口播稿...")
        for i, script_path in enumerate(script_files, 1):
            print(f"[{i}/{len(script_files)}] 处理: {os.path.basename(script_path)}")
            result = process_script(
                script_path, 
                output_dir, 
                preserve_structure, 
                duration,
                style,
                special_requirements,
                input_dir  # 传入input_dir参数
            )
            results.append(result)
            status = '成功' if result[1] else '失败'
            print(f"  状态: {status}")
            if result[1]:  # 如果成功
                print(f"  生成视频: {result[2]}")
            else:
                print(f"  错误: {result[3]}")
    
    # 计算处理时间
    total_time = time.time() - start_time
    minutes, seconds = divmod(total_time, 60)
    hours, minutes = divmod(minutes, 60)
    
    # 统计结果
    success_count = sum(1 for _, success, _, _ in results if success)
    
    # 写入日志文件
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n处理结果汇总:\n")
        f.write(f"总口播稿数: {len(script_files)}\n")
        f.write(f"成功处理: {success_count}\n")
        f.write(f"处理失败: {len(script_files) - success_count}\n")
        f.write(f"总耗时: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}\n\n")
        
        f.write("详细处理记录:\n")
        for script_path, success, video_path, message in results:
            status = "成功" if success else "失败"
            f.write(f"{script_path}: {status}")
            if success:
                f.write(f" - 生成视频: {video_path}")
            else:
                f.write(f" - {message}")
            f.write("\n")
    
    # 打印最终摘要
    print("\n处理完成!")
    print(f"总口播稿数: {len(script_files)}")
    print(f"成功处理: {success_count}")
    print(f"处理失败: {len(script_files) - success_count}")
    print(f"总耗时: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
    print(f"详细日志已保存至: {log_file}")

if __name__ == "__main__":
    main() 