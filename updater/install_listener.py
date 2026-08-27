# -*- coding: utf-8 -*-
"""เขียนไฟล์ .vbs ลง Startup folder — แยกมาเป็น Python เพราะ path มีภาษาไทย
   ซึ่ง cmd.exe เขียนไฟล์ UTF-16 เองไม่ได้"""
import os, sys, pathlib

pyw = sys.argv[1] if len(sys.argv) > 1 else "pythonw.exe"
here = pathlib.Path(__file__).resolve().parent
startup = pathlib.Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
startup.mkdir(parents=True, exist_ok=True)

vbs = (
    "' ITH Bearing Temp - Telegram acknowledge listener\r\n"
    "' Delete this file to stop it launching at logon.\r\n"
    'Set sh = CreateObject("WScript.Shell")\r\n'
    f'sh.CurrentDirectory = "{here}"\r\n'
    f'sh.Run """{pyw}"" ""{here / "telegram_listener.py"}""", 0, False\r\n'
)
target = startup / "ITH_Telegram_Listener.vbs"
target.write_text(vbs, encoding="utf-16")     # ต้อง UTF-16 ไม่งั้น VBScript อ่าน path ไทยไม่ออก
print(f"  startup entry: {target}")
