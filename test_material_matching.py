#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import sys
import logging
from services.material_matching_service import MaterialMatchingService
from services.mongodb_service import MongoDBService
from services.embedding_service import EmbeddingService
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_script_matching():
    """测试脚本到视频的匹配功能"""
    try:
        # 初始化服务
        material_matching_service = MaterialMatchingService()
        
        # 测试脚本
        script = """
        # 场景一：产品展示
        特写镜头，汽车外观设计，展示车身流线型设计和前脸造型。感觉时尚现代，充满科技感。
        
        # 场景二：功能演示
        中景，汽车内饰，驾驶者操作中控屏，展示智能导航系统。镜头平稳，展现科技感。
        
        # 场景三：驾驶体验
        远景跟随拍摄，汽车在山路上行驶，展现操控性能。画面明亮，天空湛蓝，感觉令人振奋。
        
        # 场景四：车辆特写
        特写镜头，车灯亮起，聚焦前大灯设计。夜间氛围，营造神秘感。
        """
        
        # 记录开始时间
        start_time = time.time()
        
        # 执行匹配
        results = material_matching_service.match_script_to_video(script)
        
        # 计算耗时
        elapsed_time = time.time() - start_time
        logger.info(f"脚本匹配完成，耗时: {elapsed_time:.2f}秒")
        
        # 输出脚本分析结果
        script_analysis = results.get("script_analysis", {})
        logger.info(f"脚本标题: {script_analysis.get('title', '未知')}")
        logger.info(f"品牌: {script_analysis.get('brand', '未知')}")
        logger.info(f"基调: {script_analysis.get('tonality', '未知')}")
        
        # 输出场景分析
        scenes = script_analysis.get("scenes", [])
        logger.info(f"识别到 {len(scenes)} 个场景")
        for i, scene in enumerate(scenes):
            logger.info(f"场景 {i+1}: {scene.get('id', f'场景{i+1}')}")
            logger.info(f"  描述: {scene.get('description', '无描述')}")
            logger.info(f"  镜头类型: {scene.get('shot_type_preference', '未指定')}")
            logger.info(f"  情感基调: {scene.get('emotion', '未指定')}")
            logger.info(f"  功能: {scene.get('function', '未指定')}")
            logger.info(f"  关键元素: {', '.join(scene.get('key_elements', []))}")
            logger.info(f"  视觉对象: {', '.join(scene.get('visual_objects', []))}")
            logger.info("  ------------")
        
        # 输出匹配结果
        shotlist = results.get("shotlist", {})
        shots = shotlist.get("shots", [])
        logger.info(f"匹配到 {len(shots)} 个镜头")
        
        for i, shot in enumerate(shots):
            scene_id = shot.get("scene_id", "未知")
            segment = shot.get("segment", {})
            logger.info(f"镜头 {i+1} (场景 {scene_id}):")
            logger.info(f"  视频: {segment.get('video_info', {}).get('title', '未知')}")
            logger.info(f"  时间: {segment.get('start_time', 0):.1f}s - {segment.get('end_time', 0):.1f}s")
            logger.info(f"  镜头类型: {segment.get('shot_type', '未知')}")
            logger.info(f"  得分: {segment.get('final_score', 0):.2f}")
            logger.info(f"  匹配原因: {', '.join(segment.get('match_reasons', []))}")
            logger.info("  ------------")
        
        return True
        
    except Exception as e:
        logger.error(f"测试脚本匹配时出错: {str(e)}")
        return False

def test_update_embeddings():
    """测试更新嵌入向量功能"""
    try:
        # 初始化服务
        mongodb_service = MongoDBService()
        embedding_service = EmbeddingService()
        
        # 获取所有视频ID
        db = mongodb_service.db
        video_ids = list(db.videos.find({}, {"_id": 1}))
        
        if not video_ids:
            logger.warning("没有找到视频")
            return False
        
        # 选择第一个视频进行测试
        video_id = str(video_ids[0]["_id"])
        logger.info(f"测试视频 ID: {video_id}")
        
        # 更新嵌入向量
        result = mongodb_service.update_embeddings(embedding_service, video_id)
        
        logger.info(f"更新结果: {'成功' if result else '失败'}")
        return result
        
    except Exception as e:
        logger.error(f"测试更新嵌入向量时出错: {str(e)}")
        return False

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("请指定测试类型: script_matching 或 update_embeddings")
        return
    
    test_type = sys.argv[1]
    
    if test_type == "script_matching":
        test_script_matching()
    elif test_type == "update_embeddings":
        test_update_embeddings()
    else:
        print(f"未知的测试类型: {test_type}")

if __name__ == "__main__":
    main() 