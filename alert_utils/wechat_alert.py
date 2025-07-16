"""企业微信告警模块"""
import os
import time
import requests
from typing import Dict, Any

# 企业微信token缓存
wechat_token_cache = {
    'token': '',
    'expires_at': 0  # 过期时间戳
}

def get_wechat_work_token(config: Dict[str, Any]) -> str:
    """获取企业微信access_token，带缓存和自动刷新"""
    global wechat_token_cache
    
    try:
        # 如果token未过期且剩余时间大于5分钟，直接返回缓存的token
        current_time = time.time()
        if wechat_token_cache['token'] and wechat_token_cache['expires_at'] > current_time + 300:
            return wechat_token_cache['token']
            
        secret = os.getenv('WECHAT_WORK_SECRET', config['wechat_work']['secret'])
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={config['wechat_work']['corpid']}&corpsecret={secret}"
        
        # 配置代理
        proxies = {}
        if 'proxy' in config and config['proxy']['enabled']:
            proxies = {
                'http': config['proxy']['url'],
                'https': config['proxy']['url']
            }
        
        response = requests.get(url, timeout=10, proxies=proxies).json()
        
        token = response.get('access_token', '')
        if token:
            # 企业微信token有效期为7200秒，这里设置为7100秒(约1小时58分钟)避免边界问题
            wechat_token_cache = {
                'token': token,
                'expires_at': current_time + 7100
            }
        return token
    except Exception as e:
        print(f'【BR】获取企业微信token失败: {e}')
        return ''

def send_wechat_work_alert(message: str, config: Dict[str, Any]) -> bool:
    """发送企业微信通知"""
    if not config['wechat_work']['enabled']:
        return False
        
    try:
        token = get_wechat_work_token(config)
        if not token:
            return False
            
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        data = {
            "touser": config['wechat_work']['touser'],
            "msgtype": "text",
            "agentid": config['wechat_work']['agentid'],
            "text": {
                "content": f"【BR流动性告警】\n{message}"
            },
            "safe": 0
        }
        
        # 配置代理
        proxies = {}
        if 'proxy' in config and config['proxy']['enabled']:
            proxies = {
                'http': config['proxy']['url'],
                'https': config['proxy']['url']
            }
        
        response = requests.post(url, json=data, timeout=10, proxies=proxies)
        print(f'【BR】企业微信通知发送状态: {response.status_code}, resp: {response.content} 内容: {message}, payload: {data}')
        return response.status_code == 200
    except Exception as e:
        print(f'【BR】企业微信通知发送失败: {e}')
        return False
