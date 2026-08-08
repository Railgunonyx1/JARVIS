Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir

' Launch via PowerShell hidden window — prevents any CMD flash
strCmd = "powershell -WindowStyle Hidden -Command ""Start-Process -WindowStyle Hidden -FilePath '" & strDir & "\venv\Scripts\pythonw.exe' -ArgumentList '" & strDir & "\main.py --desktop'"""
WshShell.Run strCmd, 0, False
