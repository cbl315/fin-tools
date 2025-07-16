# BR流动性自动保护系统文档

## 系统概述
这是一个针对BR代币的流动性自动保护系统，主要功能是监控BSC链上BR代币的流动性变化，并在流动性大幅减少时自动移除流动性头寸(LP)以保护资金。系统专为Mac环境设计。

## 主要功能
1. **实时流动性监控**
   - 通过WebSocket连接OKX API获取实时市场数据
   - 监控流动性总量、价格、交易量等关键指标

2. **自动保护机制**
   - 当流动性减少超过设定阈值时自动移除LP头寸
   - 2分钟时间窗口检测流动性突变
   - 自动移除冷却时间机制(默认300秒)

3. **警报系统**
   - 终端彩色输出区分警报级别
   - Mac系统声音警报
   - 中文语音播报(支持多种语音)
   - 特殊地址交易特别警报
   - Server酱微信推送告警(支持代理配置)

4. **特殊监控**
   - 监控特定地址(如KK地址)的交易行为
   - 大额卖出交易检测(可配置阈值)

## 技术实现细节
- **WebSocket连接**: 使用websocket-client库连接OKX API
- **区块链交互**: 使用web3.py与BSC链交互
- **多线程处理**: 
  - 心跳线程维持WebSocket连接
  - 语音警报线程避免阻塞主程序
- **智能合约操作**:
  - 使用PancakeSwap V3 Position Manager合约
  - 通过Multicall优化链上操作

## 配置参数
### BR代币配置(BR_CONFIG)
```python
{
    'name': 'BR',  # 代币名称
    'liquidity_threshold': 2,  # 流动性减少警报阈值(M)
    'auto_remove_enabled': True,  # 自动移除开关
    'auto_remove_threshold': 1,  # 自动移除阈值(M)
    'sell_threshold': 20000000,  # 卖出量警报阈值
    'large_sell_threshold': 50000,  # 大额卖出阈值(USDT)
    'symbol': 'BR',  # 代币符号
    'address': '0xff7d6a96ae471bbcd7713af9cb1feeb16cf56b41'  # 代币合约地址
}
```

### Server酱配置(SERVERCHAN_CONFIG)
```python
{
    'enabled': True,  # 启用Server酱告警
    'sckey': '您的SCKEY',  # Server酱SCKEY
    'title': 'BR流动性告警'  # 消息标题
}

### Web3配置(WEB3_CONFIG)
```python
{
    'rpc_url': 'https://bsc-dataseed1.binance.org/',  # BSC节点RPC
    'private_key': '',  # 钱包私钥(需用户配置)
    'wallet_address': '',  # 钱包地址(需用户配置)
    'gas_price_gwei': 0.5,  # 燃气价格
    'gas_limit': 400000,  # 燃气限制
    'usdt': '0x55d398326f99059ff775485246999027b3197955',  # USDT合约地址
    'br': '0xFf7d6A96ae471BbCD7713aF9CB1fEeB16cf56B41',  # BR合约地址
    'position_manager': '0x46A15B0b27311cedF172AB29E4f4766fbE7F4364'  # PancakeSwap V3 Position Manager
}
```

## 使用说明
1. **配置要求**:
   - Python 3.6+
   - 依赖库: websocket-client, web3.py

2. **安装依赖**:

方式一：直接安装
```bash
pip install websocket-client web3
```

方式二：使用requirements.txt安装
```bash
pip install -r requirements.txt
```

3. **配置参数**:
   - 在WEB3_CONFIG中配置钱包地址和私钥
   - 根据需求调整BR_CONFIG中的阈值参数

4. **运行系统**:
```bash
python3 br_auto.py
```

5. **注意事项**:
   - 确保网络连接稳定
   - 自动移除功能需要正确配置钱包信息
   - 生产环境使用建议配置代理
   - Server酱需要配置正确的SCKEY
   - 如遇IP限制可启用代理配置

## 维护建议
1. 定期检查依赖库版本
2. 监控WebSocket连接状态
3. 根据市场情况调整阈值参数
4. 重要操作前备份钱包私钥
