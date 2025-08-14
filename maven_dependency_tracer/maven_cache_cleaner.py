
#!/usr/bin/env python3
"""
Maven倉庫快取清理工具
清理Maven倉庫中的遠端快取檔案，包括：
- _remote.repositories
- *.lastUpdated
- *.repositories  
- resolver-status.properties
- .cache 和 .meta 目錄
"""

import os
import argparse
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from collections import defaultdict

class MavenCacheCleaner:
    def __init__(self, repo_path, verbose=False, dry_run=False):
        self.repo_path = Path(repo_path)
        self.verbose = verbose
        self.dry_run = dry_run
        self.stats = defaultdict(int)
        self.cleaned_files = []
        self.cleaned_dirs = []
        self.errors = []
        
    def log(self, message, force=False):
        """輸出日誌信息"""
        if self.verbose or force:
            print(f"[{'DRY-RUN' if self.dry_run else 'LOG'}] {message}")
    
    def clean_cache_directories(self):
        """清理主要的快取目錄"""
        cache_dirs = ['.cache', '.meta']
        
        for cache_dir in cache_dirs:
            cache_path = self.repo_path / cache_dir
            if cache_path.exists() and cache_path.is_dir():
                try:
                    if self.dry_run:
                        self.log(f"將刪除目錄: {cache_path}")
                        # 計算目錄中的檔案數量
                        file_count = sum(1 for _ in cache_path.rglob('*') if _.is_file())
                        self.stats[f'{cache_dir}_files'] = file_count
                    else:
                        self.log(f"刪除快取目錄: {cache_path}")
                        shutil.rmtree(cache_path)
                        self.cleaned_dirs.append(str(cache_path))
                        self.log(f"✓ 已刪除目錄: {cache_path}")
                    
                    self.stats[f'{cache_dir}_dirs'] += 1
                    
                except Exception as e:
                    error_msg = f"刪除目錄失敗 {cache_path}: {e}"
                    self.errors.append(error_msg)
                    self.log(f"✗ {error_msg}")
            else:
                self.log(f"快取目錄不存在: {cache_path}")
    
    def clean_file(self, file_path):
        """清理單個檔案"""
        try:
            if self.dry_run:
                self.log(f"將刪除檔案: {file_path}")
                return True
            else:
                file_path.unlink()
                self.cleaned_files.append(str(file_path))
                return True
        except Exception as e:
            error_msg = f"刪除檔案失敗 {file_path}: {e}"
            self.errors.append(error_msg)
            self.log(f"✗ {error_msg}")
            return False
    
    def find_and_clean_cache_files(self, max_workers=4):
        """尋找並清理快取檔案"""
        # 定義要清理的檔案模式
        patterns_to_clean = [
            '_remote.repositories',
            '*.lastUpdated',
            '*.repositories',
            'resolver-status.properties',
            '.lastUpdated',
            'maven-metadata-*.xml.lastUpdated',
            '*.pom.lastUpdated',
            '*.jar.lastUpdated'
        ]
        
        self.log("開始掃描快取檔案...")
        files_to_clean = []
        
        # 遍歷倉庫目錄，尋找要清理的檔案
        for root, dirs, files in os.walk(self.repo_path):
            # 跳過已經處理的快取目錄
            if any(cache_dir in Path(root).parts for cache_dir in ['.cache', '.meta']):
                continue
                
            root_path = Path(root)
            
            for file in files:
                file_path = root_path / file
                
                # 檢查是否符合清理模式
                should_clean = False
                
                # 精確匹配
                if file in ['_remote.repositories', 'resolver-status.properties', '.lastUpdated']:
                    should_clean = True
                    self.stats['exact_match'] += 1
                
                # 模式匹配
                elif (file.endswith('.lastUpdated') or 
                      file.endswith('.repositories') or
                      'lastUpdated' in file):
                    should_clean = True
                    self.stats['pattern_match'] += 1
                
                if should_clean:
                    files_to_clean.append(file_path)
        
        total_files = len(files_to_clean)
        self.log(f"找到 {total_files} 個快取檔案需要清理")
        
        if total_files == 0:
            return 0
        
        # 清理檔案
        cleaned_count = 0
        
        if total_files < 50:
            # 檔案數量少時使用單執行緒
            for file_path in files_to_clean:
                if self.clean_file(file_path):
                    cleaned_count += 1
                    if not self.dry_run and cleaned_count % 10 == 0:
                        self.log(f"已清理 {cleaned_count}/{total_files} 個檔案")
        else:
            # 檔案數量多時使用多執行緒
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self.clean_file, file_path): file_path 
                          for file_path in files_to_clean}
                
                for future in as_completed(futures):
                    if future.result():
                        cleaned_count += 1
                        if not self.dry_run and cleaned_count % 50 == 0:
                            self.log(f"已清理 {cleaned_count}/{total_files} 個檔案")
        
        return cleaned_count
    
    def clean_empty_directories(self):
        """清理空的目錄"""
        self.log("開始清理空目錄...")
        empty_dirs_removed = 0
        
        # 從最深層開始清理，避免父目錄被提前刪除
        all_dirs = []
        for root, dirs, files in os.walk(self.repo_path, topdown=False):
            all_dirs.append(Path(root))
        
        for dir_path in all_dirs:
            # 跳過根目錄
            if dir_path == self.repo_path:
                continue
                
            # 跳過快取目錄（可能已被刪除）
            if any(cache_dir in dir_path.parts for cache_dir in ['.cache', '.meta']):
                continue
            
            try:
                if dir_path.exists() and dir_path.is_dir():
                    # 檢查是否為空目錄
                    if not any(dir_path.iterdir()):
                        if self.dry_run:
                            self.log(f"將刪除空目錄: {dir_path}")
                        else:
                            dir_path.rmdir()
                            self.cleaned_dirs.append(str(dir_path))
                            self.log(f"刪除空目錄: {dir_path}")
                        
                        empty_dirs_removed += 1
                        
            except Exception as e:
                error_msg = f"清理空目錄失敗 {dir_path}: {e}"
                self.errors.append(error_msg)
                self.log(f"✗ {error_msg}")
        
        return empty_dirs_removed
    
    def generate_report(self):
        """生成清理報告"""
        total_files_cleaned = len(self.cleaned_files)
        total_dirs_cleaned = len(self.cleaned_dirs)
        
        print(f"\n{'=' * 60}")
        print(f"Maven倉庫快取清理報告 {'(模擬執行)' if self.dry_run else ''}")
        print(f"{'=' * 60}")
        print(f"倉庫路徑: {self.repo_path}")
        print(f"執行時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n清理統計:")
        print(f"  清理檔案數: {total_files_cleaned}")
        print(f"  清理目錄數: {total_dirs_cleaned}")
        print(f"  錯誤數量: {len(self.errors)}")
        
        if self.stats:
            print(f"\n檔案類型分佈:")
            for file_type, count in self.stats.items():
                if count > 0:
                    print(f"  {file_type}: {count}")
        
        if self.errors:
            print(f"\n錯誤列表:")
            for error in self.errors[:10]:  # 只顯示前10個錯誤
                print(f"  - {error}")
            if len(self.errors) > 10:
                print(f"  ... 還有 {len(self.errors) - 10} 個錯誤")
        
        # 保存詳細報告
        if not self.dry_run:
            report_file = self.repo_path / 'cache-cleanup-report.txt'
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(f"Maven倉庫快取清理報告\n")
                f.write(f"執行時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"倉庫路徑: {self.repo_path}\n\n")
                
                f.write(f"清理統計:\n")
                f.write(f"  清理檔案數: {total_files_cleaned}\n")
                f.write(f"  清理目錄數: {total_dirs_cleaned}\n")
                f.write(f"  錯誤數量: {len(self.errors)}\n\n")
                
                if self.cleaned_files:
                    f.write(f"清理的檔案列表:\n")
                    for file in self.cleaned_files:
                        f.write(f"  {file}\n")
                    f.write(f"\n")
                
                if self.cleaned_dirs:
                    f.write(f"清理的目錄列表:\n")
                    for dir in self.cleaned_dirs:
                        f.write(f"  {dir}\n")
                    f.write(f"\n")
                
                if self.errors:
                    f.write(f"錯誤列表:\n")
                    for error in self.errors:
                        f.write(f"  {error}\n")
            
            print(f"\n詳細報告已保存至: {report_file}")
        
        print(f"{'=' * 60}")
        
        return total_files_cleaned, total_dirs_cleaned, len(self.errors)

def main():
    parser = argparse.ArgumentParser(
        description='Maven倉庫快取清理工具 - 清理遠端倉庫快取檔案'
    )
    parser.add_argument('repo_path', help='Maven倉庫路徑')
    parser.add_argument('-v', '--verbose', action='store_true', help='顯示詳細日誌')
    parser.add_argument('-n', '--dry-run', action='store_true', help='模擬執行，不實際刪除檔案')
    parser.add_argument('-j', '--threads', type=int, default=4, help='並行處理執行緒數 (預設: 4)')
    parser.add_argument('--no-empty-dirs', action='store_true', help='不清理空目錄')
    
    args = parser.parse_args()
    
    # 驗證路徑
    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        print(f"錯誤: 倉庫路徑不存在: {repo_path}")
        return 1
    
    if not repo_path.is_dir():
        print(f"錯誤: 路徑不是目錄: {repo_path}")
        return 1
    
    try:
        print(f"Maven倉庫快取清理工具")
        print(f"目標路徑: {repo_path}")
        if args.dry_run:
            print("模擬執行模式 - 不會實際刪除檔案")
        print(f"開始時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 50)
        
        # 建立清理器
        cleaner = MavenCacheCleaner(repo_path, args.verbose, args.dry_run)
        
        # 1. 清理主要快取目錄
        cleaner.log("步驟 1: 清理快取目錄 (.cache, .meta)", True)
        cleaner.clean_cache_directories()
        
        # 2. 清理快取檔案
        cleaner.log("步驟 2: 清理快取檔案", True)
        files_cleaned = cleaner.find_and_clean_cache_files(args.threads)
        
        # 3. 清理空目錄（可選）
        empty_dirs_cleaned = 0
        if not args.no_empty_dirs:
            cleaner.log("步驟 3: 清理空目錄", True)
            empty_dirs_cleaned = cleaner.clean_empty_directories()
        
        # 4. 生成報告
        files_count, dirs_count, errors_count = cleaner.generate_report()
        
        # 返回結果
        if errors_count > 0:
            print(f"\n清理完成，但有 {errors_count} 個錯誤")
            return 1
        else:
            action = "將清理" if args.dry_run else "已清理"
            print(f"\n✓ 清理成功！{action} {files_count} 個檔案，{dirs_count} 個目錄")
            return 0
            
    except KeyboardInterrupt:
        print("\n\n清理被中斷")
        return 1
    except Exception as e:
        print(f"\n錯誤: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit(main())
