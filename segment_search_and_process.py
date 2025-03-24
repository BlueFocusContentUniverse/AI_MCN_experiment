#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import json
import tempfile
from pathlib import Path
from agents.segment_search_agent import SegmentSearchTool
from tools.segment_processor import SegmentProcessor

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='搜索与给定文本匹配的视频片段并处理')
    parser.add_argument('--query', type=str, required=True,
                        help='需要匹配的文本内容')
    parser.add_argument('--limit', type=int, default=5,
                        help='最大返回数量')
    parser.add_argument('--output', type=str, default='output.mp4',
                        help='输出视频文件路径')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='输出目录，用于存放临时文件')
    parser.add_argument('--save-json', type=str, default=None,
                        help='保存搜索结果到JSON文件')
    parser.add_argument('--threshold', type=float, default=0.1,
                        help='相似度阈值，低于此值的结果将被过滤')
    
    args = parser.parse_args()
    
    # 创建输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(os.path.dirname(os.path.abspath(args.output)))
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 搜索匹配的视频片段
    print(f"搜索文本: '{args.query}'")
    search_tool = SegmentSearchTool()
    search_results = search_tool._run(query_text=args.query, limit=args.limit, output_format="json")
    
    # 解析搜索结果
    try:
        results = json.loads(search_results)
        print(f"找到 {len(results)} 个匹配结果")
        
        # 过滤低相似度的结果
        if args.threshold > 0:
            filtered_results = []
            for r in results:
                try:
                    similarity_score = float(r.get("similarity_score", 0))
                    if similarity_score >= args.threshold:
                        filtered_results.append(r)
                except (ValueError, TypeError):
                    # 如果无法转换为浮点数，保留结果
                    filtered_results.append(r)
            
            if len(filtered_results) < len(results):
                print(f"过滤掉 {len(results) - len(filtered_results)} 个低相似度结果（阈值: {args.threshold}）")
                results = filtered_results
        
        if not results:
            print("没有找到符合条件的匹配结果")
            return
    except json.JSONDecodeError:
        print("搜索结果解析失败")
        return
    
    # 保存搜索结果到JSON文件
    if args.save_json:
        with open(args.save_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"搜索结果已保存到: {args.save_json}")
    
    # 2. 处理视频片段
    print(f"\n开始处理视频片段...")
    processor = SegmentProcessor(output_dir=args.output_dir)
    
    try:
        # 提取每个片段
        segment_paths = []
        for i, result in enumerate(results):
            try:
                print(f"\n结果 {i+1}:")
                print(f"  片段ID: {result.get('segment_id', 'unknown')}")
                print(f"  原始视频: {result.get('original_video_path', result.get('video_path', 'unknown'))}")
                print(f"  文本内容: {result.get('text', '')}")
                print(f"  时间范围: {result.get('start_time', 0)} - {result.get('end_time', 0)}")
                # 安全地处理相似度
                try:
                    similarity_score = float(result.get('similarity_score', 0))
                    print(f"  相似度: {similarity_score:.4f}")
                except (ValueError, TypeError):
                    print(f"  相似度: {result.get('similarity_score', 0)}")
                segment_path = processor.extract_segment(result)
                segment_paths.append(segment_path)
                print(f"已提取片段 {i+1}/{len(results)}: {os.path.basename(segment_path)}")
            except Exception as e:
                print(f"提取片段 {i+1}/{len(results)} 时出错: {str(e)}")
        
        if not segment_paths:
            print("没有成功提取任何片段")
            return
        
        # 合并所有片段
        output_path = processor.merge_segments(segment_paths, args.output)
        print(f"\n处理完成，输出文件: {output_path}")
        print(f"总共合并了 {len(segment_paths)} 个视频片段")
        
    except Exception as e:
        print(f"处理视频片段时出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 