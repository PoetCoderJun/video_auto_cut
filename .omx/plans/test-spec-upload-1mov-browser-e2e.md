# Test Spec — upload-1mov-browser-e2e

## Primary E2E Scenario
1. 启动本地 Web MVP。
2. 在浏览器中注册/登录可用账号。
3. 上传 `test_data/raw/1.MOV`。
4. 等待任务进入 `TEST_READY`，确认字幕/章节。
5. 进入导出页并执行浏览器导出。
6. 记录导出结果、下载文件名与本地保存位置。

## Regression Checks
- `cd web_frontend && npx tsc --noEmit`
- `cd web_frontend && npm run build`
- 必要时运行与修复点直接相关的后端测试。

## Evidence to Capture
- 本地服务启动命令与关键日志。
- 浏览器自动化日志 / 错误堆栈。
- 最终作业状态、导出文件路径/文件名、失败时的精确报错。
