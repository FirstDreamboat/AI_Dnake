# 狄耐克AI驱动嵌入式测试用例自动生成平台 - 后端镜像
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 系统依赖（Pillow 需要；fonts-noto-cjk 供需求体检 PDF 中文渲染）
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 清华 PyPI 镜像（服务器直连官方源易超时）
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# 数据目录（SQLite / 上传文件 / 向量库）
RUN mkdir -p /app/data /app/uploads
VOLUME ["/app/data", "/app/uploads"]

EXPOSE 8000

# 生产模式：关闭 reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
