# 智能视频分析系统

这是一个基于AI的视频分析系统，能够从视频中提取多模态信息，包括语音内容、视觉元素和拍摄特征，并能智能生成短视频内容。

## 功能特点

- **语音转录**：使用Whisper API将视频中的语音转换为文本
- **视觉分析**：识别视频中的场景、物体、人物和活动
- **拍摄分析**：分析视频的运镜、色调、节奏等动态特征
- **多模态融合**：整合语音和视觉信息，生成综合分析结果
- **数据持久化**：将分析结果保存到MongoDB数据库
- **智能视频生产**：基于分析结果和口播稿生成新的视频内容
- **多段素材剪辑**：为每个音频分段智能选择多个视频片段，创建节奏感强的短视频

## 系统架构

系统由以下主要组件组成：

1. **服务层**：
   - `VideoInfoExtractor`：视频信息提取服务
   - `WhisperTranscriptionService`：语音转录服务
   - `VideoProductionService`：视频生产服务
   - `VideoEditingService`：视频剪辑服务
   - `FishAudioService`：音频生成服务
   - `MongoDBService`：数据库服务

2. **Agent层**：
   - `VisionAgent`：视觉分析Agent
   - `CinematographyAgent`：电影摄影分析Agent
   - `ScriptAnalysisAgent`：脚本分析Agent
   - `MaterialSearchAgent`：素材搜索Agent
   - `EditingPlanningAgent`：剪辑规划Agent
   - `FusionAgent`：内容融合Agent
   - `TranscriptionAgent`：语音转录Agent
   - `EditingAgent`：视频编辑Agent
   - `DirectorAgent`：导演Agent
   - `ExecutorAgent`：执行Agent

3. **工具层**：
   - 视频帧提取和分析工具
   - 视频剪辑工具
   - 音频处理工具
   - 场景检测工具
   - 批量处理工具

## 安装与配置

### 环境要求

- Python 3.8+
- FFmpeg
- MongoDB

### 安装依赖 
```
pip install -r requirements.txt
```

### 环境变量配置

创建`.env`文件并配置以下环境变量：
```
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=your_openai_base_url
MONGODB_URI=your_mongodb_uri
MONGODB_DB=your_mongodb_database
FISH_AUDIO_API_KEY=your_fish_audio_api_key
```

## 使用方法

### 提取视频信息

```
python main.py extract path/to/video.mp4
```

### 生产视频

```
python main.py produce path/to/script.txt --duration 60 --style "汽车广告"
```

### 调试模式
```
python main.py
```

## 工作流程

1. **视频信息提取**：
   - 提取语音信息：使用Whisper API转录视频中的语音
   - 提取视觉信息：使用VisionAgent分析视频帧内容
   - 提取电影摄影信息：使用CinematographyAgent分析视频的动态特征
   - 整合信息：将语音、视觉和电影摄影信息整合为完整的视频分析

2. **视频生产**：
   - 生成音频：将口播稿转换为语音
   - 分析脚本：生成视频需求清单
   - 搜索素材：根据需求查找匹配的视频素材
   - 规划剪辑：为每个音频分段选择多个合适的视频素材片段
   - 执行剪辑：将多个视频片段组合并与音频同步，生成最终视频

## 高级剪辑功能

系统支持智能化的多段素材剪辑，具有以下特点：

1. **分段组合剪辑**：每个音频分段可以对应多个视频片段，系统会自动组合这些片段
2. **短视频优化**：每个视频片段长度控制在2-15秒，适合短视频平台的观看习惯
3. **音视频同步**：确保每个视频片段与对应的音频内容同步
4. **智能排序**：根据segment_id自动排序，确保最终视频的连贯性
5. **错误恢复**：当某个片段处理失败时，系统会尝试使用替代方案继续处理

## 项目结构
```
.
├── agents/                  # AI代理
│   ├── cinematography_agent.py
│   ├── director_agent.py
│   ├── editing_agent.py
│   ├── editing_planning_agent.py
│   ├── executor_agent.py
│   ├── fusion_agent.py
│   ├── material_search_agent.py
│   ├── script_analysis_agent.py
│   ├── transcription_agent.py
│   └── vision_agent.py
├── services/                # 核心服务
│   ├── fish_audio_service.py
│   ├── mongodb_service.py
│   ├── video_editing_service.py
│   ├── video_info_extractor.py
│   ├── video_production_service.py
│   └── whisper_transcription.py
├── tools/                   # 工具函数
│   ├── frame_analysis.py
│   ├── fusion.py
│   ├── scene_detection.py
│   ├── transcription.py
│   ├── video_analysis.py
│   ├── video_editing.py
│   └── vision_analysis_enhanced.py
├── output/                  # 输出目录
│   ├── audio/               # 音频输出
│   ├── frames_analysis/     # 帧分析结果
│   ├── segments/            # 视频片段
│   └── final/               # 最终视频
├── main.py                  # 主程序入口
├── requirements.txt         # 依赖列表
├── .env                     # 环境变量配置
├── .gitignore               # Git忽略文件
└── README.md                # 项目说明
```

## 扩展与定制

系统设计为模块化架构，可以轻松扩展和定制：

1. **添加新的Agent**：在`agents/`目录下创建新的Agent类
2. **扩展工具集**：在`tools/`目录下添加新的工具函数
3. **自定义分析流程**：修改`VideoInfoExtractor`类中的分析流程
4. **定制视频生产**：修改`VideoProductionService`类中的生产流程
5. **优化剪辑策略**：调整`EditingPlanningAgent`的提示词和`VideoEditingService`的处理逻辑