// panel.js - コンパクトなYouTube風UI用ロジック（バックグラウンド保持対応）

const els = {
  tabs: document.querySelectorAll('.tab-btn'),
  pages: document.querySelectorAll('.content'),
  notYouTube: document.getElementById('notYouTube'),
  ytContent: document.getElementById('ytContent'),
  hostWarning: document.getElementById('hostWarning'),
  
  // フォーム関連
  videoTitle: document.getElementById('videoTitle'),
  thumbnailWrap: document.getElementById('thumbnailWrap'),
  urlInput: document.getElementById('urlInput'),
  formatSelect: document.getElementById('formatSelect'),
  qualitySelect: document.getElementById('qualitySelect'),
  downloadBtn: document.getElementById('downloadBtn'),
  forceDetectBtn: document.getElementById('forceDetectBtn'),
  
  // プレイリスト関連
  playlistOptions: document.getElementById('playlistOptions'),
  dlPlaylistCheck: document.getElementById('dlPlaylistCheck'),
  playlistFolderCheck: document.getElementById('playlistFolderCheck'),
  
  // DLリスト
  dlList: document.getElementById('dlList'),
  btnClearCompleted: document.getElementById('btnClearCompleted'),

  // 設定
  uiModeSelect: document.getElementById('uiModeSelect'),
  outputDir: document.getElementById('outputDir'),
  btnSelectFolder: document.getElementById('btnSelectFolder'),

  // 手動DL関連
  manualUrlInput: document.getElementById('manualUrlInput'),
  manualFormatSelect: document.getElementById('manualFormatSelect'),
  manualQualitySelect: document.getElementById('manualQualitySelect'),
  manualDownloadBtn: document.getElementById('manualDownloadBtn')
};

let currentPageInfo = null;
let currentTasks = [];
let currentHistory = [];

async function init() {
  const versionSpan = document.getElementById('appVersion');
  if (versionSpan) versionSpan.textContent = 'v' + chrome.runtime.getManifest().version;

  setupTabs();
  setupSettings();
  setupDownloadAction();
  
  // Native Host確認
  chrome.runtime.sendMessage({ action: 'ping' }, res => {
    if (chrome.runtime.lastError || !res?.available) {
      els.hostWarning.style.display = 'block';
    }
  });

  // UIモード読み込み
  chrome.runtime.sendMessage({ action: 'getUiMode' }, res => {
    if (res && res.mode) els.uiModeSelect.value = res.mode;
  });

  // 保存先読み込み
  chrome.runtime.sendMessage({ action: 'getSettings' }, res => {
    if (res?.settings?.outputDir) els.outputDir.value = res.settings.outputDir;
  });

  // dlListのイベント委譲（Event Delegation）によるクリック判定
  // 画面の再描画中にクリックされても無反応になるのを防ぐ
  els.dlList.addEventListener('click', e => {
    const cancelBtn = e.target.closest('.cancel-btn');
    if (cancelBtn) {
      cancelBtn.style.opacity = '0.5'; // 押した瞬間のフィードバック
      chrome.runtime.sendMessage({ action: 'cancel', id: parseInt(cancelBtn.dataset.id) });
      return;
    }
    const pauseBtn = e.target.closest('.pause-btn');
    if (pauseBtn) {
      pauseBtn.style.opacity = '0.5';
      chrome.runtime.sendMessage({ action: 'pause', id: parseInt(pauseBtn.dataset.id) });
      return;
    }
    const resumeBtn = e.target.closest('.resume-btn');
    if (resumeBtn) {
      resumeBtn.style.opacity = '0.5';
      chrome.runtime.sendMessage({ action: 'resume', id: parseInt(resumeBtn.dataset.id) });
      return;
    }
  });

  // 初回のみ取得
  updateQueue();
  chrome.runtime.onMessage.addListener(msg => {
    if (msg.action === 'queueUpdate') {
      currentTasks = msg.tasks || [];
      renderCombinedList();
    } else if (msg.action === 'historyUpdate') {
      currentHistory = msg.history || [];
      renderCombinedList();
    }
  });

  // 更新ボタン
  els.btnReload = document.getElementById('btnReload');
  if (els.btnReload) {
    els.btnReload.addEventListener('click', detectVideo);
  }

  // タブの切り替えや、YouTube内でのページ遷移（SPA）時に自動更新
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' || changeInfo.url || changeInfo.title) {
      chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
        if (tabs[0] && tabs[0].id === tabId) {
          setTimeout(detectVideo, 500); // DOM更新待ち
        }
      });
    }
  });

  chrome.tabs.onActivated.addListener(() => {
    setTimeout(detectVideo, 100);
  });

  // 初回の動画検出
  detectVideo();
}

function setupTabs() {
  els.tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      els.tabs.forEach(t => t.classList.remove('active'));
      els.pages.forEach(p => p.classList.remove('active'));
      
      tab.classList.add('active');
      document.getElementById(tab.dataset.target).classList.add('active');

      // ダウンロードタブを開いた時、念のため最新状態を同期
      if (tab.dataset.target === 'page-dl') {
        updateQueue();
      }
    });
  });
}

function setupSettings() {
  // フォーマット切り替え時の品質一覧変更
  els.formatSelect.addEventListener('change', () => {
    const isAudio = ['mp3', 'm4a'].includes(els.formatSelect.value);
    els.qualitySelect.innerHTML = isAudio
      ? `<option value="320k">320kbps</option><option value="192k" selected>192kbps</option><option value="128k">128kbps</option>`
      : `<option value="best" selected>最高品質</option><option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option>`;
  });

  // UIモード切替
  els.uiModeSelect.addEventListener('change', () => {
    chrome.runtime.sendMessage({ action: 'setUiMode', mode: els.uiModeSelect.value });
  });

  // 保存先プレースホルダ
  els.outputDir.addEventListener('change', () => {
    chrome.runtime.sendMessage({ 
      action: 'setSettings', 
      settings: { outputDir: els.outputDir.value } 
    });
  });

  // フォルダ選択ダイアログ
  if (els.btnSelectFolder) {
    els.btnSelectFolder.addEventListener('click', () => {
      chrome.runtime.sendMessage({ action: 'selectFolder' }, res => {
        if (res && res.success && res.path) {
          els.outputDir.value = res.path;
          chrome.runtime.sendMessage({ 
            action: 'setSettings', 
            settings: { outputDir: res.path } 
          });
        }
      });
    });
  }
}

// ==========================================
// 動画検出
// ==========================================
async function detectVideo() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  const url = tab.url || '';
  const isYT = url.includes('youtube.com') || url.includes('youtu.be');

  if (!isYT) {
    els.notYouTube.style.display = 'block';
    els.ytContent.style.display = 'none';
    currentPageInfo = null;
    return;
  }

  els.notYouTube.style.display = 'none';
  els.ytContent.style.display = 'block';

  // 前回の情報をクリア（キャッシュクリア）
  currentPageInfo = null; 
  els.videoTitle.textContent = '読み込み中...';
  els.thumbnailWrap.innerHTML = '<div class="loading-spinner"></div>'; 
  els.downloadBtn.disabled = true; // 検出完了までボタンを無効化
  els.downloadBtn.style.opacity = '0.5';

  els.urlInput.value = url;

  let fallbackTitle = tab.title || url;
  if (fallbackTitle.endsWith(' - YouTube')) {
    fallbackTitle = fallbackTitle.slice(0, -10);
  }

  // 自力でURLパース（拡張機能リロード等でcontent.js未ロードの場合のフォールバック用）
  let cleanUrl = url;
  let hasListParamsFallback = url.includes('list=');
  let isPlaylistOnlyFallback = false;
  try {
    const u = new URL(url);
    if (u.searchParams.has('v')) {
      cleanUrl = `https://www.youtube.com/watch?v=${u.searchParams.get('v')}`;
    }
    isPlaylistOnlyFallback = u.pathname.startsWith('/playlist') && u.searchParams.has('list');
  } catch(err) {}

  // content.jsからメタ情報取得
  try {
    const info = await chrome.tabs.sendMessage(tab.id, { action: 'getPageInfo' });
    if (info) {
      currentPageInfo = info;
      
      // プレイリスト検知
      const hasListParams = url.includes('list=') || info.playlistId;
      const isPlaylistOnly = info.isPlaylistOnly || info.isPlaylist;
      const isPlaylistDisplay = hasListParams || isPlaylistOnly;

      if (hasListParams && els.playlistOptions) {
        els.playlistOptions.style.display = 'block';
        
        els.dlPlaylistCheck.onchange = () => {
          if (els.dlPlaylistCheck.checked) {
            els.urlInput.value = url; // リスト全体のURL
            els.playlistFolderCheck.disabled = false;
            els.playlistFolderCheck.parentElement.style.color = '#fff';
          } else {
            els.urlInput.value = info.cleanUrl || url; // 単体のURL
            els.playlistFolderCheck.disabled = true;
            els.playlistFolderCheck.parentElement.style.color = '#888';
          }
        };

        if (isPlaylistOnly) {
           // 再生リスト単体ページの場合は単独DL不可なので強制ON
           els.dlPlaylistCheck.checked = true;
           els.dlPlaylistCheck.disabled = true;
           els.dlPlaylistCheck.parentElement.style.opacity = '0.7';
        } else {
           // 動画＋リストページの場合は任意選択（初期化時OFF）
           els.dlPlaylistCheck.checked = false;
           els.dlPlaylistCheck.disabled = false;
           els.dlPlaylistCheck.parentElement.style.opacity = '1';
        }
        els.dlPlaylistCheck.onchange();
      } else {
        if(els.playlistOptions) els.playlistOptions.style.display = 'none';
        els.urlInput.value = info.cleanUrl || url; // クリーンURLがある場合はそれを使う
      }

      els.videoTitle.textContent = info.title || fallbackTitle;
      els.downloadBtn.disabled = false; // 検出完了
      els.downloadBtn.style.opacity = '1';
      
      const badgeText = isPlaylistDisplay ? 'PLAYLIST' : 'VIDEO';
      const badgeHtml = `<div class="type-badge">${badgeText}</div>`;
      
      if (info.thumbnail) {
        els.thumbnailWrap.innerHTML = `<img src="${info.thumbnail}" class="thumbnail">${badgeHtml}`;
      } else {
        els.thumbnailWrap.innerHTML = `<svg viewBox="0 0 24 24" fill="#444" width="24" height="24"><path d="M8 5v14l11-7z"/></svg>${badgeHtml}`;
      }
    } else {
      throw new Error("No info");
    }
  } catch (e) {
    // page info 失敗時
    currentPageInfo = { title: fallbackTitle, thumbnail: null };
    
    if (hasListParamsFallback && els.playlistOptions) {
      els.playlistOptions.style.display = 'block';
      els.dlPlaylistCheck.onchange = () => {
        if (els.dlPlaylistCheck.checked) {
          els.urlInput.value = url;
          els.playlistFolderCheck.disabled = false;
          els.playlistFolderCheck.parentElement.style.color = '#fff';
        } else {
          els.urlInput.value = cleanUrl;
          els.playlistFolderCheck.disabled = true;
          els.playlistFolderCheck.parentElement.style.color = '#888';
        }
      };
      if (isPlaylistOnlyFallback) {
         els.dlPlaylistCheck.checked = true;
         els.dlPlaylistCheck.disabled = true;
         els.dlPlaylistCheck.parentElement.style.opacity = '0.7';
      } else {
         els.dlPlaylistCheck.checked = false;
         els.dlPlaylistCheck.disabled = false;
         els.dlPlaylistCheck.parentElement.style.opacity = '1';
      }
      els.dlPlaylistCheck.onchange();
    } else {
      if(els.playlistOptions) els.playlistOptions.style.display = 'none';
      els.urlInput.value = cleanUrl;
    }

    els.videoTitle.textContent = fallbackTitle;
    els.downloadBtn.disabled = false;
    els.downloadBtn.style.opacity = '1';
    
    const badgeText = (hasListParamsFallback || isPlaylistOnlyFallback) ? 'PLAYLIST' : 'VIDEO';
    const badgeHtml = `<div class="type-badge">${badgeText}</div>`;
    els.thumbnailWrap.innerHTML = `<svg viewBox="0 0 24 24" fill="#444" width="24" height="24"><path d="M8 5v14l11-7z"/></svg>${badgeHtml}`;
  }
}

els.forceDetectBtn.addEventListener('click', detectVideo);

// ==========================================
// ダウンロード開始
// ==========================================
function setupDownloadAction() {
  els.downloadBtn.addEventListener('click', () => {
    const url = els.urlInput.value.trim();
    if (!url) return;

    const isPlaylistDL = els.dlPlaylistCheck && els.dlPlaylistCheck.checked && els.playlistOptions.style.display !== 'none';

    chrome.runtime.sendMessage({
      action: isPlaylistDL ? 'downloadPlaylist' : 'download',
      url: url,
      title: currentPageInfo?.title || url,
      thumbnail: currentPageInfo?.thumbnail,
      format: els.formatSelect.value,
      quality: els.qualitySelect.value,
      outputDir: els.outputDir.value,
      createFolder: isPlaylistDL ? els.playlistFolderCheck.checked : false
    }, () => {
      // ダウンロードタブに自動遷移
      document.querySelector('[data-target="page-dl"]').click();
    });
  });

  // 手動ダウンロードの画質連動
  if (els.manualFormatSelect) {
    els.manualFormatSelect.addEventListener('change', () => {
      const isAudio = ['mp3', 'm4a'].includes(els.manualFormatSelect.value);
      els.manualQualitySelect.innerHTML = isAudio
        ? `<option value="320k">320kbps</option><option value="192k" selected>192kbps</option><option value="128k">128kbps</option>`
        : `<option value="best" selected>最高品質</option><option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option>`;
    });
  }

  // 手動ダウンロード開始
  if (els.manualDownloadBtn) {
    els.manualDownloadBtn.addEventListener('click', () => {
      const url = els.manualUrlInput.value.trim();
      if (!url) return;

      chrome.runtime.sendMessage({
        action: 'download',
        url: url,
        title: url, // メタデータ取得してないのでとりあえずURLをタイトルに
        thumbnail: null,
        format: els.manualFormatSelect.value,
        quality: els.manualQualitySelect.value,
        outputDir: els.outputDir.value
      }, () => {
        document.querySelector('[data-target="page-dl"]').click();
        els.manualUrlInput.value = ''; // 終わったら入力欄をクリア
      });
    });
  }

  els.btnClearCompleted.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'clearCompleted' }, () => {
       chrome.runtime.sendMessage({ action: 'clearHistory' }, () => updateQueue());
    });
  });
}

// ==========================================
// リスト描画
// ==========================================
async function updateQueue() {
  chrome.runtime.sendMessage({ action: 'getQueue' }, qRes => {
    chrome.runtime.sendMessage({ action: 'getHistory' }, hRes => {
      currentTasks = qRes?.tasks || [];
      currentHistory = hRes?.history || [];
      renderCombinedList();
    });
  });
}

function renderCombinedList() {
  const tasks = currentTasks.concat(currentHistory);
  
  // IDで重複排除し、新しい順
  const uniqueTasks = [];
  const seen = new Set();
  tasks.forEach(t => {
    if (!seen.has(t.id)) {
      seen.add(t.id);
      uniqueTasks.push(t);
    }
  });
  uniqueTasks.sort((a,b) => b.id - a.id);

  renderList(uniqueTasks);
}

function formatRelativeDate(ts) {
  if (!ts) return '過去';
  const d = new Date(ts);
  const now = new Date();
  
  // 今日の日付を0時に
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  // 昨日の日付
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  
  if (target.getTime() === today.getTime()) return '今日';
  if (target.getTime() === yesterday.getTime()) return '昨日';
  
  // それより前はMM/DD
  return `${d.getMonth()+1}/${d.getDate()}`;
}

function renderList(tasks) {
  if (tasks.length === 0) {
    els.dlList.innerHTML = `<div class="empty-msg">ダウンロード履歴がありません</div>`;
    return;
  }

  // 進行中と履歴に分ける
  const inProgress = [];
  const history = [];

  tasks.forEach(t => {
    if (t.status === 'downloading' || t.status === 'pending' || t.status === 'paused') {
      inProgress.push(t);
    } else {
      history.push(t);
    }
  });

  let html = '';

  // --- 進行中 ---
  if (inProgress.length > 0) {
    html += `<div class="list-section-title">進行中</div>`;
    inProgress.forEach(t => {
      let statCls = 'status-running';
      let statText = 'DL中';
      let pCls = '';
      
      if (t.status === 'pending') { statText = '待機'; }
      if (t.status === 'paused') { statText = '一時停止'; statCls = 'status-paused'; pCls = 'paused'; }

      let subLine = `${t.format.toUpperCase()} • ${t.percentText || (t.percent ? t.percent+'%' : '')}`;
      if (t.sizeStr) subLine += ` (${t.sizeStr})`;
      if (t.speed) subLine += ` • ${t.speed}`;

      // 各種コントロールボタン（右側に配置するためのコンテナに）
      const pauseIcon = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>`;
      const resumeIcon = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>`;
      const cancelIcon = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`;

      let ctrlBtns = '';
      if (t.status === 'downloading') {
        ctrlBtns += `<button class="ctrl-btn pause-btn" data-id="${t.id}" title="一時停止">${pauseIcon}</button>`;
      } else if (t.status === 'paused') {
        ctrlBtns += `<button class="ctrl-btn resume-btn" data-id="${t.id}" title="再開">${resumeIcon}</button>`;
      }
      ctrlBtns += `<button class="ctrl-btn cancel-btn" data-id="${t.id}" title="キャンセル">${cancelIcon}</button>`;

      html += `
        <div class="dl-item">
          <div class="dl-item-header">
            <div class="dl-title-text" title="${t.title}">${t.title}</div>
            <div class="dl-status ${statCls}">${statText}</div>
          </div>
          <div class="dl-progress-bg">
            <div class="dl-progress-fill ${pCls}" style="width:${t.percent || 0}%"></div>
          </div>
          <div class="dl-meta" style="display:flex; justify-content:space-between; align-items:center;">
            <span>${subLine}</span>
            <div class="ctrl-group" style="display:flex; gap:6px;">
              ${ctrlBtns}
            </div>
          </div>
          ${t.error ? `<div style="color:#ff6666;font-size:10px;margin-top:4px;">${t.error}</div>` : ''}
        </div>
      `;
    });
  }

  // --- 履歴 ---
  if (history.length > 0) {
    if (inProgress.length > 0) {
      html += `<div class="list-section-divider"></div>`;
    }
    
    // 完了日時(または開始日時)でグループ化
    const histGroups = {};
    history.forEach(t => {
      const gLabel = formatRelativeDate(t.completedAt || t.startedAt);
      if (!histGroups[gLabel]) histGroups[gLabel] = [];
      histGroups[gLabel].push(t);
    });

    for (const [gLabel, gTasks] of Object.entries(histGroups)) {
      html += `<div class="list-section-title">${gLabel}</div>`;
      
      gTasks.forEach(t => {
        let statCls = 'status-done';
        let statText = '完了';
        let pCls = 'done';
        
        if (t.status === 'error') { statCls = 'status-error'; pCls = 'error'; statText = 'エラー'; }
        else if (t.status === 'cancelled' || t.status === 'aborted') { statCls = ''; statText = '中止'; pCls = 'paused'; }

        let subLine = `${t.format.toUpperCase()} • ${t.percentText || (t.percent ? t.percent+'%' : '')}`;

        html += `
          <div class="dl-item">
            <div class="dl-item-header">
              <div class="dl-title-text" style="color:#bbb;" title="${t.title}">${t.title}</div>
              <div class="dl-status ${statCls}">${statText}</div>
            </div>
            <div class="dl-progress-bg" style="opacity:0.5;">
              <div class="dl-progress-fill ${pCls}" style="width:${t.percent || 0}%"></div>
            </div>
            <div class="dl-meta">
              <span>${subLine}</span>
            </div>
            ${t.error ? `<div style="color:#ff6666;font-size:10px;margin-top:4px;">${t.error}</div>` : ''}
          </div>
        `;
      });
    }
  }

  els.dlList.innerHTML = html;

}

init();
