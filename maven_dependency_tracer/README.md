# Maven 依賴追蹤與離線打包增強工具 (Maven Dependency Tracer & Offline Packager)

一個強大的 Python 腳本，用於深度分析 Maven 專案的依賴關係，建立一個最小化且完整的離線 Maven 倉庫，並智慧地分析和解決缺失的依賴問題。

This is a powerful Python script designed to deeply analyze Maven project dependencies, create a minimal and complete offline Maven repository, and intelligently analyze and resolve missing dependency issues.

[![Language](https://img.shields.io/badge/Language-Python%203-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

## 解決的核心問題 (The Problem It Solves)

在企業內部網路、生產環境或任何無法存取外部 Maven 中央倉庫的離線環境中部署 Java 應用程式是一項挑戰。傳統方法，如 `mvn dependency:go-offline` 或手動複製整個 `.m2` 文件夾，存在以下缺點：

1.  **效率低下**：複製整個 `.m2` 會包含大量與當前專案無關的依賴。
2.  **資訊不透明**：當構建失敗時，很難追蹤一個間接依賴 (transitive dependency) 是由哪個直接依賴引入的。
3.  **盲目處理**：無法區分一個缺失的依賴是**必要**的 (essential)，還是**可選**的 (optional)，導致開發者花費大量時間去尋找一個其實並不影響編譯的依賴。
4.  **配置繁瑣**：需要手動配置離線環境的 `settings.xml` 文件。

本工具旨在解決以上所有問題，提供一個自動化、智慧化且透明化的解決方案。

## ✨ 主要功能 (Key Features)

*   **深度依賴鏈追蹤**：透過 `mvn dependency:tree -Dverbose` 命令，精確追蹤每個依賴的完整引入鏈，清楚了解每個 JAR 包的來源。
*   **智慧分析缺失依賴**：自動將缺失的依賴分類為**必要 (essential)**、**可選 (optional)**、**運行時提供 (provided)**、**插件 (plugin)** 或 **版本衝突 (conflict)**，幫助您專注於真正重要的問題。
*   **實際構建驗證**：在分析後，嘗試在目標倉庫上執行 `mvn compile` 和 `mvn package`，以實際構建結果驗證依賴的完整性，避免理論分析與現實脫節。
*   **自動生成報告與建議**：
    *   在終端機中提供清晰的彩色摘要報告。
    *   生成詳細的 `dependency-analysis-report.json` 文件，供進一步分析或自動化處理。
    *   對缺失的關鍵依賴提供修復建議，例如尋找可用版本或生成下載腳本。
*   **一鍵生成離線環境配置**：自動創建 `settings.xml` 文件，指向新生成的離線倉庫，讓您可以立即在離線環境中進行構建。
*   **並行處理**：使用多執行緒並行複製依賴，大幅縮短處理大型專案的時間。
*   **跨平台支援**：自動檢測作業系統並找到可用的 `mvn` 命令。

## ⚙️ 運作流程 (How It Works)

腳本的執行流程如下：

1.  **分析 (Analysis)**：
    *   執行 `mvn dependency:tree -Dverbose=true` 獲取包含完整依賴鏈、衝突和排除信息的依賴樹。
    *   執行 `mvn help:effective-pom` 分析最終生效的 POM，以獲取由 `dependencyManagement` 管理的依賴和插件資訊。
    *   解析專案的 `pom.xml` 以識別直接依賴。
2.  **複製 (Copying)**：
    *   根據分析結果，建立一份需要複製的依賴清單（已排除的依賴會被跳過）。
    *   使用多執行緒從**來源倉庫** (`source_repo`) 並行複製依賴文件到**目標倉庫** (`target_repo`)。
3.  **報告與驗證 (Reporting & Verification)**：
    *   記錄所有複製失敗的依賴。
    *   將缺失的依賴進行分類，並在控制台輸出摘要。
    *   （可選）在專案中嘗試執行 `mvn compile` 和 `mvn package`，以驗證當前依賴是否足以支持構建。
4.  **生成產物 (Artifact Generation)**：
    *   在目標倉庫目錄下生成 `dependency-analysis-report.json` 詳細報告。
    *   生成 `settings.xml` 供離線環境使用。
    *   為缺失的關鍵依賴生成一個 `download-missing-deps.sh` 腳本範本，以輔助修復。

## 🚀 使用指南 (Usage)

### 前提條件 (Prerequisites)

*   Python 3.6+
*   Apache Maven 已安裝並配置在系統的 `PATH` 環境變數中。

### 安裝 (Installation)

直接下載腳本即可，無需額外安裝。建議將腳本命名為 `maven_dependency_tracer.py` 並賦予執行權限。

```bash
# 假設腳本名稱為 maven_dependency_tracer.py
chmod +x maven_dependency_tracer.py
```

### 命令格式

```bash
./maven_dependency_tracer.py <project_path> <source_repo> <target_repo> [options]
```

### 參數說明

*   `project_path`: 【必填】你的 Maven 專案根目錄路徑。
*   `source_repo`: 【必填】來源 Maven 倉庫路徑。通常是你的本地開發機上的 `~/.m2/repository`。
*   `target_repo`: 【必填】目標離線倉庫路徑。腳本會在此路徑下創建一個乾淨的倉庫。
*   `--verbose`, `-v`: 顯示詳細的執行日誌。
*   `--threads <N>`, `-j <N>`: 設置並行複製依賴的執行緒數量 (預設: 4)。
*   `--analyze-only`: 只進行分析並生成報告，不執行任何文件複製操作。
*   `--copy-missing-only`: 假設你之前已經運行過一次，此選項會嘗試只複製上次分析報告中標記為缺失的依賴。

### 實際範例

假設你的專案在 `/path/to/my-app`，你想利用本地的 Maven 緩存 (`~/.m2/repository`) 來創建一個位於 `/tmp/offline-repo` 的離線倉庫。

```bash
./maven_dependency_tracer.py /path/to/my-app ~/.m2/repository /tmp/offline-repo -j 8
```

執行後，你將在 `/tmp/offline-repo` 目錄下得到：
*   一個包含所有必要依賴的 Maven 倉庫結構。
*   一個 `settings.xml` 文件。
*   一個 `dependency-analysis-report.json` 詳細報告。
*   （如果需要）一個 `download-missing-deps.sh` 腳本。

### 在離線環境中使用

1.  將整個 `target_repo` 目錄（例如上例中的 `/tmp/offline-repo`）打包並傳輸到你的離線伺服器。
2.  在離線伺服器上，進入你的專案目錄，使用 `-s` 參數指定 `settings.xml` 進行構建：

```bash
# -s 指定配置文件，--offline 強制離線模式
mvn -s /path/to/offline-repo/settings.xml clean package --offline
```

## 🔬 程式碼分析 (Code Analysis)

該腳本的核心是 `MavenDependencyTracer` 類，其主要方法職責如下：

*   `__init__(...)`: 初始化路徑、變數和 Maven 命令。
*   `_find_maven_command()`: 跨平台尋找可用的 `mvn` 命令。
*   `analyze_dependencies_with_tracing()`: 協調整個依賴分析流程的入口點。
*   `_analyze_dependency_tree_verbose()`: 執行 `mvn dependency:tree` 並調用解析器，這是獲取完整依賴鏈的關鍵。
*   `_parse_verbose_dependency_tree(...)`: 使用正則表達式解析 `dependency:tree` 的詳細輸出，提取依賴、範圍、版本、衝突等資訊。
*   `_analyze_effective_pom()`: 執行 `mvn help:effective-pom` 以捕獲由父 POM 或 `dependencyManagement` 影響的依賴。
*   `copy_all_dependencies_with_tracking(...)`: 使用 `ThreadPoolExecutor` 並行複製所有有效依賴。
*   `analyze_missing_dependencies()`: 對複製失敗的依賴進行分類，是此工具的智慧核心。
*   `verify_with_actual_build()`: 執行 `mvn compile` / `package` 進行實際驗證，提供最終的信心保證。
*   `generate_enhanced_report()`: 整合所有分析結果，生成最終的控制台報告和 JSON 文件。
*   `_generate_recommendations(...)`: 根據分析結果提供可行的修復建議。
*   `create_offline_settings_xml()`: 根據目標倉庫路徑動態生成 `settings.xml` 文件。

## 📜 授權 (License)

本專案採用 [MIT License](LICENSE) 授權。
