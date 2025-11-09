# .github/workflows/renew.yml
# 运行 GHA 移植版 domains.py 的工作流
# (已启用 Xvfb 以支持 Headless=False)
# (最终修正: 为 DP_PASSWORD 添加单引号以修复 '!' 字符转义)

name: DigitalPlat 域名自动续期 (domains.py)

on:
  workflow_dispatch: # 允许手动触发
  schedule:
    # 每天的 18:00 (UTC) 执行一次
    - cron: '0 18 * * *'

jobs:
  renew-domains:
    runs-on: ubuntu-latest
    steps:
      - name: 检出代码
        uses: actions/checkout@v4

      - name: 设置 Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 安装 Python 依赖
        run: |
          python -m pip install --upgrade pip
          pip install playwright # 脚本只依赖 playwright

      - name: 安装 Xvfb (虚拟显示服务)
        run: sudo apt-get update && sudo apt-get install -y xvfb

      - name: 安装 Playwright Chromium 浏览器
        run: playwright install chromium

      - name: 运行域名续期脚本 (在虚拟显示中)
        # 确保这里的 python domains.py 和您的文件名一致
        # (如果您的脚本名叫 renew.py, 请把下面改成 "xvfb-run python renew.py")
        run: xvfb-run python domains.py 
        env:
          # 注入所有 Secrets
          DP_EMAIL: ${{ secrets.DP_EMAIL }}
          # vvvvvvvvvvvv 这是唯一修改的行 vvvvvvvvvvvv
          DP_PASSWORD: '${{ secrets.DP_PASSWORD }}' # <-- 关键修正: 添加单引号
          # ^^^^^^^^^^^^^^ 这是唯一修改的行 ^^^^^^^^^^^^^^
          TG_TOKEN: ${{ secrets.TG_TOKEN }}     # (选填)
          TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}   # (选填)
          PROXY_URL: ${{ secrets.PROXY_URL }}     # (选填, 但强烈推荐)
