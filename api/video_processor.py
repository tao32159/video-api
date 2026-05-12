import os
import yt_dlp
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict

from .config import config

logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理器，使用yt-dlp下载视频和提取音频"""

    def __init__(self):
        """初始化视频处理器"""
        # 基础配置
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'prefer_ffmpeg': True,
            # 反机器人检测配置
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            **config.get_enhanced_opts()
        }

        # 平台特定的处理策略
        self.platform_strategies = {
            'youtube': self._get_youtube_strategy,
        }

        # 视频下载配置
        self.video_opts = {
            **self.base_opts,
            'format': 'best[height<=1080]/best',
            'outtmpl': '%(title)s.%(ext)s',
            'merge_output_format': 'mp4',
        }

        # 音频提取配置
        self.audio_opts = {
            **self.base_opts,
            'format': 'bestaudio/best',
            'outtmpl': '%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

    def _get_platform_from_url(self, url: str) -> str:
        """从URL识别平台"""
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'bilibili.com' in url:
            return 'bilibili'
        elif 'tiktok.com' in url:
            return 'tiktok'
        return 'generic'

    def _get_youtube_strategy(self):
        """YouTube平台的格式选择策略"""
        return {
            'format': 'best[height<=1080]/best',
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],
                    'player_client': ['android', 'web'],
                }
            },
            'http_headers': {
                **self.base_opts.get('http_headers', {}),
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            },
            'retries': 5,
            'fragment_retries': 5,
            'sleep_interval_requests': 2,
        }

    def _get_optimized_opts(self, url: str, base_opts: dict) -> dict:
        """根据平台优化配置选项"""
        platform = self._get_platform_from_url(url)
        opts = base_opts.copy()

        if platform in self.platform_strategies:
            strategy = self.platform_strategies[platform]()
            if 'http_headers' in strategy and 'http_headers' in opts:
                merged_headers = opts['http_headers'].copy()
                merged_headers.update(strategy['http_headers'])
                strategy['http_headers'] = merged_headers
            opts.update(strategy)
            logger.info(f"使用 {platform} 平台优化策略")

        return opts

    async def download_video_and_audio(
        self,
        url: str,
        output_dir: Path,
        extract_audio: bool = True,
        keep_video: bool = True
    ) -> Dict[str, Optional[str]]:
        """下载视频和/或提取音频"""
        try:
            if not extract_audio and not keep_video:
                raise ValueError("必须至少选择提取音频或保留视频中的一项")

            output_dir.mkdir(exist_ok=True)

            import uuid
            unique_id = str(uuid.uuid4())[:8]

            result_files = {}

            if keep_video and extract_audio:
                # 同时下载视频和音频
                video_task = self._download_video_only(url, output_dir, unique_id)
                audio_task = self._download_audio_only(url, output_dir, unique_id)

                video_result, audio_result = await asyncio.gather(
                    video_task, audio_task, return_exceptions=True
                )

                if not isinstance(video_result, Exception) and video_result:
                    result_files['video'] = video_result

                if not isinstance(audio_result, Exception) and audio_result:
                    result_files['audio'] = audio_result

                # 回退：音频失败则从视频提取
                if 'audio' not in result_files and 'video' in result_files:
                    audio_from_video = await self._extract_audio_from_video(
                        result_files['video'], output_dir, unique_id
                    )
                    if audio_from_video:
                        result_files['audio'] = audio_from_video

            elif keep_video:
                video_file = await self._download_video_only(url, output_dir, unique_id)
                if video_file:
                    result_files['video'] = video_file
                else:
                    raise Exception("无法下载视频文件")

            elif extract_audio:
                audio_file = await self._download_audio_only(url, output_dir, unique_id)
                if audio_file:
                    result_files['audio'] = audio_file
                else:
                    # 从视频提取音频
                    video_file = await self._download_video_only(url, output_dir, unique_id)
                    if video_file:
                        audio_from_video = await self._extract_audio_from_video(
                            video_file, output_dir, unique_id
                        )
                        if audio_from_video:
                            result_files['audio'] = audio_from_video
                            try:
                                os.unlink(video_file)
                            except:
                                pass

            if not result_files:
                raise Exception("没有成功下载任何文件")

            return result_files

        except Exception as e:
            logger.error(f"处理视频失败: {str(e)}")
            raise

    async def _download_video_only(self, url: str, output_dir: Path, unique_id: str) -> Optional[str]:
        """只下载视频文件"""
        try:
            video_template = str(output_dir / f"video_{unique_id}.%(ext)s")
            video_opts = self._get_optimized_opts(url, self.video_opts)
            video_opts['outtmpl'] = video_template

            with yt_dlp.YoutubeDL(video_opts) as ydl:
                await asyncio.to_thread(ydl.download, [url])

            for ext in ['mp4', 'webm', 'mkv', 'avi', 'mov', 'flv']:
                potential_file = output_dir / f"video_{unique_id}.{ext}"
                if potential_file.exists():
                    return str(potential_file)

            return None
        except Exception as e:
            logger.error(f"下载视频失败: {e}")
            return None

    async def _download_audio_only(self, url: str, output_dir: Path, unique_id: str) -> Optional[str]:
        """只提取音频文件"""
        try:
            audio_template = str(output_dir / f"audio_{unique_id}.%(ext)s")
            audio_opts = self._get_optimized_opts(url, self.audio_opts)
            audio_opts['outtmpl'] = audio_template

            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                await asyncio.to_thread(ydl.download, [url])

            for ext in ['mp3', 'm4a', 'wav', 'aac', 'ogg']:
                potential_file = output_dir / f"audio_{unique_id}.{ext}"
                if potential_file.exists():
                    return str(potential_file)

            return None
        except Exception as e:
            logger.error(f"提取音频失败: {e}")
            return None

    async def _extract_audio_from_video(self, video_path: str, output_dir: Path, unique_id: str) -> Optional[str]:
        """从视频文件中提取音频"""
        try:
            import subprocess
            audio_path = output_dir / f"audio_{unique_id}.mp3"

            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn', '-acodec', 'mp3', '-ab', '192k',
                '-ar', '44100', '-y', str(audio_path)
            ]

            await asyncio.to_thread(subprocess.run, cmd, capture_output=True, check=True)

            if audio_path.exists():
                return str(audio_path)

            return None
        except Exception as e:
            logger.error(f"从视频提取音频失败: {e}")
            return None

    def get_video_info(self, url: str) -> dict:
        """获取视频信息"""
        try:
            opts = self._get_optimized_opts(url, self.base_opts)

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            return {
                'title': info.get('title', '未知标题'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', '未知作者'),
                'thumbnail': info.get('thumbnail', ''),
                'webpage_url': info.get('webpage_url', url),
                'extractor': info.get('extractor', ''),
            }

        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            raise Exception(f"获取视频信息失败: {str(e)}")
