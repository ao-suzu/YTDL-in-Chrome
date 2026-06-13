// YouTubeページのメタ情報をpopupに提供するcontent script

// メッセージリスナー: popupからページ情報を要求された時に返す
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getPageInfo') {
    const info = getPageInfo();
    sendResponse(info);
  }
  return true;
});

function getPageInfo() {
  const url = window.location.href;
  let title = document.title;

  // YouTube動画ページの場合、タイトルから " - YouTube" を除去
  if (title.endsWith(' - YouTube')) {
    title = title.slice(0, -10);
  }

  // 動画IDを取得
  let videoId = null;
  const urlObj = new URL(url);
  if (urlObj.hostname.includes('youtube.com')) {
    videoId = urlObj.searchParams.get('v');
  } else if (urlObj.hostname.includes('youtu.be')) {
    videoId = urlObj.pathname.slice(1);
  }

  // プレイリストIDを取得
  const playlistId = urlObj.searchParams.get('list');

  // サムネイル
  const thumbnail = videoId
    ? `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`
    : null; // プレイリスト自体のサムネは拡張機能側ではとりあえず取らない

  // 動画時間を取得（可能な場合）
  let duration = null;
  const durationEl = document.querySelector('.ytp-time-duration');
  if (durationEl) {
    duration = durationEl.textContent;
  }

  // クリーンなURL（プレイリストのパラメータを除外した単体動画のURL）
  // ただし /playlist?list= の場合は動画単体URLが存在しないため、そのまま
  let cleanUrl = url;
  if (videoId) {
    cleanUrl = `https://www.youtube.com/watch?v=${videoId}`;
  }

  return {
    url,
    cleanUrl,
    title,
    videoId,
    playlistId,
    thumbnail,
    duration,
    isYouTube: urlObj.hostname.includes('youtube.com') || urlObj.hostname.includes('youtu.be'),
    isVideo: !!videoId,
    isPlaylist: !!playlistId && !videoId,
    isPlaylistOnly: urlObj.pathname.startsWith('/playlist') && !!playlistId,
  };
}
