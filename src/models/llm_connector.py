import time
import json
import requests
from typing import Dict, Any
import sys
import os
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)  # 强制覆盖系统环境变量

# 判断是否开启调试模式
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# 配置日志
log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import LLM_API_CONFIG

class LLMConnector:
    """大模型API连接器"""
    
    def __init__(self, api_config: Dict[str, Any] = None):
        """初始化连接器
        
        Args:
            api_config: API配置，默认使用config.py中的配置
        """
        # 强制再次加载.env中的配置，确保使用正确的API
        load_dotenv(override=True)
        
        # 从环境变量中直接读取配置，而不是使用LLM_API_CONFIG
        if api_config is None:
            api_config = {
                "API_URL": os.getenv("LLM_API_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"),
                "API_KEY": os.getenv("LLM_API_KEY", ""),
                "MODEL": os.getenv("LLM_MODEL", "qwen-max"),
                "TEMPERATURE": 0.1,
                "MAX_TOKENS": 1000,
            }
        
        self.api_config = api_config
        
        # 记录初始化参数，便于调试
        if DEBUG_MODE:
            masked_key = self.api_config["API_KEY"][:4] + "****" + self.api_config["API_KEY"][-4:] if len(self.api_config["API_KEY"]) > 8 else "****"
            logger.debug(f"LLMConnector初始化，API配置：URL={self.api_config['API_URL']}, MODEL={self.api_config['MODEL']}, KEY={masked_key}")
    
    def get_response(self, prompt: str) -> str:
        """调用大模型API获取回复
        
        Args:
            prompt: 提示词
            
        Returns:
            模型回复文本
        """
        # 通义千问API
        if "dashscope.aliyuncs.com" in self.api_config["API_URL"]:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_config['API_KEY']}"
            }
            
            # 通义千问最新版本API文档要求的参数格式
            # https://help.aliyun.com/document_detail/2400395.html
            payload = {
                "model": self.api_config["MODEL"],
                "input": {
                    "messages": [{"role": "user", "content": prompt}]
                },
                "parameters": {
                    "temperature": self.api_config["TEMPERATURE"],
                    "result_format": "text",  # 明确要求文本格式
                    "max_tokens": self.api_config["MAX_TOKENS"]
                }
            }
            
            try:
                logger.info(f"调用通义千问API, 模型: {self.api_config['MODEL']}")
                
                # 记录请求详情(调试模式)
                if DEBUG_MODE:
                    masked_key = self.api_config["API_KEY"][:4] + "****" + self.api_config["API_KEY"][-4:]
                    logger.debug(f"API密钥(部分隐藏): {masked_key}")
                    logger.debug(f"请求URL: {self.api_config['API_URL']}")
                    logger.debug(f"请求头: {json.dumps(headers, ensure_ascii=False)}")
                    logger.debug(f"请求负载: {json.dumps(payload, ensure_ascii=False)}")
                
                # 发送请求并记录时间
                start_time = time.time()
                response = requests.post(
                    self.api_config["API_URL"],
                    headers=headers,
                    json=payload,
                    timeout=30  # 设置超时为30秒
                )
                elapsed_time = time.time() - start_time
                logger.info(f"API响应时间: {elapsed_time:.2f}秒")
                
                # 检查HTTP状态码
                if response.status_code != 200:
                    logger.error(f"通义千问API HTTP错误: {response.status_code}")
                    logger.error(f"错误详情: {response.text}")
                    raise Exception(f"API调用失败(HTTP {response.status_code}): {response.text}")
                
                # 记录原始响应文本
                if DEBUG_MODE:
                    logger.debug(f"原始响应: {response.text[:1000]}")
                
                # 尝试解析JSON响应
                try:
                    result = response.json()
                    if DEBUG_MODE:
                        logger.debug(f"通义千问API完整响应: {json.dumps(result, ensure_ascii=False)}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {str(e)}")
                    logger.error(f"原始响应: {response.text[:1000]}")
                    raise Exception(f"API响应不是有效的JSON: {str(e)}")
                
                # 处理错误码
                if "code" in result:
                    if result["code"] != "Success" and result["code"] != "success" and result["code"] != 200:
                        error_msg = result.get("message", "未知错误")
                        logger.error(f"通义千问API返回错误: {result['code']} - {error_msg}")
                        raise Exception(f"通义千问API错误: {error_msg}")
                
                # 标准格式 (通义千问文档中的格式)
                if "output" in result and "text" in result["output"]:
                    logger.info("成功解析通义千问标准响应格式(output.text)")
                    return result["output"]["text"]
                
                # 检查响应中每一个可能包含文本结果的字段
                text_fields_paths = [
                    ["output", "text"],           # 标准路径
                    ["results", 0, "content"],    # 部分版本的格式
                    ["result"],                   # 可能的简化格式
                    ["response"],                 # 通用格式
                    ["generated_text"],           # 一些模型的格式
                    ["data", "text"],             # 某些API版本
                    ["data", "content"],          # 某些API版本
                    ["choices", 0, "text"],       # 类OpenAI格式
                    ["choices", 0, "message", "content"]  # 类OpenAI Chat格式
                ]
                
                # 尝试从每个可能的路径中获取文本
                for path in text_fields_paths:
                    try:
                        current_obj = result
                        for key in path:
                            if isinstance(key, int):
                                if isinstance(current_obj, list) and len(current_obj) > key:
                                    current_obj = current_obj[key]
                                else:
                                    raise KeyError(f"索引 {key} 超出列表范围")
                            else:
                                if isinstance(current_obj, dict) and key in current_obj:
                                    current_obj = current_obj[key]
                                else:
                                    raise KeyError(f"键 {key} 不在字典中")
                        
                        if isinstance(current_obj, str) and len(current_obj) > 0:
                            logger.info(f"使用路径 {' -> '.join([str(k) for k in path])} 提取文本内容")
                            return current_obj
                    except (KeyError, IndexError, TypeError) as e:
                        if DEBUG_MODE:
                            logger.debug(f"路径 {' -> '.join([str(k) for k in path])} 不可用: {str(e)}")
                
                # 查找任何可能包含文本的字符串字段
                logger.warning("无法从已知路径提取文本，尝试查找任何有效文本内容...")
                
                def find_text_field(obj, min_length=30, path=""):
                    """递归查找可能的文本内容"""
                    if isinstance(obj, str) and len(obj) >= min_length:
                        logger.info(f"在路径 {path} 处找到可能的文本内容")
                        return obj
                    
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            new_path = f"{path}.{key}" if path else key
                            result = find_text_field(value, min_length, new_path)
                            if result:
                                return result
                    
                    if isinstance(obj, list):
                        for i, item in enumerate(obj):
                            new_path = f"{path}[{i}]" if path else f"[{i}]"
                            result = find_text_field(item, min_length, new_path)
                            if result:
                                return result
                    
                    return None
                
                text_content = find_text_field(result)
                if text_content:
                    return text_content
                
                # 如果无法找到任何文本内容，返回错误提示
                logger.error(f"无法从响应中提取文本内容，返回完整JSON")
                
                # 格式化的简单版本，方便阅读
                return f"无法解析通义千问API响应。以下是原始响应：\n\n{json.dumps(result, ensure_ascii=False, indent=2)}"
                
            except Exception as e:
                logger.error(f"通义千问API异常: {str(e)}")
                import traceback
                logger.error(f"异常堆栈: {traceback.format_exc()}")
                raise Exception(f"API调用异常: {str(e)}")
        
        # 通用格式(OpenAI接口)
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_config['API_KEY']}"
            }
            
            payload = {
                "model": self.api_config["MODEL"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.api_config["TEMPERATURE"],
                "max_tokens": self.api_config["MAX_TOKENS"]
            }
            
            try:
                logger.info("调用通用OpenAI格式API")
                response = requests.post(
                    self.api_config["API_URL"],
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.error(f"API调用失败: {response.text}")
                    raise Exception(f"API调用失败: {response.text}")
                
                result = response.json()
                
                # 调试输出
                logger.info(f"API响应: {json.dumps(result, ensure_ascii=False)[:100]}...")
                
                # 尝试OpenAI格式
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                # 兜底方案，记录完整响应并尝试从其他位置提取文本
                else:
                    logger.warning(f"响应格式未知: {json.dumps(result, ensure_ascii=False)[:100]}...")
                    # 尝试其他可能的响应格式
                    if "response" in result:
                        return result["response"]
                    elif "content" in result:
                        return result["content"]
                    elif "text" in result:
                        return result["text"]
                    else:
                        raise Exception("无法解析API响应格式，请检查API文档")
            except Exception as e:
                logger.error(f"解析API响应异常: {str(e)}")
                raise Exception(f"解析API响应异常: {str(e)}")
