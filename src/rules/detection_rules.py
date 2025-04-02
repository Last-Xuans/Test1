from typing import List, Dict, Any
import re
from datetime import datetime

# 定义LLM知识截止日期（根据使用的模型进行调整）
KNOWLEDGE_CUTOFF_DATE = "2023年9月"  # 通义千问模型知识截止日期

# 定义新闻检测规则
DETECTION_RULES = [
    {
        "id": "rule1",
        "name": "域名可信度检查",
        "description": "新闻来自一个不知名或需要怀疑的域名URL。",
        "prompt_template": "首先分析新闻来源网站域名'{domain}'的可信度。该域名是否不是知名媒体网站或存在可疑性？如果域名不可信或可疑，请回答[符合]；如果是知名可信媒体网站，请回答[不符合]。",
        "weight": 0.2  # 规则权重
    },
    {
        "id": "rule2",
        "name": "标题情绪化检查",
        "description": "新闻标题中是否包含耸人听闻的引子、挑衅性或情绪化的语言、或夸张的声明，新闻可能是假的。",
        "prompt_template": "分析新闻标题'{title}'中是否包含耸人听闻的词语、挑衅性或情绪化的语言、或夸张的声明？请列出这些词语并解释。",
        "weight": 0.15
    },
    {
        "id": "rule3",
        "name": "语法错误检查",
        "description": "新闻标题是否包含错别字、语法错误、引号使用不当。",
        "prompt_template": "检查新闻标题'{title}'中是否存在错别字、语法错误或引号使用不当的情况？专业媒体很少出现这类错误。",
        "weight": 0.1
    },
    {
        "id": "rule4",
        "name": "常识合理性检查",
        "description": "新闻是否潜在地不合理或与常识相矛盾，或新闻更像八卦而不是事实报道。",
        "prompt_template": "分析新闻内容是否与常识相矛盾或不合理？内容是:\n'{content}'\n如果新闻内容与常识相矛盾或不合理，请回答[符合]；如果新闻内容合理且符合常识，请回答[不符合]。",
        "weight": 0.2
    },
    {
        "id": "rule5",
        "name": "政治偏向性检查",
        "description": "新闻是否偏向于特定的政治观点，旨在影响公众舆论而不是呈现客观信息。",
        "prompt_template": "分析新闻内容是否存在明显的政治偏向性，是否试图影响读者观点而非客观报道？内容是:\n'{content}'",
        "weight": 0.15
    },
    {
        "id": "rule6",
        "name": "信息一致性检查",
        "description": "是否存在其他在线资源包含任何不一致、矛盾或对立的内容。",
        "prompt_template": "根据你的知识库（截止到{cutoff_date}），分析新闻'{title}'是否描述了你知识库截止日期之后的事件？如果是，请标记为[无法验证]。若非如此，该新闻主题是否有其他公开报道？是否存在与该新闻内容矛盾的公开信息？请注意，如果新闻发生在{cutoff_date}之后，应当谨慎评估并依赖网络搜索验证。",
        "weight": 0.2
    }
]


def extract_date_from_content(content: str) -> str:
    """尝试从内容中提取日期

    Args:
        content: 新闻内容

    Returns:
        提取的日期字符串，如果找不到则返回空字符串
    """
    # 匹配常见的日期格式 (年月日)
    date_patterns = [
        r'(20\d{2})[-/年.\s]{1,3}([0-1]?\d)[-/月.\s]{1,3}([0-3]?\d)[日号]?',  # 2023年10月1日，2023-10-1等
        r'([0-1]?\d)[-/月.\s]{1,3}([0-3]?\d)[日号]?[,\s]+?(20\d{2})',  # 10月1日, 2023等
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, content)
        if matches:
            # 返回找到的第一个日期
            match = matches[0]
            if isinstance(match, tuple):
                if len(match) == 3:
                    # 根据模式调整年月日的顺序
                    if pattern.startswith(r'(20\d{2})'):
                        return f"{match[0]}年{match[1]}月{match[2]}日"
                    else:
                        return f"{match[2]}年{match[0]}月{match[1]}日"
            
    return ""


def get_combined_prompt(news_data: Dict[str, Any]) -> str:
    """生成包含所有规则的完整提示词

    Args:
        news_data: 包含新闻信息的字典

    Returns:
        完整的提示词
    """
    # 提取新闻数据
    title = news_data.get("title", "")
    content = news_data.get("content", "")
    domain = news_data.get("domain", "未知来源")
    
    # 尝试从内容中提取日期信息
    news_date = extract_date_from_content(content)
    
    # 构建提示词前言
    prompt = f"""你是一位专业的新闻事实核查专家，请根据以下规则分析这篇新闻的真实性，并按照要求的格式输出结果。

新闻标题: "{title}"
新闻来源: {domain}"""

    # 如果找到日期，添加到提示中
    if news_date:
        prompt += f"\n新闻日期: {news_date}"

    prompt += f"""
新闻内容: 
{content}

请注意：你的知识库截止到{KNOWLEDGE_CUTOFF_DATE}，如果新闻描述的事件明显发生在此日期之后，请在相关规则中标注[无法验证]。

请逐条分析以下规则:
"""

    # 添加每条规则的分析要求
    for i, rule in enumerate(DETECTION_RULES):
        rule_id = rule["id"]
        
        # 对于信息一致性检查规则，添加知识截止日期
        if rule_id == "rule6":
            rule_prompt = rule["prompt_template"].format(
                title=title,
                content=content,
                domain=domain,
                cutoff_date=KNOWLEDGE_CUTOFF_DATE
            )
        else:
            rule_prompt = rule["prompt_template"].format(
                title=title,
                content=content,
                domain=domain
            )
        
        prompt += f"\n规则{i + 1}: {rule['name']}\n{rule_prompt}\n"

    # 添加输出格式要求
    prompt += """
请按以下格式回答:
规则1: [符合/不符合] - <简短说明原因>
规则2: [符合/不符合] - <简短说明原因>
规则3: [符合/不符合] - <简短说明原因>
规则4: [符合/不符合] - <简短说明原因>
规则5: [符合/不符合] - <简短说明原因>
规则6: [符合/不符合/无法验证] - <简短说明原因>

注意：
- [符合]意味着检测到风险，[不符合]意味着未检测到风险
- 规则1：如果域名不可信或可疑，应回答[符合]；如果是知名可信媒体，应回答[不符合]
- 规则2：如果标题含情绪化词语，应回答[符合]；如果不含情绪化词语，应回答[不符合]
- 规则3：如果标题有语法错误，应回答[符合]；如果语法正确，应回答[不符合]
- 规则4：如果内容不合理或违背常识，应回答[符合]；如果合理且符合常识，应回答[不符合]
- 规则5：如果有政治偏向性，应回答[符合]；如果客观中立，应回答[不符合]
- 规则6：如果存在矛盾信息，应回答[符合]；如果无矛盾，应回答[不符合]；如果无法验证，应回答[无法验证]

综合结论: [0-100]% 可能性为虚假新闻 - <简短总结判断依据>

如果新闻描述的事件发生在你的知识库截止日期({KNOWLEDGE_CUTOFF_DATE})之后，请在结论中特别说明这一点，并标注这可能影响你的判断准确性。
"""
    return prompt
