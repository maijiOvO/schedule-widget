' 双击启动日程组件（不弹黑框）。开机自启由 安装到这台电脑.bat 配置。
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
On Error Resume Next
sh.Run "pythonw """ & here & "\widget.py""", 0, False
If Err.Number <> 0 Then
    MsgBox "启动失败：找不到 Python。" & vbCrLf & vbCrLf & _
           "先运行同目录下的「安装到这台电脑.bat」。", 48, "日程组件"
End If
