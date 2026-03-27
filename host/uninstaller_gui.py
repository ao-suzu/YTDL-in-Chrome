import os
import sys
import winreg
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# --- 設定 ---
APP_NAME = "YT Downloader"
HOST_NAME = "com.ytdownloader.host"

class UninstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} アンインストーラー")
        self.root.geometry("500x300")
        self.root.resizable(False, False)

        # カレントディレクトリが自分のある場所
        self.install_dir = Path(__file__).parent.resolve()

        self.setup_ui()

    def setup_ui(self):
        frm = tk.Frame(self.root, bg="white")
        frm.pack(fill="both", expand=True)

        lbl = ttk.Label(frm, text=f"{APP_NAME} アンインストール", font=("Helvetica", 14, "bold"), background="white")
        lbl.pack(padx=20, pady=20)

        lbl2 = ttk.Label(frm, text=f"{APP_NAME} をコンピュータから削除しますか？\n(レジストリ設定とプログラムファイルが削除されます)", background="white")
        lbl2.pack(padx=20, pady=10)

        footer = tk.Frame(self.root, height=50)
        footer.pack(side="bottom", fill="x")

        self.btn_uninst = ttk.Button(footer, text="アンインストール", command=self.do_uninstall)
        self.btn_uninst.pack(side="right", padx=10, pady=10)

        self.btn_cancel = ttk.Button(footer, text="キャンセル", command=self.root.destroy)
        self.btn_cancel.pack(side="right", padx=5, pady=10)

    def do_uninstall(self):
        if not messagebox.askyesno("確認", "本当にアンインストールしますか？"):
            return

        try:
            # 1. レジストリ削除
            reg_path = f"Software\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}"
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path)
            except FileNotFoundError:
                pass
            
            messagebox.showinfo("完了", "設定の削除が完了しました。\nこのウィンドウを閉じた後、インストールフォルダを手動で削除してください。")
            self.root.destroy()

        except Exception as e:
            messagebox.showerror("エラー", f"アンインストール中にエラーが発生しました:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = UninstallerApp(root)
    root.mainloop()
