import os

# MongoDB配置
MONGODB_URI = os.environ.get('MONGODB_URI', "mongodb://username:password@localhost:27018/?directConnection=true")
MONGODB_DB = os.environ.get('MONGODB_DB', 'test_mcn')

# 任务相关的集合名称
TASK_COLLECTION = 'video_analysis_tasks'
VIDEOS_COLLECTION = 'videos'
VIDEO_SEGMENTS_COLLECTION = 'video_segments'

# 上传文件配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploaded_videos')
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB

# 应用配置
APP_NAME = "视频解析平台"
REFRESH_INTERVAL = 60 # 任务状态刷新间隔（秒）

# 品牌列表（从数据库动态获取，这里仅设置为空列表作为初始值）
DEFAULT_BRANDS = []

# 视频处理选项
PROCESSING_OPTIONS = {
    "high_quality": {
        "label": "高质量分析",
        "description": "使用更高质量的模型进行分析，但处理时间更长",
        "default": False
    },
    "extract_audio": {
        "label": "提取音频信息",
        "description": "分析视频中的音频内容和语音",
        "default": True
    },
    "generate_thumbnails": {
        "label": "生成缩略图",
        "description": "为视频的关键帧生成缩略图",
        "default": True
    }
} 