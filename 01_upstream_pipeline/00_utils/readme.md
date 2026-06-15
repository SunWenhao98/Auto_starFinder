- 00_utils/prepare_files.sh
  - 通用 flat copy 工具。
  - 支持 -- item 重复传多个文件/目录。
  - 支持 source:dest 重命名。
  - 支持 -- copy-mode file|dir|auto。
  - 覆盖 001_prepareCodebook.sh、prepare_config.sh、prepare_scripts.sh、
  prepare_sourcedata.sh 这类固定源目录复制模式。

- 00_utils/prepare_mapping_files.sh
  
  - 独立 basename-mapping 文件复制工具。
  - 逻辑是 SOURCE_DIR/<目标目录basename>/<item>复制到目标目录。
  - 支持多个 -- item,也支持 source:dest。
  - 用于替代/抽象 prepare_spotiflow.sh 这类 PositionXXX 映射复制模式。

- 00_utils/cleanup_files.sh
  - 更明确命名的日志清理工具。
  - 默认 dry-run,不删除。
  - 只有传 -- execute 才执行删除。
  - 原 cleanup_logs.sh 保持不变。