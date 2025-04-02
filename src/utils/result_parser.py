import re
import logging
from typing import Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ResultParser:
    """解析大模型返回结果"""

    @staticmethod
    def parse_model_response(response: str) -> Dict[str, Any]:
        """解析模型响应，提取结构化结果

        Args:
            response: 大模型的回复文本

        Returns:
            结构化的分析结果
        """
        result = {
            "rules": {},
            "conclusion": {
                "risk_percentage": 0,
                "explanation": ""
            },
            "metadata": {
                "knowledge_cutoff_issue": False,  # 标记是否存在知识截止日期问题
                "unverifiable_rules": []  # 存储无法验证的规则ID
            }
        }

        # 记录原始响应以便调试
        logger.info(f"解析模型响应: {response[:200]}...")

        # 解析每条规则结果
        for i in range(1, 7):
            rule_pattern = rf"规则{i}:\s*\[([^\]]+)\]\s*-\s*(.+?)(?=规则|综合|$)"
            rule_match = re.search(rule_pattern, response, re.DOTALL)

            if rule_match:
                verdict = rule_match.group(1).strip()
                reason = rule_match.group(2).strip()
                
                logger.info(f"规则{i}原始判断: {verdict}")

                # 检查是否为"无法验证"
                if "无法验证" in verdict:
                    standardized_verdict = "无法验证"
                    result["metadata"]["unverifiable_rules"].append(f"rule{i}")
                    
                    # 检查是否因为知识截止日期问题
                    if any(keyword in reason.lower() for keyword in ["知识库截止", "知识截止", "截止日期", "2023年", "未来事件"]):
                        result["metadata"]["knowledge_cutoff_issue"] = True
                        logger.info(f"规则{i}因知识截止日期而无法验证")
                # 统一表示方式：当判断包含关键词时表示有风险
                elif verdict.lower() in ["符合", "是", "存在", "有"]:
                    standardized_verdict = "符合"  # 符合表示有风险
                else:
                    standardized_verdict = "不符合"  # 不符合表示无风险
                
                logger.info(f"规则{i}标准化判断: {standardized_verdict}")

                result["rules"][f"rule{i}"] = {
                    "verdict": standardized_verdict,
                    "reason": reason
                }
            else:
                # 如果匹配失败，设置默认值
                logger.warning(f"规则{i}匹配失败")
                result["rules"][f"rule{i}"] = {
                    "verdict": "未知",
                    "reason": "模型未给出明确结论"
                }

        # 检查响应中是否明确提到知识截止日期问题
        cutoff_pattern = r"(知识[库]?截止|截止日期|无法获取.*?之后的信息)"
        if re.search(cutoff_pattern, response, re.IGNORECASE):
            result["metadata"]["knowledge_cutoff_issue"] = True
            logger.info("检测到知识截止日期问题")

        # 解析综合结论
        conclusion_pattern = r"综合结论:\s*\[?(\d+)%?\]?\s*[可能性为]*虚假新闻\s*-\s*(.+)"
        conclusion_match = re.search(conclusion_pattern, response, re.DOTALL)

        if conclusion_match:
            try:
                risk_percentage = int(conclusion_match.group(1))
                explanation = conclusion_match.group(2).strip()
                logger.info(f"找到风险百分比: {risk_percentage}%")
                result["conclusion"]["risk_percentage"] = risk_percentage
                result["conclusion"]["explanation"] = explanation
            except (ValueError, IndexError) as e:
                logger.error(f"解析风险百分比失败: {e}")
                result["conclusion"]["explanation"] = "无法解析风险百分比，请查看原始响应"
        else:
            logger.warning("未找到风险百分比，从规则结果推断")
            # 如果没有找到明确的百分比，尝试从规则结果推断
            risk_score = 0
            risk_rules_count = 0
            valid_rules_count = 0

            for rule_key, rule_data in result["rules"].items():
                # 只计算有明确判断的规则
                if rule_data["verdict"] != "无法验证" and rule_data["verdict"] != "未知":
                    valid_rules_count += 1
                    if rule_data["verdict"] == "符合":
                        risk_rules_count += 1

            # 根据符合规则数量估算风险
            if valid_rules_count > 0:
                # 根据有效规则计算风险百分比，确保100是最大值
                risk_score = min(100, int((risk_rules_count / valid_rules_count) * 100))
            
            logger.info(f"推断风险百分比: {risk_score}% (基于{risk_rules_count}/{valid_rules_count}条有效风险规则)")
            result["conclusion"]["risk_percentage"] = risk_score
            result["conclusion"]["explanation"] = f"基于{risk_rules_count}/{valid_rules_count}条有效风险规则推断"

        # 处理知识截止日期问题导致的"无法验证"情况
        if result["metadata"]["knowledge_cutoff_issue"]:
            # 在结论中添加知识截止日期问题说明
            result["conclusion"]["explanation"] += "\n\n注意：部分规则因超出模型知识截止日期而无法验证，建议通过网络搜索获取最新信息"
            
            # 将"无法验证"标记为需要网络验证
            result["requires_web_validation"] = True
            
            logger.info("因知识截止日期问题，标记为需要网络验证")

        # 添加原始响应以便参考
        result["raw_response"] = response

        return result
