"""
cookie_extractor.py — Chrome CDP cookies 自动提取

通过 Chrome DevTools Protocol 从正在运行的 Chrome 实例中
提取 YouTube cookies，写入 Netscape 格式文件供 yt-dlp 使用。

Fallback 链：
1. Chrome CDP (端口 9222) — 首选，最可靠
2. Chrome cookie 文件直接读取（需要 Keychain 权限）
3. 已缓存的 cookie 文件（检查有效期）
4. 无 cookies 模式（android_vr client 不需要 cookies）
"""

import json
import time
import os
import logging
from pathlib import Path
from typing import Optional
import urllib.request

logger = logging.getLogger(__name__)

class CookieExtractor:
    def __init__(self, cdp_port: int = 9222, cookie_file: str = "/tmp/yt_cookies.txt",
                 max_age: int = 3600):
        self.cdp_port = cdp_port
        self.cookie_file = Path(cookie_file)
        self.max_age = max_age

    def get_cookies(self, force_refresh: bool = False) -> Optional[str]:
        """
        获取 YouTube cookies 文件路径。
        按 fallback 链尝试，返回 cookie 文件路径或 None。

        Args:
            force_refresh: 强制刷新 cookies（忽略缓存）

        Returns:
            cookie 文件路径字符串，或 None（无 cookies 可用）
        """
        # 1. 检查缓存是否有效
        if not force_refresh and self._cache_valid():
            logger.info(f"使用缓存的 cookies: {self.cookie_file}")
            return str(self.cookie_file)

        # 2. 尝试 Chrome CDP
        try:
            cookies = self._extract_via_cdp()
            if cookies:
                self._write_netscape_cookies(cookies)
                logger.info(f"通过 Chrome CDP 提取了 {len(cookies)} 个 cookies")
                return str(self.cookie_file)
        except Exception as e:
            logger.warning(f"Chrome CDP 提取 cookies 失败: {e}")

        # 3. 检查是否有旧缓存可用（即使过期也比没有强）
        if self.cookie_file.exists():
            logger.warning(f"CDP 失败，使用过期的 cookie 缓存: {self.cookie_file}")
            return str(self.cookie_file)

        # 4. 无 cookies — android_vr client 可能不需要
        logger.warning("无法获取 cookies，将尝试无 cookies 下载（android_vr client）")
        return None

    def _cache_valid(self) -> bool:
        """检查缓存的 cookie 文件是否有效"""
        if not self.cookie_file.exists():
            return False

        mtime = self.cookie_file.stat().st_mtime
        age = time.time() - mtime
        if age > self.max_age:
            logger.debug(f"Cookie 缓存已过期（{age:.0f}s > {self.max_age}s）")
            return False

        # 检查文件非空且有实际内容
        size = self.cookie_file.stat().st_size
        if size < 100:
            return False

        return True

    def _extract_via_cdp(self) -> list:
        """通过 Chrome DevTools Protocol 提取 cookies"""
        try:
            import asyncio
            import websockets
        except ImportError as e:
            raise RuntimeError(f"缺少依赖: {e}. 请安装 websockets: pip install websockets")

        async def _extract():
            # 获取 Chrome tabs
            try:
                resp = urllib.request.urlopen(
                    f"http://localhost:{self.cdp_port}/json", timeout=5
                )
                tabs = json.loads(resp.read())
            except Exception:
                raise RuntimeError(f"无法连接 Chrome CDP 端口 {self.cdp_port}")

            # 找到 YouTube tab（或任意 tab，cookies 是全局的）
            target_tab = None
            for tab in tabs:
                if tab.get("type") == "page":
                    if "youtube" in tab.get("url", "").lower():
                        target_tab = tab
                        break

            # 如果没有 YouTube tab，用任意 page tab
            if not target_tab:
                for tab in tabs:
                    if tab.get("type") == "page":
                        target_tab = tab
                        break

            if not target_tab:
                raise RuntimeError("Chrome 中没有可用的 page tab")

            ws_url = target_tab.get("webSocketDebuggerUrl")
            if not ws_url:
                raise RuntimeError("无法获取 WebSocket URL")

            async with websockets.connect(ws_url) as ws:
                # 启用 Network domain
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Network.enable",
                    "params": {}
                }))
                # 等待响应
                while True:
                    resp = await ws.recv()
                    data = json.loads(resp)
                    if data.get("id") == 1:
                        break

                # 获取所有 cookies
                await ws.send(json.dumps({
                    "id": 2,
                    "method": "Network.getAllCookies",
                    "params": {}
                }))

                while True:
                    resp = await ws.recv()
                    data = json.loads(resp)
                    if data.get("id") == 2:
                        break

                all_cookies = data.get("result", {}).get("cookies", [])

                # 过滤 YouTube / Google 相关 cookies
                yt_cookies = [
                    c for c in all_cookies
                    if any(domain in c.get("domain", "")
                           for domain in ["youtube", "google", "youtu.be"])
                ]

                return yt_cookies

        return asyncio.run(_extract())

    def _write_netscape_cookies(self, cookies: list):
        """将 cookies 写入 Netscape 格式文件"""
        lines = ["# Netscape HTTP Cookie File"]
        lines.append("# This is a generated file!  Do not edit.")
        lines.append("")

        for c in cookies:
            domain = c.get("domain", "")
            if not domain:
                continue

            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            expiry = c.get("expires", -1)

            # 处理无效的 expiry
            if expiry is None or expiry < 0:
                # 跳过 session cookies 的无效 expiry（yt-dlp 会警告但不影响）
                expiry = 0

            name = c.get("name", "")
            value = c.get("value", "")

            lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{int(expiry)}\t{name}\t{value}")

        with open(self.cookie_file, "w") as f:
            f.write("\n".join(lines) + "\n")

        os.chmod(self.cookie_file, 0o600)
        logger.debug(f"Cookies 写入: {self.cookie_file} ({len(cookies)} entries)")


# ── 便捷函数 ────────────────────────────────────────────────
def get_yt_cookies(force_refresh: bool = False) -> Optional[str]:
    """全局便捷函数：获取 YouTube cookies 文件路径"""
    from .config import DOWNLOAD
    extractor = CookieExtractor(
        cdp_port=DOWNLOAD.chrome_cdp_port,
        cookie_file=DOWNLOAD.cookie_file,
        max_age=DOWNLOAD.cookie_max_age,
    )
    return extractor.get_cookies(force_refresh=force_refresh)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    path = get_yt_cookies(force_refresh=True)
    if path:
        print(f"✅ Cookies 文件: {path}")
        # 统计 cookie 数量
        with open(path) as f:
            count = sum(1 for line in f if line.strip() and not line.startswith("#"))
        print(f"   Cookie 数量: {count}")
    else:
        print("❌ 无法获取 cookies")