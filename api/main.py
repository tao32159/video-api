import os
import asyncio
import logging
import json
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .video_processor import VideoProcessor

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="视频下载API",
    description="支持YouTube、B站、TikTok等平台的视频下载服务",
    version="1.0.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 目录配置
PROJECT_ROOT = Path(__file__).parent.parent
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# 任务存储
import threading
TASKS_FILE = TEMP_DIR / "tasks.json"
tasks_lock = threading.Lock()

def load_tasks():
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_tasks(tasks_data):
    try:
        with tasks_lock:
            with open(TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存任务状态失败: {e}")

tasks = load_tasks()
processing_urls = set()
active_tasks = {}

# 请求模型
class ProcessVideoRequest(BaseModel):
    url: str
    extract_audio: bool = True
    keep_video: bool = True

class ProcessVideoResponse(BaseModel):
    task_id: str
    message: str
    status_url: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    message: str
    created_at: str
    completed_at: Optional[str] = None
    files: Optional[Dict[str, str]] = None
    video_info: Optional[Dict] = None
    error: Optional[str] = None

def _sanitize_filename(title: str) -> str:
    if not title:
        return "untitled"
    safe = re.sub(r"[^\w\-\s]", "", title)
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    return safe[:80] or "untitled"

@app.get("/")
async def read_root():
    return {
        "service": "视频下载API",
        "version": "1.0.0",
        "endpoints": {
            "process": "POST /api/process",
            "status": "GET /api/status/{task_id}",
            "download": "GET /api/download/{filename}",
            "health": "GET /api/health"
        }
    }

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/process", response_model=ProcessVideoResponse)
async def process_video(request: ProcessVideoRequest):
    try:
        task_id = str(uuid.uuid4())

        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理视频...",
            "created_at": datetime.now().isoformat(),
            "url": request.url,
            "extract_audio": request.extract_audio,
            "keep_video": request.keep_video,
            "files": {},
            "video_info": {},
            "error": None
        }
        save_tasks(tasks)

        task = asyncio.create_task(
            process_video_task(task_id, request.url, request.extract_audio, request.keep_video)
        )
        active_tasks[task_id] = task

        return ProcessVideoResponse(
            task_id=task_id,
            message="任务已创建，正在处理中...",
            status_url=f"/api/status/{task_id}"
        )

    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

async def process_video_task(task_id: str, url: str, extract_audio: bool, keep_video: bool):
    try:
        video_processor = VideoProcessor()
        logger.info(f"任务 {task_id}: 开始处理视频")

        tasks[task_id].update({"status": "processing", "progress": 10, "message": "正在获取视频信息..."})
        save_tasks(tasks)

        video_info = video_processor.get_video_info(url)
        tasks[task_id]["video_info"] = video_info

        tasks[task_id].update({"progress": 20, "message": "正在下载视频..."})
        save_tasks(tasks)

        result_files = await video_processor.download_video_and_audio(
            url, TEMP_DIR, extract_audio=extract_audio, keep_video=keep_video
        )

        # 生成下载链接
        file_links = {}
        short_id = task_id.replace("-", "")[:6]
        safe_title = _sanitize_filename(video_info.get('title', 'video'))

        for file_type, file_path in result_files.items():
            if file_path and Path(file_path).exists():
                filename = Path(file_path).name
                ext = Path(filename).suffix
                new_filename = f"{file_type}_{safe_title}_{short_id}{ext}"
                new_path = TEMP_DIR / new_filename

                try:
                    Path(file_path).rename(new_path)
                    file_links[file_type] = f"/api/download/{new_filename}"
                except Exception as e:
                    logger.warning(f"重命名文件失败: {e}")
                    file_links[file_type] = f"/api/download/{filename}"

        tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "处理完成！",
            "completed_at": datetime.now().isoformat(),
            "files": file_links
        })
        save_tasks(tasks)
        logger.info(f"任务完成: {task_id}")

        processing_urls.discard(url)
        if task_id in active_tasks:
            del active_tasks[task_id]

    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {str(e)}")
        processing_urls.discard(url)
        if task_id in active_tasks:
            del active_tasks[task_id]

        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"处理失败: {str(e)}",
            "completed_at": datetime.now().isoformat()
        })
        save_tasks(tasks)

@app.get("/api/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks[task_id]
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
        created_at=task["created_at"],
        completed_at=task.get("completed_at"),
        files=task.get("files", {}),
        video_info=task.get("video_info", {}),
        error=task.get("error")
    )

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    try:
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="文件名格式无效")

        file_path = TEMP_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        ext = file_path.suffix.lower()
        if ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv']:
            media_type = "video/mp4"
        elif ext in ['.mp3', '.wav', '.m4a', '.aac', '.flac']:
            media_type = "audio/mpeg"
        else:
            media_type = "application/octet-stream"

        import urllib.parse
        encoded_filename = urllib.parse.quote(filename.encode('utf-8'))

        return FileResponse(
            file_path,
            filename=filename,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
