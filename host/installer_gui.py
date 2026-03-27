import os
import sys
import json
import shutil
import winreg
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# --- 設定 ---
APP_NAME = "YT Downloader"
HOST_NAME = "com.ytdownloader.host"
DEFAULT_INSTALL_DIR = str(Path(os.environ.get("LOCALAPPDATA", "C:\\")) / "YTDownloader")

class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} インストーラー")
        self.root.geometry("600x400")
        self.root.resizable(False, False)

        self.current_step = 0
        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.extension_id = tk.StringVar()

        # UI要素の初期化
        self.sidebar = None
        self.banner_canvas = None
        self.banner_img = None
        self.content_frame = None
        self.footer = None
        self.btn_back = None
        self.btn_next = None
        self.btn_cancel = None
        self.progress = None

        # スタイル設定
        self.style = ttk.Style()
        self.style.configure("Header.TLabel", font=("Helvetica", 14, "bold"))
        self.style.configure("Step.TFrame", background="white")

        self.setup_ui()

    def setup_ui(self):
        # メインコンテナの重み設定
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # 左側のサイドバー (行0, 列0)
        self.sidebar = tk.Frame(self.root, width=150, bg="#2c3e50")
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        # バナー画像用の領域
        self.banner_canvas = tk.Canvas(self.sidebar, width=150, height=400, bg="#2c3e50", highlightthickness=0)
        self.banner_canvas.pack(fill="both", expand=True)
        
        # メインコンテンツエリア (行0, 列1)
        self.content_frame = tk.Frame(self.root, bg="white")
        self.content_frame.grid(row=0, column=1, sticky="nsew")

        # 画面下部のボタンエリア (行1, 列0-1)
        self.footer = tk.Frame(self.root, height=50, bg="#f0f0f0", bd=1, relief="raised")
        self.footer.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.btn_cancel = ttk.Button(self.footer, text="キャンセル", command=self.root.destroy)
        self.btn_cancel.pack(side="left", padx=15, pady=10)

        self.btn_next = ttk.Button(self.footer, text="次へ", command=self.next_step)
        self.btn_next.pack(side="right", padx=15, pady=10)

        self.btn_back = ttk.Button(self.footer, text="戻る", command=self.prev_step, state="disabled")
        self.btn_back.pack(side="right", padx=5, pady=10)

        self.show_step()

    def show_step(self):
        # コンテンツのクリア
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        if self.current_step == 0:
            self.step_welcome()
        elif self.current_step == 1:
            self.step_select_dir()
        elif self.current_step == 2:
            self.step_extension_id()
        elif self.current_step == 3:
            self.step_confirm()
        elif self.current_step == 4:
            self.step_installing()
        elif self.current_step == 5:
            self.step_finish()

    def next_step(self):
        if self.current_step == 2 and not self.extension_id.get().strip():
            messagebox.showwarning("警告", "拡張機能のIDを入力してください。")
            return
        
        if self.current_step < 5:
            self.current_step += 1
            self.show_step()
            self.update_buttons()

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.show_step()
            self.update_buttons()

    def update_buttons(self):
        self.btn_back.config(state="normal" if 0 < self.current_step < 4 else "disabled")
        if self.current_step == 3:
            self.btn_next.config(text="インストール")
        elif self.current_step == 4:
            self.btn_next.config(state="disabled")
        elif self.current_step == 5:
            self.btn_next.config(text="完了", state="normal", command=self.root.destroy)
            self.btn_back.config(state="disabled")
            self.btn_cancel.config(state="disabled")
        else:
            self.btn_next.config(text="次へ", state="normal", command=self.next_step)

    # --- 各ステップのUI ---

    def step_welcome(self):
        self.content_frame.columnconfigure(0, weight=1)
        
        lbl = tk.Label(self.content_frame, text=f"{APP_NAME} へようこそ", font=("Helvetica", 16, "bold"), bg="white", fg="#2c3e50")
        lbl.grid(row=0, column=0, sticky="w", padx=30, pady=(40, 20))
        
        desc = tk.Label(self.content_frame, text=f"このウィザードは {APP_NAME} をコンピュータにインストールします。\n\n「次へ」をクリックして進んでください。", 
                        justify="left", bg="white", font=("Helvetica", 10))
        desc.grid(row=1, column=0, sticky="nw", padx=30)

    def step_select_dir(self):
        lbl = ttk.Label(self.content_frame, text="インストール先の選択", style="Header.TLabel", background="white")
        lbl.pack(anchor="w", padx=20, pady=20)

        lbl2 = ttk.Label(self.content_frame, text="インストールするフォルダを選択してください。", background="white")
        lbl2.pack(anchor="w", padx=20, pady=5)

        frm = tk.Frame(self.content_frame, bg="white")
        frm.pack(fill="x", padx=20, pady=10)

        ent = ttk.Entry(frm, textvariable=self.install_dir, width=40)
        ent.pack(side="left", padx=5)

        btn = ttk.Button(frm, text="参照...", command=self.browse_dir)
        btn.pack(side="left")

    def browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.install_dir.get())
        if d:
            self.install_dir.set(d)

    def step_extension_id(self):
        lbl = ttk.Label(self.content_frame, text="拡張機能IDの設定", style="Header.TLabel", background="white")
        lbl.pack(anchor="w", padx=20, pady=20)

        lbl2 = ttk.Label(self.content_frame, text="ブラウザの拡張機能ページで、IDを確認して入力してください。", background="white")
        lbl2.pack(anchor="w", padx=20, pady=5)

        ent = ttk.Entry(self.content_frame, textvariable=self.extension_id, width=40)
        ent.pack(padx=20, pady=10)

        btn = ttk.Button(self.content_frame, text="拡張機能ページを開く", command=lambda: os.startfile("chrome://extensions/"))
        btn.pack(padx=20, pady=5)
        
        tip = ttk.Label(self.content_frame, text="※デベロッパーモードをONにするとIDが表示されます。", font=("Helvetica", 8), background="white")
        tip.pack(padx=20, pady=5)

    def step_confirm(self):
        lbl = ttk.Label(self.content_frame, text="インストールの準備完了", style="Header.TLabel", background="white")
        lbl.pack(anchor="w", padx=20, pady=20)

        info = f"インストール先:\n{self.install_dir.get()}\n\n拡張機能ID:\n{self.extension_id.get()}\n\n「インストール」をクリックして開始します。"
        lbl2 = ttk.Label(self.content_frame, text=info, background="white", justify="left")
        lbl2.pack(anchor="w", padx=20, pady=10)

    def step_installing(self):
        lbl = ttk.Label(self.content_frame, text="インストール中...", style="Header.TLabel", background="white")
        lbl.pack(anchor="w", padx=20, pady=20)

        self.progress = ttk.Progressbar(self.content_frame, length=300, mode='determinate')
        self.progress.pack(padx=20, pady=20)

        self.root.after(500, self.do_install)

    def step_finish(self):
        lbl = ttk.Label(self.content_frame, text="インストールの完了", style="Header.TLabel", background="white")
        lbl.pack(anchor="w", padx=20, pady=20)

        lbl2 = ttk.Label(self.content_frame, text="インストールが正常に終了しました。\nブラウザで拡張機能を読み込み、ページを更新してください。", background="white")
        lbl2.pack(anchor="w", padx=20, pady=10)

    # --- インストール処理 ---

    def do_install(self):
        try:
            target = Path(self.install_dir.get())
            target.mkdir(parents=True, exist_ok=True)
            self.progress['value'] = 10
            self.root.update()

            # 元のソースの場所（このインストーラーがある場所を基準にする）
            src_base = Path(__file__).parent.parent.resolve()
            
            # 各フォルダ・ファイルのコピー
            shutil.copytree(src_base / "extension", target / "extension", dirs_exist_ok=True)
            shutil.copytree(src_base / "host", target / "host", dirs_exist_ok=True)
            self.progress['value'] = 40
            self.root.update()

            # マニフェストの更新
            manifest_path = target / "host" / "host_manifest.json"
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            runner_path = str(target / "host" / "host_runner.bat")
            manifest["path"] = runner_path
            manifest["allowed_origins"] = [f"chrome-extension://{self.extension_id.get()}/"]

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            
            self.progress['value'] = 60
            self.root.update()

            # host_runner.batの更新（Pythonパスとスクリプトパスの解決）
            runner_content = f'@echo off\n"{sys.executable}" "{target / "host" / "host.py"}"\n'
            with open(runner_path, "w", encoding="utf-8") as f:
                f.write(runner_content)

            self.progress['value'] = 80
            self.root.update()

            # レジストリへの登録
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))
            
            # アンインストーラーの書き出し（簡易版）
            self.create_uninstaller(target)

            self.progress['value'] = 100
            self.root.update()
            
            self.next_step()

        except Exception as e:
            messagebox.showerror("エラー", f"インストール中にエラーが発生しました:\n{str(e)}")
            self.root.destroy()

    def create_uninstaller(self, target):
        uninst_script = target / "uninstaller.py"
        content = f"""import os, winreg, shutil
HOST_NAME = "{HOST_NAME}"
INSTALL_DIR = r"{target}"

def uninstall():
    try:
        # レジストリ削除
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"Software\\\\Google\\\\Chrome\\\\NativeMessagingHosts\\\\{{HOST_NAME}}")
        except FileNotFoundError: pass

        print("アンインストール完了。フォルダを削除してください。")
        # 自分自身を消すのは難しいので案内のみか、バッチファイルへ逃がす
    except Exception as e:
        print(f"Error: {{e}}")

if __name__ == "__main__":
    uninstall()
"""
        with open(uninst_script, "w", encoding="utf-8") as f:
            f.write(content)

if __name__ == "__main__":
    print("Initializing Tkinter...")
    try:
        root = tk.Tk()
        print("Tkinter root created.")
        app = InstallerApp(root)
        print("Starting mainloop...")
        root.mainloop()
    except Exception as e:
        print(f"Error during execution: {e}")
        import traceback
        traceback.print_exc()
