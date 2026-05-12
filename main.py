"""AI Image Detector 入口

用法:
  uv run python -m ai_image_detector serve          # 启动 Web 界面
  uv run python -m ai_image_detector check image.png # 检测图片
"""
from ai_image_detector.cli import main

if __name__ == "__main__":
    main()
