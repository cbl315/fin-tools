"""声音告警模块 - Mac版本"""
import os
import threading
import time

def play_alert_sound():
    """播放警报音 - Mac版本"""
    def _play():
        for _ in range(5):
            os.system('afplay /System/Library/Sounds/Glass.aiff')  # macOS 系统提示音
            time.sleep(0.2)
    sound_thread = threading.Thread(target=_play)
    sound_thread.daemon = True
    sound_thread.start()
