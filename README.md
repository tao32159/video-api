# Video Download API

基于 yt-dlp 的视频下载 API 服务，支持 YouTube、B站、TikTok 等多平台。

## 功能

- ✅ 视频下载（MP4）
- ✅ 音频提取（MP3）
- ✅ 多平台支持
- ✅ 异步处理
- ✅ CORS 跨域支持

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/process` | POST | 提交下载任务 |
| `/api/status/{task_id}` | GET | 查询任务状态 |
| `/api/download/{filename}` | GET | 下载文件 |

## 使用示例

```bash
# 1. 提交下载任务
curl -X POST "https://your-api.onrender.com/api/process" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=xxxx", "extract_audio": true, "keep_video": true}'

# 返回: {"task_id": "xxx", "message": "任务已创建", "status_url": "/api/status/xxx"}

# 2. 查询任务状态
curl "https://your-api.onrender.com/api/status/{task_id}"

# 返回:
# {
#   "task_id": "xxx",
#   "status": "completed",
#   "progress": 100,
#   "message": "处理完成！",
#   "files": {
#     "video": "/api/download/video_title_xxx.mp4",
#     "audio": "/api/download/audio_title_xxx.mp3"
#   },
#   "video_info": {...}
# }

# 3. 下载文件
curl -O "https://your-api.onrender.com/api/download/video_title_xxx.mp4"
```

## 部署到 Render

### 步骤 1: 创建 GitHub 仓库

1. 访问 [GitHub](https://github.com) 登录
2. 点击右上角 `+` → `New repository`
3. 仓库名称填 `video-api`
4. 选择 **Public**（Render 免费版需要公开仓库）
5. 点击 `Create repository`

### 步骤 2: 推送代码

在项目目录执行：

```bash
cd video-api-deploy
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/video-api.git
git push -u origin main
```

### 步骤 3: 部署到 Render

1. 访问 [Render](https://render.com) 并登录
2. 点击 `New` → `Blueprint`
3. 连接你的 GitHub 仓库
4. 选择 `Public Git repository`
5. 填入仓库地址: `https://github.com/YOUR_USERNAME/video-api`
6. 点击 `Apply`

Render 会自动检测 Python 项目并部署。

### 步骤 4: 配置环境变量（可选）

如果需要代理，在 Render 控制台设置：
- `VIDEO_PROXY_URL`: 代理地址

## Render 免费版限制

- 空闲 15 分钟后自动休眠
- 每月 750 小时额度
- 下载大文件可能超时

## 本地运行

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
```

访问 http://localhost:8001/docs 查看 API 文档。
