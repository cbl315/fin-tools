"""控制台日志模块"""
from typing import Dict, List, Any

def format_amount(amount: float) -> str:
    """将数量格式化为合适的单位（M、K等）"""
    if amount >= 1000000:
        return f"{amount/1000000:.2f}M"
    elif amount >= 1000:
        return f"{amount/1000:.2f}K"
    return f"{amount:.2f}"

def log_liquidity_alert(current_liquidity: float, max_drop_from: float, max_liquidity_drop: float, threshold: float):
    """记录流动性警报"""
    print(f'\033[91m【BR】警告！流动性突然减少 {max_liquidity_drop:.2f}M！从 {max_drop_from:.2f}M 降至 {current_liquidity:.2f}M\033[0m')

def log_auto_remove_alert(current_liquidity: float, max_liquidity: float, threshold: float):
    """记录自动移除警报"""
    print(f'\033[93m【BR】🚨 流动性减少超过自动移除阈值 {threshold}M，触发自动保护！从 {max_liquidity:.2f}M 降至 {current_liquidity:.2f}M\033[0m')

def log_kk_alert(alert_type: str, value: float, token_info: str):
    """记录KK地址警报"""
    if alert_type == 'enter':
        print(f'\033[93m【BR】🚨 KK入场警报！新增流动性 - 价值: ${value:.2f}, 代币变化: {token_info}\033[0m')
    else:
        print(f'\033[95m【BR】🚨 KK跑路警报！减少流动性 - 价值: ${value:.2f}, 代币变化: {token_info}\033[0m')

def log_position_change(old_count: int, new_count: int, position_ids: List[str]):
    """记录头寸变化"""
    if new_count > old_count:
        print(f'【BR】🔄 检测到新头寸！头寸数量从 {old_count} 增加到 {new_count}')
    else:
        print(f'【BR】🔄 检测到头寸减少！头寸数量从 {old_count} 减少到 {new_count}')
    print(f'【BR】📋 当前头寸编号: {", ".join(position_ids)}')

def log_market_status(current_time: str, liquidity: float, price: float, volume: float, 
                     token_amounts: Dict[str, float], position_ids: List[str]):
    """记录市场状态"""
    token_amounts_str = ", ".join([f"{symbol}: {format_amount(amount)}" for symbol, amount in token_amounts.items()])
    position_info = f"  LP池子：{', '.join(position_ids)}" if position_ids else ""
    print(f'【BR】Time: {current_time}  Liquidity: {liquidity:.2f}M   Price: {price:.5f}  Volume (5min): {volume:.2f}M  代币数量: {token_amounts_str}{position_info}')
