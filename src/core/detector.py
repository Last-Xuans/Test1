import sys
import os
import logging
from typing import Dict, Any, List, Tuple

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.models.llm_connector import LLMConnector
from src.rules.detection_rules import get_combined_prompt, DETECTION_RULES, KNOWLEDGE_CUTOFF_DATE
from src.utils.text_analyzer import TextAnalyzer
from src.utils.result_parser import ResultParser
from src.utils.web_search import WebSearchValidator
from config import THRESHOLDS

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FakeNewsDetector:
    """虚假新闻检测核心类"""

    def __init__(self, enable_web_search: bool = False, google_api_key: str = None, search_engine_id: str = None):
        """初始化检测器
        
        Args:
            enable_web_search: 是否启用网络搜索验证
            google_api_key: Google搜索API密钥
            search_engine_id: 自定义搜索引擎ID
        """
        self.llm = LLMConnector()
        self.text_analyzer = TextAnalyzer()
        self.result_parser = ResultParser()
        self.enable_web_search = enable_web_search
        
        # 如果启用网络搜索，初始化验证器
        if enable_web_search:
            self.web_validator = WebSearchValidator(
                api_key=google_api_key,
                search_engine_id=search_engine_id
            )

    def preprocess_news(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """预处理新闻数据

        Args:
            news_data: 原始新闻数据

        Returns:
            预处理后的新闻数据
        """
        processed_data = news_data.copy()

        # 提取域名（如果有URL）
        if "url" in news_data and news_data["url"]:
            processed_data["domain"] = self.text_analyzer.extract_domain(news_data["url"])
        elif "domain" not in news_data or not news_data["domain"]:
            processed_data["domain"] = "未知来源"

        return processed_data
    
    def _adjust_rules_weights(self, result: Dict[str, Any]) -> Dict[str, float]:
        """根据结果动态调整规则权重
        
        当某些规则无法验证时，调整其他规则的权重
        
        Args:
            result: 解析后的结果
            
        Returns:
            调整后的规则权重
        """
        weights = {rule["id"]: rule["weight"] for rule in DETECTION_RULES}
        total_weight = sum(weights.values())
        
        # 检查是否有无法验证的规则
        if "metadata" in result and result["metadata"]["unverifiable_rules"]:
            unverifiable_rules = result["metadata"]["unverifiable_rules"]
            logger.info(f"发现无法验证的规则: {unverifiable_rules}")
            
            # 计算无法验证规则的总权重
            unverifiable_weight = sum(weights[rule_id] for rule_id in unverifiable_rules)
            
            # 如果有无法验证的规则，将其权重设为0
            for rule_id in unverifiable_rules:
                weights[rule_id] = 0
            
            # 重新计算剩余有效规则的总权重
            valid_weight = total_weight - unverifiable_weight
            
            if valid_weight > 0:
                # 按比例调整剩余规则的权重，使总权重仍为1
                scale_factor = total_weight / valid_weight
                for rule_id in weights:
                    if rule_id not in unverifiable_rules:
                        weights[rule_id] = weights[rule_id] * scale_factor
        
        return weights

    def detect(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行虚假新闻检测

        Args:
            news_data: 新闻数据，必须包含title和content字段

        Returns:
            检测结果
        """
        # 参数校验
        if not news_data.get("title") or not news_data.get("content"):
            raise ValueError("新闻数据必须包含标题(title)和内容(content)")

        # 预处理数据
        processed_data = self.preprocess_news(news_data)

        # 构建提示词
        prompt = get_combined_prompt(processed_data)

        # 调用大模型
        response = self.llm.get_response(prompt)

        # 解析结果
        result = self.result_parser.parse_model_response(response)
        
        # 添加知识截止日期信息
        result["knowledge_cutoff_date"] = KNOWLEDGE_CUTOFF_DATE
        
        # 动态调整规则权重
        adjusted_weights = self._adjust_rules_weights(result)
        
        # 根据调整后的权重重新计算风险百分比
        self._recalculate_risk_with_weights(result, adjusted_weights)

        # 添加风险级别评估
        risk_percentage = result["conclusion"]["risk_percentage"]
        
        # 检查是否需要强制进行网络验证
        should_validate = False
        forced_validation = False
        
        # 默认情况下，只对中高风险新闻进行验证
        if self.enable_web_search and risk_percentage >= THRESHOLDS["LOW_RISK_THRESHOLD"]:
            should_validate = True
        
        # 如果有知识截止日期问题，强制进行网络验证
        if "requires_web_validation" in result and result["requires_web_validation"]:
            should_validate = True
            forced_validation = True
            logger.info("因知识截止日期问题，强制进行网络验证")
        
        # 执行网络搜索验证
        web_search_result = None
        if self.enable_web_search and should_validate:
            web_search_result = self.validate_with_web_search(processed_data, forced_by_cutoff=forced_validation)
            
            # 根据网络搜索结果调整风险评估
            if web_search_result:
                # 调整风险百分比
                risk_adjustment = web_search_result["risk_adjustment"]
                adjusted_risk = risk_percentage + risk_adjustment
                
                # 确保风险百分比在0-100范围内
                adjusted_risk = max(0, min(100, adjusted_risk))
                
                # 更新风险评估
                result["conclusion"]["risk_percentage"] = adjusted_risk
                result["conclusion"]["explanation"] += f"\n\n网络验证调整: {web_search_result['explanation']}"
                
                # 保存网络验证结果
                result["web_validation"] = web_search_result
                
                # 重新计算风险等级
                risk_percentage = adjusted_risk
        
        # 设置最终风险等级
        if risk_percentage >= THRESHOLDS["HIGH_RISK_THRESHOLD"]:
            result["risk_level"] = "高风险"
        elif risk_percentage <= THRESHOLDS["LOW_RISK_THRESHOLD"]:
            result["risk_level"] = "低风险"
        else:
            result["risk_level"] = "中等风险"
            
        # 添加网络搜索置信度，用于前端展示
        if "metadata" in result and result["metadata"]["knowledge_cutoff_issue"] and not self.enable_web_search:
            result["confidence"] = "低 (需要网络验证)"
            result["confidence_explanation"] = f"此新闻描述的事件可能发生在模型知识截止日期({KNOWLEDGE_CUTOFF_DATE})之后，需要网络验证以提高可信度"
        elif web_search_result and "validation_results" in web_search_result:
            if web_search_result["validation_results"]["consistency_score"] >= 70:
                result["confidence"] = "高"
            elif web_search_result["validation_results"]["consistency_score"] >= 40:
                result["confidence"] = "中"
            else:
                result["confidence"] = "低"
        else:
            result["confidence"] = "中"

        return result
    
    def _recalculate_risk_with_weights(self, result: Dict[str, Any], weights: Dict[str, float]) -> None:
        """根据调整后的权重重新计算风险百分比
        
        Args:
            result: 解析后的结果
            weights: 调整后的规则权重
        """
        weighted_score = 0
        total_weight = 0
        
        for rule_id, weight in weights.items():
            if weight > 0 and rule_id in result["rules"]:
                rule_data = result["rules"][rule_id]
                # 只考虑有明确判断的规则
                if rule_data["verdict"] == "符合":
                    weighted_score += weight * 100  # 风险度100%
                elif rule_data["verdict"] == "不符合":
                    weighted_score += weight * 0    # 风险度0%
                # 忽略"无法验证"的规则
                if rule_data["verdict"] != "无法验证":
                    total_weight += weight
        
        # 计算加权平均风险百分比
        if total_weight > 0:
            risk_percentage = weighted_score / total_weight
            logger.info(f"使用调整后的权重重新计算风险百分比: {risk_percentage:.2f}%")
            result["conclusion"]["risk_percentage"] = round(risk_percentage)
        
    def validate_with_web_search(self, news_data: Dict[str, Any], forced_by_cutoff: bool = False) -> Dict[str, Any]:
        """使用网络搜索验证新闻真实性
        
        Args:
            news_data: 预处理后的新闻数据
            forced_by_cutoff: 是否因知识截止日期问题强制验证
            
        Returns:
            验证结果
        """
        if not self.enable_web_search:
            return None
        
        # 执行网络验证
        web_result = self.web_validator.validate_news(news_data)
        
        # 如果是因知识截止日期问题强制验证，调整风险评分幅度
        if forced_by_cutoff and web_result:
            # 根据验证结果的可信度分级调整风险值
            consistency_score = web_result["validation_results"]["consistency_score"]
            
            # 降低风险调整的影响幅度
            if consistency_score >= 70:
                # 高可信度证实，大幅降低风险
                web_result["risk_adjustment"] = max(-15, web_result["risk_adjustment"] / 2)
                web_result["explanation"] += " (因超出知识截止日期，网络验证结果更具参考价值)"
            elif consistency_score <= 20:
                # 低可信度反驳，适度提高风险
                web_result["risk_adjustment"] = min(15, web_result["risk_adjustment"] / 2)
                web_result["explanation"] += " (因超出知识截止日期，网络验证结果更具参考价值)"
            else:
                # 一般可信度，小幅调整
                web_result["risk_adjustment"] = web_result["risk_adjustment"] / 3
                web_result["explanation"] += " (验证结果可信度一般)"
        else:
            # 非强制验证情况下，也降低风险调整幅度
            if web_result:
                consistency_score = web_result["validation_results"]["consistency_score"]
                original_adjustment = web_result["risk_adjustment"]
                
                # 分级调整风险值
                if consistency_score >= 70:
                    # 证据充分，但最多调整±15%
                    web_result["risk_adjustment"] = max(-15, min(15, original_adjustment))
                elif consistency_score >= 40:
                    # 证据中等，但最多调整±10%
                    web_result["risk_adjustment"] = max(-10, min(10, original_adjustment))
                else:
                    # 证据较弱，但最多调整±5%
                    web_result["risk_adjustment"] = max(-5, min(5, original_adjustment))
        
        return web_result
