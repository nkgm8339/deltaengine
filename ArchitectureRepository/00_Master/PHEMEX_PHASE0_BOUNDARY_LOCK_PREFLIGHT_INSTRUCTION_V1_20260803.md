# Phemex統合 Phase 0 Boundary Lock / Preflight 実施指示書

**文書ID:** DE05M-PHEMEX-PHASE0-INSTR-001

**版:** 1.0

**作成日:** 2026-08-03

**対象リポジトリ:** DeltaEngine05M

**対象Phase:** Phase 0 — Boundary Lock / Preflight

**文書状態:** Phase 0実行GO待ち

**本書作成で承認された範囲:** 指示書作成のみ

---

## 1. 正本と優先順位

本指示書の仕様正本は次のfileである。

```text
ArchitectureRepository/00_Master/PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md
```

Phase 0開始時に、正本の実SHA-256が次と一致することを確認する。

```text
bd965d88d6c649df51f4e34ea1e1968808b91c830a5b4d52d8bbb37939a9a7ba
```

不一致の場合は、異なる版の仕様書を前提に作業してはならない。Phase 0を開始せず、実SHA-256、
bytes、LF行数、4行目の版番号を報告して停止する。

本指示書と正本が衝突する場合、ユーザーの最新の明示指示、正本§0、その他の正本記載、
本指示書の順で優先する。本指示書は正本の変更許可範囲を拡張しない。

---

## 2. Phase 0の目的と完了状態

Phase 0の目的は、Phemex実装を開始することではない。現在のdirty worktree、変更可能境界、
hard protected領域、実行環境、Phase 1の予定file、配布defaultに依存する既存testを、最初の
production変更より前に証拠付きで固定することである。

Phase 0完了時の状態は次のとおりとする。

```text
production code change: 0
test change: 0
config change: 0
runtime/deployment change: 0
network connection change: 0
order/API credential operation: 0
Phase 1 implementation: 0
allowed write: PHEMEX_IMPLEMENTATION_CHECKPOINT.md only
```

Phase 0の成果は、次のcheckpoint一つへ集約する。

```text
ArchitectureRepository/00_Master/PHEMEX_IMPLEMENTATION_CHECKPOINT.md
```

checkpointを提示した時点で停止する。Phase 1へ自動進行してはならない。

---

## 3. 承認境界

### 3.1 Phase 0実行に必要なGO

本指示書の作成または承認は、Phase 0実行のGOではない。ユーザーからPhase 0開始の明示指示を
受けた後に限り、本書の読取調査とcheckpoint作成を実行する。

### 3.2 唯一の変更可能file

Phase 0実行中に作成または更新できるfileは次だけである。

```text
ArchitectureRepository/00_Master/PHEMEX_IMPLEMENTATION_CHECKPOINT.md
```

調査用script、CSV、JSON、hash manifest、一時test、fixtureをリポジトリ内へ新規作成してはならない。
hash manifest、棚卸し表、command結果はcheckpoint本文へ記録する。OSの一時領域を使用する場合も、
終了前に残存物と影響を確認し、checkpointへ記録する。

### 3.3 変更禁止

Phase 0では、次を一切変更しない。

- `Delta_Engine_Pro4web/**`配下のproduction code、test、config、fixture、data
- 正本仕様書と既存ArchitectureRepository文書
- `.git/**`、index、branch、commit、tag、remote
- Docker image、container、volume、Compose runtime
- Windows Scheduled Task、MT5/HFM、環境変数、credential store
- Phemex/Binanceへの接続状態

`git add`、`git commit`、`git push`、branch操作、stash、checkout、reset、cleanを実行してはならない。

---

## 4. 開始時の固定

Phase 0開始直後、他の調査より先にcheckpointへ次を記録する。

1. 現在時刻、timezone、repository絶対path。
2. ユーザーが承認した範囲がPhase 0だけであること。
3. 正本仕様書のSHA-256、bytes、LF、CRLF、末尾LF、版番号。
4. current branchとHEAD。これは識別のためのread-only取得であり、branch操作ではない。
5. `git status --porcelain=v1 -uall`の省略なし全文。
6. 開始前から存在するmodified/untracked entryの一覧。
7. checkpoint自身が開始前から存在したか、新規作成対象か。
8. Phase 0で変更可能なのはcheckpoint一つだけであること。

dirty entryを整理、削除、復元、stageしてはならない。開始前dirtyとPhase 0による変更を混同せず、
checkpointの最終節で開始時snapshotと終了時snapshotを比較する。

---

## 5. Repository Boundary整合確認

### 5.1 判定方法

正本§0.3から§0.8のallowlist、限定bridge、hard protected、変更禁止test、Binance reference、
data/auth境界を一項目ずつ実在pathと照合する。globを一行確認しただけで済ませず、既存fileを
再帰列挙する。

照合結果には最低限、次の列を持たせる。

| spec section | declared path | kind | current state | Phase 0 interpretation |
|---|---|---|---|---|
| §0.3〜§0.5 | path | allowlist/new/bridge/test | EXISTS/MISSING | 後続Phaseでのみ変更候補 |
| §0.6〜§0.8 | path | protected/read-only | EXISTS/MISSING | Phase 0を含め変更禁止 |

新規Phemex namespaceが未作成であることは、それだけではFAILではない。既存pathを誤って新規扱いする、
または正本にない既存fileを暗黙の変更許可対象にすることはFAILである。正本に列挙されていないpathは
既定で変更禁止とする。

### 5.2 hard protected SHA-256 manifest

正本§0.6の全directory/fileと、§0.7の変更禁止test・Binance production/referenceを対象に、
pathをordinal昇順で並べたSHA-256 manifestをcheckpointへ保存する。

manifestの各行には次を記録する。

```text
relative_path | bytes | sha256
```

directoryは配下の通常fileを再帰列挙する。`__pycache__`、`.pytest_cache`等の生成cacheはmanifestへ
含めず、存在自体を別欄へ記録する。symlink/reparse pointが存在する場合は追跡展開せず、その事実と
link targetを記録して停止判断へ回す。読取不能file、宣言済みfileの欠落、列挙失敗を黙って除外しては
ならない。

manifestの個別file一覧に加え、正規化した各行をLFで連結した全体SHA-256、file件数、総bytesを記録する。
Phase 0終了時に同じ方法で再計算し、開始時と一致することを確認する。

### 5.3 production/test tree fingerprint

Phase 0でproduction code差分0、test差分0を証明するため、開始時と終了時に次を別々にfingerprintする。

```text
production:
  Delta_Engine_Pro4web/src/**
  Delta_Engine_Pro4web/webapp/**
  Delta_Engine_Pro4web/config/**
  Delta_Engine_Pro4web/docker-compose.yml

tests:
  Delta_Engine_Pro4web/tests/**
```

各集合は、通常fileの`relative_path | bytes | sha256`をordinal昇順、区切りと改行を固定して集約する。
checkpointには集合ごとのfile件数、総bytes、aggregate SHA-256を記録する。開始時と終了時が不一致なら、
差分fileを特定してPhase 0をPASSにしてはならない。既存dirtyの内容が開始時から存在したことは、
Phase 0中の変化を許可する理由にならない。

---

## 6. Python / pytest実行環境の確認

Phase 0ではtest suiteを変更・実行して実装結果を評価しない。次の環境情報だけをread-onlyで確認する。

- 使用されるPython executableの絶対path
- `python --version`
- `python -m pytest --version`
- repositoryが想定するworking directory
- `pytest.ini`、`pyproject.toml`、`setup.cfg`、`tox.ini`の有無
- ruff/mypy設定と依存宣言の有無

Pythonまたはpytestが使用不能なら、環境確認だけを限定blockerとして記録する。依存install、upgrade、
lockfile変更をPhase 0内で行ってはならない。ruff/mypyが未設定の場合は正本どおり
`NOT_CONFIGURED`とし、未実行を`PASS`と記載しない。

環境確認が`.pyc`、`.pytest_cache`等を生成した場合は、開始時snapshotとの差を明示する。既存fileか
Phase 0生成物か確認できないものを削除してはならない。

---

## 7. Public market data / credential境界の確認

Phase 0ではPhemexへ接続しない。正本の契約と後続Phaseの予定責務を照合し、次をcheckpointへ明記する。

- Phase 1からPhase 8の対象はpublic market dataだけである。
- public WebSocket、public product metadata、public OIにAPI key/secretを要求しない。
- authenticated account/order/position APIと注文送信は対象外である。
- API key/secretの作成、入力、読取、検索、表示をPhase 0で行わない。
- credentialがないことを理由にPhase 0をFAILにしない。
- 将来の注文執行は正本§27の別仕様・別承認境界である。

環境変数やcredential storeを値付きでdumpしてはならない。credential存在確認を目的とした走査自体を
行わない。

---

## 8. Phase 1作成予定fileの固定

Phase 0 checkpointへ、Phase 1で作成を予定するfile名を次のとおり固定する。

```text
Delta_Engine_Pro4web/src/exchange/__init__.py
Delta_Engine_Pro4web/src/exchange/phemex/transport.py
Delta_Engine_Pro4web/src/exchange/phemex/protocol.py
Delta_Engine_Pro4web/src/exchange/phemex/errors.py
Delta_Engine_Pro4web/tests/exchange/__init__.py
Delta_Engine_Pro4web/tests/exchange/phemex/test_transport.py
Delta_Engine_Pro4web/tests/exchange/phemex/fixtures/control/**
```

`fixtures/control/**`はdirectory契約である。Phase 0でdirectoryや空fileを先行作成しない。Phase 1開始時に
必要なfixture file名が具体化した場合は、Phase 1 checkpointへ追記する。

Phemex fixture rootは、後続の全Phaseを通じて次へ一本化する。

```text
Delta_Engine_Pro4web/tests/exchange/phemex/fixtures/**
```

次の旧候補pathは使用も作成もしない。

```text
Delta_Engine_Pro4web/tests/fixtures/phemex/**
```

Phase 0の実在path照合で旧候補pathが見つかった場合は、移動や削除をせず、boundary不整合として
checkpointへ記録する。

Phase 1では次を行わないこともcheckpointへ固定する。

- trade正規化
- 板構築
- DB保存
- pipeline接続
- UI変更

この固定はPhase 1の実行承認ではない。

Phase 3で初めて実装対象となるpre-snapshot bufferの暫定値も、仕様逸脱防止のためPhase 0 checkpointへ
次のとおり転記する。Phase 0またはPhase 1でcode/configへ実装してはならない。

```text
pre_snapshot_max_messages: 128
pre_snapshot_max_bytes: 16777216
snapshot_wait_timeout_sec: 10
overflow_action: FAIL_CLOSED_RECONNECT
review_gate: Phase 8 public-data measurement
```

既存Binanceの`max_buffered_diffs=100000`をPhemex pre-snapshot bufferへ流用しない。暫定値はPhase 8の
実測後に見直すものであり、Phase 0で恒久値と認定しない。

---

## 9. 配布default test全件棚卸し

### 9.1 棚卸しの目的

配布defaultをBinanceからPhemexへ変更したとき、既存testのどのassertionが意図的に変わり、どの
Binance契約を別testとして保存すべきかを、test変更前に確定する。testを先に書換えて失敗原因を
消してはならない。

棚卸しは文字列`Binance`の件数集計ではない。各testが何を入力し、どのdefaultを解決し、何を
assertするかをtest単位で読む。

### 9.2 必須調査範囲

最低限、次を全件調査する。

1. `Delta_Engine_Pro4web/tests/**/*.py`内で`config/config.yaml`、`DEFAULT_CONFIG`、または同等の
   配布config pathを読み込むtest。
2. path省略または既定引数により配布configを解決するtest。
3. `market.exchange`、`normalizer.exchange_profile`、WebSocket URL、subscribe stream、profile path、
   source label、active exchangeを直接assertするtest。
4. 配布configを読み込んだpipeline/webappを構築し、Binance defaultへ間接依存するtest。
5. `src/config.py`のschema defaultを、key省略fixtureでassertするtest。
6. 明示的な`config/profiles/binance.yaml`、Binance local dict、Binance raw fixtureを入力するtest。
7. test helper、fixture、factory、parameterized caseを経由して上記入力を受けるtest。

検索は`rg`等で候補を広く列挙した後、各candidateのtest functionとhelperの入力経路を読んで判定する。
検索結果0件や単一patternの一致数だけを完全性の証拠にしてはならない。

### 9.3 必須seed anchor

次は既知の実害anchorであり、必ず棚卸し表へ含める。

| path | 現行anchor | 確認対象 |
|---|---:|---|
| `Delta_Engine_Pro4web/tests/test_config.py` | `test_shipped_config_is_valid`内（v1.3確認時は99行付近） | 配布configの`btcusdt@trade`、`btcusdt@depth@100ms`、`btcusdt@forceOrder`厳密assertion |
| `Delta_Engine_Pro4web/src/config.py` | schema `market.exchange`（v1.3確認時は241行付近） | key省略時default `BINANCE` |
| `Delta_Engine_Pro4web/src/config.py` | schema `normalizer.exchange_profile`（v1.3確認時は255行付近） | key省略時default `binance` |

行番号は補助情報であり、test名、field名、実内容を正とする。行移動を理由に対象外へしてはならない。

### 9.4 二分類

in-scope testは、必ず次のどちらか一つへ分類する。

#### A. 明示的Binance契約test

test自身がBinance profile、Binance raw fixture、Binance URL/stream、Binance sourceを明示的に入力し、
配布defaultに依存せずBinance互換性を検証するtestである。Phemexをactive defaultにしても削除、緩和、
renameしない。

#### B. 配布default test

配布`config/config.yaml`、schema default、path省略時default、またはそれらで構築されたruntimeを入力とし、
現在のactive exchange/normalizer/URL/stream/sourceを直接または間接に検証するtestである。Phemexへの
配布default変更で期待値変更の候補になるが、Phase 0では変更しない。

候補検索に一致しても上記どちらにも該当しないものは、棚卸し表の除外欄へtest ID、該当文字列、
除外理由を記録する。除外を黙って捨ててはならない。

### 9.5 棚卸し表の必須列

checkpointへ次の列を持つ表を記録する。

| ID | test path | test node/function | input origin | asserted/consumed default | direct/indirect | classification | evidence | future action candidate | approval required |
|---|---|---|---|---|---|---|---|---|---|

`future action candidate`は次のいずれかとする。

```text
KEEP_EXPLICIT_BINANCE_CONTRACT
CHANGE_SHIPPED_DEFAULT_EXPECTATION
SPLIT_AND_PRESERVE_BINANCE_CONTRACT
NO_CHANGE_FALSE_POSITIVE
UNRESOLVED
```

`UNRESOLVED`を残したままPhase 0をPASSにしてはならない。変更候補は提案であり、Phase 0ではtestを
編集しない。

### 9.6 完全性確認

棚卸し完了前に、少なくとも次を相互照合する。

- 配布config読込callsite一覧と棚卸し表の対応
- schema default field一覧とそれを省略するtestの対応
- Binance profile/raw fixture明示入力一覧と分類Aの対応
- active exchange/normalizer/URL/stream assertion一覧と分類A/Bの対応
- helper/fixture経由callsiteと最終test nodeの対応

候補件数、in-scope件数、分類A件数、分類B件数、除外件数を記録し、次が成立することを確認する。

```text
candidate count = classified A + classified B + documented exclusions
```

重複candidateは一意なtest nodeへ正規化し、重複を除いた件数と元hit件数を併記する。

### 9.7 将来変更案の固定

分類Bについて、将来の配布default変更で変更が必要と判断したtest/assertionを一件ずつ列挙する。
ユーザー承認前に変更してはならない。

配布default assertionをPhemexへ変更する案を出す場合、対応する旧Binance契約を、明示的なBinance
fixture/profileを入力する別test caseとして保存する案を必ず併記する。既存testの削除、assertion削除、
期待値の緩和、skip/xfail化だけで通過させる案は禁止する。

---

## 10. MIXED_EXCHANGE_CONFIG境界

Phase 0のtest棚卸し目的でrepository内をread-only検索することと、runtimeの
`MIXED_EXCHANGE_CONFIG`検査は別である。

将来の`MIXED_EXCHANGE_CONFIG`検査対象は、正本§17どおり、resolved active configのexchangeが
`PHEMEX`である場合のresolved active configだけに限定する。

次をMIXED判定の走査対象にしてはならない。

- 未選択の`config/profiles/binance.yaml`
- 明示的Binance契約test
- Binance fixture
- 過去のBinance manifest、DB、Parquet、raw journal、report
- source comment、文書、test名、file名に残る`Binance`文字列
- repository全体のgrep結果

棚卸しで見つけたBinance文字列を「Phemex active時の混在事故」と自動判定してはならない。
Phase 0 checkpointには、MIXED検査をrepository-wide scanに拡張しないことを明記する。

---

## 11. Phase 0 checkpoint必須構成

`PHEMEX_IMPLEMENTATION_CHECKPOINT.md`は最低限、次の順で構成する。

1. 文書情報、現在時刻、timezone、承認範囲。
2. 正本identityとSHA-256照合結果。
3. repository path、branch、HEAD。
4. 開始時`git status --porcelain=v1 -uall`全文。
5. 開始前dirty/untrackedの帰属区分。
6. allowlist/protected path整合表。
7. hard protected SHA-256 manifestとaggregate。
8. production/test tree開始時fingerprint。
9. Python/pytest環境確認結果。
10. public market data / credential境界確認。
11. Phase 1作成予定file一覧と禁止責務。
12. default test候補抽出方法とcommand結果。
13. default test全件棚卸し表。
14. 候補数と分類・除外件数の完全性照合。
15. 将来変更候補test/assertionと旧Binance契約保存案。
16. MIXED_EXCHANGE_CONFIG限定条件確認。
17. 完了済み、未完了、blocker、影響範囲。
18. Phase 0中に変更したfile。
19. 終了時`git status --porcelain=v1 -uall`全文。
20. hard protectedおよびproduction/test tree終了時再照合。
21. 実行command、exit code、PASS/FAIL/NOT_CONFIGURED/NOT_RUN。
22. Gate判定と次の再開位置。

出力が長いことを理由に`git status`、manifest、棚卸し表を省略しない。確認していない項目をPASSに
しない。

---

## 12. 停止条件

次のいずれかが発生した場合、その項目をFAILまたは限定blockerとしてcheckpointへ記録する。

- 正本SHA-256不一致
- repository root不一致
- allowlist/protected宣言と実在pathの説明不能な不整合
- protected fileの読取不能またはhash取得不能
- Python/pytest executableの特定不能
- default test候補の未分類または`UNRESOLVED`残存
- 開始時と終了時のprotected/production/test fingerprint不一致
- checkpoint以外のagent-owned変更
- Phase 0中にcredential、外部接続、runtime変更が必要と判明
- Phase 1予定fileを正本のallowlist外へ拡張する必要が判明

一部blockerがあっても、安全かつ独立したread-only棚卸しは継続する。blockerと直接依存しない項目を
未調査のまま全体終了してはならない。未完了で停止する場合も、現在時刻、完了済み、未完了、変更file、
検証結果、blockerの限定範囲、次の再開位置をcheckpointへ残す。

---

## 13. Gate判定

### 13.1 PASS条件

次をすべて満たした場合だけ、Phase 0をPASSとする。

- 正本v1.3のidentity一致
- allowlist/protected listと実在pathの整合説明完了
- 開始時worktree snapshot保存完了
- hard protected SHA-256 manifest保存・終了時一致
- production/test tree fingerprint開始時・終了時一致
- Python/pytest環境確認完了
- public dataにcredential不要、注文執行対象外を確認
- Phase 1予定file名固定完了
- default test全候補のA/B分類または根拠付き除外完了
- 変更候補test/assertionと旧Binance契約保存案の提示完了
- MIXED検査をresolved active PHEMEX configだけへ限定
- checkpoint以外のagent-owned差分0件
- production code、test、config差分0件

PASS時の状態表記は次とする。

```text
PHASE_0_PASS_AWAITING_USER_GO_FOR_PHASE_1
```

### 13.2 NO-GO条件

一項目でも未成立なら、未確認事項を成功扱いせず次とする。

```text
PHASE_0_NO_GO
```

NO-GOはPhase 1へ進めないという意味であり、安全に完了した他のread-only調査結果を無効にしない。

---

## 14. 終了と次の再開位置

Phase 0 checkpointをユーザーへ提示したら停止する。Phase 1 transport fileを作成せず、testやconfigを
変更せず、Phemexへ接続しない。

PASS後の再開位置は、ユーザーによる次の二つの判断である。

1. 配布default testの変更候補と、旧Binance契約保存案を承認するか。
2. Phase 1 — Phemex Transportを開始するか。

両判断を推測でまとめてGO扱いしてはならない。
