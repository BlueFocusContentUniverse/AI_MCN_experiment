#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
from pathlib import Path

# 将项目根目录添加到Python路径
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.material_matching_service import MaterialMatchingService
from services.mongodb_service import MongoDBService

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="视频素材智能匹配测试工具")
    parser.add_argument("-s", "--script", help="脚本文件路径", required=True)
    parser.add_argument("-o", "--output", help="输出文件路径", default="./material_matching_result.json")
    parser.add_argument("-v", "--verbose", help="显示详细信息", action="store_true")
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    
    # 检查脚本文件是否存在
    if not os.path.exists(args.script):
        print(f"脚本文件不存在: {args.script}")
        return 1
    
    # 读取脚本内容
    try:
        with open(args.script, 'r', encoding='utf-8') as f:
            script_content = f.read()
    except Exception as e:
        print(f"读取脚本文件出错: {e}")
        return 1
    
    # 初始化服务
    print("初始化MongoDB服务和匹配服务...")
    try:
        mongodb_service = MongoDBService()
        material_matcher = MaterialMatchingService(mongodb_service=mongodb_service)
    except Exception as e:
        print(f"初始化服务出错: {e}")
        return 1
    
    # 获取视频库摘要
    print("获取视频库摘要...")
    try:
        summary = material_matcher.get_library_summary()
        print(f"视频库包含 {summary['total_videos']} 个视频，{summary['total_segments']} 个视频片段")
        print(f"可用品牌: {summary['brands']}")
        print(f"可用镜头类型: {summary['shot_types'][:5]}..." if len(summary['shot_types']) > 5 else f"可用镜头类型: {summary['shot_types']}")
    except Exception as e:
        print(f"获取视频库摘要出错: {e}")
        return 1
    
    # 执行匹配
    print(f"开始执行脚本到视频匹配，这可能需要一些时间...")
    start_time = time.time()
    try:
        result = material_matcher.match_script_to_video(script_content)
        elapsed = time.time() - start_time
        print(f"匹配完成，耗时 {elapsed:.2f} 秒")
        
        # 打印摘要信息
        scenes_count = len(result["script_analysis"].get("scenes", []))
        matched_count = sum(1 for scene in result["shotlist"]["scenes"] if "selected_clip" in scene)
        
        print(f"脚本标题: {result['script_analysis'].get('title', '未命名脚本')}")
        print(f"识别场景数: {scenes_count}")
        print(f"成功匹配场景数: {matched_count}/{scenes_count}")
        print(f"生成视频预计时长: {result['shotlist'].get('total_duration', 0):.1f} 秒")
        
        # 详细信息
        if args.verbose:
            print("\n--- 详细匹配结果 ---")
            for i, scene in enumerate(result["shotlist"]["scenes"]):
                print(f"\n场景 {i+1}: {scene.get('scene_id', f'场景{i+1}')}")
                print(f"描述: {scene.get('scene_description', '无描述')}")
                
                if "selected_clip" in scene:
                    clip = scene["selected_clip"]
                    print(f"最佳匹配: 得分={clip.get('similarity_score', 0):.2f}, "
                          f"时长={clip.get('duration', 0):.2f}秒, "
                          f"镜头类型={clip.get('shot_type', '未知')}")
                    print(f"匹配原因: {', '.join(clip.get('match_reasons', ['未知']))}")
                else:
                    print("未找到匹配片段")
        
        # 保存结果
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"匹配结果已保存到: {args.output}")
        
        return 0
        
    except Exception as e:
        print(f"执行匹配出错: {e}")
        return 1
    finally:
        # 关闭MongoDB连接
        mongodb_service.close()

if __name__ == "__main__":
    sys.exit(main()) 