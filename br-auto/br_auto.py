#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BR流动性自动保护系统 - Mac版本
结合流动性监控和自动移除功能，当流动性减少超过阈值时自动移除头寸
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import websocket
import json
import time
import threading
from datetime import datetime
import os
import random
import ssl
import subprocess
import yaml
from web3_utils import Web3Manager

# 加载配置文件
with open('br-auto/config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 配置变量
BR_CONFIG = config['br_config']
WEB3_CONFIG = config['web3_config']
PROXY_CONFIG = config['proxy_config']
LARGE_SELL_ALERT_CONFIG = config['large_sell_alert_config']
WALLET_NAMES = config['wallet_names']
KK_ADDRESS = config['kk_address']

# 全局变量
liquidity_history = []  # 保留原有数组（用于现有报警逻辑）
liquidity_history_with_time = []  # 新增时间戳数组（用于2分钟窗口检测）
reconnect_count = 0
MAX_RECONNECT_ATTEMPTS = 10
reconnect_delay = 5
heartbeat_running = False
heartbeat_thread = None
current_ws = None
top_pool_data = None
web3_manager = None  # Web3Manager实例
auto_remove_in_progress = False  # 防止重复触发自动移除
last_auto_remove_time = 0  # 记录上次自动移除时间
AUTO_REMOVE_COOLDOWN = 300  # 自动移除冷却时间（秒）
voice_thread_active = False  # 防止语音重叠的标志
current_positions = []  # 当前流动性头寸信息

def play_alert_sound():
    """播放警报音 - Mac版本"""
    def _play():
        for _ in range(5):
            os.system('afplay /System/Library/Sounds/Glass.aiff')  # macOS 系统提示音
            time.sleep(0.2)
    sound_thread = threading.Thread(target=_play)
    sound_thread.daemon = True
    sound_thread.start()

def get_available_voice():
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
        else:
            # 非macOS系统，返回None
            return None
    except Exception:
        return None

def play_voice_alert(message):
    """播放语音警报"""
    global voice_thread_active
    
    # 如果有语音正在播放，跳过新的语音播放
    if voice_thread_active:
        print(f'【BR】🔊 语音播放中，跳过新语音: {message}')
        return
    
    def _play_voice():
        global voice_thread_active
        try:
            voice_thread_active = True
            # 清理消息文本
            clean_message = message.replace('"', '').replace("'", "")
            print(f'【BR】🔊 准备播放语音: {clean_message}')
            
            # 检查系统和可用语音
            if os.name == 'posix' and os.uname().sysname == 'Darwin':
                # macOS系统
                available_voice = get_available_voice()
                
                # 重复播放逻辑
                for i in range(3):  # 播放3次语音
                    try:
                        if available_voice:
                            # 使用可用的中文语音
                            subprocess.run(['say', '-v', available_voice, clean_message], timeout=15)
                        else:
                            # 使用默认语音
                            subprocess.run(['say', clean_message], timeout=15)
                        print(f'【BR】语音播放第{i+1}次执行成功')
                        time.sleep(0.3)  # 语音间隔
                    except subprocess.TimeoutExpired:
                        print(f'【BR】语音播放第{i+1}次超时')
                    except Exception as inner_e:
                        print(f'【BR】语音播放第{i+1}次内部错误: {inner_e}')
            elif os.name == 'nt':
                # Windows系统
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    # 设置中文语音（如果可用）
                    voices = engine.getProperty('voices')
                    for voice in voices:
                        if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
                            engine.setProperty('voice', voice.id)
                            break
                    
                    for i in range(3):
                        engine.say(clean_message)
                        engine.runAndWait()
                        print(f'【BR】语音播放第{i+1}次执行成功')
                        time.sleep(0.3)
                except ImportError:
                    print('【BR】Windows系统需要安装pyttsx3库: pip install pyttsx3')
                    # 使用系统提示音作为替代
                    for i in range(3):
                        os.system('echo \a')  # 系统提示音
                        time.sleep(0.5)
                except Exception as e:
                    print(f'【BR】Windows语音播放错误: {e}')
            else:
                # 其他系统，只打印消息
                print(f'【BR】🔊 语音消息: {clean_message}')
                
        except Exception as e:
            print(f'【BR】语音播放错误: {e}')
        finally:
            voice_thread_active = False
    
    voice_thread = threading.Thread(target=_play_voice)
    voice_thread.daemon = True
    voice_thread.start()

def format_amount(amount):
    """将数量格式化为合适的单位（M、K等）"""
    if amount >= 1000000:
        return f"{amount/1000000:.2f}M"
    elif amount >= 1000:
        return f"{amount/1000:.2f}K"
    else:
        return f"{amount:.2f}"


def auto_remove_positions():
    """自动移除所有USDT-BR头寸"""
    global auto_remove_in_progress, last_auto_remove_time, current_positions
    
    # 检查是否在冷却期内
    current_time = time.time()
    if current_time - last_auto_remove_time < AUTO_REMOVE_COOLDOWN:
        remaining_time = AUTO_REMOVE_COOLDOWN - (current_time - last_auto_remove_time)
        print(f"【BR】⏰ 自动移除冷却中，剩余 {remaining_time:.0f} 秒")
        return
    
    if auto_remove_in_progress:
        print("【BR】⚠️ 自动移除正在进行中，跳过")
        return
    
    auto_remove_in_progress = True
    last_auto_remove_time = current_time
    
    try:
        print("【BR】🚨 触发自动移除保护机制！")
        play_voice_alert("警告！流动性大幅减少，正在自动移除头寸保护资金")
        
        if not web3_manager:
            print("【BR】❌ Web3连接不可用，无法执行自动移除")
            return
        
        # 优先使用缓存的头寸信息，避免重复查询延迟
        if current_positions:
            positions = current_positions
            print(f"【BR】⚡ 使用缓存头寸信息，跳过查询步骤")
        else:
            print("【BR】🔍 缓存为空，重新查询头寸")
            web3_manager.get_v3_positions()
            positions = web3_manager.get_current_positions()
            if not positions:
                print("【BR】❌ 未找到活跃的USDT-BR头寸")
                return
        
        print(f"【BR】🎯 找到 {len(positions)} 个USDT-BR头寸，开始自动移除")
        
        success_count = 0
        for i, position in enumerate(positions):
            print(f"【BR】处理头寸 #{position['token_id']} ({i+1}/{len(positions)})")
            if web3_manager.execute_multicall(position):
                success_count += 1
            if i < len(positions) - 1:
                time.sleep(3)
        
        print(f"【BR】🎉 自动移除完成，成功移除 {success_count}/{len(positions)} 个头寸")
        if success_count > 0:
            # 等待前一个语音播放完成，避免重叠
            time.sleep(8)  # 等待8秒确保前一个语音播放完成
            play_voice_alert(f"自动移除完成，成功保护了 {success_count} 个头寸")
        
        # 更新当前头寸信息
        web3_manager.get_v3_positions()
        current_positions = web3_manager.get_current_positions()
        
    except Exception as e:
        print(f'【BR】自动移除过程中发生错误: {e}')
    finally:
        auto_remove_in_progress = False

def on_message(ws, message):
    """WebSocket消息处理"""
    global top_pool_data, liquidity_history_with_time
    try:
        data = json.loads(message)
        
        # 检查是否是订阅确认消息
        if 'event' in data:
            return
        
        # 处理dex-market-v3-topPool数据
        if 'arg' in data and 'data' in data and data['arg']['channel'] == 'dex-market-v3-topPool':
            token_address = data['arg']['tokenAddress']
            if 'data' in data and len(data['data']) > 0 and 'data' in data['data'][0]:
                pool_list = data['data'][0]['data']
                
                if token_address.lower() == BR_CONFIG['address'].lower():
                    total_liquidity = 0
                    token_amounts = {}
                    pool_details = []  # 保存池子详细信息
                    
                    for i, pool in enumerate(pool_list):
                        pool_liquidity = float(pool['liquidity'])
                        total_liquidity += pool_liquidity
                        
                        # 保存池子信息
                        pool_tokens = []
                        for token_info in pool['poolTokenInfoList']:
                            if token_info['tokenSymbol'] != 'BR':  # 只保存非BR的token
                                pool_tokens.append(token_info['tokenSymbol'])
                        
                        pool_info = {
                            'index': i + 1,
                            'liquidity': pool_liquidity,
                            'pool_address': pool.get('poolAddress', 'N/A'),
                            'tokens': pool_tokens
                        }
                        pool_details.append(pool_info)
                        
                        for token_info in pool['poolTokenInfoList']:
                            token_symbol = token_info['tokenSymbol']
                            token_amount = float(token_info['amount'])
                            
                            if token_symbol in token_amounts:
                                token_amounts[token_symbol] += token_amount
                            else:
                                token_amounts[token_symbol] = token_amount
                    
                    top_pool_data = {
                        'total_liquidity': total_liquidity,
                        'token_amounts': token_amounts,
                        'pool_details': pool_details
                    }
        
        # 处理市场数据（流动性监控的核心逻辑）
        if 'arg' in data and 'data' in data and data['arg']['channel'] == 'dex-market-v3' and data['arg']['chainId'] == '56':
            if 'data' in data and len(data['data']) > 0:
                market_data = data['data'][0]
                token_address = market_data['tokenContractAddress']
                
                if token_address.lower() != BR_CONFIG['address'].lower():
                    return
                
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 使用topPool的流动性数据
                if top_pool_data is not None:
                    liquidity = top_pool_data['total_liquidity']
                    token_amounts = top_pool_data['token_amounts']
                else:
                    liquidity = float(market_data['liquidity'])
                    token_amounts = {}
                
                liquidity_m = liquidity / 1000000
                price = float(market_data['price'])
                volume_5m = float(market_data['volume5M'])
                volume_5m_m = volume_5m / 1000000
                
                # 添加当前流动性到历史记录
                liquidity_history.append(liquidity_m)
                if len(liquidity_history) > 10:
                    liquidity_history.pop(0)
                
                # 同时维护带时间戳的历史记录（用于2分钟窗口检测）
                current_timestamp = time.time()
                liquidity_history_with_time.append((current_timestamp, liquidity_m))
                
                # 清理2分钟之外的数据
                liquidity_history_with_time = [
                    (ts, liq) for ts, liq in liquidity_history_with_time 
                    if current_timestamp - ts <= 120  # 保留2分钟内的数据
                ]
                
                # 检查流动性是否突然减少
                if len(liquidity_history) > 1:
                    current_liquidity = liquidity_history[-1]
                    threshold = BR_CONFIG['liquidity_threshold']
                    auto_threshold = BR_CONFIG['auto_remove_threshold']
                    
                    # 计算最大流动性下降
                    max_liquidity_drop = 0
                    max_drop_from = 0
                    
                    for historical_liquidity in liquidity_history[:-1]:
                        liquidity_drop = historical_liquidity - current_liquidity
                        if liquidity_drop > max_liquidity_drop:
                            max_liquidity_drop = liquidity_drop
                            max_drop_from = historical_liquidity
                    
                    # 2分钟时间窗口检测（最高优先级）
                    time_window_triggered = False
                    if BR_CONFIG['auto_remove_enabled'] and len(liquidity_history_with_time) >= 2 and current_positions:
                        max_liquidity_in_2min = max(liq for _, liq in liquidity_history_with_time)
                        time_window_drop = max_liquidity_in_2min - current_liquidity
                        
                        if time_window_drop > auto_threshold:
                            print(f'\033[93m【BR】🚨 2分钟内流动性减少超过自动移除阈值 {auto_threshold}M，触发自动保护！从 {max_liquidity_in_2min:.2f}M 降至 {current_liquidity:.2f}M\033[0m')
                            # 在新线程中执行自动移除，避免阻塞WebSocket
                            auto_remove_thread = threading.Thread(target=auto_remove_positions)
                            auto_remove_thread.daemon = True
                            auto_remove_thread.start()
                            time_window_triggered = True
                    
                    # 传统检测逻辑（作为备用）
                    if not time_window_triggered and BR_CONFIG['auto_remove_enabled'] and max_liquidity_drop > auto_threshold and current_positions:
                        print(f'\033[93m【BR】🚨 流动性减少超过自动移除阈值 {auto_threshold}M，触发自动保护！从 {max_drop_from:.2f}M 降至 {current_liquidity:.2f}M\033[0m')
                        # 在新线程中执行自动移除，避免阻塞WebSocket
                        auto_remove_thread = threading.Thread(target=auto_remove_positions)
                        auto_remove_thread.daemon = True
                        auto_remove_thread.start()
                    
                    # 独立的警报检查（只有在未触发自动移除时才执行）
                    elif not time_window_triggered and max_liquidity_drop > threshold:
                        warning_msg = f'\033[91m【BR】警告！流动性突然减少 {max_liquidity_drop:.2f}M！从 {max_drop_from:.2f}M 降至 {current_liquidity:.2f}M\033[0m'
                        print(warning_msg)
                        play_alert_sound()
                
                # 显示当前状态
                if token_amounts:
                    token_amounts_str = ", ".join([f"{symbol}: {format_amount(amount)}" for symbol, amount in token_amounts.items()])
                    
                    # 生成头寸信息字符串
                    position_info_str = ""
                    if current_positions:
                        position_ids = [f"\033[93m#{pos['token_id']}\033[0m" for pos in current_positions]
                        position_info_str = f"  LP池子：{', '.join(position_ids)}"
                    
                    print(f'【BR】Time: {current_time}  Liquidity: {liquidity_m:.2f}M   Price: {price:.5f}  Volume (5min): {volume_5m_m:.2f}M  代币数量: {token_amounts_str}{position_info_str}')
                else:
                    # 生成头寸信息字符串
                    position_info_str = ""
                    if current_positions:
                        position_ids = [f"\033[93m#{pos['token_id']}\033[0m" for pos in current_positions]
                        position_info_str = f"  LP池子：{', '.join(position_ids)}"
                    
                    print(f'【BR】Time: {current_time}  Liquidity: {liquidity_m:.2f}M   Price: {price:.5f}  Volume (5min): {volume_5m_m:.2f}M{position_info_str}')
        
        # 处理池子历史数据
        if 'arg' in data and 'data' in data and data['arg']['channel'] == 'dex-market-pool-history':
            pool_data = data['data']
            if pool_data['chainId'] == '56':
                token_contract_address = pool_data.get('tokenContractAddress', '')
                
                if token_contract_address and token_contract_address.lower() == BR_CONFIG['address'].lower():
                    changed_tokens = pool_data.get('changedTokenInfo', [])
                    if changed_tokens:
                        token_info_str = ", ".join([f"{token['tokenSymbol']}: {float(token['amount']):.6f}" for token in changed_tokens])
                        
                        value = float(pool_data['value'])
                        type_str = pool_data['type']
                        wallet_address = pool_data.get('userWalletAddress', '')
                        wallet_name = WALLET_NAMES.get(wallet_address, '')
                        wallet_info = f", 钱包: {wallet_name}" if wallet_name else ""
                        
                        # 检查是否是KK地址的操作
                        if wallet_address.lower() == KK_ADDRESS.lower():
                            if type_str == '1':
                                print(f'\033[93m【BR】🚨 KK入场警报！新增流动性 - 价值: ${value:.2f}, 代币变化: {token_info_str}\033[0m')
                                play_voice_alert("请注意，KK入场了，KK入场了")
                            elif type_str == '2':
                                print(f'\033[95m【BR】🚨 KK跑路警报！减少流动性 - 价值: ${value:.2f}, 代币变化: {token_info_str}\033[0m')
                                play_voice_alert("请注意，KK跑路了，KK跑路了")
                        else:
                            if type_str == '1':
                                print(f'\033[92m【BR】新增流动性 - 价值: ${value:.2f}, 代币变化: {token_info_str}{wallet_info}\033[0m')
                            elif type_str == '2':
                                print(f'\033[91m【BR】减少流动性 - 价值: ${value:.2f}, 代币变化: {token_info_str}{wallet_info}\033[0m')

        # 处理交易历史数据
        if 'arg' in data and 'data' in data:
            channel = data['arg'].get('channel', '')
            if channel == 'dex-market-trade-history-pub' and data['arg'].get('chainIndex') == '56':
                token_address = data['arg'].get('tokenContractAddress')
                if token_address and token_address.lower() == BR_CONFIG['address'].lower():
                    
                    if isinstance(data['data'], list):
                        for trade_info in data['data']:
                            is_buy = trade_info.get('isBuy', '')
                            wallet = trade_info.get('userAddress', '')
                            timestamp = trade_info.get('timestamp', '')
                            volume = trade_info.get('volume', 0)
                            
                            br_amount = 0
                            usdt_amount = 0
                            changed_tokens = trade_info.get('changedTokenInfo', [])
                            for token_info in changed_tokens:
                                if token_info.get('tokenSymbol') == 'BR':
                                    br_amount = float(token_info.get('amount', 0))
                                elif token_info.get('tokenSymbol') == 'USDT':
                                    usdt_amount = float(token_info.get('amount', 0))
                            
                            if wallet and br_amount > 0 and is_buy == "0":
                                if timestamp:
                                    try:
                                        trade_time = datetime.fromtimestamp(int(timestamp) / 1000).strftime('%Y-%m-%d %H:%M:%S')
                                    except:
                                        trade_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                else:
                                    trade_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                
                                # 格式化钱包地址 - 显示完整地址以避免信息丢失
                                display_address = wallet
                                
                                if float(volume) >= LARGE_SELL_ALERT_CONFIG['threshold']:
                                    print(f'\033[91m【卖出】{trade_time} - {display_address} 卖出 {br_amount:.2f} BR 获得 {usdt_amount:.2f} USDT (交易量: ${float(volume):.2f})\033[0m')
                                    
                                    if LARGE_SELL_ALERT_CONFIG['enabled'] and float(volume) >= LARGE_SELL_ALERT_CONFIG['threshold']:
                                        if wallet.lower() == KK_ADDRESS.lower():
                                            play_voice_alert("警告！KK大额卖出，KK大额卖出")
                                            time.sleep(4)
                                            play_alert_sound()
                                        else:
                                            play_alert_sound()

        # 处理实时交易数据
        if 'arg' in data and 'data' in data and data['arg']['channel'] == 'dex-market-tradeRealTime' and data['arg']['chainId'] == '56':
            trade_data = data['data'][0]
            token_address = data['arg'].get('tokenAddress')
            
            if token_address and token_address.lower() == BR_CONFIG['address'].lower():
                sell_volume = float(trade_data['tradeNumSell5M'])
                buy_volume = float(trade_data['tradeNumBuy5M'])
                volume_diff = sell_volume - buy_volume
                
                if volume_diff > BR_CONFIG['sell_threshold']:
                    print(f'\033[91m【BR】警告：5分钟内卖出量超过买入量 {volume_diff:.2f} 个代币\033[0m')

    except Exception as e:
        print(f'【BR】Error processing message: {e}')

def on_error(ws, error):
    """WebSocket错误处理"""
    print(f'【BR】WebSocket Error: {error}')
    stop_heartbeat()

def on_close(ws, close_status_code, close_msg):
    """WebSocket关闭处理"""
    global reconnect_count, reconnect_delay, current_ws
    print(f'【BR】WebSocket连接关闭: {close_status_code} - {close_msg}')
    
    stop_heartbeat()
    current_ws = None
    
    if reconnect_count < MAX_RECONNECT_ATTEMPTS:
        jitter = random.uniform(0.1, 0.5) * reconnect_delay
        next_delay = min(60, reconnect_delay + jitter)
        
        print(f'【BR】将在 {next_delay:.2f} 秒后尝试重新连接... (尝试 {reconnect_count + 1}/{MAX_RECONNECT_ATTEMPTS})')
        time.sleep(next_delay)
        
        reconnect_count += 1
        reconnect_delay = min(60, reconnect_delay * 1.5)
        connect_websocket()
    else:
        print(f'【BR】达到最大重连次数 ({MAX_RECONNECT_ATTEMPTS})，停止重连')
        reconnect_count = 0
        reconnect_delay = 5

def stop_heartbeat():
    """停止心跳线程"""
    global heartbeat_running, heartbeat_thread
    heartbeat_running = False
    if heartbeat_thread and heartbeat_thread.is_alive():
        print('【BR】正在停止心跳线程...')
        heartbeat_thread.join(timeout=2)

def start_heartbeat(ws):
    """启动心跳线程"""
    global heartbeat_running, heartbeat_thread, current_ws
    
    stop_heartbeat()
    heartbeat_running = True
    current_ws = ws
    
    def heartbeat():
        consecutive_errors = 0
        max_consecutive_errors = 3
        last_position_check = 0
        position_check_interval = 300  # 5分钟检查一次头寸
        
        while heartbeat_running:
            try:
                if not current_ws or current_ws.sock is None:
                    print('【BR】WebSocket连接已断开，停止心跳')
                    break

                # BR代币订阅消息
                messages = [
                    {
                        "op": "unsubscribe",
                        "args": [{
                            "channel": "dex-market-v3",
                            "chainId": 56,
                            "tokenAddress": BR_CONFIG['address']
                        }]
                    },
                    {
                        "op": "subscribe",
                        "args": [{
                            "channel": "dex-market-v3",
                            "chainId": 56,
                            "tokenAddress": BR_CONFIG['address']
                        }]
                    },
                    {
                        "op": "subscribe",
                        "args": [{
                            "channel": "dex-market-v3-topPool",
                            "chainId": "56",
                            "tokenAddress": BR_CONFIG['address']
                        }]
                    },
                    {
                        "op": "subscribe",
                        "args": [{
                            "channel": "dex-market-pool-history",
                            "extraParams": json.dumps({
                                "chainId": "56",
                                "tokenContractAddress": BR_CONFIG['address'],
                                "type": "0",
                                "userAddressList": [],
                                "volumeMin": "10000",
                                "volumeMax": ""
                            })
                        }]
                    },
                    {
                        "op": "subscribe",
                        "args": [{
                            "channel": "dex-market-tradeRealTime",
                            "chainId": "56",
                            "tokenAddress": BR_CONFIG['address']
                        }]
                    },
                    {
                        "op": "subscribe",
                        "args": [{
                            "channel": "dex-market-trade-history-pub",
                            "chainIndex": "56",
                            "tokenContractAddress": BR_CONFIG['address']
                        }]
                    }
                ]
                
                for msg in messages:
                    if not heartbeat_running:
                        break
                    current_ws.send(json.dumps(msg))
                    time.sleep(0.1)
                
                consecutive_errors = 0
                
                # 检查是否需要更新头寸信息
                current_time = time.time()
                if current_time - last_position_check >= position_check_interval:
                    if web3_manager:
                        try:
                            global current_positions
                            web3_manager.get_v3_positions()
                            new_positions = web3_manager.get_current_positions()
                            
                            # 检查头寸是否有变化
                            if len(new_positions) != len(current_positions):
                                old_count = len(current_positions)
                                current_positions = new_positions
                                new_count = len(current_positions)
                                
                                if new_count > old_count:
                                    print(f'【BR】🔄 检测到新头寸！头寸数量从 {old_count} 增加到 {new_count}')
                                    if current_positions:
                                        position_ids = [str(pos['token_id']) for pos in current_positions]
                                        print(f'【BR】📋 当前头寸编号: {", ".join(position_ids)}')
                                elif new_count < old_count:
                                    print(f'【BR】🔄 检测到头寸减少！头寸数量从 {old_count} 减少到 {new_count}')
                                    if current_positions:
                                        position_ids = [str(pos['token_id']) for pos in current_positions]
                                        print(f'【BR】📋 当前头寸编号: {", ".join(position_ids)}')
                            else:
                                # 即使数量相同，也检查token_id是否有变化
                                old_ids = set(pos['token_id'] for pos in current_positions)
                                new_ids = set(pos['token_id'] for pos in new_positions)
                                
                                if old_ids != new_ids:
                                    current_positions = new_positions
                                    print(f'【BR】🔄 检测到头寸变化！头寸已更新')
                                    if current_positions:
                                        position_ids = [str(pos['token_id']) for pos in current_positions]
                                        print(f'【BR】📋 当前头寸编号: {", ".join(position_ids)}')
                            
                            last_position_check = current_time
                        except Exception as e:
                            print(f'【BR】头寸检查失败: {e}')
                
                for _ in range(20):
                    if not heartbeat_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                consecutive_errors += 1
                print(f'【BR】心跳发送错误 ({consecutive_errors}/{max_consecutive_errors}): {e}')
                
                if consecutive_errors >= max_consecutive_errors:
                    print('【BR】连续心跳错误过多，停止心跳线程')
                    break
                
                time.sleep(2)
        
        print('【BR】心跳线程已停止')
    
    heartbeat_thread = threading.Thread(target=heartbeat)
    heartbeat_thread.daemon = True
    heartbeat_thread.start()

def on_open(ws):
    """WebSocket连接建立"""
    global reconnect_count, reconnect_delay
    print('【BR】WebSocket连接已建立')
    
    reconnect_count = 0
    reconnect_delay = 5
    
    start_heartbeat(ws)

def connect_websocket():
    """连接WebSocket"""
    global current_ws
    
    try:
        ws = websocket.WebSocketApp(
            "wss://wsdexpri.okx.com/ws/v5/ipublic",
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        current_ws = ws
        
        # Mac系统SSL配置
        wst = threading.Thread(target=lambda: ws.run_forever(
            sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
        ))
        wst.daemon = True
        wst.start()
        
        return ws
    except Exception as e:
        print(f'【BR】创建WebSocket连接失败: {e}')
        return None

def main():
    """主函数"""
    global web3_instance
    
    try:
        print('【BR】🚀 启动BR流动性自动保护系统 - Mac版本...')
        print(f'【BR】监控代币地址: {BR_CONFIG["address"]}')
        print(f'【BR】流动性减少阈值: {BR_CONFIG["liquidity_threshold"]}M')
        
        # 自动移除功能状态
        auto_status = "开启" if BR_CONFIG['auto_remove_enabled'] else "关闭"
        auto_color = '\033[92m' if BR_CONFIG['auto_remove_enabled'] else '\033[91m'
        print(f'【BR】🛡️ 自动移除保护: {auto_color}{auto_status}\033[0m')
        if BR_CONFIG['auto_remove_enabled']:
            print(f'【BR】🚨 自动移除阈值: {BR_CONFIG["auto_remove_threshold"]}M')
            print(f'【BR】⏰ 自动移除冷却时间: {AUTO_REMOVE_COOLDOWN}秒')
        
        # 大额卖出警报状态
        alert_status = "开启" if LARGE_SELL_ALERT_CONFIG['enabled'] else "关闭"
        alert_color = '\033[92m' if LARGE_SELL_ALERT_CONFIG['enabled'] else '\033[91m'
        print(f'【BR】🚨 大额卖出阈值: ${LARGE_SELL_ALERT_CONFIG["threshold"]:,} USDT')
        print(f'【BR】🔔 大额卖出警报状态: {alert_color}{alert_status}\033[0m')
        
        print(f'【BR】特殊监控地址: {KK_ADDRESS} (KK)')
        
        # 检查钱包地址配置
        if not WEB3_CONFIG['wallet_address']:
            print('\n【BR】⚠️ 钱包地址未配置！')
            print('【BR】📝 请在脚本中的 WEB3_CONFIG["wallet_address"] 处配置您的钱包地址')
            print('【BR】💡 配置后重启脚本即可启用头寸查询和自动移除功能')
            print('【BR】🔄 当前将只进行流动性监控，不进行头寸相关操作\n')
        
        # 初始化Web3Manager
        print('【BR】🔗 初始化Web3Manager...')
        config = {
            'web3_config': WEB3_CONFIG,
            'proxy_config': PROXY_CONFIG
        }
        web3_manager = Web3Manager(config)
        if web3_manager.connect():
            print('【BR】✅ Web3连接成功')
            # 检查当前头寸（仅在有钱包地址时）
            if WEB3_CONFIG['wallet_address']:
                web3_manager.get_v3_positions()
                current_positions = web3_manager.get_current_positions()
                print(f'【BR】📊 当前USDT-BR头寸数量: {len(current_positions)}')
                if current_positions:
                    position_ids = [str(pos['token_id']) for pos in current_positions]
                    print(f'【BR】📋 头寸编号: {", ".join(position_ids)}')
            else:
                print('【BR】⚠️ 未配置钱包地址，跳过头寸查询')
        else:
            print('【BR】❌ Web3连接失败，自动移除功能将不可用')
        
        # 启动WebSocket监控
        print('【BR】📡 启动WebSocket监控...')
        ws = connect_websocket()
        
        if ws:
            print('【BR】✅ 监控系统启动成功')
            print('【BR】🔍 开始监控流动性变化...')
            print('【BR】💡 当流动性减少超过阈值时，系统将自动移除头寸保护资金')
            print('【BR】🔄 系统将每5分钟自动检查头寸变化，如需立即刷新请重启脚本')
            
            # 保持主线程运行
            while True:
                time.sleep(1)
        else:
            print('【BR】❌ WebSocket连接失败')
            
    except KeyboardInterrupt:
        print('\n【BR】程序被用户终止')
        stop_heartbeat()
    except Exception as e:
        print(f'【BR】程序异常: {e}')
        stop_heartbeat()

if __name__ == "__main__":
    main()
