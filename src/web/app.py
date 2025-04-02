import sys
import os
import gradio as gr
import json
import traceback

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.detector import FakeNewsDetector
from config import WEB_CONFIG, GOOGLE_SEARCH_CONFIG
from src.rules.detection_rules import DETECTION_RULES, KNOWLEDGE_CUTOFF_DATE


def create_app(enable_web_search=False):
    """创建Gradio Web应用"""

    detector = FakeNewsDetector(
        enable_web_search=enable_web_search,
        google_api_key=GOOGLE_SEARCH_CONFIG["API_KEY"],
        search_engine_id=GOOGLE_SEARCH_CONFIG["SEARCH_ENGINE_ID"]
    )

    def detect_news(title, content, url=""):
        """执行新闻检测
        
        Args:
            title: 新闻标题
            content: 新闻内容
            url: 新闻来源URL
            
        Returns:
            规则分析结果和综合结论
        """
        try:
            # 构造新闻数据
            news_data = {
                "title": title,
                "content": content
            }
            
            if url:
                news_data["url"] = url
                
            # 执行检测
            result = detector.detect(news_data)
            
            # 提取规则分析结果
            rules_output = "## 规则分析\n\n"
            
            for i, rule in enumerate(DETECTION_RULES):
                rule_id = rule["id"]
                rule_name = rule["name"]
                
                if rule_id in result["rules"]:
                    rule_result = result["rules"][rule_id]
                    verdict = rule_result["verdict"]
                    reason = rule_result["reason"]
                    
                    # 格式化显示
                    if verdict == "符合":
                        icon = "🔴"  # 风险标记
                    elif verdict == "无法验证":
                        icon = "⚠️"  # 无法验证标记
                    else:
                        icon = "✅"  # 安全标记
                        
                    rules_output += f"{icon} **{rule_name}**\n{reason}\n\n"
            
            # 提取综合结论
            risk_level = result["risk_level"]
            risk_percentage = result["conclusion"]["risk_percentage"]
            explanation = result["conclusion"]["explanation"]
            
            # 添加知识截止日期信息
            knowledge_cutoff_info = f"\n\n**模型知识截止日期**: {result.get('knowledge_cutoff_date', KNOWLEDGE_CUTOFF_DATE)}"
            
            # 格式化结论
            if risk_level == "高风险":
                level_icon = "⚠️"
            elif risk_level == "中等风险":
                level_icon = "⚠️"
            else:
                level_icon = "✅"
                
            # 简化知识截止日期警告信息
            cutoff_warning = ""
            if "metadata" in result and result["metadata"].get("knowledge_cutoff_issue", False):
                cutoff_warning = "\n\n⚠️ **注意**: 此新闻可能发生在模型知识截止日期之后"
                
            conclusion = f"""## 综合结论 {level_icon}

**风险评估**: {risk_level} ({risk_percentage}%){cutoff_warning}

{explanation}{knowledge_cutoff_info}
"""

            # 添加网络验证结果（如果有）
            web_validation = ""
            if "web_validation" in result:
                web_result = result["web_validation"]
                web_validation = f"## 网络搜索验证\n\n"
                
                # 可信源数量
                trusted_count = web_result["validation_results"]["trusted_sources_count"]
                web_validation += f"- 可信来源数: {trusted_count}\n"
                
                # 一致性得分
                consistency = web_result["validation_results"]["consistency_score"]
                web_validation += f"- 内容一致性: {consistency}%\n"
                
                # 来源列表
                sources = web_result["validation_results"]["sources"]
                if sources:
                    web_validation += "- 参考来源:\n"
                    for source in sources:
                        trust_marker = "✓" if source["is_trusted"] else "⚠️"
                        domain = source["domain"]
                        title = source.get("title", "")
                        web_validation += f"  {trust_marker} {domain}"
                        if title:
                            web_validation += f" - {title}"
                        web_validation += "\n"
                
                # 结论
                web_validation += f"\n**验证结论:** {web_result['explanation']}\n"
                
                # 风险调整
                adjustment = web_result["risk_adjustment"]
                if adjustment != 0:
                    direction = "降低" if adjustment < 0 else "提高"
                    web_validation += f"（风险评估{direction}了{abs(adjustment)}%）"
            elif "metadata" in result and result["metadata"].get("knowledge_cutoff_issue", False) and not enable_web_search:
                # 如果存在知识截止日期问题但未启用网络搜索，提供详细解释
                web_validation = f"""## 知识截止日期问题说明

此新闻描述的事件可能发生在模型知识截止日期（{KNOWLEDGE_CUTOFF_DATE}）之后，模型无法验证此类事件的真实性。

**建议启用网络搜索验证功能以获取更准确的结果。**

启用方法：重新运行应用时添加 `--web-search` 参数，或在配置文件中设置 `ENABLE_WEB_SEARCH=true`。
"""

            return rules_output, conclusion, web_validation
        except Exception as e:
            error_tb = traceback.format_exc()
            print(f"处理异常: {str(e)}\n{error_tb}")
            
            # 构建用户友好的错误信息
            error_detail = f"处理出错: {str(e)}"
            
            # 添加一些常见错误的特定处理
            if "API调用异常" in str(e):
                error_detail += "\n\n可能的原因:\n1. API密钥无效或已过期\n2. API调用额度已用完\n3. 网络连接问题"
                error_detail += "\n\n请检查您的API配置并尝试重新运行。"
            elif "无法解析API响应" in str(e):
                error_detail += "\n\n可能的原因:\n1. API响应格式发生变化\n2. 您使用的模型与配置不符"
                error_detail += "\n\n请确认您使用的是通义千问API且配置正确。"
            
            return error_detail, "无法完成分析", ""

    # 设计UI界面
    with gr.Blocks(title=WEB_CONFIG["TITLE"], theme=WEB_CONFIG["THEME"]) as app:
        gr.Markdown(f"""
        # {WEB_CONFIG["TITLE"]}
        
        {WEB_CONFIG["DESCRIPTION"]}
        
        本系统基于以下6条规则检测虚假新闻：
        1. 域名可信度检查
        2. 标题情绪化检查
        3. 语法错误检查
        4. 常识合理性检查
        5. 政治偏向性检查
        6. 信息一致性检查
        
        📅 模型知识截止日期: {KNOWLEDGE_CUTOFF_DATE}
        """)

        if enable_web_search:
            gr.Markdown("✓ 已启用网络搜索验证功能，可自动验证时效性新闻")
        else:
            gr.Markdown("⚠️ 未启用网络搜索验证功能。对于{KNOWLEDGE_CUTOFF_DATE}之后事件的新闻，分析结果可能不准确")

        with gr.Row():
            with gr.Column():
                title_input = gr.Textbox(
                    label="新闻标题",
                    placeholder="请输入新闻标题"
                )
                
                content_input = gr.Textbox(
                    label="新闻内容",
                    placeholder="请输入新闻正文内容",
                    lines=10
                )
                
                url_input = gr.Textbox(
                    label="新闻来源URL (可选)",
                    placeholder="例如: https://example.com/news"
                )
                
                detect_button = gr.Button("开始检测", variant="primary")
                
            with gr.Column():
                rules_output = gr.Markdown(label="规则分析结果")
                conclusion_output = gr.Markdown(label="综合结论")
                web_validation_output = gr.Markdown(label="网络验证结果")

        # 添加示例
        gr.Examples(
            [
                ["地震救援狗在废墟中救出15人", "昨日，一只搜救犬在地震废墟中成功找到并救出了15名被困人员，创下了搜救犬救援记录...", ""],
                ["科学家发现喝咖啡能预防癌症", "近日，一项新研究表明，每天喝3杯咖啡可以将癌症风险降低80%，这一发现震惊了医学界...", "health.example.org"],
                ["2024年世界经济论坛在达沃斯开幕", "2024年1月15日，第54届世界经济论坛年会在瑞士达沃斯开幕。来自130多个国家的2800多名领导人、企业家和专家齐聚一堂，共同讨论全球经济形势和未来发展方向...", ""],
            ],
            [title_input, content_input, url_input],
            "点击加载示例"
        )
        
        # 设置点击事件
        detect_button.click(
            fn=detect_news,
            inputs=[title_input, content_input, url_input],
            outputs=[rules_output, conclusion_output, web_validation_output]
        )

    return app


def launch_app(enable_web_search=False, port=None):
    """启动Web应用
    
    Args:
        enable_web_search: 是否启用网络搜索验证
        port: 服务端口，如果为None则使用配置中的端口
    """
    app = create_app(enable_web_search)
    # 如果提供了自定义端口，则使用它，否则使用配置中的默认端口
    server_port = port if port is not None else WEB_CONFIG["PORT"]
    
    # 尝试启动应用，如果端口被占用则尝试其他端口
    try:
        app.launch(server_port=server_port)
    except OSError as e:
        if "address already in use" in str(e).lower():
            print(f"端口 {server_port} 已被占用，尝试使用其他端口...")
            for alt_port in range(7865, 7880):
                if alt_port == server_port:
                    continue
                try:
                    print(f"尝试端口 {alt_port}...")
                    app.launch(server_port=alt_port)
                    break
                except OSError:
                    continue
            else:
                print("无法找到可用端口，请手动指定一个未被占用的端口")
                print("例如: python main.py --web --port 8000")
        else:
            raise

if __name__ == "__main__":
    launch_app()

