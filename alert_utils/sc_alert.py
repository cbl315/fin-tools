"""Server酱告警模块"""
import requests
import re
from typing import Dict, Any

def send_serverchan_alert(message: str, config: Dict[str, Any], options=None) -> bool:
    """发送Server酱通知
    
    Args:
        message: 要发送的消息内容
        config: 配置文件对象
        
    Returns:
        bool: 是否发送成功
    """
    if not config['serverchan']['enabled']:
        return False
        
    try:
        if options is None:
            options = {}
        sendkey = config['serverchan']['sckey']
        title = config['serverchan']['title']
        # 判断 sendkey 是否以 'sctp' 开头，并提取数字构造 URL
        if sendkey.startswith('sctp'):
            match = re.match(r'sctp(\d+)t', sendkey)
            if match:
                num = match.group(1)
                url = f'https://9749.push.ft07.com/send/{sendkey}.send'
            else:
                raise ValueError('Invalid sendkey format for sctp')
        else:
            url = f'https://sctapi.ftqq.com/{sendkey}.send'
        params = {
            'title': title,
            'desp': message,
            **options
        }
        headers = {
            'Content-Type': 'application/json;charset=utf-8'
        }
        response = requests.post(url, json=params, headers=headers)
        result = response.json()
        return result

    except Exception as e:
        print(f'【BR】Server酱通知发送失败: {e}')
        return False
