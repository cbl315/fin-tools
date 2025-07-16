"""语音告警模块"""
import os
import subprocess
import time
import threading
from typing import Optional

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

def play_voice_alert(message: str, voice_thread_active: bool) -> bool:
    """播放语音警报"""
    if voice_thread_active:
        return False
    
    def _play_voice():
        try:
            # 清理消息文本
            clean_message = message.replace('"', '').replace("'", "")
            
            # 检查系统和可用语音
            if os.name == 'posix' and os.uname().sysname == 'Darwin':
                # macOS系统
                available_voice = get_available_voice()
                
                # 重复播放逻辑
                for _ in range(3):  # 播放3次语音
                    try:
                        if available_voice:
                            subprocess.run(['say', '-v', available_voice, clean_message], timeout=15)
                        else:
                            subprocess.run(['say', clean_message], timeout=15)
                        time.sleep(0.3)  # 语音间隔
                    except subprocess.TimeoutExpired:
                        continue
        except Exception:
            pass
    
    voice_thread = threading.Thread(target=_play_voice)
    voice_thread.daemon = True
    voice_thread.start()
    return True
