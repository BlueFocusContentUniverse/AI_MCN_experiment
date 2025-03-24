#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from tools.text_matching_tool import TextMatchingTool

def test_text_matching():
    """测试文本匹配工具"""
    # 创建TextMatchingTool实例
    text_matching_tool = TextMatchingTool()
    
    # 测试查询
    test_queries = [
        "你一定能在你的领域里脱颖而出 你一定能做出让自己骄傲的事情来"
    ]
    
    # 对每个查询进行测试
    for query in test_queries:
        print(f"\n测试查询: '{query}'")
        results = text_matching_tool._run(query_text=query, limit=3)
        
        if not results:
            print("  未找到匹配结果")
            continue
        
        # 打印结果
        print(f"  找到 {len(results)} 个匹配结果:")
        for i, result in enumerate(results):
            print(f"  {i+1}. 相似度: {result['similarity_score']:.4f}")
            print(f"     文本: {result['text']}")
            print(f"     视频: {result['video_path']}")
            print(f"     时间: {result['start_time']:.2f}s - {result['end_time']:.2f}s")

if __name__ == "__main__":
    test_text_matching() 