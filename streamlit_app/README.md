# 视频解析平台

基于Streamlit的视频解析平台前端界面，用于上传、监控和查看视频解析结果。

## 功能特点

1. **视频上传**
   - 支持批量上传视频文件
   - 可设置品牌、型号和特殊需求
   - 提供高级处理选项

2. **任务监控**
   - 实时查看任务状态和进度
   - 支持取消、重启和删除任务
   - 查看任务详情和视频处理情况

3. **结果查看**
   - 浏览解析结果，支持筛选
   - 查看视频详细分析，包括片段时间线
   - 查看主题分析和关键事件

## 目录结构

```
streamlit_app/
  ├── app.py                 # 主应用入口
  ├── config.py              # 配置文件
  ├── pages/
  │   ├── 01_upload.py       # 上传页面
  │   ├── 02_tasks.py        # 任务监控页面
  │   └── 03_results.py      # 结果页面
  ├── components/
  │   ├── status_badge.py    # 状态徽章组件
  │   ├── task_card.py       # 任务卡片组件
  │   └── video_card.py      # 视频卡片组件
  ├── utils/
  │   └── video_processor.py # 视频处理工具
  └── services/
      └── mongo_service.py   # MongoDB服务
```

## 安装和使用

### 前提条件

- Python 3.7+
- MongoDB
- Streamlit

### 安装依赖

```bash
pip install streamlit pymongo pandas
```

### 运行应用

1. 确保MongoDB服务已启动

2. 运行Streamlit应用：

```bash
./run_streamlit_app.sh
```

或直接使用Streamlit命令：

```bash
streamlit run streamlit_app/app.py
```

3. 在浏览器中访问应用（默认地址: http://localhost:8501）

## 使用流程

1. **上传视频**
   - 进入"上传视频"页面
   - 选择要上传的视频文件（支持mp4, avi, mov, mkv）
   - 填写品牌、型号和特殊需求
   - 点击"开始解析"按钮

2. **监控任务**
   - 进入"任务监控"页面
   - 查看任务状态和进度
   - 可以取消或重启任务

3. **查看结果**
   - 进入"解析结果"页面
   - 使用筛选器查找视频
   - 点击视频查看详细分析结果

## 配置说明

应用配置可在`config.py`文件中修改，主要包括：

- MongoDB连接信息
- 上传文件配置
- 应用名称和刷新间隔
- 默认品牌列表和处理选项 