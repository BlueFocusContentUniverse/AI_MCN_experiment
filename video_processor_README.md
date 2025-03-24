# 视频处理工具

这个工具用于处理视频文件，包括提取音频、使用Whisper进行语音转录，以及根据转录结果切片视频。

## 功能

- 批量处理指定目录下的所有视频文件
- 使用OpenAI的Whisper API进行语音转录
- 根据转录的时间段切片视频
- 将转录文本和视频片段路径保存到JSON文件中

## 依赖

- Python 3.6+
- FFmpeg
- OpenAI API密钥
- 以下Python库:
  - httpx
  - openai

## 环境变量

在运行脚本前，请确保设置以下环境变量：

```bash
export OPENAI_API_KEY="你的OpenAI API密钥"
export OPENAI_BASE_URL="OpenAI API的基础URL"
# 如果需要代理，可以设置
export HTTP_PROXY="http://your-proxy:port"
```

## 使用方法

```bash
python video_processor.py [--input-dir INPUT_DIR] [--output-dir OUTPUT_DIR] [--json-file JSON_FILE]
```

### 参数

- `--input-dir`: 输入视频目录，默认为 `/home/jinpeng/multi-agent/李想公关`
- `--output-dir`: 输出切片目录，默认为 `/home/jinpeng/multi-agent/segments`
- `--json-file`: 输出JSON文件路径，默认为 `/home/jinpeng/multi-agent/segments/segments_info.json`

### 示例

使用默认参数运行：

```bash
python video_processor.py
```

指定自定义目录：

```bash
python video_processor.py --input-dir /path/to/videos --output-dir /path/to/segments --json-file /path/to/output.json
```

### 后台运行

由于处理视频可能需要较长时间，建议使用nohup在后台运行：

```bash
nohup python video_processor.py > video_processing.log 2>&1 &
```

这样即使关闭终端，脚本也会继续运行。可以通过查看日志文件来监控进度：

```bash
tail -f video_processing.log
```

## 输出

脚本将在指定的输出目录中创建视频片段，并在JSON文件中保存以下信息：

```json
[
  {
    "id": 0,
    "text": "转录的文本内容",
    "start_time": 0.0,
    "end_time": 10.5,
    "video_path": "/absolute/path/to/original/video.mp4",
    "segment_path": "/absolute/path/to/segment/video_segment_0.mp4"
  },
  ...
]
```

## 注意事项

- 脚本会跳过已经处理过的视频文件，所以可以安全地中断和重新运行
- 每处理完一个片段就会更新JSON文件，以防中途出错丢失数据
- 如果视频没有可转录的内容，将会被跳过
- 处理大型视频文件可能需要较长时间，特别是在转录阶段
- 确保有足够的磁盘空间来存储切片后的视频文件
- 如果遇到"直接转录视频失败"的消息，不用担心，脚本会自动尝试提取音频后再转录

## 故障排除

如果遇到问题，请检查：

1. 环境变量是否正确设置
2. FFmpeg是否已安装并可在PATH中找到
3. 网络连接是否正常（特别是在使用OpenAI API时）
4. 磁盘空间是否充足
5. 查看日志文件中的详细错误信息 