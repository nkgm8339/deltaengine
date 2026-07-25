# MT5 signal bridge checkpoint

実装日: 2026-07-25

`tools/write_hfm_order_command.py` を追加した。これはDeltaEngineのシグナルを直接発注せず、検証済みのコマンドファイルへ原子的に出力する境界である。

入力は `command_id`, `side`, `stop_loss`, `take_profit`。BUY/SELL以外、SLなし、負の価格、重複しうる空IDは拒否する。MT5 EAはこのファイルを読み、初期状態ではSHADOW記録だけを行う。

現時点で、Flow Price Responseの観測イベントをそのまま売買シグナルとして接続していない。既存コード自身が同イベントを「観測状態でありtrade signalではない」と定義しているため、シグナル条件を別途明示するまで自動発注経路は開かない。

次の検証順序:

1. Python側コマンド生成テスト
2. MetaEditorでEAコンパイル
3. MT5デモ口座でSHADOW確認
4. デモで注文・SL・緊急停止確認
5. シグナル条件を明示承認後にのみ接続

LIVE有効化はこのcheckpointの完了条件に含めない。
