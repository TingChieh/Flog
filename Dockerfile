FROM python:slim

# 设置工作目录
WORKDIR /app

# 复制并安装依赖
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn pymysql cryptography

# 复制应用代码
COPY app app
COPY migrations migrations
COPY flog.py config.py boot.sh ./

# 确保 boot.sh 可执行
RUN chmod a+x boot.sh

# 设置环境变量和编译 Flask 翻译文件
ENV FLASK_APP=flog.py
RUN flask translate compile

# 设置数据库连接环境变量 (根据你的系统情况调整 host.docker.internal 或宿主机 IP 地址)
# ENV DATABASE_URL=mysql+pymysql://root:ogihana77**@host.docker.internal/flask
# 如果在 Linux 上使用宿主机 IP 地址，比如 172.17.0.1
# ENV DATABASE_URL=mysql+pymysql://root:ogihana77**@172.17.0.1/flask

# 暴露 Flask 的默认端口
EXPOSE 5000

# 启动容器时运行 boot.sh 脚本
ENTRYPOINT ["./boot.sh"]
