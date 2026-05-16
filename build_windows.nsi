; SCATT Companion — Windows インストーラ (NSIS)
; 使い方:
;   makensis /DAPP_VERSION=0.4.12 build_windows.nsi
;   → dist/SCATT-Companion-Setup-0.4.12.exe

!ifndef APP_VERSION
  !define APP_VERSION "0.4.12"
!endif
!define APP_NAME    "SCATT Companion"
!define PUBLISHER   "Kai Tabata"
!define APP_ID      "scatt-companion"
!define MAIN_EXE    "SCATT Companion.exe"
!define INSTALL_DIR_NAME "SCATT Companion"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

SetCompressor /SOLID lzma
Unicode True

Name "${APP_NAME} ${APP_VERSION}"
OutFile "dist\SCATT-Companion-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\${INSTALL_DIR_NAME}"
InstallDirRegKey HKCU "Software\${APP_ID}" "InstallDir"
RequestExecutionLevel user      ; 管理者権限不要 (per-user インストール)
ShowInstDetails show
ShowUninstDetails show

;------ Modern UI ------
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${MAIN_EXE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "English"

;------ メインセクション ------
Section "Install"
  SetOutPath "$INSTDIR"
  ; PyInstaller の COLLECT 結果 (dist/SCATT Companion/ 配下) を全コピー
  File /r "dist\SCATT Companion\*.*"

  ; スタートメニュー ショートカット
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                 "$INSTDIR\${MAIN_EXE}" "" "$INSTDIR\${MAIN_EXE}" 0
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\アンインストール.lnk" \
                 "$INSTDIR\uninstall.exe"

  ; デスクトップ ショートカット
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
                 "$INSTDIR\${MAIN_EXE}" "" "$INSTDIR\${MAIN_EXE}" 0

  ; アンインストーラ書き出し
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; レジストリ: アンインストール情報 + インストールパス記録
  WriteRegStr HKCU "Software\${APP_ID}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon"     "$INSTDIR\${MAIN_EXE}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

;------ アンインストールセクション ------
Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\アンインストール.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"

  ; インストールディレクトリ丸ごと削除
  RMDir /r "$INSTDIR"

  ; レジストリクリーンアップ
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  DeleteRegKey /ifempty HKCU "Software\${APP_ID}"

  ; ユーザーデータ (extra.db、profiles) は残す方針
  ; (削除したい場合は手動で %APPDATA%\scatt-companion を削除する旨を表示)
  MessageBox MB_OK "アンインストール完了。$\r$\n$\r$\nユーザー設定・補助 DB (心拍履歴) は %APPDATA%\scatt-companion に残してあります。完全に削除する場合は手動で削除してください。"
SectionEnd
