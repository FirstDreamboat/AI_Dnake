# 狄耐克AI驱动嵌入式测试用例自动生成平台 - 后端服务入口
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["."],
    )
