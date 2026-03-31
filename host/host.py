#!/usr/bin/env python3
"""
YT Downloader - Native Messaging Host
Chrome拡張機能とのstdio通信 + yt-dlpでダウンロード実行
"""

import sys
import os
import json
import struct
import time
import threading
from pathlib import Path


# このスクリプトのあるディレクトリをPATHに追加（ffmpegを確実に見つけるため）
BASE_DIR = Path(__file__).parent.resolve()
os.environ["PATH"] = str(BASE_DIR) + os.pathsep + os.environ.get("PATH", "")

YTDLP_PATH  = BASE_DIR / 'yt-dlp.exe'
FFMPEG_PATH = BASE_DIR / 'ffmpeg.exe'

VERSION = '1.0.1'


# ========================================================
# Native Messaging プロトコル
# ========================================================

def read_message():
    """Chromeからメッセージを読む（4バイトのLE長 + JSON）"""
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    msg_len = struct.unpack('<I', raw_len)[0]
    if msg_len == 0:
        return None
    raw_msg = sys.stdin.buffer.read(msg_len)
    return json.loads(raw_msg.decode('utf-8'))


write_lock = threading.Lock()

def send_message(msg: dict):
    """Chromeへメッセージを送る（4バイトのLE長 + JSON）"""
    data = json.dumps(msg, ensure_ascii=False).encode('utf-8')
    with write_lock:
        sys.stdout.buffer.write(struct.pack('<I', len(data)))
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


# ========================================================
# yt-dlp 呼び出し
# ========================================================

try:
    import yt_dlp
    from yt_dlp.postprocessor.common import PostProcessor
    from yt_dlp.postprocessor.embedthumbnail import EmbedThumbnailPP
    from yt_dlp.postprocessor.ffmpeg import FFmpegThumbnailsConvertorPP
    from PIL import Image
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

class CropSquarePP(PostProcessor):
    def run(self, info):
        filepath = info.get('filepath')
        if not filepath:
            return [], info
        base_path = os.path.splitext(filepath)[0]
        jpg_file = base_path + '.jpg'
        if os.path.exists(jpg_file):
            try:
                img = Image.open(jpg_file)
                width, height = img.size
                if width != height:
                    new_size = min(width, height)
                    left = (width - new_size) // 2
                    top = (height - new_size) // 2
                    right = left + new_size
                    bottom = top + new_size
                    img_cropped = img.crop((left, top, right, bottom))
                    img_cropped.save(jpg_file, 'JPEG', quality=95)
            except Exception:
                pass
        return [], info

def format_bytes(bytes_num):
    if not bytes_num: return "0MB"
    mb = bytes_num / (1024 * 1024)
    if mb >= 1024:
        return f"{mb/1024:.2f}GB"
    else:
        return f"{mb:.1f}MB"

last_progress_time = 0
progress_lock = threading.Lock()

def progress_hook(d):
    global last_progress_time
    status = d.get('status')
    
    if status == 'downloading':
        now = time.time()
        
        # マルチスレッドによる競合を防ぐ
        with progress_lock:
            # 0.5秒未満の連続送信を防ぐ（スロットリング）
            if now - last_progress_time < 0.5:
                return
            last_progress_time = now
        
        percent = 0
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        
        if total_bytes:
            percent = (downloaded / total_bytes) * 100
            
        speed = d.get('speed', 0)
        eta = d.get('eta', 0)
        
        speed_str = f"{speed/1024/1024:.2f}MiB/s" if speed else ""
        eta_str = f"{eta//60:02d}:{eta%60:02d}" if eta else ""
        
        total_str = format_bytes(total_bytes)
        dl_str = format_bytes(downloaded)
        size_str = f"{dl_str} / {total_str}" if total_bytes else f"{dl_str}"
        
        send_message({
            'type': 'progress',
            'percent': f"{percent:.1f}%",
            'percentNum': float(percent),
            'speed': speed_str,
            'eta': eta_str,
            'sizeStr': size_str
        })
    elif status == 'finished':
        send_message({
            'type': 'progress',
            'percent': "100.0%",
            'percentNum': 100.0,
            'speed': "",
            'eta': "00:00",
            'sizeStr': "完了"
        })


def download(url: str, fmt: str, quality: str, output_dir: str | None):
    if not HAS_YTDLP:
        send_message({
            'type': 'done',
            'success': False,
            'error': 'Pythonのyt-dlpまたはPillowがインストールされていません。拡張機能フォルダ内のinstall.batを再度実行してください。'
        })
        return

    try:
        if not output_dir:
            output_dir = str(Path.home() / 'Downloads')
        os.makedirs(output_dir, exist_ok=True)

        ffmpeg_loc = str(FFMPEG_PATH) if FFMPEG_PATH.exists() else 'ffmpeg'
        
        log_file = BASE_DIR / 'host_debug.log'
        class Logger:
            def debug(self, msg):
                pass # debug 出力は捨てる（バッファ詰まりの最大の原因）
            def warning(self, msg):
                try:
                    with open(log_file, 'a', encoding='utf-8') as f: f.write(msg + '\n')
                except Exception:
                    pass
            def error(self, msg):
                try:
                    with open(log_file, 'a', encoding='utf-8') as f: f.write(msg + '\n')
                except Exception:
                    pass

        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'logger': Logger(),
            'no_warnings': True, # 警告も最小限にする
            'noprogress': True,
            'writethumbnail': True,
            'source_address': '0.0.0.0',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'concurrent_fragment_downloads': 5, # 並行処理で高速化
        }

        if fmt in ['mp3', 'm4a']:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': fmt,
                    'preferredquality': quality.replace('k', '') if 'k' in quality else '192',
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                }
            ]
        elif fmt == 'mp4':
            res = quality if quality.isdigit() else '1080'
            # MP4(h264) + M4A(aac) の組み合わせを最優先で探し、なければ最高画質を拾う
            ydl_opts['format'] = f'bestvideo[height<={res}][ext=mp4]+bestaudio[ext=m4a]/best[height<={res}][ext=mp4]/bestvideo[height<={res}]+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
            # 合体時の変換引数をより明示的に（-acodec aac を使用）
            ydl_opts['postprocessor_args'] = {
                'merger': ['-vcodec', 'copy', '-acodec', 'aac']
            }
            ydl_opts['postprocessors'] = [{'key': 'FFmpegMetadata', 'add_metadata': True}]
            ydl_opts['prefer_ffmpeg'] = True
        else:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegMetadata', 'add_metadata': True}]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if fmt in ['mp3', 'm4a']:
                ydl.add_post_processor(FFmpegThumbnailsConvertorPP(ydl, 'jpg'))
                ydl.add_post_processor(CropSquarePP())
                ydl.add_post_processor(EmbedThumbnailPP())
            else:
                ydl.add_post_processor(EmbedThumbnailPP())

            info = ydl.extract_info(url, download=True)
            
            if info:
                final_path = ydl.prepare_filename(info)
                base = os.path.splitext(final_path)[0]
                possible_path = base + '.' + fmt
                if os.path.exists(possible_path):
                    final_path = possible_path
                elif os.path.exists(base + '.mp4') and fmt != 'm4a' and fmt != 'mp3':
                    final_path = base + '.mp4'
                    
                send_message({
                    'type': 'done',
                    'success': True,
                    'path': final_path,
                })
            else:
                send_message({
                    'type': 'done',
                    'success': False,
                    'error': 'Download failed'
                })

    except Exception as e:
        send_message({
            'type': 'done',
            'success': False,
            'error': str(e),
        })

def select_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="保存先フォルダを選択")
        root.destroy()
        return folder if folder else None
    except Exception as e:
        return None

def get_playlist(url: str) -> dict:
    if not HAS_YTDLP:
        return {'type': 'error', 'error': 'yt_dlp not installed'}
    try:
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = []
            if 'entries' in info:
                for entry in info['entries']:
                    entries.append({
                        'title': entry.get('title', ''),
                        'url': entry.get('url') or (f"https://www.youtube.com/watch?v={entry.get('id')}" if entry.get('id') else url)
                    })
            
            return {
                'type': 'playlistData', 
                'title': info.get('title', 'Playlist'), 
                'entries': entries
            }
    except Exception as e:
        return {'type': 'error', 'error': str(e)}

# ========================================================
# メインループ
# ========================================================

def main():
    while True:
        try:
            msg = read_message()
        except Exception:
            break

        if msg is None:
            break

        action = msg.get('action')

        if action == 'ping':
            send_message({'type': 'pong', 'version': VERSION})

        elif action == 'selectFolder':
            folder = select_folder()
            send_message({'type': 'folderSelected', 'path': folder})

        elif action == 'getPlaylist':
            url = msg.get('url', '')
            if not url:
                send_message({'type': 'error', 'error': 'URLが指定されていません'})
            else:
                res = get_playlist(url)
                send_message(res)

        elif action == 'download':
            url        = msg.get('url', '')
            fmt        = msg.get('format', 'mp3')
            quality    = msg.get('quality', '192k')
            output_dir = msg.get('outputDir')

            if not url:
                send_message({'type': 'done', 'success': False, 'error': 'URLが指定されていません'})
            else:
                # 無意味なスレッド処理を削除し、直接実行
                download(url, fmt, quality, output_dir)

        else:
            send_message({'type': 'error', 'error': f'不明なアクション: {action}'})


if __name__ == '__main__':
    main()
