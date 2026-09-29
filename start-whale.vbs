' WorkBuddy credit whale widget - double-click this file to start it.
' Kept ASCII-only with CRLF line endings on purpose: a UTF-8 .vbs makes the
' script host decode it as ANSI, eat the line break after each Chinese char,
' and merge the following code line into the comment -> 'ws' undefined.
' Every path is resolved at run time, so this folder can sit anywhere.
Option Explicit

Dim fso, ws, here, py, cands, i, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
ws.CurrentDirectory = here

cands = Array( _
    here & "\.venv\Scripts\pythonw.exe", _
    here & "\pythonw.exe", _
    ws.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"), _
    ws.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"), _
    ws.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"), _
    ws.ExpandEnvironmentStrings("%USERPROFILE%\anaconda3\pythonw.exe"), _
    ws.ExpandEnvironmentStrings("%USERPROFILE%\miniconda3\pythonw.exe"), _
    "C:\anaconda\pythonw.exe", _
    "C:\ProgramData\anaconda3\pythonw.exe", _
    "C:\ProgramData\miniconda3\pythonw.exe" _
)

py = ""
For i = 0 To UBound(cands)
    If py = "" Then
        If fso.FileExists(cands(i)) Then py = cands(i)
    End If
Next

If py = "" Then
    MsgBox "No pythonw.exe found on this machine." & vbCrLf & vbCrLf & _
           "Install Python 3 from https://www.python.org/downloads/ and tick" & vbCrLf & _
           """Add python.exe to PATH"" during setup. Then double-click setup.bat" & vbCrLf & _
           "once to install the dependencies." & vbCrLf & vbCrLf & _
           "Already installed somewhere unusual? Drop its pythonw.exe next to" & vbCrLf & _
           "whale.py and start again.", 48, "WorkBuddy Whale"
    WScript.Quit 1
End If

cmd = """" & py & """ """ & here & "\whale.py"""
ws.Run cmd, 0, False
