import json
import re
from typing import Optional
from urllib.parse import urlparse

import requests

from app.core.platforms.platform_handlers.stream.data import StreamData, wrap_stream
from app.core.platforms.platform_handlers.stream.async_http import async_req
from app.core.platforms.platform_handlers.stream.base import BaseLiveStream


class ChaturbateLiveStream(BaseLiveStream):
    """
    A class for fetching and processing Chaturbate live stream information.
    """

    def __init__(self, proxy_addr: str | None = None, cookies: str | None = None):
        super().__init__(proxy_addr, cookies)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://chaturbate.com/',
            'Cookie': self.cookies or ''
        })
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://chaturbate.com/',
            'Cookie': self.cookies or ''
        }

    async def fetch_web_stream_data(self, url: str) -> dict:
        """获取原始流数据"""
        username = self._extract_username(url)
        if not username:
            raise ValueError("Invalid Chaturbate URL")

        api_url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
        response = await async_req(api_url, proxy_addr=self.proxy_addr, headers=self.headers)
        data = json.loads(response)

        if not data.get('hls_source'):
            return {
                'platform': 'Chaturbate',
                'anchor_name': self._extract_username(url),
                'is_live': False
            }

        m3u8_url = data['hls_source']
        try:
            # play_url_list = self.parse_playlist(m3u8_url, 1080, 60)
            play_url_list = await self.get_cb_play_url_list(m3u8_url, proxy=self.proxy_addr, headers=self._get_pc_headers)
        except Exception as e:
            print(f"解析播放列表失败: {e}")
            return None

        direct_url = 'https://edge8-sea.live.mmcdn.com/live-hls/'

        direct_url_list = []
        for url in play_url_list:
            url = re.sub(
                r"https://[^/]+\.live\.mmcdn\.com/live-hls/",
                direct_url,
                url
            )
            direct_url_list.append(url)
        # play_url_list = await self.get_play_url_list(m3u8_url, proxy=self.proxy_addr, headers=self._get_pc_headers)
        return {
            'platform': 'Chaturbate',
            'anchor_name': username,
            'is_live': True,
            'm3u8_url': m3u8_url,
            # 'record_url': m3u8_url,
            "play_url_list": direct_url_list,
            'title': f"{username}'s Chaturbate Stream"
        }


    async def get_cb_play_url_list(self, m3u8: str, proxy: str | None = None, headers: dict | None = None) -> list[str]:
        """
        Fetches a list of play URLs from an M3U8 file.

        Args:
            m3u8 (str): The URL of the M3U8 file.
            proxy (str | None): The proxy address to use. Defaults to None.
            headers (dict | None): Custom headers for the request. Defaults to None.

        Returns:
            List[str]: A list of play URLs sorted by bandwidth (highest first).
        """
        proxies = {
            "http": proxy,
            "https": proxy
        }
        base_url = m3u8.rsplit('/', 1)[0] + '/'
        resp = self.session.get(m3u8, proxies=proxies).text
        play_url_list = []
        for i in resp.split('\n'):
            if i.startswith('chunklist_'):
                play_url_list.append(base_url + i.strip())
        if not play_url_list:
            for i in resp.split('\n'):
                if i.strip().endswith('m3u8'):
                    play_url_list.append(i.strip())
        bandwidth_pattern = re.compile(r'BANDWIDTH=(\d+)')
        bandwidth_list = bandwidth_pattern.findall(resp)
        url_to_bandwidth = {url: int(bandwidth) for bandwidth, url in zip(bandwidth_list, play_url_list)}
        play_url_list = sorted(play_url_list, key=lambda url: url_to_bandwidth[url], reverse=True)
        return play_url_list

    async def fetch_stream_url(self, json_data: dict, video_quality: str | int | None = None) -> StreamData:
        """
        Fetches the stream URL for a live room and wraps it into a StreamData object.
        """
        data = await self.get_stream_url(json_data, video_quality, spec=True, platform='Chaturbate')
        return wrap_stream(data)


    @staticmethod
    def _extract_username(url: str) -> Optional[str]:
        """从URL提取用户名"""
        parsed = urlparse(url)
        if 'chaturbate.com' not in parsed.netloc:
            return url.strip('/')  # 假设输入的是用户名
        return parsed.path.strip('/').split('/')[0]


class StripchatLiveStream(BaseLiveStream):
    """
    A class for fetching and processing Stripchat live stream information.
    """

    def __init__(self, proxy_addr: str | None = None, cookies: str | None = None):
        super().__init__(proxy_addr, cookies)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://zh.stlivexxx.com',
            # 'origin': 'https://zh.stlivexxx.com',
            'Cookie': self.cookies or ''
        }

    async def fetch_web_stream_data(self, url: str) -> dict:
        """获取原始流数据"""
        username = self._extract_username(url)
        if not username:
            raise ValueError("Invalid Stripchat URL")

        # api_url = f"https://stripchat.com/api/front/v2/models/username/{username}/cam"
        api_url = f"https://zh.stlivexxx.com/api/front/v2/models/username/{username}/cam"
        response = await async_req(api_url, proxy_addr=self.proxy_addr, headers=self.headers)
        data = json.loads(response)
        cam_data = data.get('cam')
        username = self._extract_username(url)

        if not cam_data or not cam_data.get('isCamAvailable', False):
            return {
                'platform': 'Stripchat',
                'anchor_name': username,
                'is_live': False
            }

        stream_name = cam_data.get('streamName')
        if not stream_name:
            return {
                'platform': 'Stripchat',
                'anchor_name': username,
                'is_live': False
            }

        m3u8_url = f"https://edge-hls.doppiocdn.com/hls/{stream_name}/master/{stream_name}_auto.m3u8?playlistType=lowLatency"

        # m3u8_url = f"https://b-hls-23.doppiocdn.live/hls/{stream_name}/master/{stream_name}_auto.m3u8"
        play_url_list = await self.get_play_url_list(m3u8_url, proxy=self.proxy_addr, headers=self._get_pc_headers())

        direct_url = 'https://b-hls-23.doppiocdn.live/hls/'

        direct_url_list = []
        for url in play_url_list:
            url = re.sub(
                r'https://media-hls\.doppiocdn\.com/b-hls-\d+/',
                direct_url,
                url
            )
            direct_url_list.append(url)

        return {
            'platform': 'Stripchat',
            'anchor_name': username,
            'is_live': True,
            'm3u8_url': m3u8_url,
            "play_url_list": direct_url_list,
            'title': f"{username}'s Stripchat Stream"
        }

    async def fetch_stream_url(self, json_data: dict, video_quality: str | int | None = None) -> StreamData:
        """
        Fetches the stream URL for a live room and wraps it into a StreamData object.
        """
        data = await self.get_stream_url(json_data, video_quality, spec=True, platform='Stripchat')
        return wrap_stream(data)

    @staticmethod
    def _extract_username(url: str) -> Optional[str]:
        """从URL提取用户名"""
        parsed = urlparse(url)
        # if 'stripchat.com' not in parsed.netloc:
        #     return url.strip('/')  # 假设输入的是用户名
        return parsed.path.strip('/').split('/')[0]