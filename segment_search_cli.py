#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import json
from services.segment_search_service import SegmentSearchService
from agents.segment_search_agent import SegmentSearchAgent, SegmentSearchTool

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
    parser.add_argument('--keep-audio', action='store_true', default=True,
                        help='是否保留原始音频')
    parser.add_argument('--use-agent', action='store_true',
                        help='使用Agent进行搜索，否则直接使用工具')
    parser.add_argument('--save-json', type=str, default=None,
                        help='保存搜索结果到指定的JSON文件')
    
    args = parser.parse_args()
    
    print(f"开始搜索文本: '{args.query}'")
    print(f"参数: 最大返回数量={args.limit}, 相似度阈值={args.threshold}, 输出目录={args.output_dir}, 保留音频={args.keep_audio}")
    
    # 设置环境变量（如果未设置）
    if not os.environ.get('SEGMENTS_JSON_PATH'):
        segments_json_path = os.path.join(os.getcwd(), 'segments', 'segments_info.json')
        print(f"设置SEGMENTS_JSON_PATH环境变量为: {segments_json_path}")
        os.environ['SEGMENTS_JSON_PATH'] = segments_json_path
    
    if args.use_agent:
        # 使用Agent进行搜索
        print(f"使用Agent搜索: '{args.query}'")
        agent = SegmentSearchAgent.create()
        result = agent.execute_task(f"搜索与以下文本匹配的视频片段，并以JSON格式输出结果：\n\n'{args.query}'")
        print("\n执行结果:")
        print(result)
        
        # 保存结果到JSON文件
        if args.save_json:
            try:
                # 尝试解析结果为JSON
                import re
                json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    json_data = json.loads(json_str)
                    with open(args.save_json, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    print(f"搜索结果已保存到: {args.save_json}")
                else:
                    print("无法从结果中提取JSON数据")
            except Exception as e:
                print(f"保存JSON时出错: {str(e)}")
    else:
        # 使用SegmentSearchService进行搜索和处理
        print(f"使用SegmentSearchService搜索和处理: '{args.query}'")
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
                print(f"  视频路径: {segment.get('video_path', '')}")
                print()
            
            # 保存结果到指定的JSON文件
            if args.save_json:
                with open(args.save_json, 'w', encoding='utf-8') as f:
                    json.dump(result['search_result']['data'], f, ensure_ascii=False, indent=2)
                print(f"搜索结果已保存到: {args.save_json}")

if __name__ == "__main__":
    main() 