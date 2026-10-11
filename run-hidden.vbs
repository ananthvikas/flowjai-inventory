' run-hidden.vbs - runs flowjai-service.ps1 with no window at all.
' Task Scheduler calls this so the 2-minute watchdog doesn't flash a console.
'   wscript.exe run-hidden.vbs check|start|stop|restart
Dim sh, fso, here, action
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
action = "check"
If WScript.Arguments.Count > 0 Then action = WScript.Arguments(0)
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & here & "\flowjai-service.ps1"" " & action, 0, False
