from agents.script_parsing_agent import ScriptParsingAgent, ScriptParsingTool

# 测试脚本
test_script = """
第一场景：汽车外观展示（10秒）
特斯拉Model 3停放在现代化的城市街道上，阳光照射下车身线条流畅优美。

第二场景：车内视角（8秒）
展示车内宽敞的空间和简约的中控台设计，突出大屏幕和无按键界面。

第三场景：驾驶场景（12秒）
车辆在城市道路上行驶，展示驾驶的流畅性和操控感。
"""

# 测试错误情况：参数作为字典传递
test_dict_params = {
    "script": {"description": test_script, "type": "str"},
    "target_duration": {"description": 30.0, "type": "float"}
}

# 测试正常情况：参数作为原始类型传递
test_normal_params = {
    "script": test_script,
    "target_duration": 30.0
}

def test_script_parsing_tool():
    """测试ScriptParsingTool"""
    
    # 创建工具实例
    tool = ScriptParsingTool()
    
    print("=== 测试正常参数 ===")
    try:
        result = tool._run(**test_normal_params)
        print(f"成功处理正常参数，目标时长: {result['target_duration']}")
    except Exception as e:
        print(f"处理正常参数时出错: {str(e)}")
    
    print("\n=== 测试字典参数 ===")
    try:
        result = tool._run(**test_dict_params)
        print(f"成功处理字典参数，目标时长: {result['target_duration']}")
    except Exception as e:
        print(f"处理字典参数时出错: {str(e)}")
    
    return "测试完成"

def main():
    print("开始测试ScriptParsingAgent...\n")
    result = test_script_parsing_tool()
    print(f"\n{result}")

if __name__ == "__main__":
    main() 