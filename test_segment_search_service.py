#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import traceback
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_segment_search_service():
    """测试SegmentSearchService"""
    try:
        # 打印当前工作目录
        print(f"当前工作目录: {os.getcwd()}")
        
        # 检查环境变量
        print("检查环境变量:")
        print(f"OPENAI_API_KEY: {'已设置' if os.environ.get('OPENAI_API_KEY') else '未设置'}")
        print(f"OPENAI_BASE_URL: {'已设置' if os.environ.get('OPENAI_BASE_URL') else '未设置'}")
        print(f"SEGMENTS_JSON_PATH: {'已设置' if os.environ.get('SEGMENTS_JSON_PATH') else '未设置'}")
        
        # 设置环境变量（如果未设置）
        if not os.environ.get('SEGMENTS_JSON_PATH'):
            segments_json_path = os.path.join(os.getcwd(), 'segments', 'segments_info.json')
            print(f"设置SEGMENTS_JSON_PATH环境变量为: {segments_json_path}")
            os.environ['SEGMENTS_JSON_PATH'] = segments_json_path
        
        # 创建输出目录
        output_dir = "./test_output"
        os.makedirs(output_dir, exist_ok=True)
        print(f"创建输出目录: {output_dir}")
        
        # 导入服务
        print("导入SegmentSearchService...")
        try:
            from services.segment_search_service import SegmentSearchService
            print("成功导入SegmentSearchService")
        except ImportError as e:
            print(f"导入SegmentSearchService失败: {str(e)}")
            print("尝试添加当前目录到sys.path...")
            sys.path.append(os.getcwd())
            try:
                from services.segment_search_service import SegmentSearchService
                print("成功导入SegmentSearchService")
            except ImportError as e2:
                print(f"再次导入失败: {str(e2)}")
                raise
        
        # 创建服务
        print("创建SegmentSearchService实例...")
        service = SegmentSearchService(output_dir=output_dir)
        print("成功创建SegmentSearchService实例")
        
        # 测试查询
        test_query = "你一定能在你的领域里脱颖而出 你一定能做出让自己骄傲的事情来"
        
        print(f"开始搜索文本: '{test_query}'")
        
        # 执行搜索和处理
        print("调用search_and_process方法...")
        result = service.search_and_process(
            query_text=test_query,
            limit=10,
            threshold=0.1,
            keep_audio=True
        )
        print("search_and_process方法执行完成")
        
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
        
        # 保存结果到文件
        result_file = os.path.join(output_dir, "test_result.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"测试结果已保存到: {result_file}")
    
    except Exception as e:
        print(f"测试过程中出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    print("开始执行测试...")
    test_segment_search_service()
    print("测试执行完毕") 