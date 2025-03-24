import os
import sys
import json
import argparse
from dotenv import load_dotenv
from services.quote_matching_video_service import QuoteMatchingVideoService

# 加载环境变量
load_dotenv()

def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description="基于原话匹配的视频剪辑工具")
    
    parser.add_argument("script_file", default="./script.txt", help="脚本文件路径")
    parser.add_argument("--output", "-o", default="./output", help="输出目录")
    parser.add_argument("--special-requirements", "-r", default="这是理想汽车创始人李想的公关视频，需要突出李想的创业牛人形象，以及理想汽车的科技感和未来感，使用**理想L9公关**文件夹下的表情包（作为辅助内容），和**李想公关**文件夹下的视频（作为主要内容）", help="特殊需求")
    
    args = parser.parse_args()
    
    # 读取脚本文件
    try:
        with open(args.script_file, 'r', encoding='utf-8') as f:
            script = f.read()
    except Exception as e:
        print(f"读取脚本文件时出错: {str(e)}")
        return 1
    
    # 创建服务实例
    service = QuoteMatchingVideoService(output_dir=args.output)
    
    # 执行视频生产
    try:
        result = service.produce_video(script, args.special_requirements)
        
        # 保存结果
        result_file = os.path.join(args.output, "result.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"视频生产完成，最终视频: {result.get('final_video', '未生成')}")
        print(f"详细结果已保存到: {result_file}")
        
        return 0
    except Exception as e:
        print(f"视频生产过程中出错: {str(e)}")
        return 1
# 测试用例
def test_main():
    """测试用例"""
    # 测试脚本文件
    script_file = "./script.txt"
    # 测试特殊需求
    special_requirements = "这是理想汽车创始人李想的公关视频，需要突出李想的创业牛人形象，以及理想汽车的科技感和未来感，使用**理想L9公关**文件夹下的表情包（作为辅助内容），和**李想公关**文件夹下的视频（作为主要内容）视频风格是营销号， 适量使用表情包,必须使用多个视频源素材！！！"
    # 测试输出目录
    output_dir = "./test_output"
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建服务实例
    service = QuoteMatchingVideoService(output_dir=output_dir)
    
    # 读取脚本文件
    try:
        with open(script_file, 'r', encoding='utf-8') as f:
            script = f.read()
    except Exception as e:
        print(f"读取脚本文件时出错: {str(e)}")
        return 1
    
    # 执行视频生产
    try:
        result = service.produce_video(script, special_requirements)
        print(f"测试成功，视频生产完成，最终视频: {result.get('final_video', '未生成')}")
        return 0
    except Exception as e:
        print(f"测试失败，视频生产过程中出错: {str(e)}")
        return 1

if __name__ == "__main__":
    # 主程序
    #sys.exit(main())
    
    
    
    # 如果需要运行测试用例，取消下面这行的注释
    sys.exit(test_main())