# 指示書_Docker_MT5公開_v1

**この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。**

---

## 0. 目的

web の独立検証で以下 2 件のギャップが確定した。本指示書で塞ぐ。

1. `docker-compose.yml` が 8080 のみ公開しており、コンテナ起動時に MT5 クライアントが MT5Server（TCP 5555）へ到達できない。最終目標「`docker-compose up` ワンクリック稼働」と「MT5 連動」が両立しない
2. `requirements.txt` にテスト依存 `httpx` が欠落しており、クリーン環境で `pytest` が collection error になる（FastAPI TestClient が要求。web 環境で実測済み）

---

## 1. 変更対象（3 ファイルのみ）

- `project/docker-compose.yml`
- `project/requirements.txt`
- `project/config/config.yaml`（コメント 2 行の追加のみ。値の変更は一切しない）

Python コード・正本・その他ファイルは無変更。

---

## 2. 変更内容

### 2.1 `docker-compose.yml`

`ports:` を次の通りとする（8080 行は無変更、5555 行を追加）:

```yaml
    ports:
      - "8080:8080"
      - "127.0.0.1:5555:5555"
```

コメントを 5555 行の直上に追加する:

```yaml
      # MT5 Adapter (SIGNAL/HEARTBEAT)。ホストの loopback のみに公開（LAN 非公開）。
      # MT5 は同一 Windows ホスト上の 127.0.0.1:5555 へ接続する。
```

### 2.2 `requirements.txt`

`# Test dependency` セクションの `pytest>=8.0` の直後に次の 2 行を追加する:

```text
# httpx: FastAPI TestClient (tests/webapp/test_api.py) が要求
httpx>=0.27
```

### 2.3 `config/config.yaml`

`mt5:` セクションの `bind_address: 127.0.0.1` の直上にコメント 2 行を追加する（値は変更しない）:

```yaml
  # Docker コンテナ内で MT5 連動する場合は 0.0.0.0 に変更すること
  # （compose 側で 127.0.0.1:5555 にのみ公開するためホスト外へは露出しない）
```

---

## 3. 禁則

- `mt5.enabled` / `bind_address` の**値**を変更しない（既定は enabled: false / 127.0.0.1 のまま）
- 上記 3 ファイル以外を変更しない
- Python コード無変更

---

## 4. 検証手順（Code が実施）

1. クリーン venv（または `pip uninstall httpx` 後）で `pip install -r requirements.txt` → `python -m pytest -q` → **281 passed**（httpx 欠落の再発防止確認）
2. `grep -n "5555" docker-compose.yml` → 追加行が存在すること
3. `python -c "from src.config import load_config; c=load_config('config/config.yaml'); print(c.mt5.enabled, str(c.mt5.bind_address))"` → `False 127.0.0.1`（値不変の確認）

## 5. 完了条件

- [ ] 281 passed（クリーン依存解決で）
- [ ] diff が §2 の 3 ファイル・記載箇所のみ
- [ ] config 値の不変を §4-3 で実証

## 6. 報告（三点セット）

1. `CompletionLog.md` に完了エントリ追記
2. `DeltaEngine_DockerMT5公開_完了.zip`
3. チャット完了報告（§4 実測結果・逸脱有無）
