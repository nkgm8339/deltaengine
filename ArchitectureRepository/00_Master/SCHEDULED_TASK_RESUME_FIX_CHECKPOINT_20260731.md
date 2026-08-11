# Scheduled Task resume checkpoint

- 対象: `Delta_Engine_Pro4web/tools/windows/resume_hook_capture.ps1`
- 完了: 旧stage2a/stage2b compose選択、旧image固定起動、`--no-build`を削除。固定project rootから `docker compose up -d` に統一。
- 維持: Docker待機300秒、health待機1200秒、boot artifact、coverage integrity検証、C空き記録、mutex/error handling。
- 禁止対象: hook_thresholds.yaml、playbooks.yaml、UI、収録データ、稼働中コンテナは変更なし。
- backup: `C:\tmp\resume_hook_capture.ps1.bak.20260731`（SHA-256 `C5D29888ACF62F0F10C60976DE83E20C5DE2869C7BFB278C2E0DBE2B912FD218`）。
- 検証: PowerShell parser `PARSE_OK`、Scheduled Task actionは修正後scriptを参照。pytest `773 passed, 1 skipped, 1 known UI failure`。
- 未完了: scriptの限定コミットとcommit後確認。
