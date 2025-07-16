#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web3Manager测试脚本
"""

import yaml
from web3_utils.web3_manager import Web3Manager

def main():
    # 加载配置文件
    with open('br-auto/config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 创建Web3Manager实例
    web3_config = {
        'web3_config': config['web3_config'],
        'proxy_config': config['proxy_config']
    }
    manager = Web3Manager(web3_config)
    
    # 连接Web3
    print("正在连接Web3...")
    if not manager.connect():
        print("Web3连接失败")
        return
    
    # 获取头寸
    print("获取USDT-BR头寸...")
    positions = manager.get_v3_positions()
    if not positions:
        print("没有找到可用的USDT-BR头寸")
        return
    
    print(f"找到 {len(positions)} 个头寸:")
    for pos in positions:
        print(f"Token ID: {pos['token_id']}, Liquidity: {pos['liquidity']}")
    
    # 测试execute_multicall
    print("\n测试execute_multicall方法...")
    for pos in positions:
        print(f"\n处理头寸 #{pos['token_id']}")
        result = manager.execute_multicall(pos)
        print(f"执行结果: {'成功' if result else '失败'}")
        if not result:
            break  # 如果失败则停止测试

if __name__ == "__main__":
    main()
