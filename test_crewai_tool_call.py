from agents.script_parsing_agent import ScriptParsingTool, ScriptParsingInput
import json

# 测试脚本
test_script = """
第一场景：汽车外观展示（10秒）
特斯拉Model 3停放在现代化的城市街道上，阳光照射下车身线条流畅优美。

第二场景：车内视角（8秒）
展示车内宽敞的空间和简约的中控台设计，突出大屏幕和无按键界面。

第三场景：驾驶场景（12秒）
车辆在城市道路上行驶，展示驾驶的流畅性和操控感。
"""

def main():
    print("模拟CrewAI工具调用测试")
    print("=" * 50)
    
    # 创建工具实例
    tool = ScriptParsingTool()
    
    # 模拟CrewAI解析的参数结构
    crewai_style_params = {
        "script": {
            "description": test_script,
            "type": "str"
        },
        "target_duration": {
            "description": 30.0,
            "type": "float"
        }
    }
    
    print("\n模拟CrewAI参数结构:")
    print(json.dumps(crewai_style_params, indent=2))
    
    # 测试直接使用这种参数结构调用工具
    print("\n测试直接调用_run方法:")
    try:
        result = tool._run(**crewai_style_params)
        print("✅ 成功处理CrewAI参数结构!")
        print(f"脚本长度: {len(result['script'])} 字符")
        print(f"目标时长: {result['target_duration']} 秒")
    except Exception as e:
        print(f"❌ 调用失败: {str(e)}")
    
    # 测试参数验证
    print("\n测试Pydantic参数验证:")
    try:
        # 创建Pydantic模型实例
        model = ScriptParsingInput(**crewai_style_params)
        print("✅ Pydantic验证通过!")
        
        # 测试属性访问
        print(f"Script值: {model.script_value[:20]}...")
        print(f"Duration值: {model.duration_value}")
    except Exception as e:
        print(f"❌ Pydantic验证失败: {str(e)}")
    
    print("\n测试完成")

if __name__ == "__main__":
    main() 