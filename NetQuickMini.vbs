' Lanza NetQuick Mini sin ninguna ventana de consola (0 = oculto).
' Portable: se ubica solo y usa pyw (Python launcher, sin consola).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\mini.py"
sh.Run "pyw """ & target & """", 0, False
