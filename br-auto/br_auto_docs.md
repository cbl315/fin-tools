# BR流动性自动保护系统文档

## 系统概述
这是一个针对BR代币的流动性自动保护系统，主要功能是监控BSC链上BR代币的流动性变化，并在流动性大幅减少时自动移除流动性头寸(LP)以保护资金。系统专为Mac环境设计。

## 重构说明 (v2.0)
- 从过程式编程重构为面向对象设计
- 所有功能封装在 `BRMonitor` 类中
- 消除全局变量，改进状态管理
- 新增2分钟时间窗口流动性检测机制
- 改进头寸缓存机制，减少链上查询
- 增强WebSocket连接稳定性和错误处理
- 集成Web3Manager进行链上操作

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
### 重构对比 (v1.x vs v2.0)

| 特性                | v1.x (过程式)               | v2.0 (面向对象)             |
|---------------------|---------------------------|---------------------------|
| 状态管理            | 全局变量                   | 类实例属性                |
| 配置加载            | 全局加载                   | 类初始化时加载            |
| WebSocket连接       | 独立函数                   | 类方法                    |
| 自动移除逻辑        | 全局函数                   | 类方法                    |
| 线程安全            | 需手动管理                 | 通过类封装自动管理        |
| 可测试性            | 困难                       | 易于单元测试              |
| 流动性检测          | 简单阈值检测               | 2分钟时间窗口检测         |
| 头寸管理            | 每次查询链上数据           | 缓存机制减少链上查询      |
| 错误处理            | 基本重试逻辑               | 智能重连和错误恢复        |

### 代码架构
#### 类设计模式 (v2.0+)
系统采用面向对象的类设计模式，主要类结构如下：

```python
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
        with open(path, 'r') as f:
            self.config = yaml.safe_load(f)
        
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
    
    # 主要功能方法
    def connect_websocket(self): ...
    def auto_remove_positions(self): ...
    def on_message(self, ws, message): ...
    def on_error(self, ws, error): ...
    def on_close(self, ws, close_status_code, close_msg): ...
    def on_open(self, ws): ...
    def start_heartbeat(self, ws): ...
    def stop_heartbeat(self): ...
```

#### 架构优势
1. **状态封装**：所有相关状态变量封装在类实例中
2. **减少全局污染**：消除global关键字使用
3. **更好的可测试性**：可以创建独立实例进行单元测试
4. **明确的作用域**：方法通过self访问实例状态
5. **更好的线程安全**：状态修改集中在类方法中

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

## 重构优势
1. **更好的封装性**：
   - 所有相关状态和方法集中管理
   - 减少命名冲突风险

2. **更清晰的架构**：
   - 明确的方法作用域
   - 直观的类层次结构

3. **改进的可维护性**：
   - 更容易添加新功能
   - 更简单的调试流程

4. **增强的线程安全**：
   - 状态修改集中在类方法中
   - 减少竞态条件风险

## 使用说明
### 版本迁移指南 (v1.x → v2.0)

#### 迁移注意事项
1. **状态访问**：
   - 原版：直接访问全局变量
   ```python
   global current_positions
   ```
   - 新版：通过self访问实例属性
   ```python
   self.current_positions
   ```

2. **方法调用**：
   - 原版：独立函数调用
   ```python
   connect_websocket()
   ```
   - 新版：通过实例调用方法
   ```python
   monitor.connect_websocket()
   ```

3. **初始化差异**：
   - 原版：直接执行main()
   - 新版：先创建实例再调用run()
   ```python
   monitor = BRMonitor('config.yaml')
   monitor.run()
   ```

#### 主要变更
- 从过程式编程改为面向对象设计
- 移除所有global变量
- 状态管理集中到BRMonitor类

#### 迁移步骤
1. 创建BRMonitor实例：
```python
monitor = BRMonitor('br-auto/config.yaml')
```

2. 替换原有全局函数调用为实例方法：
```python
# 旧代码
connect_websocket()

# 新代码
monitor.connect_websocket()
```

3. 主程序入口改为：
```python
if __name__ == "__main__":
    monitor = BRMonitor('br-auto/config.yaml')
    monitor.main()  # 假设将原main()逻辑移到类方法中
```

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

## Recent Changes

### [2025-07-19 23:30:00]
- 新增2分钟时间窗口流动性检测机制
- 改进头寸缓存机制，减少链上查询
- 增强WebSocket连接稳定性和错误处理
- 集成Web3Manager进行链上操作
- 优化自动移除冷却期处理逻辑
- 改进语音警报线程管理

## 维护建议
1. **面向对象设计实践**：
   - 状态修改应通过方法而非直接属性访问
   - 类方法应保持单一职责原则
   - 便于扩展子类实现特定行为
   - 支持依赖注入进行测试

2. 定期检查依赖库版本
3. 监控WebSocket连接状态
4. 根据市场情况调整阈值参数
5. 重要操作前备份钱包私钥
