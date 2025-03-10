from pydub import AudioSegment
from pydub.silence import split_on_silence
from dataclasses import dataclass
from pathlib import Path
import sys

@dataclass
class AudioCutConfig:
    """音频剪切配置"""
    threshold: float = -50          # 静音阈值 (dBFS)
    min_silence_len: int = 500      # 最小静音长度 (毫秒)
    keep_silence: int = 0           # 保留的静音长度 (毫秒)

class TTSAudioCutter:
    def __init__(self, config: AudioCutConfig):
        """
        初始化音频剪切器

        参数：
        - config: AudioCutConfig 对象，包含剪切配置
        """
        self.config = config

    def cut_audio(self, input_path: str, output_path: str):
        """
        剪切音频文件

        参数：
        - input_path: 输入音频文件路径
        - output_path: 输出音频文件路径
        """
        # 读取输入音频
        audio = AudioSegment.from_file(input_path)
        original_duration = len(audio) / 1000.0  # 以秒为单位

        # 记录原始音频参数
        frame_rate = audio.frame_rate
        sample_width = audio.sample_width
        channels = audio.channels

        # print(f"原始音频参数：")
        # print(f"- 采样率: {frame_rate} Hz")
        # print(f"- 采样宽度: {sample_width * 8} 位")
        # print(f"- 声道数: {channels}")
        # print(f"- 时长: {original_duration:.2f} 秒")

        # 使用 pydub 的 split_on_silence 方法进行静音切分
        chunks = split_on_silence(
            audio,
            min_silence_len=self.config.min_silence_len,
            silence_thresh=self.config.threshold,
            keep_silence=self.config.keep_silence
        )

        # 拼接非静音片段
        output_audio = AudioSegment.empty()
        for i, chunk in enumerate(chunks):
            output_audio += chunk
            # print(f"添加第 {i+1} 个音频段，长度 {len(chunk)/1000.0:.2f} 秒")

        # 确保输出音频参数与输入一致
        output_audio = output_audio.set_frame_rate(frame_rate)
        output_audio = output_audio.set_sample_width(sample_width)
        output_audio = output_audio.set_channels(channels)

        # 保存输出音频
        output_audio.export(output_path, format="wav")

        processed_duration = len(output_audio) / 1000.0  # 以秒为单位

        print(f"\n 音频处理完成！")
        # print(f"- 原始时长: {original_duration:.2f} 秒")
        # print(f"- 处理后时长: {processed_duration:.2f} 秒")
        # print(f"- 减少时长: {original_duration - processed_duration:.2f} 秒")
        # print(f"- 压缩比例: {(1 - processed_duration / original_duration) * 100:.1f}%")

        return original_duration, processed_duration

if __name__ == "__main__":
    # 输入和输出文件路径
    input_file = "/home/jinpeng/MoneyPrinterPlus/MoneyPrinterPlus/work/17328634339691_with_effect.wav"
    input_path = Path(input_file)
    output_path = input_path.parent / f"{input_path.stem}_cut{input_path.suffix}"

    # 配置参数，可根据需要调整
    config = AudioCutConfig(
        threshold=-50,          # 静音阈值 (dBFS)
        min_silence_len=500,    # 最小静音长度 (毫秒)
        keep_silence=0          # 保留的静音长度 (毫秒)
    )

    # 初始化 TTSAudioCutter 对象
    cutter = TTSAudioCutter(config)

    try:
        # 执行音频剪切
        print(f"正在处理音频: {input_file}")
        print(f"输出文件: {output_path}")
        cutter.cut_audio(
            str(input_path),
            str(output_path)
        )
    except Exception as e:
        print(f"处理失败: {e}")
        sys.exit(1)