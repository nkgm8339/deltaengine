# Reference Duplicate Check

作成日: 2026-07-07
対象: ArchitectureRepository/40_Reference/

---

## 確認項目

- 同一概念の複数ファイル存在
- バージョン違い
- 命名揺れ
- 内容重複
- 階層不整合

---

## 1. バージョン重複

### 1-1. DataDictionary（重大度：高）

| ファイル | 内容 |
|---------|------|
| DataDictionary_v3.0.md | REF-001。共通フィールド・時刻標準・命名規則・所有権を定義。汎用SSOT。 |
| DataDictionary_v3.1.md | 市場データエンティティ（Tick/Trade/Bid/Ask/Volume/Delta/CVD等）に特化。異なるフォーマット。 |

**問題**: 同名ファイルのバージョン違いが並存。v3.1がv3.0の上位互換か別用途かが不明。  
v3.0はフォーマット・命名ルール中心、v3.1は市場データエンティティ中心で、内容が重複しつつ異なる。

**対応案**: v3.1の内容をv3.0に統合し、v3.1を廃止するか、v3.1を「MarketDataDictionary」に改名して役割を明確化する。

---

### 1-2. Enum（重大度：高）

| ファイル | 内容 |
|---------|------|
| EnumDefinitions_v3.0.md | REF-002。正式定義。TradeSide/SignalType/MarketState/SystemStateを定義。 |
| Enum.md | 日本語草稿テンプレート。Side/SignalTypeを定義。作成日2026-07-07（当日）。 |

**問題**: Enum.mdは草稿段階であり、EnumDefinitions_v3.0.mdと同概念（Side/SignalType）を日本語形式で重複定義している。  
Enum.mdのSignalTypeはEnumDefinitions_v3.0のSignalTypeと定義が異なる点も問題。

**対応案**: Enum.mdの必要な更新をEnumDefinitions_v3.0.mdに反映後、Enum.mdは削除または廃止マークをつける。

---

### 1-3. IndicatorDefinitions バージョン表記揺れ（重大度：低）

| ファイル | バージョン表記 |
|---------|-------------|
| IndicatorDefinitions_v3.md | v3（.0なし） |
| 他の全ファイル | v3.0形式 |

**問題**: 命名規則が他ファイルと一致しない（v3.0ではなくv3）。  
**対応案**: リネームして v3.0 に統一する。

---

## 2. 内容重複クラスター

### 2-1. セキュリティ（重大度：中）

3ファイルが類似するセキュリティ概念を定義している。

| ファイル | スコープ |
|---------|---------|
| SecurityReference_v3.0.md | 認証・認可・暗号化等の一般セキュリティ用語 |
| DataSecurityReference_v3.0.md | データ機密性・完全性・可用性・アクセス制御 |
| DataOperationSecurityReference_v3.0.md | 運用時の権限管理・監査証跡・セキュリティ監視 |

**重複概念**: Access Control、Audit Trail、Encryption が複数ファイルで定義されている。  
**対応案**: SecurityReferenceを親SSO Tとして維持し、DataSecurity/DataOperationSecurityを統合または廃止。

---

### 2-2. データガバナンス（重大度：中）

5ファイルが類似するガバナンス概念を定義している。

| ファイル | スコープ |
|---------|---------|
| DataGovernanceReference_v3.0.md | ガバナンスフレームワーク全体 |
| DataOperationalGovernanceReference_v3.0.md | 日常運用ガバナンス |
| DataOwnershipReference_v3.0.md | オーナーシップ・責任体制 |
| DataStewardshipReference_v3.0.md | スチュワードシップ・品質維持 |
| DataCatalogReference_v3.0.md | データカタログ・データ資産管理 |

**重複概念**: Data Owner、Data Steward が DataGovernance・DataOwnership・DataStewardship の3ファイルで重複定義。  
**対応案**: DataGovernanceReferenceを親SSO Tとし、Ownership/Stewardshipの定義を集約。

---

### 2-3. データリカバリー・BCP（重大度：中）

4ファイルが類似する復旧・継続性概念を定義している。

| ファイル | スコープ |
|---------|---------|
| DataRecoveryReference_v3.0.md | データ復旧全般 |
| DataDisasterRecoveryReference_v3.0.md | 大規模障害からの復旧 |
| DataBackupReference_v3.0.md | バックアップ手順 |
| DataBusinessContinuityReference_v3.0.md | 事業継続性 |

**重複概念**: Business Continuity が DataRecovery と DataDisasterRecovery の両方に定義されている。Recovery Planが複数ファイルで重複定義。  
**対応案**: DataRecoveryReferenceを親として集約。DataDisasterRecoveryは統合候補、DataBusinessContinuityは不要候補。

---

### 2-4. データストレージアーキテクチャ（重大度：中）

4ファイルがストレージアーキテクチャパターンを定義している。

| ファイル | スコープ |
|---------|---------|
| DataStorageArchitectureReference_v3.0.md | ストレージアーキテクチャ全体（DataLakeも定義） |
| DataLakeArchitectureReference_v3.0.md | データレーク（Lakehouseも定義） |
| DataLakehouseArchitectureReference_v3.0.md | データレイクハウス |
| DataWarehouseArchitectureReference_v3.0.md | データウェアハウス |

**重複概念**: Data Lake・Data Lakehouse がDataStorageArchitecture、DataLakeArchitecture、DataLakehouseArchitectureの3ファイルで重複定義。  
**対応案**: DataStorageArchitectureを親として維持し、DataLake/DataLakehouse/DataWarehouseを統合または廃止。

---

### 2-5. データ運用管理クラスター（重大度：中）

14ファイルがデータ運用管理の各側面を細分化して定義している（ITSM的分割）。

| 親ファイル | 子ファイル群 |
|-----------|------------|
| DataOperationsReference_v3.0.md | DataOperationAudit / DataOperationAutomation / DataOperationCompliance / DataOperationConfigurationManagement / DataOperationDeploymentManagement / DataOperationEnvironmentManagement / DataOperationIncident / DataOperationLifecycle / DataOperationMonitoring / DataOperationProblemManagement / DataOperationReleaseManagement / DataOperationSecurity / DataOperationalGovernance |

**問題**: DataOperationsReferenceが親として概念を包含しつつ、13の子ファイルが個別に詳細化している。  
多くの子ファイルの内容は既存の汎用Reference（ConfigurationReference, DeploymentReference, MonitoringReference, SecurityReference等）と重複している。  
**対応案**: DataOperationsReferenceを維持しつつ、子ファイルはプロジェクト固有の拡張のみを含むものに絞る。

---

### 2-6. デプロイメント（重大度：低）

| ファイル | スコープ |
|---------|---------|
| DeploymentReference_v3.0.md | デプロイメント一般用語 |
| DataOperationDeploymentManagementReference_v3.0.md | データ運用デプロイ管理 |
| DataOperationReleaseManagementReference_v3.0.md | データ運用リリース管理 |

**重複概念**: Deployment、Rollback、Release等が複数ファイルで重複定義。

---

### 2-7. モニタリング（重大度：低）

| ファイル | スコープ |
|---------|---------|
| MonitoringReference_v3.0.md | 監視・可観測性全般 |
| DataObservabilityReference_v3.0.md | データ固有の可観測性 |
| DataOperationMonitoringReference_v3.0.md | 運用監視 |
| AlertingReference_v3.0.md | アラート |

**重複概念**: Observability、Monitoring、Alertの概念が重複している箇所がある。

---

### 2-8. API・アクセスパターン（重大度：低）

| ファイル | スコープ |
|---------|---------|
| APIReference_v3.0.md | API全般 |
| DataAPIArchitectureReference_v3.0.md | データAPI設計 |
| DataAccessArchitectureReference_v3.0.md | データアクセス設計 |

**重複概念**: API Endpoint、API Versioning、Data API等が複数ファイルで重複定義。

---

### 2-9. データ品質（重大度：低）

| ファイル | スコープ |
|---------|---------|
| DataQualityReference_v3.0.md | 品質概念（Completeness/Accuracy/Consistency等） |
| DataQualityMetricsReference_v3.0.md | 品質メトリクス（Completeness Rate/Accuracy Rate等） |

**重複概念**: Completeness・Accuracy等の概念がReferenceとMetrics両方に定義されている。  
**対応案**: DataQualityReferenceに統合可能。

---

### 2-10. データ統合（重大度：低）

| ファイル | スコープ |
|---------|---------|
| DataIntegrationReference_v3.0.md | データ統合の概念 |
| DataIntegrationArchitectureReference_v3.0.md | データ統合のアーキテクチャ設計 |

**重複概念**: Source System、Target System、Data Exchangeが両方で定義されている。

---

### 2-11. データアーカイブ・保持（重大度：低）

| ファイル | スコープ |
|---------|---------|
| DataRetentionReference_v3.0.md | 保持ポリシー・期間 |
| DataArchiveReference_v3.0.md | アーカイブ方針 |

**重複概念**: Retention Period、Archive Policyが両方で定義されている。

---

## 3. 階層不整合

### 3-1. DataReferenceArchitecture vs DataArchitectureReference（重大度：中）

| ファイル | 概要 |
|---------|------|
| DataArchitectureReference_v3.0.md | データアーキテクチャ全体の用語定義 |
| DataReferenceArchitecture_v3.0.md | データ参照アーキテクチャの用語定義 |

**問題**: ファイル名の語順が逆（DataArchitecture vs ReferenceArchitecture）で混同しやすい。内容も類似しており、DataDictionary・CanonicalModel等の共通概念が存在する。  
**対応案**: DataReferenceArchitectureをDataArchitectureReferenceに統合または廃止。

---

### 3-2. DataDictionary vs MarketDataSchema（重大度：低）

| ファイル | 内容 |
|---------|------|
| DataDictionary_v3.0.md | 共通フィールド定義（event_time, price, quantity等） |
| MarketDataSchema_v3.0.md | Tick/Candleスキーマ（同じフィールドを構造化） |

**問題**: 同一フィールド（timestamp、price、volume等）が両ファイルで定義されている。MarketDataSchemaがDataDictionaryを参照すべきだが、参照記述がない。

---

## 4. 命名規則の揺れ

| 問題 | 対象ファイル |
|------|------------|
| バージョン表記：v3 vs v3.0 | IndicatorDefinitions_v3.md のみ |
| 接頭辞なし：Enum.md（他はすべてXxxReference or XxxSchema等） | Enum.md |
| DataDictionary（VersionサフィックスなしのDictionary系） | DataDictionary_v3.0.md, DataDictionary_v3.1.md |
| DataReferenceArchitecture vs DataArchitectureReference（語順逆） | DataReferenceArchitecture_v3.0.md |

---

## 5. 重複サマリー

| No | 重複グループ | 重複ファイル数 | 重大度 |
|----|------------|-------------|--------|
| 1 | DataDictionary バージョン | 2 | 高 |
| 2 | Enum 重複 | 2 | 高 |
| 3 | セキュリティ | 3 | 中 |
| 4 | ガバナンス | 5 | 中 |
| 5 | リカバリー・BCP | 4 | 中 |
| 6 | ストレージアーキテクチャ | 4 | 中 |
| 7 | データ運用管理クラスター | 14 | 中 |
| 8 | デプロイメント | 3 | 低 |
| 9 | モニタリング | 4 | 低 |
| 10 | API・アクセス | 3 | 低 |
| 11 | データ品質 | 2 | 低 |
| 12 | データ統合 | 2 | 低 |
| 13 | アーカイブ・保持 | 2 | 低 |
