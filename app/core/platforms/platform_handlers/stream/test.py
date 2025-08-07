import re
import json
import time
import requests
from typing import Dict, Optional, Callable
from urllib.parse import urlparse, urljoin
from m3u8 import M3U8, Segment

from app.core.platforms.platform_handlers.stream.base import BaseLiveStream


class ChaturbateClient:
    def __init__(self, base_url="https://chaturbate.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        self.room_dossier_regex = re.compile(r'window\.initialRoomDossier = "(.*?)"')

    def get_stream(self, username: str) -> Optional['Stream']:
        """获取主播的HLS流信息"""
        try:
            url = f"{self.base_url}/{username}/"
            resp = self.session.get(url)
            resp.raise_for_status()

            if "playlist.m3u8" not in resp.text:
                return None  # 频道离线

            return self.parse_stream(resp.text)
        except Exception as e:
            print(f"获取流信息失败: {e}")
            return None

    def parse_stream(self, html: str) -> Optional['Stream']:
        """从HTML解析HLS源"""
        match = self.room_dossier_regex.search(html)
        if not match:
            return None

        try:
            # 处理Unicode转义序列
            json_str = match.group(1).encode('utf-8').decode('unicode-escape')
            data = json.loads(json_str)
            hls_source = data.get("hls_source")
            if hls_source:
                return Stream(hls_source, self.session)
        except Exception as e:
            print(f"解析流信息失败: {e}")

        return None


class Stream:
    def __init__(self, hls_source: str, session: requests.Session):
        self.hls_source = hls_source
        self.session = session

    def get_playlist(self, resolution: int = 1080, framerate: int = 30) -> Optional['Playlist']:
        """获取指定分辨率的播放列表"""
        try:
            resp = self.session.get(self.hls_source)
            resp.raise_for_status()
            return self.parse_playlist(resp.text, resolution, framerate)
        except Exception as e:
            print(f"获取播放列表失败: {e}")
            return None

    def parse_playlist(self, m3u8_content: str, resolution: int, framerate: int) -> Optional['Playlist']:
        """解析主播放列表并选择合适的分辨率"""
        try:
            master = M3U8(m3u8_content)
            if not master.is_variant:
                return None

            resolutions = {}
            for playlist in master.playlists:
                # 解析分辨率 (如 "1920x1080")
                if not playlist.stream_info.resolution:
                    continue

                width = playlist.stream_info.resolution[0]
                # 检测帧率 (通常包含在名称中)
                fr = 30
                if playlist.stream_info.name and "60" in playlist.stream_info.name:
                    fr = 60

                if width not in resolutions:
                    resolutions[width] = {"framerate": {}, "width": width}

                resolutions[width]["framerate"][fr] = playlist.uri

            # 选择最佳分辨率
            variant = None
            if resolution in resolutions:
                variant = resolutions[resolution]
            else:
                # 降级选择: 找出比请求分辨率小的最大分辨率
                candidates = [r for r in resolutions.values() if r["width"] < resolution]
                if candidates:
                    variant = max(candidates, key=lambda x: x["width"])

            if not variant:
                return None

            # 选择最佳帧率
            selected_framerate = framerate
            playlist_url = variant["framerate"].get(framerate)
            if not playlist_url:
                # 回退到第一个可用帧率
                selected_framerate, playlist_url = next(iter(variant["framerate"].items()))

            base_url = self.hls_source[:self.hls_source.rfind("playlist.m3u8")]
            return Playlist(
                url=urljoin(base_url, playlist_url),
                base_url=base_url,
                resolution=variant["width"],
                framerate=selected_framerate,
                session=self.session
            )
        except Exception as e:
            print(f"解析播放列表失败: {e}")
            return None


class Playlist:
    def __init__(self, url: str, base_url: str, resolution: int, framerate: int, session: requests.Session):
        self.url = url
        self.base_url = base_url
        self.resolution = resolution
        self.framerate = framerate
        self.session = session
        self.last_seq = -1

    def watch_segments(self, handler: Callable[[bytes, float], None], interval: float = 1.0):
        """持续获取并处理视频分段"""
        while True:
            try:
                resp = self.session.get(self.url)
                resp.raise_for_status()
                media_playlist = M3U8(resp.text)

                for segment in media_playlist.segments:
                    if not segment:
                        continue

                    # 简单的序列号检测 (实际应该用更可靠的方法)
                    seq = self._parse_segment_seq(segment.uri)
                    if seq == -1 or seq <= self.last_seq:
                        continue

                    self.last_seq = seq

                    # 重试机制
                    for attempt in range(3):
                        try:
                            segment_url = urljoin(self.base_url, segment.uri)
                            seg_resp = self.session.get(segment_url)
                            seg_resp.raise_for_status()
                            handler(seg_resp.content, segment.duration)
                            break
                        except Exception as e:
                            if attempt == 2:
                                raise
                            time.sleep(0.6)

                time.sleep(interval)
            except Exception as e:
                print(f"处理分段时出错: {e}")
                time.sleep(5)  # 出错后等待

    @staticmethod
    def _parse_segment_seq(uri: str) -> int:
        """从分段URL解析序列号 (简化版)"""
        try:
            # 假设格式如 "segment-12345.ts"
            parts = uri.split("-")
            if len(parts) > 1:
                return int(parts[1].split(".")[0])
        except:
            pass
        return -1


# 使用示例
if __name__ == "__main__":
    def segment_handler(data: bytes, duration: float):
        print(f"收到分段，时长: {duration:.2f}s，大小: {len(data) / 1024:.1f}KB")
        # 这里可以保存到文件或进一步处理


    client = ChaturbateClient()
    stream = client.get_stream("katkittykate")  # 替换为实际用户名

    if stream:
        print(f"获取到HLS源: {stream.hls_source}")
        playlist = stream.get_playlist(resolution=1080, framerate=30)

        if playlist:
            print(f"选择播放列表: {playlist.url}")
            print(f"分辨率: {playlist.resolution}p, 帧率: {playlist.framerate}fps")

            # 开始监控分段
            try:
                playlist.watch_segments(segment_handler)
            except KeyboardInterrupt:
                print("停止监控")
        else:
            print("无法获取合适的播放列表")
    else:
        print("无法获取流信息或主播离线")