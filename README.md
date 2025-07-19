# BR Liquidity Auto Protection System

A Python script that monitors BR token liquidity and automatically removes positions when liquidity drops below configured thresholds.

## Prerequisites

- Python 3.8+
- pip package manager

## Installation

1. Clone this repository
2. Install dependencies:
```bash
pip install -r br-auto/requirements.txt
```

## Configuration

Create/edit `br-auto/config.yaml` with the following required settings:

```yaml
# BR代币配置
br_config:
  name: BR
  liquidity_threshold: 2  # Liquidity drop threshold (M)
  auto_remove_enabled: True  # Auto remove switch
  auto_remove_threshold: 1  # Auto remove threshold (M)
  address: "0xff7d6a96ae471bbcd7713af9cb1feeb16cf56b41"  # BR token address

# Web3配置 (Required for auto-remove functionality)
web3_config:
  rpc_url: "https://bsc-dataseed1.binance.org/"
  private_key: ""  # Your wallet private key
  wallet_address: ""  # Your wallet address
  gas_price_gwei: 0.5
  gas_limit: 400000
  usdt: "0x55d398326f99059ff775485246999027b3197955"
  br: "0xFf7d6A96ae471BbCD7713aF9CB1fEeB16cf56B41"
  position_manager: "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364"

# Proxy配置 (Optional)
proxy_config:
  enabled: False
  http_proxy: ""
  https_proxy: ""
```

## Running the Script

```bash
python br-auto/br_auto.py
```

## Features

- Real-time liquidity monitoring
- Automatic position removal when thresholds are breached
- Large sell alerts
- Special address monitoring (e.g., KK wallet)
- Voice and sound alerts (Mac only)

## Important Notes

1. **Security Warning**: Never commit your private key to version control. The `config.yaml` file is included in `.gitignore` by default.
2. For auto-remove functionality, you must configure your wallet private key and address in `config.yaml`.
3. The script requires Web3 connection to Binance Smart Chain for full functionality.
4. Voice alerts are only available on macOS systems.
5. Monitor the console output for important alerts and status updates.

## Recent Changes

### [2025-07-19 23:45:00]
- 新增2分钟时间窗口流动性检测机制
- 改进头寸缓存机制，减少链上查询
- 增强WebSocket连接稳定性和错误处理
- 集成Web3Manager进行链上操作
- 优化自动移除冷却期处理逻辑
- 改进语音警报线程管理
- 修复缩进问题导致的错误触发移除头寸
- 修复play_voice_alert功能不可用问题

### [2025-07-19 23:30:00]
- 重构为面向对象设计 (v2.0)

## Troubleshooting

- If you get SSL errors, try:
  ```bash
  pip install --upgrade certifi
  ```
- For Web3 connection issues, verify your RPC URL is correct
- Ensure all required fields in config.yaml are properly configured
