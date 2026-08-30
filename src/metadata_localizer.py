"""
metadata_localizer.py — 元数据汉化 & B站文案生成

从 YouTube 视频的原始元数据生成 B站上传所需的：
- 中文标题
- 中文简介
- B站标签
- 封面引用
- 分区选择

翻译策略：
1. 如果标题/描述已经是中文 → 直接使用
2. 音乐类视频 → 保留原标题 + 中文注释
3. 其他类型 → 智能翻译标题，简介翻译+补充
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from .config import METADATA, DIRS

logger = logging.getLogger(__name__)


@dataclass
class LocalizedMetadata:
    """汉化后的 B站上传元数据"""
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    tid: int = 3               # B站分区 ID
    cover_file: str = ""        # 封面文件路径
    video_file: str = ""        # 视频文件路径
    source_url: str = ""
    source_title: str = ""
    source_uploader: str = ""

    def to_dict(self) -> Dict:
        return {
            "bili_title": self.title,
            "bili_description": self.description,
            "bili_tags": self.tags,
            "bili_tid": self.tid,
            "bili_cover": Path(self.cover_file).name if self.cover_file else "",
            "video_file": Path(self.video_file).name if self.video_file else "",
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_uploader": self.source_uploader,
        }

    def to_json(self, path: str):
        """写入 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


class MetadataLocalizer:
    def __init__(self):
        self.base_tags = list(METADATA.base_tags)

    def localize(self, metadata: Dict[str, Any],
                 video_file: str = "",
                 thumbnail_file: str = "",
                 video_file_path: str = "") -> LocalizedMetadata:
        """
        从 YouTube 元数据生成 B站上传元数据。

        Args:
            metadata: yt-dlp info.json 数据
            video_file: 视频文件名
            thumbnail_file: 封面文件名
            video_file_path: 视频文件完整路径

        Returns:
            LocalizedMetadata
        """
        title = metadata.get("title", "")
        description = metadata.get("description", "")
        uploader = metadata.get("uploader", metadata.get("channel", ""))
        tags = metadata.get("tags", [])
        categories = metadata.get("categories", [])
        url = metadata.get("webpage_url", metadata.get("original_url", ""))
        duration = metadata.get("duration", 0)

        # 检测语言
        is_chinese = self._is_chinese(title)

        # 生成分区
        tid = self._determine_tid(categories, tags, title, description)

        # 生成标题
        bili_title = self._generate_title(title, tags, categories, uploader, is_chinese)

        # 生成简介
        bili_desc = self._generate_description(
            title, description, uploader, tags, categories, duration, is_chinese
        )

        # 生成标签
        bili_tags = self._generate_tags(tags, categories, title, uploader, tid)

        return LocalizedMetadata(
            title=bili_title,
            description=bili_desc,
            tags=bili_tags,
            tid=tid,
            cover_file=thumbnail_file,
            video_file=video_file_path,
            source_url=url,
            source_title=title,
            source_uploader=uploader,
        )

    def _is_chinese(self, text: str) -> bool:
        """检测文本是否主要是中文"""
        if not text:
            return False
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        return chinese_chars > len(text) * 0.3

    def _determine_tid(self, categories: list, tags: list, title: str, desc: str) -> int:
        """
        确定 B站分区 ID

        常用分区：
        3 = 音乐
        95 = 数码
        188 = 科普
        233 = 电影
        27 = 综合
        """
        text = (title + " " + desc + " " + " ".join(tags) + " " + " ".join(categories)).lower()

        # 音乐类
        music_keywords = ["music", "song", "beat", "rap", "trap", "lofi", "remix",
                          "cover", "album", "mv", "audio", "soundtrack", "单曲",
                          "专辑", "歌手", "beats", "hip hop", "edm", "electronic"]
        if any(kw in text for kw in music_keywords) or "Music" in categories:
            return 3

        # 科技/数码
        tech_keywords = ["tech", "programming", "code", "software", "hardware",
                         "review", "unboxing", "ai", "machine learning"]
        if any(kw in text for kw in tech_keywords):
            return 95

        # 科普
        science_keywords = ["science", "physics", "math", "explained", "how does"]
        if any(kw in text for kw in science_keywords):
            return 188

        # 默认音乐区（搬运视频最常见）
        return METADATA.default_tid

    def _generate_title(self, title: str, tags: list, categories: list,
                        uploader: str, is_chinese: bool) -> str:
        """生成 B站标题（基于 config.yaml 的 title_format，占位符 {title} {uploader} {source_title}）"""
        if is_chinese:
            # 已经是中文，直接用
            return self._truncate(title, METADATA.max_title_length)

        is_music = "Music" in categories or any(kw in title.lower() for kw in ["beat", "rap", "trap"])
        fmt = METADATA.title_format_music if is_music else METADATA.title_format
        fmt = fmt or "【搬运】{title}"
        bili_title = fmt.replace("{title}", title).replace("{source_title}", title)

        # 处理 uploader：为空或已含在标题里则去掉
        artist = uploader or ""
        if artist and artist.lower() not in title.lower():
            bili_title = bili_title.replace("{uploader}", artist)
        else:
            bili_title = bili_title.replace("{uploader}", "")

        # 清理残留的 " - " 等空占位符产生的多余分隔
        bili_title = re.sub(r"\s*-\s*$", "", bili_title).strip()
        bili_title = re.sub(r"\s{2,}", " ", bili_title).strip()
        return self._truncate(bili_title, METADATA.max_title_length)

    def _generate_description(self, title: str, desc: str, uploader: str,
                              tags: list, categories: list, duration: int,
                              is_chinese: bool) -> str:
        """生成 B站简介（基于根目录 description_template.txt 模板，用户可自定义结构/格式）"""
        is_music = "Music" in categories or any(kw in title.lower() for kw in ["beat", "rap"])

        # ── 构建占位符值 ──────────────────────────────────────
        placeholders = {
            "title": title,
            "uploader": uploader or "",
            "source_title": title,
        }

        # 音乐信息块
        music_info = ""
        if is_music:
            parsed = self._parse_music_description(desc)
            parts = []
            if parsed.get("artist"):
                parts.append(f"艺人：{parsed['artist']}")
            if parsed.get("album"):
                parts.append(f"专辑：{parsed['album']}")
            if parsed.get("release_date"):
                parts.append(f"发行日期：{parsed['release_date']}")
            if parsed.get("label"):
                parts.append(f"厂牌：{parsed['label']}")
            if not is_chinese:
                note = self._generate_context_note(title, tags)
                if note:
                    parts.append("")
                    parts.append(note)
            music_info = "\n".join(parts)
        placeholders["music_info"] = music_info

        # 摘要块（非音乐）
        summary = ""
        if not is_music and desc and not is_chinese:
            desc_lines = desc.strip().split("\n")
            summary = "\n".join(desc_lines[:5])
        placeholders["summary"] = summary

        # 版权声明
        copyright_text = ""
        if METADATA.add_copyright_notice:
            copyright_text = "本视频仅作搬运分享，版权归原作者所有\n如有侵权请联系删除"
        placeholders["copyright"] = copyright_text

        # credit（根目录 credit.txt）
        placeholders["credit"] = self._load_credit()

        # 标签
        tag_str = ""
        if tags:
            tag_str = " ".join(f"#{self._clean_tag(t)}" for t in tags[:5] if t)
        placeholders["tags"] = tag_str

        # ── 读取模板并填充 ────────────────────────────────────
        template = self._load_template()
        result = template
        for key, value in placeholders.items():
            result = result.replace("{" + key + "}", value)

        # 清理多余空行（3+ 个换行折叠为 2 个）
        result = re.sub(r"\n{3,}", "\n\n", result).strip()
        return self._truncate(result, METADATA.max_desc_length)

    def _load_template(self) -> str:
        """读取简介模板：优先 template.yaml 的 description_template，否则用内置默认"""
        if METADATA.description_template:
            return METADATA.description_template
        return self._default_template()

    def _default_template(self) -> str:
        """默认简介模板（与旧版结构一致）"""
        return (
            "🎵 {title}\n\n"
            "{music_info}\n\n"
            "{summary}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "原作者：{uploader}\n"
            "原视频：{source_title}\n\n"
            "{copyright}\n\n"
            "{credit}\n\n"
            "{tags}"
        )

    def _load_credit(self) -> str:
        """读取 credit 内容：template.yaml 的 credit；空则不追加"""
        return METADATA.credit.strip() if METADATA.credit else ""

    def _parse_music_description(self, desc: str) -> Dict[str, str]:
        """解析 YouTube 自动生成的音乐描述"""
        result = {}
        if not desc:
            return result

        # DistroKid 格式示例：
        # Kuchiyose · Gravy Beats · Gravy Beats · Grzegorz Szromek
        # Trappuden V
        # ℗ 1305381 Records DK
        # Released on: 2025-04-11

        lines = desc.strip().split("\n")
        for i, line in enumerate(lines):
            line = line.strip()

            # 艺人行：Title · Artist · ...
            if "·" in line and "artist" not in result:
                parts = [p.strip() for p in line.split("·")]
                if len(parts) >= 2:
                    # 第一个是标题，后面的是艺人
                    result["artist"] = parts[1] if len(parts) > 1 else parts[0]

            # 专辑名（单独一行，在艺人行之后）
            if "℗" in line or "Records" in line or "DK" in line:
                result["label"] = line.replace("℗", "").strip()

            if "Released on:" in line:
                result["release_date"] = line.replace("Released on:", "").strip()

            # 通用格式
            if line.startswith("Album:"):
                result["album"] = line.replace("Album:", "").strip()
            if line.startswith("Artist:"):
                result["artist"] = line.replace("Artist:", "").strip()
            if line.startswith("Released:"):
                result["release_date"] = line.replace("Released:", "").strip()

        # 专辑名通常是艺人行之后的独立行
        for i, line in enumerate(lines):
            line = line.strip()
            if "·" in line and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and "·" not in next_line and "℗" not in next_line \
                   and "Released" not in next_line and "Provided" not in next_line \
                   and "Auto-generated" not in next_line:
                    if "album" not in result:
                        result["album"] = next_line
                    break

        return result

    def _generate_context_note(self, title: str, tags: list) -> str:
        """为非中文视频生成简短的中文背景说明"""
        # 根据标签和标题推断内容
        tag_str = " ".join(tags).lower()

        notes = []

        # 音乐风格推断
        style_map = {
            "trap": "Trap 音乐",
            "lofi": "Lo-Fi 放松音乐",
            "hip hop": "Hip-Hop",
            "edm": "电子舞曲",
            "chill": "Chill 放松",
            "ambient": "氛围音乐",
            "phonk": "Phonk",
            "dnb": "Drum & Bass",
            "house": "House",
        }
        for kw, cn_name in style_map.items():
            if kw in tag_str or kw in title.lower():
                notes.append(cn_name)
                break

        if not notes:
            notes.append("音乐分享")

        return f"{'，'.join(notes)}，来自海外创作者的优质内容。"

    def _generate_tags(self, tags: list, categories: list, title: str,
                       uploader: str, tid: int) -> list:
        """生成 B站标签"""
        bili_tags = list(self.base_tags)  # 基础标签

        # 从原始标签中选取有意义的
        for tag in tags:
            if not tag or len(tag) > 20:
                continue
            clean = self._clean_tag(tag)
            if clean and clean not in bili_tags:
                bili_tags.append(clean)

        # 添加创作者名
        if uploader:
            clean_uploader = self._clean_tag(uploader)
            if clean_uploader and clean_uploader not in bili_tags:
                bili_tags.append(clean_uploader)

        # 音乐区额外标签
        if tid == 3:
            music_tags = ["音乐", "music"]
            for t in music_tags:
                if t not in bili_tags:
                    bili_tags.append(t)

        # 限制数量
        return bili_tags[:METADATA.max_tags]

    def _clean_tag(self, tag: str) -> str:
        """清理标签"""
        # 去除特殊字符
        tag = re.sub(r'[<>:"/\\|?*\n\r\t]', '', tag).strip()
        # 去首尾空格
        tag = tag.strip()
        return tag

    def _truncate(self, text: str, max_len: int) -> str:
        """截断文本到最大长度"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."


# ── 便捷函数 ────────────────────────────────────────────────
def localize_metadata(metadata: Dict, video_file: str = "",
                      thumbnail_file: str = "",
                      video_file_path: str = "") -> LocalizedMetadata:
    """全局便捷函数"""
    localizer = MetadataLocalizer()
    return localizer.localize(metadata, video_file, thumbnail_file, video_file_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("用法: python -m src.metadata_localizer <info.json> [video_file] [thumbnail]")
        sys.exit(1)

    info_file = sys.argv[1]
    video_file = sys.argv[2] if len(sys.argv) > 2 else ""
    thumb = sys.argv[3] if len(sys.argv) > 3 else ""

    with open(info_file, encoding="utf-8") as f:
        meta = json.load(f)

    result = localize_metadata(meta, video_file=video_file, thumbnail_file=thumb,
                               video_file_path=video_file)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))