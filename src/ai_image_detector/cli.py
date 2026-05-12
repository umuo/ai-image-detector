"""
CLI 入口 — 支持命令行检测和启动 Web 服务
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="AI Image Detector — 多维度 AI 生成图片检测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  ai-detect check image.png              检测单张图片
  ai-detect check ./photos/ --json       批量检测并输出 JSON
  ai-detect serve                        启动 Web 界面
  ai-detect serve --port 9000            指定端口启动
  ai-detect serve --host 127.0.0.1       仅允许本机访问
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # check 子命令
    check_p = sub.add_parser("check", help="检测图片是否为 AI 生成")
    check_p.add_argument("path", help="图片文件或包含图片的目录")
    check_p.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # serve 子命令
    serve_p = sub.add_parser("serve", help="启动 Web 检测界面")
    serve_p.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认 0.0.0.0)")
    serve_p.add_argument("--port", type=int, default=8899, help="端口 (默认 8899)")

    args = parser.parse_args()

    if args.command == "check":
        _cmd_check(args)
    elif args.command == "serve":
        _cmd_serve(args)
    else:
        parser.print_help()


def _cmd_check(args):
    from .engine import DetectionEngine

    engine = DetectionEngine()
    extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
    path = args.path

    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, f)
            for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in extensions
        )
    elif os.path.isfile(path):
        files = [path]
    else:
        print(f"错误: 路径不存在 — {path}", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("未找到图片文件", file=sys.stderr)
        sys.exit(1)

    results = []
    for fpath in files:
        report = engine.detect(fpath)
        if args.json:
            results.append({
                "file": fpath,
                "is_ai": report.is_ai_generated,
                "confidence": report.confidence,
                "verdict": report.verdict,
                "risk_level": report.risk_level,
                "scores": {
                    "metadata": report.metadata_score,
                    "spectrum": report.spectrum_score,
                    "statistical": report.statistical_score,
                },
                "time_ms": round(report.analysis_time_ms, 1),
            })
        else:
            icon = "🤖" if report.is_ai_generated else "✅"
            conf_pct = f"{report.confidence * 100:.1f}%"
            time_s = f"{report.analysis_time_ms:.0f}ms"
            name = os.path.basename(fpath)
            print(f"{icon} {name:<40s} {report.verdict}  "
                  f"(置信度={conf_pct}, 耗时={time_s})")

            # 打印关键发现
            for f in report.key_findings:
                print(f"   {f['icon']} {f['title']}: {f['detail']}")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))


def _cmd_serve(args):
    import uvicorn
    print(f"\n🚀 AI Image Detector 启动中…")
    print(f"   地址: http://{args.host}:{args.port}")
    print(f"   按 Ctrl+C 停止\n")
    uvicorn.run(
        "ai_image_detector.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
