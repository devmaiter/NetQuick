' Lanza NetQuick sin ninguna ventana de consola (0 = oculto).
' Portable: se ubica solo y usa pythonw (sin consola).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target = scriptDir & "\netquick.py"
sh.Run "pythonw """ & target & """", 0, False
