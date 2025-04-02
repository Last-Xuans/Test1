import argparse
import json
import sys
import os
from dotenv import load_dotenv

# 强制加载.env文件的配置，覆盖系统环境变量
load_dotenv(override=True)

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.detector import FakeNewsDetector
from src.web.app import launch_app
from config import GOOGLE_SEARCH_CONFIG, WEB_CONFIG


def run_tests(test_file_path, enable_web_search=False):
    """运行测试用例

    Args:
        test_file_path: 测试用例文件路径
        enable_web_search: 是否启用网络搜索验证
    """
    try:
        with open(test_file_path, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
    except Exception as e:
        print(f"读取测试用例失败: {e}")
        return

    # 创建检测器，根据配置决定是否启用网络搜索
    detector = FakeNewsDetector(
        enable_web_search=enable_web_search,
        google_api_key=GOOGLE_SEARCH_CONFIG["API_KEY"],
        search_engine_id=GOOGLE_SEARCH_CONFIG["SEARCH_ENGINE_ID"]
    )

    print(f"开始运行{len(test_cases)}个测试用例..." + 
          (f" (启用网络搜索验证)" if enable_web_search else ""))

    for i, test_case in enumerate(test_cases):
        print(f"\n====== 测试用例 {i + 1} ======")
        print(f"标题: {test_case['title']}")

        try:
            result = detector.detect(test_case)

            # 打印结果
            print(f"检测结果: {result['risk_level']} ({result['conclusion']['risk_percentage']}%)")
            if enable_web_search and 'web_validation' in result:
                print(f"网络验证: {result['web_validation']['explanation']}")
            print(f"预期结果: {test_case['expected_result']['risk_level']}")

            # 简单验证
            if result['risk_level'] == test_case['expected_result']['risk_level']:
                print("✅ 测试通过!")
            else:
                print("❌ 测试失败!")
        except Exception as e:
            print(f"测试出错: {e}")

    print("\n测试完成!")


def main():
    """主入口函数"""
    # 打印当前API配置，便于调试
    from config import LLM_API_CONFIG
    masked_api_key = LLM_API_CONFIG["API_KEY"][:4] + "****" + LLM_API_CONFIG["API_KEY"][-4:] if len(LLM_API_CONFIG["API_KEY"]) > 8 else "****"
    print(f"当前API配置: URL={LLM_API_CONFIG['API_URL']}, MODEL={LLM_API_CONFIG['MODEL']}, KEY={masked_api_key}")
    
    parser = argparse.ArgumentParser(description="虚假新闻检测系统")
    parser.add_argument('--web', action='store_true', help="启动Web界面")
    parser.add_argument('--test', action='store_true', help="运行测试用例")
    parser.add_argument('--test-file', default='data/test_cases.json', help="测试文件路径")
    parser.add_argument('--web-search', action='store_true', help="启用网络搜索验证")
    parser.add_argument('--port', type=int, default=WEB_CONFIG["PORT"], help="Web服务端口号")

    args = parser.parse_args()

    # 根据命令行参数覆盖配置
    enable_web_search = args.web_search or GOOGLE_SEARCH_CONFIG["ENABLED"]

    if args.test:
        run_tests(args.test_file, enable_web_search=enable_web_search)
    elif args.web:
        launch_app(enable_web_search=enable_web_search, port=args.port)
    else:
        print("请指定运行模式: --web 启动Web界面 或 --test 运行测试")
        print("可选参数: --web-search 启用网络搜索验证功能, --port 指定Web端口")


if __name__ == "__main__":
    main()
