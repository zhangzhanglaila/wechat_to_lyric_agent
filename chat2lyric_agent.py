"""
v12.x GenWriter Agent - 歌词/诗歌生成引擎
==============================================================
统一入口：generate(content, mode, style, constraints)

用法：
    python chat2lyric_agent.py --input chat.txt --mode lyrics --style douyin_sad
    python chat2lyric_agent.py --input keywords.txt --mode poem --style modern
"""

import os
import argparse
import json
from dotenv import load_dotenv

load_dotenv()

# 禁用代理
for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(k, None)


def main():
    parser = argparse.ArgumentParser(description="GenWriter Agent - 歌词/诗歌生成引擎")
    parser.add_argument("--input", type=str, required=True, help="输入文件路径")
    parser.add_argument("--mode", type=str, default="lyrics",
                        choices=["lyrics", "poem"], help="生成模式")
    parser.add_argument("--style", type=str, default=None,
                        help="风格: douyin_sad / rap / pop / emo / modern / classical / imagist / diary")
    parser.add_argument("--candidates", type=int, default=3, help="候选数量")
    parser.add_argument("--intensity", type=float, default=None, help="情绪强度 0.0-1.0")
    parser.add_argument("--save", type=str, default=None, help="保存路径")
    parser.add_argument("--show-candidates", action="store_true", help="显示所有候选")

    args = parser.parse_args()

    # 读取输入
    with open(args.input, encoding="utf-8") as f:
        content_text = f.read()

    # 解析输入：聊天记录(list) 或 关键词(str)
    try:
        chat_messages = json.loads(content_text)
        if isinstance(chat_messages, list):
            content = chat_messages
        else:
            content = content_text.strip()
    except json.JSONDecodeError:
        content = content_text.strip()

    # 确定模式
    mode = args.mode

    # 构建约束
    constraints = {}
    if args.intensity is not None:
        constraints["intensity"] = args.intensity

    print(f"\n{'='*50}")
    print(f"GenWriter Agent - {mode.upper()} | style={args.style or 'auto'}")
    print(f"{'='*50}\n")

    # 生成
    from agent_os.integration import EnhancedAgentOS
    eos = EnhancedAgentOS()

    result = eos.generate(
        content=content,
        mode=mode,
        style=args.style,
        constraints=constraints,
        num_candidates=args.candidates,
    )

    # 输出
    print(f"【风格】{result.style}")
    print(f"【情绪】{result.emotion} | 强度 {result.emotion_intensity:.1f}")
    print(f"【评分】{result.score:.2f}")
    print()

    if args.show_candidates:
        for i, c in enumerate(result.candidates):
            print(f"--- Candidate {i+1} ---")
            print(c.text)
            print()
        print("="*50)
        print()

    print("【主结果】")
    print("-"*40)
    print(result.text)
    print("-"*40)
    print()

    print(f"【Hook】{result.hook}")
    print()

    # 保存
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(f"# {result.style} | {result.emotion}\n\n")
            f.write(result.text)
            if result.hook:
                f.write(f"\n\n# Hook: {result.hook}\n")
        print(f"✅ 已保存: {args.save}")


if __name__ == "__main__":
    main()
