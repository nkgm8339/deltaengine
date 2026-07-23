# 指示書_UI_LayoutWatchdog_v1

**この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。**

---

## 0. 目的

WebApp UI で報告された「時間経過で表示領域が狭くなる」現象について、web による実測検証（headless Chrome、120分運転相当）で **HTML/JS/CSS 単体では再現しない**ことが確定した。原因は外部要因（ブラウザズーム / OSスケーリング / DevTools / ウィンドウリサイズ）または未知の内部要因である。

発生を待つ受け身の切り分けは行わない。**発生した瞬間に原因を自動分類して記録する監視コード（Layout Watchdog）を UI に恒久組み込みする。**

分類ロジックは web 側で 5 テスト（4原因の意図的再現 + 無変化時の誤検知なし）全通過を実証済み。

---

## 1. 変更対象

- `project/webapp/static/index.html` **のみ**
- Python コードの変更は一切なし。既存 pytest 221 本に影響ゼロ

`delta_preview.html` は静的デザイン参照物のため対象外とする（web の設計判断）。

---

## 2. 変更内容

### 2.1 DEVELOPER OVERLAY に表示行を追加

既存の行:

```html
<div id="devov"><div class="dh">🐛 DEVELOPER OVERLAY</div><div id="devgrid"></div></div>
```

を次に置換する:

```html
<div id="devov"><div class="dh">🐛 DEVELOPER OVERLAY</div><div id="devgrid"></div><div id="wdlog" style="margin-top:4px;font-size:9px;color:#FFC400;min-height:12px"></div></div>
```

### 2.2 Watchdog 本体の追加

`renderTabs(); connect();` の直後（既存 `</script>` の直前）に、以下を**一字一句このまま**追加する:

```javascript

// ============================================================
// Layout Watchdog v1（恒久組み込み・診断専用）
// 2秒周期で環境・レイアウト指標をサンプリングし、変化検知時に原因を
// 自動分類してログに残す。ログは有界リングバッファ（最大100件）。
// 画面出力は textContent 上書きのみ。DOM蓄積ゼロ保証。
// 判定ロジックではない（§UIは Payload のみ参照、の対象外の診断計装）。
// ============================================================
(function(){
  const MAX_LOG = 100;
  const log = [];
  let base = null;

  function sample(){
    const panels = {};
    for (const id of ["appgrid","main","bookbody","fpbody","flowbody","alertrows"]){
      const el = document.getElementById(id);
      if (el) panels[id] = el.clientHeight + "x" + el.clientWidth;
    }
    return {
      t: new Date().toISOString(),
      dpr: window.devicePixelRatio,
      vvScale: window.visualViewport ? window.visualViewport.scale : null,
      innerW: window.innerWidth, innerH: window.innerHeight,
      outerW: window.outerWidth, outerH: window.outerHeight,
      screenW: screen.availWidth, screenH: screen.availHeight,
      panels
    };
  }

  function classify(prev, cur){
    const causes = [];
    if (cur.dpr !== prev.dpr){
      if (cur.outerW === prev.outerW && cur.outerH === prev.outerH)
        causes.push("BROWSER_ZOOM（Ctrl+ホイール/Ctrl+±。Ctrl+0で復旧）");
      else
        causes.push("OS_DISPLAY_SCALING（Windowsの拡大率変更）");
    }
    if (cur.vvScale !== prev.vvScale && cur.vvScale !== 1)
      causes.push("PINCH_ZOOM（visualViewport scale=" + cur.vvScale + "）");
    if (cur.outerW !== prev.outerW || cur.outerH !== prev.outerH)
      causes.push("WINDOW_RESIZE（ウィンドウ寸法変更）");
    if ((cur.innerW !== prev.innerW || cur.innerH !== prev.innerH)
        && cur.outerW === prev.outerW && cur.outerH === prev.outerH
        && cur.dpr === prev.dpr)
      causes.push("BROWSER_CHROME（DevToolsドッキング/サイドバー等）");
    if (causes.length === 0){
      for (const k in cur.panels){
        if (prev.panels[k] !== cur.panels[k]){
          causes.push("INTERNAL_LAYOUT（環境変数不変のままパネル寸法変化: " + k
            + " " + prev.panels[k] + "→" + cur.panels[k] + "）");
          break;
        }
      }
    }
    return causes;
  }

  function record(entry){
    log.push(entry);
    if (log.length > MAX_LOG) log.shift();
    console.warn("[LayoutWatchdog]", JSON.stringify(entry));
    const el = document.getElementById("wdlog");
    if (el) el.textContent = entry.t.slice(11,19) + " " + entry.causes.join(" / ");
  }

  window.__watchdog = {
    dump: () => log.slice(),
    baseline: () => base,
    tick: function(){
      const cur = sample();
      if (!base){ base = cur; return null; }
      const causes = classify(base, cur);
      if (causes.length){
        const e = { t: cur.t, causes, prev: base, cur };
        record(e); base = cur; return e;
      }
      base = cur; return null;
    }
  };
  setInterval(window.__watchdog.tick, 2000);
})();
```

---

## 3. 禁則

- 上記 2 箇所以外、`index.html` の既存コードを 1 文字も変更しない
- Python ファイル・config・正本（Repository docs）は無変更
- Watchdog コードの改変・「改善」は禁止（分類ロジックは web 側でテスト実証済みの確定版である）

---

## 4. 検証手順（Code が実施）

1. `python -m pytest -q` → **221 passed**（無影響確認）
2. `index.html` をブラウザで直接開く（またはWebApp起動）
3. DEVELOPER OVERLAY 表示状態で、コンソールに `window.__watchdog.dump()` と入力 → `[]`（空配列）が返ること
4. Ctrl+ホイールでズーム変更 → 2秒以内にコンソールに `[LayoutWatchdog]` 警告が出力され、`causes` に `BROWSER_ZOOM` が含まれること
5. `window.__watchdog.dump()` → 1 件記録されていること

---

## 5. 完了条件

- [ ] 221 passed 無影響
- [ ] §4 手順 3〜5 の実測結果を完了報告に記載
- [ ] `index.html` の diff が §2 の 2 箇所のみであること

## 6. 報告（三点セット）

1. `ArchitectureRepository/00_Master/CompletionLog.md` に完了エントリ追記
2. `DeltaEngine_LayoutWatchdog_完了.zip`（`__pycache__` / `.pytest_cache` / `data/parquet` / `data/duckdb` 除外可、他は全て含む）
3. チャット完了報告（§4 実測結果・逸脱有無を含む）
