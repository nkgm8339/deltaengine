# Big Trades実装前 Git除外manifest

- 作成日: 2026-08-11
- 用途: pre-Big-Trades baseline commitへ入れないlocal生成物の識別
- 除外数: 23 file
- 合計: 414,527,145 bytes
- 処置: Gitから除外するだけで、移動・変更・削除しない

| bytes | SHA-256 | path |
|---:|---|---|
| 97,210 | `D07166BF97B8CB84DE23B68F77BD44514A23E2E319C7C2512053DB599CAEF45B` | `ArchitectureRepository/00_Master/__pycache__/delta_engine_backtest_simulator.cpython-313.pyc` |
| 527,899 | `58048404F36A7FCB4A2487CB87D8C9A9F95386D624C3D4BCCB1C21B227747DD6` | `ArchitectureRepository/00_Master/HEATMAP/p21_evidence/data/validation/segments/raw_depth.20260729T193154.046959Z.jsonl` |
| 535,833 | `1AAF0643344A30338CFB8E7BCED642A83751C52A95008C488B91C93E13741A6D` | `ArchitectureRepository/00_Master/HEATMAP/p21_evidence/data/validation/segments/raw_depth.20260729T193201.309417Z.jsonl` |
| 2,431 | `DFB50DC32545D28B822E5287632F193AAB4751D8BCDCF2C674025C521414DF09` | `ArchitectureRepository/00_Master/HEATMAP/tools_p22/p22_task4_pytest_stdout_20260731.log` |
| 108,960 | `E3DE49359AFC63117433DDF9B8183CA2C4B0AE2C6E21ADE08963EF14997C1B70` | `ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch` |
| 7,090,176 | `52C892B26E0844520DC45633BD72A2B4EFC1511E60CFD4AAE28DF3B683BACE44` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/nested_bars.duckdb` |
| 4,773,286 | `E7AE356EF1DAA2EA8E9FD0361FB5D26E719125AD6052A1A7B339EDE2B9170FEC` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/nested_zstd.parquet` |
| 40,644,608 | `55B816039CABC173E421B4C2C8B75C88580DF0D8BF6F4372A4BC165FE746E1EF` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/normalized_index.duckdb` |
| 7,876,608 | `36D44FE4D6B72E83CE8006D260C56E93EA1DCBE6E9DF11C4A5F491693920432E` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/normalized_no_index.duckdb` |
| 4,067,060 | `842277EBC13E67003EFFB7C0F03C00825B6BEFDD1900335AC55CA8D9A0EBC0B3` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/normalized_zstd.parquet` |
| 60,043,264 | `7508EA6E11EB55BA22B6C9C126BE86C5519AA610074283BB4FF78CCD85370AA8` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/source_trades.duckdb` |
| 43,266,048 | `130F7AE0C2733C8932AE2EF993FF0D0767995FBF718EC1EC1873FD995A0F930D` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/write_benchmark_indexed.duckdb` |
| 14,168,064 | `6FE84858586B61497CF752D3FCD5715544FAECC207B6BF946E7F3150E57DAC8A` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/write_benchmark_nested.duckdb` |
| 8,138,752 | `D781CE47E7A48A82CE6E938744FBDD24C9BC0734CD1F1FB73C7589A50E5EB522` | `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/write_benchmark_no_index.duckdb` |
| 798,720 | `87E40DCE5A74F77CC64B40F7F942565141963E6E4D0D4DF314C3AC1BAC2BB1CD` | `pytest-vwap-ui-elevated/test_query_candles_filters_tim0/test.duckdb` |
| 798,720 | `83A83FA06B6F89086D97287E73C3E5592DD74C6B2EBBEE40269ED3044E5EAEE0` | `pytest-vwap-ui-elevated/test_query_candles_returns_lis0/test.duckdb` |
| 536,576 | `00EF6E3E4BDF7067860B6A8451C5F943A46B15E6F24B5CB40588DC6B12E002D1` | `pytest-vwap-ui-elevated/test_query_flow_response_event0/test.duckdb` |
| 536,576 | `1FC2DB9C8D9D3909B464F8986078303C815C189DA80698A1F879F915D5ABC23E` | `pytest-vwap-ui-elevated/test_query_signals_returns_lis0/test.duckdb` |
| 798,720 | `647DCCFA67380D1E58DA0B9F0A7921EE6AFDCE1747F44EA414EC0E7071F3AB92` | `pytest-vwap-ui-elevated/test_query_trades_returns_list0/test.duckdb` |
| 26,788 | `A968BD1D8B11F1CC26C52A8C17F757CE158E016918375B688A6A5B6E3642A81F` | `vwap_first100.jsonl` |
| 0 | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | `vwap_restore_ws_capture.jsonl` |
| 1,886 | `5C41DECCC40471959500E1F3E83EFD61D18C393F57412E1629C7F828A3BA71F4` | `vwap_ws_capture.jsonl` |
| 219,688,960 | `2EFF9ABC86EEAF6DCA795E6A505F36ADB16F186A292E43B71EBDA12AEFFED4C1` | `vwap-audit.duckdb` |

## 復元境界

Git tagはsource、config、tests、正本文書を復元する。上表のlocal生成物はGit tagから復元されない。これらは現pathに保持し、削除には別の明示承認を必要とする。
