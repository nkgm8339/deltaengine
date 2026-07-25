# Manual HFM execution decision

決定時刻: 2026-07-25 14:05 JST  
承認: ユーザー承認済み  
対象: 5M・10Mオーダーフロー研究のHFM執行経路

## 決定

HFMは、当面の実戦検証では手動執行を許容する。
自動発注APIや自動注文接続を、オーダーフローの有効性確認より先に作らない。

## 理由

- HFMはBinanceとは別市場・別法人である
- HFM source timeとlocal received timeに約3時間のずれがある
- 既存05M EpisodeにはHFM local clockがない
- 5M・10Mの観測なら、1Mより人間の執行遅延を許容できる可能性がある
- 最初に必要なのは自動化ではなく、HFM実約定で値動きが残るかの確認である

## 手動実測で分けて保存するもの

### オーダーフロー観測

- Episode ID
- checkpoint stage
- Binance event／observation time
- pressure side
- 5分・10分後のBinance事後ラベル

### 人間の執行

- signal displayed time
- human decision time
- HFM order time
- HFM fill time
- entry side
- actual fill price
- observed Bid／Ask
- observed spread
- exit time
- exit fill price
-見送り理由または未執行理由

観測上のEpisodeと、実際に手動執行した取引を同じ標本として扱わない。
見送り、判断遅延、入力ミス、約定拒否、quote staleを欠測として隠さない。

## 評価の分離

1. Binanceのオーダーフロー現象が5～10分先へ有効だったか
2. HFMへ伝わったか
3. 人間の手動執行後にもnet結果が残ったか

この3段階を分ける。手動取引の成績だけでオーダーフロー原理を否定せず、
Binance観測だけでHFM実戦性を肯定しない。

## 変更禁止

- 自動発注を追加しない
- 既存1M Flow Price Responseを変更しない
- 3段チャート、8パターン、OI、Flow Eventを変更しない
- 手動結果を既存Outcomeへ混ぜない
- 手動で利益が出る前提のentry ruleを作らない

## 次の工程

手動実測用の記録形式を先に固定する。実装する場合も、最初は
「シグナル・判断・約定・決済の監査ログ」に限定し、自動発注は対象外とする。

