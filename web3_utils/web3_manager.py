#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web3操作管理类 - 封装所有与Web3相关的操作
"""

from web3 import Web3
import json
import time
from datetime import datetime

# 兼容不同版本的web3.py库
try:
    from web3.middleware import geth_poa_middleware
except ImportError:
    try:
        from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
    except ImportError:
        geth_poa_middleware = None

class Web3Manager:
    """管理所有Web3相关操作"""
    
    def __init__(self, config):
        """
        初始化Web3Manager
        
        Args:
            config (dict): 包含web3配置的字典
        """
        self.web3 = None
        self.config = config
        self.position_manager_abi = self._load_position_manager_abi()
        self.current_positions = []
        
    def _load_position_manager_abi(self):
        """加载Position Manager ABI"""
        return '''[
            {
                "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
                "name": "positions",
                "outputs": [
                    {"internalType": "uint96", "name": "nonce", "type": "uint96"},
                    {"internalType": "address", "name": "operator", "type": "address"},
                    {"internalType": "address", "name": "token0", "type": "address"},
                    {"internalType": "address", "name": "token1", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
                    {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
                    {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
                    {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
                    {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {
                        "components": [
                            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
                            {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
                            {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
                            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                        ],
                        "internalType": "struct INonfungiblePositionManager.DecreaseLiquidityParams",
                        "name": "params",
                        "type": "tuple"
                    }
                ],
                "name": "decreaseLiquidity",
                "outputs": [
                    {"internalType": "uint256", "name": "amount0", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1", "type": "uint256"}
                ],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {
                        "components": [
                            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                            {"internalType": "address", "name": "recipient", "type": "address"},
                            {"internalType": "uint128", "name": "amount0Max", "type": "uint128"},
                            {"internalType": "uint128", "name": "amount1Max", "type": "uint128"}
                        ],
                        "internalType": "struct INonfungiblePositionManager.CollectParams",
                        "name": "params",
                        "type": "tuple"
                    }
                ],
                "name": "collect",
                "outputs": [
                    {"internalType": "uint256", "name": "amount0", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1", "type": "uint256"}
                ],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
                "name": "burn",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "bytes[]", "name": "data", "type": "bytes[]"}],
                "name": "multicall",
                "outputs": [{"internalType": "bytes[]", "name": "results", "type": "bytes[]"}],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "address", "name": "owner", "type": "address"}, {"internalType": "uint256", "name": "index", "type": "uint256"}],
                "name": "tokenOfOwnerByIndex",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]'''
    
    def connect(self):
        """创建Web3连接"""
        try:
            if self.config['proxy_config']['enabled']:
                self.web3 = Web3(Web3.HTTPProvider(self.config['web3_config']['rpc_url'], request_kwargs={
                    'proxies': {'http': self.config['proxy_config']['http_proxy'], 'https': self.config['proxy_config']['https_proxy']},
                    'timeout': 30
                }))
            else:
                self.web3 = Web3(Web3.HTTPProvider(self.config['web3_config']['rpc_url']))
            
            # 安全注入POA中间件
            if geth_poa_middleware is not None:
                try:
                    self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except Exception as e:
                    print(f'【BR】注入POA中间件失败: {e}')
            
            if hasattr(self.web3, 'is_connected') and self.web3.is_connected():
                print("【BR】✅ BSC网络连接成功")
                return True
            else:
                print("【BR】❌ BSC网络连接失败")
                return False
        except Exception as e:
            print(f'【BR】Web3连接失败: {e}')
            return False

    def is_connected(self):
        """检查Web3连接状态"""
        return hasattr(self, 'web3') and self.web3 is not None and self.web3.is_connected()
    
    def get_v3_positions(self):
        """获取USDT-BR活跃头寸 - 倒序优化版本"""
        if not self.web3 or not self.web3.is_connected():
            print("【BR】❌ Web3未连接")
            return []
            
        try:
            position_manager = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.config['web3_config']['position_manager']),
                abi=json.loads(self.position_manager_abi)
            )
            
            wallet = Web3.to_checksum_address(self.config['web3_config']['wallet_address'])
            balance = position_manager.functions.balanceOf(wallet).call()
            
            if balance == 0:
                print("【BR】钱包无头寸")
                self.current_positions = []
                return []
            
            print(f"【BR】开始倒序查询头寸，总数: {balance}")
            
            usdt = Web3.to_checksum_address(self.config['web3_config']['usdt'])
            br = Web3.to_checksum_address(self.config['web3_config']['br'])
            positions = []
            
            # 倒序查询，从最新的头寸开始
            for i in range(balance - 1, -1, -1):
                try:
                    token_id = position_manager.functions.tokenOfOwnerByIndex(wallet, i).call()
                    data = position_manager.functions.positions(token_id).call()
                    
                    token0, token1, liquidity = Web3.to_checksum_address(data[2]), Web3.to_checksum_address(data[3]), data[7]
                    
                    # 检查是否为USDT-BR头寸
                    if liquidity > 0 and ((token0 == usdt and token1 == br) or (token0 == br and token1 == usdt)):
                        position_info = {'token_id': token_id, 'liquidity': liquidity}
                        positions.append(position_info)
                        print(f"【BR】✅ 找到USDT-BR头寸 #{token_id}，流动性: {liquidity}")
                        # 找到目标头寸后立即返回，提高效率
                        print(f"【BR】🚀 倒序查询完成，查询了 {balance - i} 个头寸")
                        self.current_positions = positions
                        return positions
                except Exception as e:
                    print(f"【BR】查询头寸 {i} 失败: {e}")
                    continue
            
            print("【BR】❌ 未找到USDT-BR头寸")
            self.current_positions = []
            return positions
        except Exception as e:
            print(f'【BR】获取头寸失败: {e}')
            self.current_positions = []
            return []
    
    def execute_multicall(self, position):
        """执行Multicall原子操作"""
        if not self.web3 or not self.web3.is_connected():
            print("【BR】❌ Web3未连接")
            return False
            
        try:
            position_manager = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.config['web3_config']['position_manager']),
                abi=json.loads(self.position_manager_abi)
            )
            
            wallet = Web3.to_checksum_address(self.config['web3_config']['wallet_address'])
            token_id = position['token_id']
            liquidity = position['liquidity']
            deadline = int(time.time()) + 3600
            uint128_max = int('0xffffffffffffffffffffffffffffffff', 16)
            
            # 兼容不同版本的web3.py库
            def encode_function_call(contract, function_name, args):
                """兼容encodeABI和encode_abi方法"""
                try:
                    # 尝试新版本的encode_abi方法
                    return contract.encode_abi(function_name, args)
                except AttributeError:
                    # 回退到旧版本的encodeABI方法
                    return contract.encodeABI(function_name, args)
            
            # 构建Multicall
            calls = [
                encode_function_call(position_manager, 'decreaseLiquidity', [(token_id, liquidity, 0, 0, deadline)]),
                encode_function_call(position_manager, 'collect', [(token_id, wallet, uint128_max, uint128_max)]),
                encode_function_call(position_manager, 'burn', [token_id])
            ]
            
            # 发送交易
            txn = position_manager.functions.multicall(calls).build_transaction({
                'from': wallet,
                'nonce': self.web3.eth.get_transaction_count(wallet),
                'gas': self.config['web3_config']['gas_limit'],
                'gasPrice': self.web3.to_wei(self.config['web3_config']['gas_price_gwei'], 'gwei')
            })
            
            signed = self.web3.eth.account.sign_transaction(txn, self.config['web3_config']['private_key'])
            # 兼容不同版本的web3.py库中SignedTransaction对象的属性名
            try:
                # 尝试新版本的raw_transaction属性
                raw_transaction = signed.raw_transaction
            except AttributeError:
                # 回退到旧版本的rawTransaction属性
                raw_transaction = signed.rawTransaction
            
            tx_hash = self.web3.eth.send_raw_transaction(raw_transaction)
            
            print(f"【BR】🚀 自动移除交易: {tx_hash.hex()}")
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                print(f"【BR】✅ 头寸 #{token_id} 自动移除成功")
                return True
            else:
                print(f"【BR】❌ 头寸 #{token_id} 自动移除失败")
                return False
        except Exception as e:
            print(f'【BR】执行自动移除失败: {e}')
            return False
    
    def get_current_positions(self):
        """获取当前缓存的头寸信息"""
        return self.current_positions
