' Creates a "Jadeit" shortcut on the Desktop (Windows 7 / 8 / 10 / 11)
Option Explicit
Dim sh, fso, here, desktop, lnk
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FileExists(here & "\Jadeit.exe") Then
  MsgBox "Jadeit.exe was not found next to this file. Extract the whole ZIP first.", 16, "Jadeit"
  WScript.Quit 1
End If
desktop = sh.SpecialFolders("Desktop")
Set lnk = sh.CreateShortcut(desktop & "\Jadeit.lnk")
lnk.TargetPath = here & "\Jadeit.exe"
lnk.WorkingDirectory = here
lnk.IconLocation = here & "\Jadeit.exe, 0"
lnk.Description = "Jadeit - customer accounts"
lnk.Save
MsgBox "A shortcut named ""Jadeit"" was created on your Desktop.", 64, "Jadeit"
