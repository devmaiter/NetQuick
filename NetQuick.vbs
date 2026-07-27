' Launches NetQuick without any console window (0 = hidden).
' Portable: it locates itself and uses pythonw (no console).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\netquick.py"
sh.Run "pythonw """ & target & """", 0, False
