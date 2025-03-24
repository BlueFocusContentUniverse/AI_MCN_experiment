#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from services.segment_search_service import SegmentSearchService

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='使用Agent Task搜索与给定文本匹配的视频片段并处理')
    parser.add_argument('--query', type=str, required=True,
                        help='需要匹配的文本内容')
    parser.add_argument('--limit', type=int, default=5,
                        help='最大返回数量')
    parser.add_argument('--threshold', type=float, default=0.1,
                        help='相似度阈值，低于此值的结果将被过滤')
    parser.add_argument('--output-dir', type=str, default="./output",
                        help='输出目录')
    parser.add_argument('--keep-audio', action='store_true',
                        help='是否保留原始音频')
    
    args = parser.parse_args()
    
    print(f"开始搜索文本: '{args.query}'")
    print(f"参数: 最大返回数量={args.limit}, 相似度阈值={args.threshold}, 输出目录={args.output_dir}, 保留音频={args.keep_audio}")
    
    # 创建服务并执行搜索和处理
    service = SegmentSearchService(output_dir=args.output_dir)
    result = service.search_and_process(
        query_text=args.query,
        limit=args.limit,
        threshold=args.threshold,
        keep_audio=args.keep_audio
    )
    
    # 打印结果
    if "error" in result:
        print(f"错误: {result['error']}")
    else:
        print(f"\n处理完成!")
        print(f"输出文件: {result['final_video']}")
        print(f"总共合并了 {len(result['segment_paths'])} 个视频片段")
        print(f"搜索结果保存在: {result['search_result']['file']}")
        
        # 打印匹配的片段信息
        print("\n匹配的片段信息:")
        for i, segment in enumerate(result['search_result']['data']):
            print(f"片段 {i+1}:")
            print(f"  ID: {segment.get('segment_id', 'unknown')}")
            print(f"  文本: {segment.get('text', '')[:50]}..." if len(segment.get('text', '')) > 50 else f"  文本: {segment.get('text', '')}")
            print(f"  相似度: {segment.get('similarity_score', 0):.4f}")
            print(f"  视频路径: {segment.get('segment_path', '')}")
            print()

if __name__ == "__main__":
    main() 