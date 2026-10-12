"""兼容原文件名：运行本文件同样可以启动系统。"""

from app import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
