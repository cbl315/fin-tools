#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重构后的BR流动性自动保护系统 - 面向对象版本 v2
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
import requests
from web3_utils import Web3Manager
from alert_utils.sc_alert import send_serverchan_alert
from alert_utils.sound_alert import play_alert_sound
from alert_utils.voice_alert import VoiceAlert
from alert_utils.wechat_alert import send_wechat_work_alert, wechat_token_cache
from alert_utils.console_logger import (
    format_amount,
    log_liquidity_alert,
    log_auto_remove_alert,
    log_kk_alert,
    log_position_change,
    log_market_status
)

class BRMonitor:
    """BR流动性监控与自动保护系统主类"""
    
    # 类常量
    MAX_RECONNECT_ATTEMPTS = 10
    AUTO_REMOVE_COOLDOWN = 300  # 5分钟冷却
    
    def __init__(self, config_path):
        """初始化监控器"""
        self.load_config(config_path)
        self.init_state()
        
    def load_config(self, path):
        """加载配置文件"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # 配置变量
            self.BR_CONFIG = self.config['br_config']
            self.WEB3_CONFIG = self.config['web3_config']
            self.PROXY_CONFIG = self.config['proxy_config']
            self.LARGE_SELL_ALERT_CONFIG = self.config['large_sell_alert_config']
            self.WALLET_NAMES = self.config['wallet_names']
            self.KK_ADDRESS = self.config['kk_address']
            self.WECHAT_WORK_CONFIG = self.config['wechat_work']
        except Exception as e:
            print(f'【BR】加载配置文件错误: {e}')
            raise
        
    def init_state(self):
        """初始化状态变量"""
        self.liquidity_history = []
        self.liquidity_history_with_time = []
        self.reconnect_count = 0
        self.reconnect_delay = 5
        self.heartbeat_running = False
        self.heartbeat_thread = None
        self.current_ws = None
        self.top_pool_data = None
        self.web3_manager = None
        self.auto_remove_in_progress = False
        self.last_auto_remove_time = 0
        self.voice_thread_active = False
        self.current_positions = []
        # 语音播报类 用于告警时播报语音
        self.voice_alert = VoiceAlert()
    
    def auto_remove_positions(self):
        """自动移除所有USDT-BR头寸"""
        # 检查是否在冷却期内
        current_time = time.time()
        if current_time - self.last_auto_remove_time < self.AUTO_REMOVE_COOLDOWN:
            remaining_time = self.AUTO_REMOVE_COOLDOWN - (current_time - self.last_auto_remove_time)
            print(f"【BR】⏰ 自动移除冷却中，剩余 {remaining_time:.0f} 秒")
            return
        
        if self.auto_remove_in_progress:
            print("【BR】⚠️ 自动移除正在进行中，跳过")
            return
        
        self.auto_remove_in_progress = True
        self.last_auto_remove_time = current_time
        
        try:
            print("【BR】🚨 触发自动移除保护机制！")
            self.voice_alert.play_voice_alert("警告！流动性大幅减少，正在自动移除头寸保护资金")

            if not self.web3_manager:
                print("【BR】❌ Web3连接不可用，无法执行自动移除")
                return
            
            # 优先使用缓存的头寸信息
            if self.current_positions:
                positions = self.current_positions
                print(f"【BR】⚡ 使用缓存头寸信息，跳过查询步骤")
            else:
                print("【BR】🔍 缓存为空，重新查询头寸")
                self.web3_manager.get_v3_positions()
                positions = self.web3_manager.get_current_positions()
                if not positions:
                    print("【BR】❌ 未找到活跃的USDT-BR头寸")
                    return
            
            print(f"【BR】🎯 找到 {len(positions)} 个USDT-BR头寸，开始自动移除")
            
            success_count = 0
            for i, position in enumerate(positions):
                print(f"【BR】处理头寸 #{position['token_id']} ({i+1}/{len(positions)})")
                if self.web3_manager.execute_multicall(position):
                    success_count += 1
                if i < len(positions) - 1:
                    time.sleep(3)
            
            print(f"【BR】🎉 自动移除完成，成功移除 {success_count}/{len(positions)} 个头寸")
            if success_count > 0:
                time.sleep(8)  # 等待语音播放完成
                self.voice_alert.play_voice_alert(f"自动移除完成，成功保护了 {success_count} 个头寸")
            
            # 更新当前头寸信息
            self.web3_manager.get_v3_positions()
            self.current_positions = self.web3_manager.get_current_positions()
            
        except Exception as e:
            print(f'【BR】自动移除过程中发生错误: {e}')
        finally:
            self.auto_remove_in_progress = False

    def on_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            
            if 'arg' not in data or 'data' not in data:
                return
                
            channel = data['arg'].get('channel', '')
            chain_id = data['arg'].get('chainId', data['arg'].get('chainIndex', ''))
            
            if chain_id != '56':
                return
                
            token_address = data['arg'].get('tokenAddress', 
                                         data.get('data', [{}])[0].get('tokenContractAddress', ''))
                
            if not token_address or token_address.lower() != self.BR_CONFIG['address'].lower():
                return
                
            # 处理dex-market-v3-topPool数据
            if channel == 'dex-market-v3-topPool':
                try:
                    token_address = data['arg']['tokenAddress']
                    if 'data' in data and len(data['data']) > 0 and 'data' in data['data'][0]:
                        pool_list = data['data'][0]['data']
                        
                        if token_address.lower() == self.BR_CONFIG['address'].lower():
                            total_liquidity = 0
                            token_amounts = {}
                            pool_details = []
                            
                            for i, pool in enumerate(pool_list):
                                pool_liquidity = float(pool['liquidity'])
                                total_liquidity += pool_liquidity
                                
                                pool_tokens = []
                                for token_info in pool['poolTokenInfoList']:
                                    if token_info['tokenSymbol'] != 'BR':
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
                            
                            self.top_pool_data = {
                                'total_liquidity': total_liquidity,
                                'token_amounts': token_amounts,
                                'pool_details': pool_details
                            }
                except Exception as e:
                    print(f'【BR】处理topPool数据错误: {e}')
            
            # 处理市场数据
            elif channel == 'dex-market-v3':
                if 'data' in data and len(data['data']) > 0:
                    market_data = data['data'][0]
                    token_address = market_data['tokenContractAddress']
                    
                    if token_address.lower() != self.BR_CONFIG['address'].lower():
                        return
                    
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 使用topPool的流动性数据
                    if self.top_pool_data is not None:
                        liquidity = self.top_pool_data['total_liquidity']
                        token_amounts = self.top_pool_data['token_amounts']
                    else:
                        liquidity = float(market_data['liquidity'])
                        token_amounts = {}
                        
                    liquidity_m = liquidity / 1000000
                    price = float(market_data['price'])
                    volume_5m = float(market_data['volume5M'])
                    volume_5m_m = volume_5m / 1000000
                    
                    # 添加当前流动性到历史记录
                    self.liquidity_history.append(liquidity_m)
                    if len(self.liquidity_history) > 10:
                        self.liquidity_history.pop(0)
                        
                        # 维护带时间戳的历史记录
                        current_timestamp = time.time()
                        self.liquidity_history_with_time.append((current_timestamp, liquidity_m))
                        
                        # 清理2分钟之外的数据
                        self.liquidity_history_with_time = [
                            (ts, liq) for ts, liq in self.liquidity_history_with_time 
                            if current_timestamp - ts <= 120
                        ]
                        
                        # 检查流动性是否突然减少
                        if len(self.liquidity_history) > 1:
                            current_liquidity = self.liquidity_history[-1]
                            threshold = self.BR_CONFIG['liquidity_threshold']
                            auto_threshold = self.BR_CONFIG['auto_remove_threshold']
                            
                            # 计算最大流动性下降
                            max_liquidity_drop = 0
                            max_drop_from = 0
                            
                            for historical_liquidity in self.liquidity_history[:-1]:
                                liquidity_drop = historical_liquidity - current_liquidity
                                if liquidity_drop > max_liquidity_drop:
                                    max_liquidity_drop = liquidity_drop
                                    max_drop_from = historical_liquidity
                            
                            # 2分钟时间窗口检测
                            time_window_triggered = False
                            if self.BR_CONFIG['auto_remove_enabled'] and len(self.liquidity_history_with_time) >= 2 and self.current_positions:
                                max_liquidity_in_2min = max(liq for _, liq in self.liquidity_history_with_time)
                                time_window_drop = max_liquidity_in_2min - current_liquidity
                                
                                if time_window_drop > auto_threshold:
                                    log_auto_remove_alert(current_liquidity, max_liquidity_in_2min, auto_threshold)
                                    auto_remove_thread = threading.Thread(target=self.auto_remove_positions)
                                    auto_remove_thread.daemon = True
                                    auto_remove_thread.start()
                                    time_window_triggered = True
                                    alert_msg = f"2分钟内流动性减少超过自动移除阈值 {auto_threshold}M\n从 {max_liquidity_in_2min:.2f}M 降至 {current_liquidity:.2f}M"
                                    send_wechat_work_alert(alert_msg, config=self.config)
                                    send_serverchan_alert(alert_msg, config=self.config)
                            
                            # 传统检测逻辑
                            if not time_window_triggered and self.BR_CONFIG['auto_remove_enabled'] and max_liquidity_drop > auto_threshold and self.current_positions:
                                log_auto_remove_alert(current_liquidity, max_drop_from, auto_threshold)
                                auto_remove_thread = threading.Thread(target=self.auto_remove_positions)
                                auto_remove_thread.daemon = True
                                auto_remove_thread.start()
                                alert_msg = f"流动性减少超过自动移除阈值 {auto_threshold}M\n从 {max_drop_from:.2f}M 降至 {current_liquidity:.2f}M"
                                send_wechat_work_alert(alert_msg, config=self.config)
                                send_serverchan_alert(alert_msg, config=self.config)
                            
                            # 独立的警报检查
                            elif not time_window_triggered and max_liquidity_drop > threshold:
                                log_liquidity_alert(current_liquidity, max_drop_from, max_liquidity_drop, threshold)
                                play_alert_sound()
                                alert_msg = f"流动性突然减少 {max_liquidity_drop:.2f}M\n从 {max_drop_from:.2f}M 降至 {current_liquidity:.2f}M"
                                send_wechat_work_alert(alert_msg, config=self.config)
                                send_serverchan_alert(alert_msg, config=self.config)
                        
                        # 显示当前状态
                        if token_amounts:
                            token_amounts_str = ", ".join([f"{symbol}: {format_amount(amount)}" for symbol, amount in token_amounts.items()])
                            
                            position_info_str = ""
                            if self.current_positions:
                                position_ids = [f"\033[93m#{pos['token_id']}\033[0m" for pos in self.current_positions]
                                position_info_str = f"  LP池子：{', '.join(position_ids)}"
                            
                            print(f'【BR】Time: {current_time}  Liquidity: {liquidity_m:.2f}M   Price: {price:.5f}  Volume (5min): {volume_5m_m:.2f}M  代币数量: {token_amounts_str}{position_info_str}')
                        else:
                            position_info_str = ""
                            if self.current_positions:
                                position_ids = [f"\033[93m#{pos['token_id']}\033[0m" for pos in self.current_positions]
                                position_info_str = f"  LP池子：{', '.join(position_ids)}"
                            
                            print(f'【BR】Time: {current_time}  Liquidity: {liquidity_m:.2f}M   Price: {price:.5f}  Volume (5min): {volume_5m_m:.2f}M{position_info_str}')
            
            # 处理池子历史数据
            elif channel == 'dex-market-pool-history':
                pool_data = data['data']
                if pool_data['chainId'] == '56':
                    token_contract_address = pool_data.get('tokenContractAddress', '')
                    
                    if token_contract_address and token_contract_address.lower() == self.BR_CONFIG['address'].lower():
                        changed_tokens = pool_data.get('changedTokenInfo', [])
                        if changed_tokens:
                            token_info_str = ", ".join([f"{token['tokenSymbol']}: {float(token['amount']):.6f}" for token in changed_tokens])
                            
                            value = float(pool_data['value'])
                            type_str = pool_data['type']
                            wallet_address = pool_data.get('userWalletAddress', '')
                            wallet_name = self.WALLET_NAMES.get(wallet_address, '')
                            wallet_info = f", 钱包: {wallet_name}" if wallet_name else ""
                            
                            # 检查是否是KK地址的操作
                            if wallet_address.lower() == self.KK_ADDRESS.lower():
                                if type_str == '1':
                                    log_kk_alert('enter', value, token_info_str)
                                    self.voice_alert.play_voice_alert("请注意，KK入场了，KK入场了")
                                    alert_msg = f"KK入场警报！新增流动性\n价值: ${value:.2f}\n代币变化: {token_info_str}"
                                    send_wechat_work_alert(alert_msg, config=self.config)
                                    send_serverchan_alert(alert_msg, config=self.config)
                                elif type_str == '2':
                                    log_kk_alert('exit', value, token_info_str)
                                    self.voice_alert.play_voice_alert("请注意，KK跑路了，KK跑路了")
                                    alert_msg = f"KK跑路警报！减少流动性\n价值: ${value:.2f}\n代币变化: {token_info_str}"
                                    send_wechat_work_alert(alert_msg, config=self.config)
                                    send_serverchan_alert(alert_msg, config=self.config)
                            else:
                                if type_str == '1':
                                    print(f'\033[92m【BR】新增流动性 - 价值: ${value:.2f}, 代币变化: {token_info_str}{wallet_info}\033[0m')
                                elif type_str == '2':
                                    print(f'\033[91m【BR】减少流动性 - 价值: ${value:.2f}, 代币变化: {token_info_str}{wallet_info}\033[0m')

            # 处理交易历史数据
            elif channel == 'dex-market-trade-history-pub':
                if isinstance(data['data'], list):
                    for trade_info in data['data']:
                        try:
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
                                    except Exception as e:
                                        print(f'【BR】时间戳转换错误: {e}')
                                        trade_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                else:
                                    trade_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                
                                # 格式化钱包地址
                                display_address = wallet
                                
                                if float(volume) >= self.LARGE_SELL_ALERT_CONFIG['threshold']:
                                    print(f'\033[91m【卖出】{trade_time} - {display_address} 卖出 {br_amount:.2f} BR 获得 {usdt_amount:.2f} USDT (交易量: ${float(volume):.2f})\033[0m')
                                    
                                    if self.LARGE_SELL_ALERT_CONFIG['enabled'] and float(volume) >= self.LARGE_SELL_ALERT_CONFIG['threshold']:
                                        if wallet.lower() == self.KK_ADDRESS.lower():
                                            self.voice_alert.play_voice_alert("警告！KK大额卖出，KK大额卖出")
                                            time.sleep(4)
                                            play_alert_sound()
                                        else:
                                            play_alert_sound()
                                        # 发送微信通知
                                        alert_msg = f"大额卖出警报！\n时间: {trade_time}\n地址: {display_address}\n卖出: {br_amount:.2f} BR\n获得: {usdt_amount:.2f} USDT\n交易量: ${float(volume):.2f}"
                                        send_wechat_work_alert(alert_msg, config=self.config)
                                        send_serverchan_alert(alert_msg, config=self.config)
                        except Exception as e:
                            print(f'【BR】处理交易历史数据错误: {e}')
                            continue

            # 处理实时交易数据
            elif channel == 'dex-market-tradeRealTime':
                if 'data' in data and len(data['data']) > 0:
                    trade_data = data['data'][0]
                    sell_volume = float(trade_data['tradeNumSell5M'])
                    buy_volume = float(trade_data['tradeNumBuy5M'])
                    volume_diff = sell_volume - buy_volume
                    
                    if volume_diff > self.BR_CONFIG['sell_threshold']:
                        print(f'\033[91m【BR】警告：5分钟内卖出量超过买入量 {volume_diff:.2f} 个代币\033[0m')

        except Exception as e:
            print(f'【BR】Error processing message: {e}')

    def on_error(self, ws, error):
        """WebSocket错误处理"""
        print(f'【BR】WebSocket Error: {error}')
        self.stop_heartbeat()

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket关闭处理"""
        print(f'【BR】WebSocket连接关闭: {close_status_code} - {close_msg}')
        
        self.stop_heartbeat()
        self.current_ws = None
        
        if self.reconnect_count < self.MAX_RECONNECT_ATTEMPTS:
            jitter = random.uniform(0.1, 0.5) * self.reconnect_delay
            next_delay = min(60, self.reconnect_delay + jitter)
            
            print(f'【BR】将在 {next_delay:.2f} 秒后尝试重新连接... (尝试 {self.reconnect_count + 1}/{self.MAX_RECONNECT_ATTEMPTS})')
            time.sleep(next_delay)
            
            self.reconnect_count += 1
            self.reconnect_delay = min(60, self.reconnect_delay * 1.5)
            self.connect_websocket()
        else:
            print(f'【BR】达到最大重连次数 ({self.MAX_RECONNECT_ATTEMPTS})，停止重连')
            self.reconnect_count = 0
            self.reconnect_delay = 5

    def stop_heartbeat(self):
        """停止心跳线程"""
        self.heartbeat_running = False
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            print('【BR】正在停止心跳线程...')
            self.heartbeat_thread.join(timeout=2)

    def start_heartbeat(self, ws):
        """启动心跳线程"""
        self.stop_heartbeat()
        self.heartbeat_running = True
        self.current_ws = ws
        
        def heartbeat():
            consecutive_errors = 0
            max_consecutive_errors = 3
            last_position_check = 0
            position_check_interval = 300  # 5分钟检查一次头寸
            
            while self.heartbeat_running:
                try:
                    if not self.current_ws or self.current_ws.sock is None:
                        print('【BR】WebSocket连接已断开，停止心跳')
                        break

                    # BR代币订阅消息
                    messages = [
                        {
                            "op": "unsubscribe",
                            "args": [{
                                "channel": "dex-market-v3",
                                "chainId": 56,
                                "tokenAddress": self.BR_CONFIG['address']
                            }]
                        },
                        {
                            "op": "subscribe",
                            "args": [{
                                "channel": "dex-market-v3",
                                "chainId": 56,
                                "tokenAddress": self.BR_CONFIG['address']
                            }]
                        },
                        {
                            "op": "subscribe",
                            "args": [{
                                "channel": "dex-market-v3-topPool",
                                "chainId": "56",
                                "tokenAddress": self.BR_CONFIG['address']
                            }]
                        },
                        {
                            "op": "subscribe",
                            "args": [{
                                "channel": "dex-market-pool-history",
                                "extraParams": json.dumps({
                                    "chainId": "56",
                                    "tokenContractAddress": self.BR_CONFIG['address'],
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
                                "tokenAddress": self.BR_CONFIG['address']
                            }]
                        },
                        {
                            "op": "subscribe",
                            "args": [{
                                "channel": "dex-market-trade-history-pub",
                                "chainIndex": "56",
                                "tokenContractAddress": self.BR_CONFIG['address']
                            }]
                        }
                    ]
                    
                    for msg in messages:
                        if not self.heartbeat_running:
                            break
                        self.current_ws.send(json.dumps(msg))
                        time.sleep(0.1)
                    
                    consecutive_errors = 0
                    
                    # 检查是否需要更新头寸信息
                    current_time = time.time()
                    if current_time - last_position_check >= position_check_interval:
                        if self.web3_manager:
                            try:
                                self.web3_manager.get_v3_positions()
                                new_positions = self.web3_manager.get_current_positions()
                                
                                # 检查头寸是否有变化
                                if len(new_positions) != len(self.current_positions):
                                    old_count = len(self.current_positions)
                                    self.current_positions = new_positions
                                    new_count = len(self.current_positions)
                                    
                                    if new_count > old_count:
                                        log_position_change(old_count, new_count, [str(pos['token_id']) for pos in self.current_positions])
                                    elif new_count < old_count:
                                        log_position_change(old_count, new_count, [str(pos['token_id']) for pos in self.current_positions])
                                else:
                                    # 即使数量相同，也检查token_id是否有变化
                                    old_ids = set(pos['token_id'] for pos in self.current_positions)
                                    new_ids = set(pos['token_id'] for pos in new_positions)
                                    
                                    if old_ids != new_ids:
                                        log_position_change(len(self.current_positions), len(new_positions), [str(pos['token_id']) for pos in new_positions])
                                        self.current_positions = new_positions
                                
                                last_position_check = current_time
                            except Exception as e:
                                print(f'【BR】头寸检查失败: {e}')
                    
                    for _ in range(20):
                        if not self.heartbeat_running:
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
        
        self.heartbeat_thread = threading.Thread(target=heartbeat)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()

    def on_open(self, ws):
        """WebSocket连接建立"""
        print('【BR】WebSocket连接已建立')
        
        self.reconnect_count = 0
        self.reconnect_delay = 5
        
        self.start_heartbeat(ws)

    def connect_websocket(self):
        """连接WebSocket"""
        try:
            ws = websocket.WebSocketApp(
                "wss://wsdexpri.okx.com/ws/v5/ipublic",
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_open=self.on_open
            )
            
            self.current_ws = ws
            
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

    def run(self):
        """运行监控系统"""
        try:
            msg = f'【BR】🔔 BR流动性监控系统已启动'
            send_wechat_work_alert(msg, config=self.config)
            send_serverchan_alert(msg, config=self.config)
            print('【BR】🚀 启动BR流动性自动保护系统 - Mac版本...')
            print(f'【BR】监控代币地址: {self.BR_CONFIG["address"]}')
            print(f'【BR】流动性减少阈值: {self.BR_CONFIG["liquidity_threshold"]}M')
            
            # 自动移除功能状态
            auto_status = "开启" if self.BR_CONFIG['auto_remove_enabled'] else "关闭"
            auto_color = '\033[92m' if self.BR_CONFIG['auto_remove_enabled'] else '\033[91m'
            print(f'【BR】🛡️ 自动移除保护: {auto_color}{auto_status}\033[0m')
            if self.BR_CONFIG['auto_remove_enabled']:
                print(f'【BR】🚨 自动移除阈值: {self.BR_CONFIG["auto_remove_threshold"]}M')
                print(f'【BR】⏰ 自动移除冷却时间: {self.AUTO_REMOVE_COOLDOWN}秒')
            
            # 大额卖出警报状态
            alert_status = "开启" if self.LARGE_SELL_ALERT_CONFIG['enabled'] else "关闭"
            alert_color = '\033[92m' if self.LARGE_SELL_ALERT_CONFIG['enabled'] else '\033[91m'
            print(f'【BR】🚨 大额卖出阈值: ${self.LARGE_SELL_ALERT_CONFIG["threshold"]:,} USDT')
            print(f'【BR】🔔 大额卖出警报状态: {alert_color}{alert_status}\033[0m')
            
            print(f'【BR】特殊监控地址: {self.KK_ADDRESS} (KK)')
            
            # 检查钱包地址配置
            if not self.WEB3_CONFIG['wallet_address']:
                print('\n【BR】⚠️ 钱包地址未配置！')
                print('【BR】📝 请在脚本中的 WEB3_CONFIG["wallet_address"] 处配置您的钱包地址')
                print('【BR】💡 配置后重启脚本即可启用头寸查询和自动移除功能')
                print('【BR】🔄 当前将只进行流动性监控，不进行头寸相关操作\n')
            
            # 初始化Web3Manager
            print('【BR】🔗 初始化Web3Manager...')
            self.web3_manager = Web3Manager(self.config)
            if self.web3_manager.connect():
                print('【BR】✅ Web3连接成功')
                # 检查当前头寸（仅在有钱包地址时）
                if self.WEB3_CONFIG['wallet_address']:
                    self.web3_manager.get_v3_positions()
                    self.current_positions = self.web3_manager.get_current_positions()
                    print(f'【BR】📊 当前USDT-BR头寸数量: {len(self.current_positions)}')
                    if self.current_positions:
                        position_ids = [str(pos['token_id']) for pos in self.current_positions]
                        print(f'【BR】📋 头寸编号: {", ".join(position_ids)}')
                else:
                    print('【BR】⚠️ 未配置钱包地址，跳过头寸查询')
            else:
                print('【BR】❌ Web3连接失败，自动移除功能将不可用')
            
            # 启动WebSocket监控
            print('【BR】📡 启动WebSocket监控...')
            ws = self.connect_websocket()
            
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
            self.stop_heartbeat()
        except Exception as e:
            print(f'【BR】程序异常: {e}')
            self.stop_heartbeat()

if __name__ == "__main__":
    monitor = BRMonitor('br-auto/config.yaml')
    monitor.run()
