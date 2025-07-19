"""语音告警模块
提供基于macOS系统say命令的语音告警功能，支持中文语音选择和多线程播放控制。

使用示例:
    >>> from alert_utils.voice_alert import VoiceAlert
    >>> alert = VoiceAlert()
    >>> alert.play_voice_alert("测试警告消息")

主要功能:
- 自动检测可用的中文语音
- 防止语音消息重叠播放
- 支持消息文本清理
- 自动重试机制
"""

import os
import subprocess
import time
import threading
from typing import Optional

class VoiceAlert:
    """语音告警类
    
    封装语音告警功能，维护播放状态防止消息重叠。
    
    Attributes:
        voice_thread_active (bool): 标识当前是否有语音正在播放
    """
    def __init__(self):
        self.voice_thread_active = False

    @staticmethod
    def get_available_voice() -> Optional[str]:
        """获取可用的中文语音"""
        try:
            # 检查是否为macOS系统
            if os.name == 'posix' and os.uname().sysname == 'Darwin':
                # 尝试获取可用的中文语音
                result = subprocess.run(['say', '-v', '?'], capture_output=True, text=True, timeout=5)
                voices = result.stdout.lower()
                
                # 按优先级检查可用的中文语音
                chinese_voices = ['mei-jia', 'sin-ji', 'ting-ting', 'ya-ling']
                for voice in chinese_voices:
                    if voice in voices:
                        return voice
                
                # 如果没有中文语音，返回默认语音
                return None
            return None
        except Exception:
            return None

    def play_voice_alert(self, message: str) -> None:
        """播放语音警报
        
        参数:
            message (str): 要播放的语音消息文本
            
        功能:
            - 自动清理消息中的特殊字符
            - 检测并优先使用中文语音
            - 防止语音消息重叠播放
            - 自动重试3次播放
            - 提供详细的播放状态日志
        """
        # 如果有语音正在播放，跳过新的语音播放
        if self.voice_thread_active:
            print(f'🔊 语音播放中，跳过新语音: {message}')
            return
        
        def _play_voice():
            try:
                self.voice_thread_active = True
                # 清理消息文本
                clean_message = message.replace('"', '').replace("'", "")
                print(f'🔊 准备播放语音: {clean_message}')
                
                # 检查系统和可用语音
                if os.name == 'posix' and os.uname().sysname == 'Darwin':
                    # macOS系统
                    available_voice = self.get_available_voice()
                    
                    # 重复播放逻辑
                    for i in range(3):  # 播放3次语音
                        try:
                            if available_voice:
                                subprocess.run(['say', '-v', available_voice, clean_message], timeout=15)
                            else:
                                subprocess.run(['say', clean_message], timeout=15)
                            print(f'语音播放第{i+1}次执行成功')
                            time.sleep(0.3)  # 语音间隔
                        except subprocess.TimeoutExpired:
                            print(f'语音播放第{i+1}次超时')
                        except Exception as inner_e:
                            print(f'语音播放第{i+1}次内部错误: {inner_e}')
            except Exception as e:
                print(f'语音播放错误: {e}')
            finally:
                self.voice_thread_active = False
        
        voice_thread = threading.Thread(target=_play_voice)
        voice_thread.daemon = True
        voice_thread.start()
