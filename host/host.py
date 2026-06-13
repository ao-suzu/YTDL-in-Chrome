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
import logging
import traceback
from pathlib import Path
from logging.handlers import RotatingFileHandler


# このスクリプトのあるディレクトリをPATHに追加（ffmpegを確実に見つけるため）
BASE_DIR = Path(__file__).parent.resolve()
pathes = [str(BASE_DIR)]

# Node.js や Deno の標準的なインストールパスを追加
pf = os.environ.get("ProgramFiles")
if pf:
    pathes.append(str(Path(pf) / "nodejs"))
pf86 = os.environ.get("ProgramFiles(x86)")
if pf86:
    pathes.append(str(Path(pf86) / "nodejs"))

appdata = os.environ.get("APPDATA")
if appdata:
    pathes.append(str(Path(appdata) / "npm"))
localappdata = os.environ.get("LOCALAPPDATA")
if localappdata:
    pathes.append(str(Path(localappdata) / "deno" / "bin"))
    pathes.append(str(Path(localappdata) / "Programs" / "node"))

userprofile = os.environ.get("USERPROFILE")
if userprofile:
    pathes.append(str(Path(userprofile) / ".deno" / "bin"))

# 重複を排除しつつ、現在の PATH に結合
existing_path = os.environ.get("PATH", "")
path_list = [p for p in pathes if os.path.exists(p)]
if path_list:
    os.environ["PATH"] = os.pathsep.join(path_list) + os.pathsep + existing_path


YTDLP_PATH  = BASE_DIR / 'yt-dlp.exe'
FFMPEG_PATH = BASE_DIR / 'ffmpeg.exe'

VERSION = '1.1.0'


# ========================================================
# ロギング設定
# ========================================================

LOG_FILE = BASE_DIR / 'host.log'

def setup_logger() -> logging.Logger:
    logger = logging.getLogger('ytdl_host')
    logger.setLevel(logging.DEBUG)

    # ログファイル（最大 1MB × 1世代ローテーション）
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1 * 1024 * 1024,
        backupCount=1,
        encoding='utf-8',
    )
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger

log = setup_logger()


# ========================================================
# Native Messaging プロトコル
# ========================================================

def read_message():
    """Chromeからメッセージを読む（4バイトのLE長 + JSON）"""
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        log.info('RECV: stdin EOF or short read — exiting')
        return None
    msg_len = struct.unpack('<I', raw_len)[0]
    if msg_len == 0:
        log.info('RECV: zero-length message — exiting')
        return None
    raw_msg = sys.stdin.buffer.read(msg_len)
    msg = json.loads(raw_msg.decode('utf-8'))
    # actionだけ抜いてログ（URLが長くても読みやすいように）
    action = msg.get('action', '?')
    url    = msg.get('url', '')
    fmt    = msg.get('format', '')
    log.info(f'RECV: action={action} fmt={fmt} url={url[:80]}')
    return msg


write_lock = threading.Lock()

def send_message(msg: dict):
    """Chromeへメッセージを送る（4バイトのLE長 + JSON）"""
    # ログ用に短く整形（progressは percent だけ）
    msg_type = msg.get('type', '?')
    if msg_type == 'progress':
        log.debug(f'SEND: progress {msg.get("percent","")} speed={msg.get("speed","")} size={msg.get("sizeStr","")}')
    elif msg_type == 'done':
        if msg.get('success'):
            log.info(f'SEND: done OK path={msg.get("path","")}')
        else:
            log.warning(f'SEND: done ERROR: {msg.get("error","")}')
    else:
        log.info(f'SEND: {json.dumps(msg, ensure_ascii=False)[:200]}')

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
    log.info(f'yt-dlp imported OK (version: {yt_dlp.version.__version__})')
except ImportError as e:
    HAS_YTDLP = False
    log.error(f'Import failed: {e}')


class CropSquarePP(PostProcessor):
    def run(self, info):
        filepath = info.get('filepath')
        log.debug(f'CropSquarePP: filepath={filepath}')
        if not filepath:
            return [], info
        base_path = os.path.splitext(filepath)[0]
        jpg_file = base_path + '.jpg'
        if os.path.exists(jpg_file):
            try:
                img = Image.open(jpg_file)
                width, height = img.size
                log.debug(f'CropSquarePP: original size={width}x{height}')
                if width != height:
                    new_size = min(width, height)
                    left = (width - new_size) // 2
                    top  = (height - new_size) // 2
                    right  = left + new_size
                    bottom = top  + new_size
                    img_cropped = img.crop((left, top, right, bottom))
                    img_cropped.save(jpg_file, 'JPEG', quality=95)
                    log.debug(f'CropSquarePP: cropped to {new_size}x{new_size}')
                else:
                    log.debug('CropSquarePP: already square, skip')
            except Exception as e:
                log.warning(f'CropSquarePP: error: {e}')
        else:
            log.debug(f'CropSquarePP: jpg not found: {jpg_file}')
        return [], info


def format_bytes(bytes_num):
    if not bytes_num: return "0MB"
    mb = bytes_num / (1024 * 1024)
    if mb >= 1024:
        return f"{mb/1024:.2f}GB"
    else:
        return f"{mb:.1f}MB"


last_sent_percent = 0.0
last_progress_time = 0
progress_lock = threading.Lock()

def progress_hook(d):
    global last_progress_time, last_sent_percent
    status = d.get('status')

    if status == 'downloading':
        now = time.time()
        with progress_lock:
            if now - last_progress_time < 0.5:
                return
            last_progress_time = now

        percent = 0.0
        total_bytes  = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded   = d.get('downloaded_bytes', 0)
        if total_bytes:
            percent = (downloaded / total_bytes) * 100.0

        # マージダウンロード時の進捗補正
        requested_formats = d.get('info_dict', {}).get('requested_formats')
        tmpfilename = d.get('tmpfilename') or d.get('filename') or ''
        if requested_formats and len(requested_formats) == 2:
            format_id_0 = requested_formats[0].get('format_id')
            format_id_1 = requested_formats[1].get('format_id')
            
            if format_id_0 and format_id_0 in tmpfilename:
                percent = percent * 0.85
            elif format_id_1 and format_id_1 in tmpfilename:
                percent = 85.0 + (percent * 0.15)

        # 進捗の逆戻り防止
        if percent < last_sent_percent:
            percent = last_sent_percent
        else:
            last_sent_percent = percent

        speed = d.get('speed', 0)
        eta   = d.get('eta', 0)
        speed_str = f"{speed/1024/1024:.2f}MiB/s" if speed else ""
        eta_str   = f"{eta//60:02d}:{eta%60:02d}" if eta else ""
        size_str  = f"{format_bytes(downloaded)} / {format_bytes(total_bytes)}" if total_bytes else format_bytes(downloaded)

        log.debug(f'DL progress: {percent:.1f}% {speed_str} eta={eta_str} ({size_str})')
        send_message({
            'type': 'progress',
            'percent': f"{percent:.1f}%",
            'percentNum': float(percent),
            'speed': speed_str,
            'eta': eta_str,
            'sizeStr': size_str
        })

    elif status == 'finished':
        filename = d.get('filename', '')
        log.info(f'DL finished (raw): {filename} — entering postprocessing')
        send_message({
            'type': 'progress',
            'percent': "100.0%",
            'percentNum': 100.0,
            'speed': "",
            'eta': "",
            'sizeStr': "変換中..."
        })


def postprocessor_hook(d):
    """ffmpeg変換フック：変換の開始・完了をUIに通知"""
    status = d.get('status')
    pp     = d.get('postprocessor', '')
    info   = d.get('info_dict', {})
    filename = info.get('filepath') or info.get('filename', '')

    if status == 'started':
        log.info(f'PP started: {pp} file={filename}')
        label = '変換中...'
        if 'EmbedThumbnail' in pp:
            label = 'サムネイル埋め込み中...'
        elif 'Metadata' in pp:
            label = 'メタデータ書き込み中...'
        send_message({
            'type': 'progress',
            'percent': "100.0%",
            'percentNum': 100.0,
            'speed': '',
            'eta': '',
            'sizeStr': label
        })
    elif status == 'finished':
        log.info(f'PP finished: {pp} file={filename}')
        send_message({
            'type': 'progress',
            'percent': "100.0%",
            'percentNum': 100.0,
            'speed': '',
            'eta': '',
            'sizeStr': "後処理完了"
        })


def download(url: str, fmt: str, quality: str, output_dir: str | None):
    global last_sent_percent, last_progress_time
    last_sent_percent = 0.0
    last_progress_time = 0
    log.info(f'=== DOWNLOAD START === url={url} fmt={fmt} quality={quality} output_dir={output_dir}')

    if not HAS_YTDLP:
        log.error('yt-dlp not available')
        send_message({
            'type': 'done',
            'success': False,
            'error': 'Pythonのyt-dlpまたはPillowがインストールされていません。拡張機能フォルダ内のinstall.batを再度実行してください。'
        })
        return

    try:
        if not output_dir:
            output_dir = str(Path.home() / 'Downloads')
            log.info(f'output_dir not set, using default: {output_dir}')
        os.makedirs(output_dir, exist_ok=True)

        ffmpeg_loc = str(FFMPEG_PATH) if FFMPEG_PATH.exists() else 'ffmpeg'
        log.info(f'ffmpeg path: {ffmpeg_loc}')
        log.info(f'yt-dlp path: {YTDLP_PATH} (exists={YTDLP_PATH.exists()})')

        # yt-dlp内部ログをhost.logに統合
        _log = log
        class YtdlpLogger:
            def debug(self, msg):
                # [debug] プレフィックスを除いた実質的なメッセージだけ記録
                if msg.startswith('[debug] '):
                    _log.debug(f'yt-dlp: {msg[8:]}')
                # それ以外のdebugは量が多すぎるので捨てる
            def warning(self, msg):
                _log.warning(f'yt-dlp WARNING: {msg}')
            def error(self, msg):
                _log.error(f'yt-dlp ERROR: {msg}')

        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'postprocessor_hooks': [postprocessor_hook],
            'logger': YtdlpLogger(),
            'no_warnings': True,
            'noprogress': True,
            'writethumbnail': True,
            'source_address': '0.0.0.0',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'concurrent_fragment_downloads': 5,
            'continuedl': True,
            'nopart': False,
            'retries': 10,
            'fragment_retries': 20,
            'socket_timeout': 30,
        }

        if fmt in ['mp3', 'm4a']:
            log.info(f'Format: audio ({fmt}) quality={quality}')
            
            if fmt == 'm4a':
                # M4Aの場合は再圧縮（エンコード）を避けるため、最初からm4a(aac)を要求し、品質指定も行わない
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
                pp_args = {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                }
            else:
                # MP3の場合は必ずエンコードが必要なので品質を指定する
                ydl_opts['format'] = 'bestaudio/best'
                pp_args = {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality.replace('k', '') if 'k' in quality else '192',
                }

            ydl_opts['postprocessors'] = [
                pp_args,
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                }
            ]
        elif fmt == 'mp4':
            res = quality if quality.isdigit() else '1080'
            log.info(f'Format: video mp4 res<={res}')
            ydl_opts['format'] = f'bestvideo[height<={res}][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<={res}][ext=mp4][vcodec^=avc1]/bestvideo[height<={res}][ext=mp4]+bestaudio[ext=m4a]/best[height<={res}][ext=mp4]/bestvideo[height<={res}]+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessor_args'] = {
                'merger': ['-vcodec', 'copy', '-acodec', 'aac']
            }
            ydl_opts['postprocessors'] = [{'key': 'FFmpegMetadata', 'add_metadata': True}]
            ydl_opts['prefer_ffmpeg'] = True
        else:
            log.info(f'Format: fallback best (fmt={fmt})')
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegMetadata', 'add_metadata': True}]

        log.info('Calling yt-dlp extract_info...')
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if fmt in ['mp3', 'm4a']:
                ydl.add_post_processor(FFmpegThumbnailsConvertorPP(ydl, 'jpg'))
                ydl.add_post_processor(CropSquarePP())
                ydl.add_post_processor(EmbedThumbnailPP())
                log.debug('PP chain: FFmpegThumbnailsConvertor -> CropSquare -> EmbedThumbnail')
            else:
                # MP4もwebp→jpg変換してから埋め込む（webpのままだとffmpegが失敗する）
                ydl.add_post_processor(FFmpegThumbnailsConvertorPP(ydl, 'jpg'))
                ydl.add_post_processor(EmbedThumbnailPP())
                log.debug('PP chain: FFmpegThumbnailsConvertor -> EmbedThumbnail')

            info = ydl.extract_info(url, download=True)
            log.info('extract_info completed')

            if info:
                title = info.get('title', '(unknown)')
                log.info(f'Video title: {title}')

                # 1) requested_downloads から実際の変換後パスを取得（最優先）
                final_path = None
                reqs = info.get('requested_downloads') or []
                if reqs and isinstance(reqs, list) and reqs[0].get('filepath'):
                    final_path = reqs[0]['filepath']
                    log.info(f'final_path from requested_downloads: {final_path}')

                # 2) フォールバック：拡張子を順番に試す
                if not final_path or not os.path.exists(final_path):
                    base_path = ydl.prepare_filename(info)
                    base = os.path.splitext(base_path)[0]
                    log.debug(f'Fallback search base: {base}')
                    for ext in [fmt, 'mp4', 'm4a', 'webm', 'mkv']:
                        candidate = base + '.' + ext
                        if os.path.exists(candidate):
                            final_path = candidate
                            log.info(f'final_path from fallback search (.{ext}): {final_path}')
                            break

                if not final_path:
                    final_path = ydl.prepare_filename(info)
                    log.warning(f'Could not find actual file, using prepare_filename: {final_path}')

                log.info(f'=== DOWNLOAD COMPLETE === path={final_path}')
                send_message({
                    'type': 'done',
                    'success': True,
                    'path': final_path,
                })
            else:
                log.error('extract_info returned None')
                send_message({
                    'type': 'done',
                    'success': False,
                    'error': 'Download failed'
                })

    except Exception as e:
        log.error(f'=== DOWNLOAD EXCEPTION === {e}')
        log.error(traceback.format_exc())
        send_message({
            'type': 'done',
            'success': False,
            'error': str(e),
        })


def select_folder():
    log.info('select_folder: opening dialog')
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="保存先フォルダを選択")
        root.destroy()
        log.info(f'select_folder: selected={folder!r}')
        return folder if folder else None
    except Exception as e:
        log.error(f'select_folder: error: {e}')
        return None


def get_playlist(url: str) -> dict:
    log.info(f'get_playlist: url={url}')
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
            log.info(f'get_playlist: title={info.get("title")} entries={len(entries)}')
            return {
                'type': 'playlistData',
                'title': info.get('title', 'Playlist'),
                'entries': entries
            }
    except Exception as e:
        log.error(f'get_playlist: error: {e}\n{traceback.format_exc()}')
        return {'type': 'error', 'error': str(e)}


# ========================================================
# メインループ
# ========================================================

def main():
    log.info(f'========== HOST STARTED (v{VERSION}) ==========')
    log.info(f'BASE_DIR: {BASE_DIR}')
    log.info(f'ffmpeg: {FFMPEG_PATH} exists={FFMPEG_PATH.exists()}')
    log.info(f'yt-dlp: {YTDLP_PATH} exists={YTDLP_PATH.exists()}')
    log.info(f'HAS_YTDLP: {HAS_YTDLP}')

    while True:
        try:
            msg = read_message()
        except Exception as e:
            log.error(f'read_message exception: {e}\n{traceback.format_exc()}')
            break

        if msg is None:
            log.info('========== HOST EXITING (no more messages) ==========')
            break

        action = msg.get('action')

        if action == 'ping':
            log.info('PING received')
            send_message({'type': 'pong', 'version': VERSION})

        elif action == 'selectFolder':
            folder = select_folder()
            send_message({'type': 'folderSelected', 'path': folder})

        elif action == 'getPlaylist':
            url = msg.get('url', '')
            if not url:
                log.warning('getPlaylist: no URL')
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
                log.warning('download: no URL')
                send_message({'type': 'done', 'success': False, 'error': 'URLが指定されていません'})
            else:
                download(url, fmt, quality, output_dir)

        else:
            log.warning(f'Unknown action: {action}')
            send_message({'type': 'error', 'error': f'不明なアクション: {action}'})


if __name__ == '__main__':
    main()
