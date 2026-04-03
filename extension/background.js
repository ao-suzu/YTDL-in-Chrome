// background.js - YT Downloader Service Worker
// ダウンロードキューをバックグラウンドで管理し、popup/sidebar閉じても継続

const HOST_NAME = 'com.ytdownloader.host';
const VERSION = '1.1.0';
const MAX_CONCURRENT = 1; // 同時ダウンロード制限（1本ずつ処理でffmpeg変換が最速）

// ========================================
// 状態管理（メモリ + storage）
// ========================================

// ダウンロード状態をメモリで管理（service workerのライフタイム内）
const downloadQueue = new Map(); // id -> DownloadTask
let nextId = 1;
let historyCache = []; // ディスク（Storage）アクセスを減らすためのキャッシュ

// ダウンロードタスクの構造:
// { id, url, title, format, quality, outputDir, status, percent, speed, eta, path, error, startedAt, completedAt }

// 状態をstorageに永続化
async function persistState() {
  const tasks = Array.from(downloadQueue.values()).map(t => ({
    ...t,
    // port は保存しない
    _port: undefined,
  }));
  await chrome.storage.local.set({ downloadQueue: tasks });
}

// storage から状態を復元（SW再起動後）
async function restoreState() {
  const { downloadQueue: saved, downloadHistory: hist } = await chrome.storage.local.get(['downloadQueue', 'downloadHistory']);
  if (hist) historyCache = hist;

  if (!saved) return;
  for (const task of saved) {
    // 実行中だったものは中断状態に変更
    if (task.status === 'downloading' || task.status === 'pending') {
      task.status = 'aborted';
    }
    downloadQueue.set(task.id, task);
    if (task.id >= nextId) nextId = task.id + 1;
  }
}

// 全UIページへ状態をブロードキャスト
function broadcast(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {});
}

// ========================================
// ダウンロード処理
// ========================================


function getActiveCount() {
  return Array.from(downloadQueue.values()).filter(t => t.status === 'downloading').length;
}

async function startDownload(task) {
  task.status = 'pending';
  downloadQueue.set(task.id, task);
  broadcast({ action: 'queueUpdate', tasks: getTaskList() });
  await persistState();
  processQueue();
}

// キューを処理する
async function processQueue() {
  if (getActiveCount() >= MAX_CONCURRENT) return;

  // 古い順（ID順）に待機中のタスクを探す
  const pendingTasks = Array.from(downloadQueue.values())
    .filter(t => t.status === 'pending')
    .sort((a, b) => a.id - b.id);

  if (pendingTasks.length === 0) return;

  // 上限に達するまで開始
  for (const task of pendingTasks) {
    if (getActiveCount() >= MAX_CONCURRENT) break;
    await startDownloadProcess(task);
  }
}

async function startDownloadProcess(task) {
  let port;
  try {
    port = chrome.runtime.connectNative(HOST_NAME);
  } catch (e) {
    task.status = 'error';
    task.error = 'Native Hostに接続できません。install.bat を実行してください。';
    broadcast({ action: 'queueUpdate', tasks: getTaskList() });
    await persistState();
    return;
  }

  task.status = 'downloading';
  task._port = port;
  broadcast({ action: 'queueUpdate', tasks: getTaskList() });
  await persistState();

  port.onMessage.addListener(async (msg) => {
    if (msg.type === 'progress') {
      task.percent = msg.percentNum || 0;
      task.speed   = msg.speed || '';
      task.eta     = msg.eta || '';
      task.percentText = msg.percent || '';
      if (msg.sizeStr) task.sizeStr = msg.sizeStr;
      
      broadcast({ action: 'queueUpdate', tasks: getTaskList() });
    } else if (msg.type === 'done') {
      if (msg.success) {
        task.status = 'done';
        task.path   = msg.path || '';
        task.percent = 100;
        task.completedAt = Date.now();
      } else {
        task.status = 'error';
        task.error  = msg.error || '不明なエラー';
      }
      task._port = null;
      broadcast({ action: 'queueUpdate', tasks: getTaskList() });
      await persistState();
      await appendHistory(task);
      port.disconnect();
      processQueue();
    }
  });

  port.onDisconnect.addListener(async () => {
    if (task.status === 'downloading' || task.status === 'pending') {
      task.status = 'error';
      task.error  = chrome.runtime.lastError?.message || '接続が切断されました';
      task._port = null;
      broadcast({ action: 'queueUpdate', tasks: getTaskList() });
      await persistState();
      processQueue();
    }
  });

  port.postMessage({
    action: 'download',
    url:       task.url,
    format:    task.format,
    quality:   task.quality,
    outputDir: task.outputDir || null,
  });
}

function getTaskList() {
  return Array.from(downloadQueue.values()).map(t => {
    const { _port, ...rest } = t;
    return rest;
  });
}

async function cancelDownload(id) {
  const task = downloadQueue.get(id);
  if (!task) return;
  if (task._port) {
    try { task._port.disconnect(); } catch {}
    task._port = null;
  }
  task.status = 'cancelled';
  broadcast({ action: 'queueUpdate', tasks: getTaskList() });
  await persistState();
  processQueue();
}

async function clearCompleted() {
  for (const [id, task] of downloadQueue.entries()) {
    if (['done', 'error', 'cancelled', 'aborted'].includes(task.status)) {
      downloadQueue.delete(id);
    }
  }
  broadcast({ action: 'queueUpdate', tasks: getTaskList() });
  await persistState();
}

// ========================================
// 履歴管理
// ========================================

async function appendHistory(task) {
  const { _port, ...clean } = task;
  historyCache.unshift(clean);
  // 最大100件
  historyCache = historyCache.slice(0, 100);
  await chrome.storage.local.set({ downloadHistory: historyCache });
  broadcast({ action: 'historyUpdate', history: historyCache });
}

async function getHistory() {
  return historyCache;
}

async function clearHistory() {
  historyCache = [];
  await chrome.storage.local.set({ downloadHistory: [] });
  broadcast({ action: 'historyUpdate', history: [] });
}

// ========================================
// ポップアップ / サイドバー切替
// ========================================

async function getUiMode() {
  const { uiMode = 'popup' } = await chrome.storage.local.get('uiMode');
  return uiMode;
}

async function setUiMode(mode) {
  await chrome.storage.local.set({ uiMode: mode });
  if (mode === 'sidebar') {
    // アイコンクリック時にサイドバーを開く
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
    // action は popup なし
    chrome.action.setPopup({ popup: '' });
  } else {
    // popup モード
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false });
    chrome.action.setPopup({ popup: 'panel.html' });
  }
}

// ========================================
// メッセージハンドラ
// ========================================

chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  handle(req, sendResponse);
  return true;
});

async function handle(req, sendResponse) {
  try {
    switch (req.action) {

      case 'ping': {
        // Native host の接続チェック
        let port;
        try {
          port = chrome.runtime.connectNative(HOST_NAME);
          port.onMessage.addListener(msg => {
            sendResponse({ available: true, version: msg.version });
            port.disconnect();
          });
          port.onDisconnect.addListener(() => sendResponse({ available: false }));
          port.postMessage({ action: 'ping' });
        } catch {
          sendResponse({ available: false });
        }
        break;
      }

      case 'download': {
        const task = {
          id:          nextId++,
          url:         req.url,
          title:       req.title || req.url,
          thumbnail:   req.thumbnail || null,
          format:      req.format   || 'mp3',
          quality:     req.quality  || '192k',
          outputDir:   req.outputDir || null,
          status:      'pending',
          percent:     0,
          percentText: '0%',
          speed:       '',
          eta:         '',
          path:        '',
          error:       '',
          startedAt:   Date.now(),
          completedAt: null,
          _port:       null,
        };
        downloadQueue.set(task.id, task);
        startDownload(task); // 非同期で開始
        sendResponse({ success: true, id: task.id });
        break;
      }

      case 'downloadPlaylist': {
        const { url, format, quality, outputDir, createFolder } = req;
        
        // 情報取得中のプレースホルダー（ダミー）タスクを表示させる
        const mockTaskId = nextId++;
        const mockTask = {
          id:          mockTaskId,
          url:         url,
          title:       'プレイリスト情報の取得中...',
          thumbnail:   null,
          format:      format   || 'mp3',
          quality:     quality  || '192k',
          outputDir:   outputDir || null,
          status:      'pending',
          percent:     0,
          percentText: '0%',
          speed:       '',
          eta:         '',
          path:        '',
          error:       '',
          startedAt:   Date.now(),
          completedAt: null,
          _port:       null,
        };
        downloadQueue.set(mockTaskId, mockTask);
        broadcast({ action: 'queueUpdate', tasks: getTaskList() });

        // Native Hostにプレイリスト情報を要求
        try {
          const port = chrome.runtime.connectNative(HOST_NAME);
          port.onMessage.addListener(msg => {
            downloadQueue.delete(mockTaskId); // ダミーを削除

            if (msg.type === 'playlistData') {
              const entries = msg.entries || [];
              let finalOutputDir = outputDir;
              
              if (createFolder && finalOutputDir) {
                // サニタイズ（Windows用）
                const safeTitle = (msg.title || 'Playlist').replace(/[<>:"/\\|?*]/g, '_');
                // 簡易的なパス結合 (末尾のスラッシュ等考慮)
                if (finalOutputDir.endsWith('\\') || finalOutputDir.endsWith('/')) {
                  finalOutputDir += safeTitle;
                } else {
                  finalOutputDir += '\\' + safeTitle;
                }
              }

              for (const entry of entries) {
                const task = {
                  id:          nextId++,
                  url:         entry.url,
                  title:       entry.title || entry.url,
                  thumbnail:   null, // 一旦null
                  format:      format   || 'mp3',
                  quality:     quality  || '192k',
                  outputDir:   finalOutputDir || null,
                  status:      'pending',
                  percent:     0,
                  percentText: '0%',
                  speed:       '',
                  eta:         '',
                  path:        '',
                  error:       '',
                  startedAt:   Date.now(),
                  completedAt: null,
                  _port:       null,
                };
                downloadQueue.set(task.id, task);
                startDownload(task);
              }
              broadcast({ action: 'queueUpdate', tasks: getTaskList() });
            }
            port.disconnect();
          });
          port.postMessage({ action: 'getPlaylist', url: url });
          sendResponse({ success: true }); // 受け付け完了
        } catch(e) {
          downloadQueue.delete(mockTaskId);
          broadcast({ action: 'queueUpdate', tasks: getTaskList() });
          sendResponse({ success: false, error: e.message });
        }
        break;
      }

      case 'getQueue': {
        sendResponse({ tasks: getTaskList() });
        break;
      }

      case 'pause': {
        const task = downloadQueue.get(req.id);
        if (task && task.status === 'downloading') {
          if (task._port) {
            task._port.disconnect();
            task._port = null;
          }
          task.status = 'paused';
          task.speed = '';
          task.eta = '';
          persistState();
          broadcast({ action: 'queueUpdate', tasks: getTaskList() });
        }
        sendResponse({ success: true });
        break;
      }

      case 'resume': {
        const task = downloadQueue.get(req.id);
        if (task && task.status === 'paused') {
          startDownload(task);
          sendResponse({ success: true });
        } else {
          sendResponse({ success: false });
        }
        break;
      }

      case 'cancel': {
        await cancelDownload(req.id);
        sendResponse({ success: true });
        break;
      }

      case 'clearCompleted': {
        await clearCompleted();
        sendResponse({ success: true });
        break;
      }

      case 'getHistory': {
        const history = await getHistory();
        sendResponse({ history });
        break;
      }

      case 'clearHistory': {
        await clearHistory();
        sendResponse({ success: true });
        break;
      }

      case 'getUiMode': {
        const mode = await getUiMode();
        sendResponse({ mode });
        break;
      }

      case 'setUiMode': {
        await setUiMode(req.mode);
        sendResponse({ success: true });
        break;
      }

      case 'getSettings': {
        const { settings = defaultSettings() } = await chrome.storage.local.get('settings');
        sendResponse({ settings });
        break;
      }

      case 'setSettings': {
        await chrome.storage.local.set({ settings: req.settings });
        sendResponse({ success: true });
        break;
      }

      case 'selectFolder': {
        try {
          const port = chrome.runtime.connectNative(HOST_NAME);
          port.onMessage.addListener(msg => {
            if (msg.type === 'folderSelected') {
              sendResponse({ success: true, path: msg.path });
            } else {
              sendResponse({ success: false });
            }
            port.disconnect();
          });
          port.onDisconnect.addListener(() => {
            if (chrome.runtime.lastError) sendResponse({ success: false });
          });
          port.postMessage({ action: 'selectFolder' });
        } catch {
          sendResponse({ success: false });
        }
        break;
      }

      default:
        sendResponse({ error: `Unknown action: ${req.action}` });
    }
  } catch (e) {
    sendResponse({ error: e.message });
  }
}

function defaultSettings() {
  return {
    defaultFormat:  'mp3',
    defaultQuality: '192k',
    outputDir:      '',
    saveHistory:    true,
    historyMax:     100,
    autoCleanDays:  30,
  };
}

// ========================================
// 初期化
// ========================================

chrome.runtime.onInstalled.addListener(async () => {
  await restoreState();
  const mode = await getUiMode();
  await setUiMode(mode);
});

// SW起動時にも復元
(async () => {
  await restoreState();
  const mode = await getUiMode();
  await setUiMode(mode);
})();
