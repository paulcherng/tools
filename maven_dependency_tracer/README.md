# Maven 依賴追蹤與離線打包測試工具 (Maven Dependency Tracer & Offline Packager)

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

------------------------------------------------------------------------------
# Maven 倉庫快取清理工具 (Maven Repository Cache Cleaner)

一個輕量、快速且安全的 Python 腳本，用於清理本地 Maven 倉庫中的遠端快取文件和損壞的元數據，解決常見的 "Could not resolve dependencies" 問題。

A lightweight, fast, and safe Python script for cleaning remote cache files and corrupted metadata from your local Maven repository, designed to fix common "Could not resolve dependencies" issues.

[![Language](https://img.shields.io/badge/Language-Python%203-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

## 😠 解決的問題 (The Problem It Solves)

每個 Maven 使用者幾乎都遇過這種情況：專案在昨天還能正常構建，今天卻突然因為無法解析某個依賴而失敗，即使你知道那個依賴明明存在。這通常是由於本地 Maven 倉庫中的快取文件（如 `_remote.repositories` 或 `*.lastUpdated`）損壞或過期導致的。

傳統的解決方法有：
1.  **手動刪除**：進入特定的依賴目錄，手動尋找並刪除這些快取文件，非常繁瑣且容易出錯。
2.  **暴力刪除**：直接刪除整個 `~/.m2/repository` 目錄。雖然有效，但會導致所有專案的依賴都需要重新下載，浪費大量時間和網路頻寬。

本工具提供了一個**外科手術式**的解決方案：精準地找出並刪除這些有問題的快取文件，而保留已經下載好的 JAR 和 POM 文件，讓您在幾秒鐘內修復倉庫，無需重新下載任何東西。

## ✨ 主要功能 (Key Features)

*   **精準清理**：專門針對 Maven 的遠端倉庫標識文件進行清理，包括：
    *   `_remote.repositories`
    *   所有 `*.lastUpdated` 文件
    *   `*.repositories`
    *   `resolver-status.properties`
*   **清理快取目錄**：可選地刪除由某些 Maven 版本或 IDE 生成的 `.cache` 和 `.meta` 目錄。
*   **安全第一：模擬執行 (`dry-run`)**：在不實際刪除任何文件的情況下，預覽將會被清理的所有文件和目錄，確保操作的安全性。
*   **高效並行處理**：利用多執行緒並行掃描和刪除文件，即使面對體積龐大（數十 GB）的倉庫也能快速完成。
*   **清理空目錄**：在清理快取文件後，自動刪除因此產生的空目錄，保持倉庫結構的整潔。
*   **詳細報告**：執行完畢後，生成一份清晰的報告，總結清理的文件和目錄數量，並將詳細列表保存到日誌文件中。

## ⚙️ 運作流程 (How It Works)

1.  **掃描目錄**：腳本會遍歷指定的 Maven 倉庫路徑。
2.  **識別目標**：
    *   首先，清理頂層的 `.cache` 和 `.meta` 目錄（如果存在）。
    *   然後，遞迴尋找所有符合清理規則的檔案（如 `_remote.repositories`, `*.lastUpdated` 等）。
3.  **執行清理**：使用多執行緒並行刪除所有已識別的檔案。
4.  **清理空巢**：從最深層的目錄開始，反向遍歷並刪除所有空目錄。
5.  **生成報告**：在控制台輸出摘要報告，並在倉庫根目錄下創建一份 `cache-cleanup-report.txt` 詳細日誌。

## 🚀 使用指南 (Usage)

### 前提條件 (Prerequisites)

*   Python 3.6+

### 安裝 (Installation)

直接下載腳本即可，無需額外安裝。建議將腳本命名為 `maven_cache_cleaner.py` 並賦予執行權限。

```bash
# 假設腳本名稱為 maven_cache_cleaner.py
chmod +x maven_cache_cleaner.py
```

### 命令格式

```bash
./maven_cache_cleaner.py <repo_path> [options]
```

### 參數說明

*   `repo_path`: 【必填】你的 Maven 倉庫路徑 (例如 `~/.m2/repository`)。
*   `--dry-run`, `-n`: **(推薦首次使用)** 模擬執行模式。只列出將要刪除的文件和目錄，不執行任何實際刪除操作。
*   `--verbose`, `-v`: 顯示詳細的執行日誌，輸出每個被處理的文件或目錄。
*   `--threads <N>`, `-j <N>`: 設置並行處理的執行緒數量 (預設: 4)。
*   `--no-empty-dirs`: 禁止在清理後刪除空目錄。

### 實際範例

#### 1. 安全檢查（模擬執行）

在執行任何實際操作前，先用 `dry-run` 模式檢查將會發生什麼。

```bash
./maven_cache_cleaner.py ~/.m2/repository --dry-run
```

#### 2. 實際清理

確認模擬執行的結果符合預期後，移除 `--dry-run` 參數來執行真正的清理。

```bash
# 使用 8 個執行緒並顯示詳細日誌
./maven_cache_cleaner.py ~/.m2/repository -j 8 -v
```

執行後，Maven 在下次構建時會重新檢查依賴的元數據，但不會重新下載已有的 JAR 文件。

## 🔬 程式碼分析 (Code Analysis)

該腳本的核心是 `MavenCacheCleaner` 類，其主要方法職責如下：

*   `__init__(...)`: 初始化倉庫路徑和執行選項（如 `dry_run`, `verbose`）。
*   `clean_cache_directories()`: 專門處理 `.cache` 和 `.meta` 這類頂層快取目錄。
*   `find_and_clean_cache_files()`: 腳本的核心邏輯所在，使用 `os.walk` 遞迴掃描整個倉庫，識別所有符合清理規則的檔案，並使用 `ThreadPoolExecutor` 進行並行刪除。
*   `clean_file()`: 執行單個檔案的刪除操作，並包含錯誤處理邏輯。
*   `clean_empty_directories()`: 在檔案清理後執行，從底向上刪除空目錄，以保持倉庫整潔。
*   `generate_report()`: 彙總所有操作的統計數據（已刪除檔案數、目錄數、錯誤數），並生成用戶友好的控制台報告和詳細的文字日誌。
------------------------------------------------------------------------------
## 📜 授權 (License)

本專案採用 [MIT License](LICENSE) 授權。
