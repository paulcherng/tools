
#!/usr/bin/env python3
"""
Maven依賴追蹤增強工具
追蹤每個依賴的來源鏈，分析缺失依賴的必要性
"""

import os
import shutil
import subprocess
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import platform
import sys
import time
from datetime import datetime
from collections import defaultdict, deque

class MavenDependencyTracer:
    def __init__(self, project_path, source_repo, target_repo, verbose=False):
        self.project_path = Path(project_path)
        self.source_repo = Path(source_repo)
        self.target_repo = Path(target_repo)
        self.verbose = verbose
        self.dependencies = {}  # 改為字典，儲存依賴詳細信息
        self.dependency_tree = {}  # 儲存依賴樹結構
        self.dependency_chains = defaultdict(list)  # 儲存依賴鏈
        self.copied_files = []
        self.failed_copies = []
        self.missing_dependencies = []
        self.optional_dependencies = set()
        self.provided_dependencies = set()
        self.maven_cmd = self._find_maven_command()
        self.build_results = {}
        
    def _find_maven_command(self):
        """尋找Maven命令"""
        if platform.system() == "Windows":
            commands_to_try = ['mvn.cmd', 'mvn.bat', 'mvn']
        else:
            commands_to_try = ['mvn']
        
        for cmd in commands_to_try:
            try:
                result = subprocess.run([cmd, '-version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    self.log(f"找到Maven命令: {cmd}")
                    return cmd
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        raise FileNotFoundError("找不到Maven命令！")
        
    def log(self, message):
        """輸出日誌信息"""
        if self.verbose:
            print(f"[LOG] {message}")
    
    def analyze_dependencies_with_tracing(self):
        """分析依賴並建立追蹤鏈"""
        self.log("開始全面分析專案依賴...")
        
        try:
            original_cwd = os.getcwd()
            os.chdir(self.project_path)
            
            print(f"使用Maven命令: {self.maven_cmd}")
            print(f"專案路徑: {self.project_path}")
            
            # 1. 獲取完整的依賴樹（包含排除信息）
            self._analyze_dependency_tree_verbose()
            
            # 2. 分析有效POM
            self._analyze_effective_pom()
            
            # 3. 分析直接依賴
            self._analyze_direct_dependencies()
            
            # 4. 建立依賴鏈追蹤
            self._build_dependency_chains()
            
        except Exception as e:
            print(f"依賴分析時發生錯誤: {e}")
            raise
        finally:
            os.chdir(original_cwd)
    
    def _analyze_dependency_tree_verbose(self):
        """分析詳細的依賴樹"""
        self.log("執行 dependency:tree (verbose模式)...")
        
        try:
            # 使用verbose模式獲取完整依賴信息
            cmd = [self.maven_cmd, 'dependency:tree', '-Dverbose=true', '-DoutputType=text']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            
            self._parse_verbose_dependency_tree(result.stdout)
            
        except subprocess.CalledProcessError as e:
            self.log(f"獲取詳細依賴樹失敗: {e}")
            # 降級到普通模式
            try:
                cmd = [self.maven_cmd, 'dependency:tree']
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
                self._parse_simple_dependency_tree(result.stdout)
            except Exception as e2:
                self.log(f"獲取依賴樹完全失敗: {e2}")
    
    def _parse_verbose_dependency_tree(self, output):
        """解析verbose模式的依賴樹輸出"""
        if not output:
            return
        
        lines = output.split('\n')
        current_chain = []
        
        for line in lines:
            line_clean = line.strip()
            
            # 跳過非依賴行
            if not line_clean or line_clean.startswith('[INFO]') and not any(marker in line_clean for marker in ['+-', '\\-', '|']):
                continue
            
            # 解析依賴行
            # 計算縮排層級
            indent_level = 0
            for char in line:
                if char in [' ', '|', '+', '\\', '-']:
                    indent_level += 1
                else:
                    break
            
            # 提取依賴信息
            dep_match = re.search(r'([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([a-zA-Z0-9._.-]+)(?::([a-zA-Z0-9._-]+))?', line_clean)
            
            if dep_match:
                group_id = dep_match.group(1)
                artifact_id = dep_match.group(2)
                packaging = dep_match.group(3)
                version = dep_match.group(4)
                scope = dep_match.group(5) if dep_match.group(5) else 'compile'
                
                # 檢查版本格式，調整解析
                if re.match(r'^\d+\.\d+', packaging):
                    version = packaging
                    packaging = 'jar'
                
                dep_key = f"{group_id}:{artifact_id}"
                
                # 調整當前鏈的長度以匹配縮排層級
                chain_level = indent_level // 3  # 假設每層縮排3個字符
                current_chain = current_chain[:chain_level]
                current_chain.append(dep_key)
                
                # 儲存依賴信息
                dep_info = {
                    'groupId': group_id,
                    'artifactId': artifact_id,
                    'version': version,
                    'packaging': packaging,
                    'scope': scope,
                    'chain': current_chain.copy(),
                    'level': chain_level,
                    'optional': 'optional' in line_clean.lower(),
                    'excluded': 'omitted for conflict' in line_clean or 'omitted for duplicate' in line_clean,
                    'conflict_version': None
                }
                
                # 檢查衝突信息
                conflict_match = re.search(r'omitted for conflict with ([0-9.]+)', line_clean)
                if conflict_match:
                    dep_info['conflict_version'] = conflict_match.group(1)
                    dep_info['excluded'] = True
                
                # 檢查是否為provided scope
                if scope == 'provided':
                    self.provided_dependencies.add(dep_key)
                
                # 檢查是否為optional
                if dep_info['optional']:
                    self.optional_dependencies.add(dep_key)
                
                self.dependencies[dep_key] = dep_info
                
                # 建立依賴鏈映射
                if len(current_chain) > 1:
                    parent = current_chain[-2]
                    self.dependency_chains[dep_key].append(current_chain.copy())
    
    def _parse_simple_dependency_tree(self, output):
        """解析簡單模式的依賴樹"""
        if not output:
            return
            
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            
            patterns = [
                r'([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([a-zA-Z0-9._.-]+)(?::([a-zA-Z0-9._-]+))?',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    group_id = match.group(1)
                    artifact_id = match.group(2)
                    packaging = match.group(3)
                    version = match.group(4)
                    scope = match.group(5) if len(match.groups()) >= 5 and match.group(5) else 'compile'
                    
                    if re.match(r'^\d+\.\d+', packaging):
                        version = packaging
                        packaging = 'jar'
                    
                    dep_key = f"{group_id}:{artifact_id}"
                    
                    self.dependencies[dep_key] = {
                        'groupId': group_id,
                        'artifactId': artifact_id,
                        'version': version,
                        'packaging': packaging,
                        'scope': scope,
                        'chain': [dep_key],
                        'level': 0,
                        'optional': False,
                        'excluded': False
                    }
                    break
    
    def _analyze_effective_pom(self):
        """分析有效POM"""
        self.log("分析有效POM...")
        
        try:
            cmd = [self.maven_cmd, 'help:effective-pom', '-Doutput=effective-pom.xml']
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            
            effective_pom = self.project_path / 'effective-pom.xml'
            if effective_pom.exists():
                self._parse_effective_pom(effective_pom)
                effective_pom.unlink()  # 清理臨時文件
        
        except Exception as e:
            self.log(f"分析有效POM失敗: {e}")
    
    def _parse_effective_pom(self, pom_file):
        """解析有效POM文件"""
        try:
            tree = ET.parse(pom_file)
            root = tree.getroot()
            
            # 查找所有依賴管理
            for dep_mgmt in root.iter():
                if dep_mgmt.tag.endswith('dependencyManagement'):
                    for dep in dep_mgmt.iter():
                        if dep.tag.endswith('dependency'):
                            self._extract_dependency_info(dep, 'managed')
            
            # 查找插件
            for plugin in root.iter():
                if plugin.tag.endswith('plugin'):
                    group_id = None
                    artifact_id = None
                    version = None
                    
                    for child in plugin:
                        if child.tag.endswith('groupId'):
                            group_id = child.text
                        elif child.tag.endswith('artifactId'):
                            artifact_id = child.text
                        elif child.tag.endswith('version'):
                            version = child.text
                    
                    if group_id and artifact_id:
                        dep_key = f"{group_id}:{artifact_id}"
                        if dep_key not in self.dependencies:
                            self.dependencies[dep_key] = {
                                'groupId': group_id,
                                'artifactId': artifact_id,
                                'version': version or 'LATEST',
                                'packaging': 'maven-plugin',
                                'scope': 'plugin',
                                'chain': [dep_key],
                                'level': 0,
                                'optional': False,
                                'excluded': False
                            }
                            
        except Exception as e:
            self.log(f"解析有效POM失敗: {e}")
    
    def _extract_dependency_info(self, dep_element, dep_type):
        """從XML元素提取依賴信息"""
        group_id = None
        artifact_id = None
        version = None
        scope = 'compile'
        optional = False
        
        for child in dep_element:
            if child.tag.endswith('groupId'):
                group_id = child.text
            elif child.tag.endswith('artifactId'):
                artifact_id = child.text
            elif child.tag.endswith('version'):
                version = child.text
            elif child.tag.endswith('scope'):
                scope = child.text
            elif child.tag.endswith('optional'):
                optional = child.text and child.text.lower() == 'true'
        
        if group_id and artifact_id:
            dep_key = f"{group_id}:{artifact_id}"
            if dep_key not in self.dependencies:
                self.dependencies[dep_key] = {
                    'groupId': group_id,
                    'artifactId': artifact_id,
                    'version': version,
                    'packaging': 'jar',
                    'scope': scope,
                    'chain': [dep_key],
                    'level': 0,
                    'optional': optional,
                    'excluded': False,
                    'type': dep_type
                }
                
                if optional:
                    self.optional_dependencies.add(dep_key)
    
    def _analyze_direct_dependencies(self):
        """分析直接依賴"""
        self.log("分析直接依賴...")
        
        pom_file = self.project_path / 'pom.xml'
        if pom_file.exists():
            try:
                tree = ET.parse(pom_file)
                root = tree.getroot()
                
                # 處理namespace
                namespace = {'maven': 'http://maven.apache.org/POM/4.0.0'}
                if root.tag.startswith('{'):
                    namespace = {'maven': root.tag.split('}')[0][1:]}
                
                # 查找直接依賴
                for dep in root.iter():
                    if dep.tag.endswith('dependency'):
                        self._extract_dependency_info(dep, 'direct')
                        
            except ET.ParseError as e:
                self.log(f"解析專案POM失敗: {e}")
    

    def _build_dependency_chains(self):
        """建立依賴鏈追蹤"""
        self.log("建立依賴鏈追蹤...")
        
        # 如果沒有鏈信息，嘗試重新分析
        if not any(len(chains) > 0 for chains in self.dependency_chains.values()):
            self._rebuild_chains_from_tree()
    
    def _rebuild_chains_from_tree(self):
        """從依賴樹重建鏈信息"""
        try:
            cmd = [self.maven_cmd, 'dependency:tree', '-DoutputType=text']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            
            lines = result.stdout.split('\n')
            stack = []  # 用於追蹤當前路徑
            
            for line in lines:
                if not line.strip():
                    continue
                
                # 計算縮排層級
                indent = 0
                for char in line:
                    if char in [' ', '|', '+', '\\', '-']:
                        indent += 1
                    else:
                        break
                
                # 提取依賴信息
                dep_match = re.search(r'([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):', line)
                if dep_match:
                    group_id = dep_match.group(1)
                    artifact_id = dep_match.group(2)
                    dep_key = f"{group_id}:{artifact_id}"
                    
                    # 調整堆疊以匹配當前層級
                    level = max(0, indent // 3 - 1)  # 估算層級
                    stack = stack[:level]
                    
                    # 建立完整鏈路
                    current_chain = stack + [dep_key]
                    
                    if dep_key in self.dependencies:
                        if not self.dependency_chains[dep_key]:
                            self.dependency_chains[dep_key] = []
                        self.dependency_chains[dep_key].append(current_chain.copy())
                    
                    stack.append(dep_key)
                    
        except Exception as e:
            self.log(f"重建依賴鏈失敗: {e}")
    
    def copy_dependency_with_tracking(self, dep_key):
        """複製單個依賴並追蹤結果"""
        if dep_key not in self.dependencies:
            return False
        
        dep_info = self.dependencies[dep_key]
        group_id = dep_info['groupId']
        artifact_id = dep_info['artifactId']
        version = dep_info['version']
        packaging = dep_info['packaging']
        
        if not version or version == 'LATEST':
            error_info = {
                'key': dep_key,
                'error': '版本信息缺失',
                'chains': self.dependency_chains.get(dep_key, []),
                'info': dep_info
            }
            self.failed_copies.append(error_info)
            return False
        
        group_path = group_id.replace('.', '/')
        artifact_path = f"{group_path}/{artifact_id}/{version}"
        
        source_dir = self.source_repo / artifact_path
        target_dir = self.target_repo / artifact_path
        
        if not source_dir.exists():
            error_info = {
                'key': dep_key,
                'error': f'來源目錄不存在: {source_dir}',
                'chains': self.dependency_chains.get(dep_key, []),
                'info': dep_info,
                'source_path': str(source_dir)
            }
            self.failed_copies.append(error_info)
            self.missing_dependencies.append(dep_key)
            return False
        
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            
            copied_count = 0
            for file in source_dir.iterdir():
                if file.is_file():
                    target_file = target_dir / file.name
                    shutil.copy2(file, target_file)
                    self.copied_files.append(str(target_file))
                    copied_count += 1
            
            # 複製maven-metadata檔案
            metadata_dir = source_dir.parent
            for metadata_file in metadata_dir.glob('maven-metadata*'):
                if metadata_file.is_file():
                    target_metadata = target_dir.parent / metadata_file.name
                    target_metadata.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(metadata_file, target_metadata)
                    self.copied_files.append(str(target_metadata))
                    copied_count += 1
            
            self.log(f"✓ 已複製 {dep_key}:{version} ({copied_count} 個檔案)")
            return True
            
        except Exception as e:
            error_info = {
                'key': dep_key,
                'error': f'複製失敗: {e}',
                'chains': self.dependency_chains.get(dep_key, []),
                'info': dep_info
            }
            self.failed_copies.append(error_info)
            return False
    
    def copy_all_dependencies_with_tracking(self, max_workers=4):
        """複製所有依賴並追蹤"""
        if not self.dependencies:
            print("警告: 沒有找到任何依賴")
            return 0
        
        print(f"開始複製 {len(self.dependencies)} 個依賴...")
        self.target_repo.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        
        # 過濾掉被排除的依賴
        active_deps = {k: v for k, v in self.dependencies.items() if not v.get('excluded', False)}
        print(f"實際需要複製: {len(active_deps)} 個依賴 (排除了 {len(self.dependencies) - len(active_deps)} 個)")
        
        if len(active_deps) < 10:
            for dep_key in active_deps:
                if self.copy_dependency_with_tracking(dep_key):
                    success_count += 1
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_dep = {
                    executor.submit(self.copy_dependency_with_tracking, dep_key): dep_key 
                    for dep_key in active_deps
                }
                
                for future in as_completed(future_to_dep):
                    if future.result():
                        success_count += 1
        
        return success_count
    
    def analyze_missing_dependencies(self):
        """分析缺失依賴的必要性"""
        if not self.missing_dependencies:
            return
        
        print(f"\n分析缺失依賴的必要性...")
        print("=" * 60)
        
        # 按類型分類缺失的依賴
        essential_missing = []
        optional_missing = []
        provided_missing = []
        plugin_missing = []
        conflict_missing = []
        
        for dep_key in self.missing_dependencies:
            dep_info = self.dependencies[dep_key]
            
            if dep_info.get('excluded', False):
                conflict_missing.append(dep_key)
            elif dep_info.get('scope') == 'provided':
                provided_missing.append(dep_key)
            elif dep_info.get('optional', False):
                optional_missing.append(dep_key)
            elif dep_info.get('packaging') == 'maven-plugin':
                plugin_missing.append(dep_key)
            else:
                essential_missing.append(dep_key)
        
        # 顯示分析結果
        self._print_dependency_category("🔴 必要依賴缺失 (可能影響編譯)", essential_missing)
        self._print_dependency_category("🟡 可選依賴缺失 (通常不影響編譯)", optional_missing)
        self._print_dependency_category("🔵 Provided依賴缺失 (運行時提供)", provided_missing)
        self._print_dependency_category("🟣 Maven插件缺失 (可能影響構建)", plugin_missing)
        self._print_dependency_category("🟤 衝突依賴缺失 (已被排除)", conflict_missing)
        
        return {
            'essential': essential_missing,
            'optional': optional_missing,
            'provided': provided_missing,
            'plugin': plugin_missing,
            'conflict': conflict_missing
        }
    
    def _print_dependency_category(self, title, dep_list):
        """顯示特定類型的依賴"""
        if not dep_list:
            return
        
        print(f"\n{title} ({len(dep_list)}個):")
        print("-" * 50)
        
        for dep_key in dep_list[:10]:  # 只顯示前10個
            dep_info = self.dependencies[dep_key]
            chains = self.dependency_chains.get(dep_key, [])
            
            print(f"\n📦 {dep_key}:{dep_info.get('version', 'unknown')}")
            print(f"   範圍: {dep_info.get('scope', 'compile')}")
            print(f"   類型: {dep_info.get('packaging', 'jar')}")
            
            if dep_info.get('optional'):
                print("   🏷️  可選依賴")
            if dep_info.get('excluded'):
                print("   ❌ 已被排除")
                if dep_info.get('conflict_version'):
                    print(f"   ⚠️  版本衝突，被 {dep_info['conflict_version']} 取代")
            
            # 顯示依賴鏈
            if chains:
                print("   📋 依賴鏈:")
                for i, chain in enumerate(chains[:3]):  # 最多顯示3條鏈
                    chain_str = " → ".join(chain)
                    print(f"      {i+1}. {chain_str}")
                if len(chains) > 3:
                    print(f"      ... 還有 {len(chains) - 3} 條鏈")
            else:
                print("   📋 直接依賴")
        
        if len(dep_list) > 10:
            print(f"\n   ... 還有 {len(dep_list) - 10} 個依賴")
    
    def verify_with_actual_build(self):
        """通過實際構建驗證依賴的必要性"""
        print(f"\n驗證依賴必要性...")
        print("=" * 40)
        
        original_cwd = os.getcwd()
        
        try:
            os.chdir(self.project_path)
            
            # 測試1: 嘗試編譯
            print("1. 測試編譯階段...")
            compile_result = subprocess.run(
                [self.maven_cmd, 'compile', '-q'],
                capture_output=True, text=True, timeout=300
            )
            
            compile_success = compile_result.returncode == 0
            print(f"   編譯結果: {'✓ 成功' if compile_success else '✗ 失敗'}")
            
            if not compile_success:
                # 分析編譯錯誤中提到的缺失依賴
                missing_in_compile = self._extract_missing_from_error(compile_result.stderr)
                if missing_in_compile:
                    print("   編譯錯誤中提到的缺失依賴:")
                    for missing in missing_in_compile:
                        print(f"     - {missing}")
            
            # 測試2: 嘗試打包
            if compile_success:
                print("\n2. 測試打包階段...")
                package_result = subprocess.run(
                    [self.maven_cmd, 'package', '-DskipTests', '-q'],
                    capture_output=True, text=True, timeout=300
                )
                
                package_success = package_result.returncode == 0
                print(f"   打包結果: {'✓ 成功' if package_success else '✗ 失敗'}")
                
                if not package_success:
                    missing_in_package = self._extract_missing_from_error(package_result.stderr)
                    if missing_in_package:
                        print("   打包錯誤中提到的缺失依賴:")
                        for missing in missing_in_package:
                            print(f"     - {missing}")
            
            # 結論
            print(f"\n結論:")
            if compile_success:
                print("✅ 現有依賴足以支持基本編譯")
                if 'package_success' in locals() and package_success:
                    print("✅ 現有依賴足以支持完整打包")
                    print("💡 缺失的依賴可能都是非必要的")
                else:
                    print("⚠️  打包階段可能需要額外依賴")
            else:
                print("❌ 編譯失敗，可能缺少必要依賴")
                
        except subprocess.TimeoutExpired:
            print("   ⏰ 構建超時")
        except Exception as e:
            print(f"   ❌ 構建測試失敗: {e}")
        
        finally:
            os.chdir(original_cwd)
    
    def _extract_missing_from_error(self, error_output):
        """從錯誤輸出中提取缺失的依賴"""
        missing_deps = []
        if not error_output:
            return missing_deps
        
        # 常見的缺失依賴錯誤模式
        patterns = [
            r'Could not find artifact ([^:]+:[^:]+:[^:]+:[^:\s]+)',
            r'Failure to find ([^:]+:[^:]+:[^:]+:[^:\s]+)',
            r'The following artifacts could not be resolved: ([^:]+:[^:]+:[^:]+:[^:\s]+)',
            r'Missing artifact ([^:]+:[^:]+:[^:]+:[^:\s]+)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, error_output)
            missing_deps.extend(matches)
        
        return list(set(missing_deps))  # 去重
    

    def generate_enhanced_report(self):
        """生成增強版報告"""
        print(f"\n{'='*60}")
        print("Maven依賴分析詳細報告")
        print(f"{'='*60}")
        
        # 基本統計
        total_deps = len(self.dependencies)
        active_deps = len([d for d in self.dependencies.values() if not d.get('excluded', False)])
        copied_deps = active_deps - len(self.missing_dependencies)
        
        print(f"專案路徑: {self.project_path}")
        print(f"來源倉庫: {self.source_repo}")
        print(f"目標倉庫: {self.target_repo}")
        print(f"分析時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\n依賴統計:")
        print(f"  發現總依賴: {total_deps}")
        print(f"  需要複製: {active_deps}")
        print(f"  成功複製: {copied_deps}")
        print(f"  複製失敗: {len(self.missing_dependencies)}")
        print(f"  被排除: {total_deps - active_deps}")
        
        # 按範圍統計
        scope_stats = defaultdict(int)
        for dep_info in self.dependencies.values():
            if not dep_info.get('excluded', False):
                scope_stats[dep_info.get('scope', 'compile')] += 1
        
        print(f"\n依賴範圍分布:")
        for scope, count in sorted(scope_stats.items()):
            print(f"  {scope}: {count}")
        
        # 分析缺失依賴
        missing_analysis = self.analyze_missing_dependencies()
        
        # 驗證實際構建需求
        self.verify_with_actual_build()
        
        # 生成建議
        self._generate_recommendations(missing_analysis)
        
        # 保存詳細報告到文件
        report_data = self._create_report_data(missing_analysis)
        report_file = self.target_repo / 'dependency-analysis-report.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 詳細報告已保存: {report_file}")
        
        return missing_analysis
    
    def _generate_recommendations(self, missing_analysis):
        """生成修復建議"""
        print(f"\n💡 修復建議:")
        print("-" * 30)
        
        essential_missing = missing_analysis.get('essential', [])
        optional_missing = missing_analysis.get('optional', [])
        provided_missing = missing_analysis.get('provided', [])
        plugin_missing = missing_analysis.get('plugin', [])
        
        if not essential_missing and not plugin_missing:
            print("✅ 太好了！所有必要依賴都已找到")
            if optional_missing:
                print(f"ℹ️  有 {len(optional_missing)} 個可選依賴缺失，通常不影響構建")
            if provided_missing:
                print(f"ℹ️  有 {len(provided_missing)} 個provided依賴缺失，這些在運行時由容器提供")
        else:
            print("需要處理的缺失依賴:")
            
            if essential_missing:
                print(f"\n🔴 優先處理 ({len(essential_missing)}個):")
                for dep_key in essential_missing[:5]:
                    dep_info = self.dependencies[dep_key]
                    print(f"  {dep_key}:{dep_info.get('version', 'unknown')}")
                    
                    # 提供解決方案
                    print("    💡 解決方案:")
                    print(f"       1. 檢查Maven中央倉庫是否有此版本")
                    print(f"       2. 嘗試更新到可用版本")
                    print(f"       3. 檢查是否拼寫錯誤")
                    
                    # 檢查是否有類似的可用版本
                    similar_versions = self._find_similar_versions(dep_info['groupId'], dep_info['artifactId'])
                    if similar_versions:
                        print(f"       4. 可用的類似版本: {', '.join(similar_versions[:3])}")
            
            if plugin_missing:
                print(f"\n🟣 Maven插件缺失 ({len(plugin_missing)}個):")
                for dep_key in plugin_missing[:3]:
                    dep_info = self.dependencies[dep_key]
                    print(f"  {dep_key}:{dep_info.get('version', 'unknown')}")
                print("    💡 通常可以通過更新Maven版本或明確指定插件版本解決")
        
        # 通用建議
        print(f"\n📝 通用建議:")
        print("1. 定期更新依賴版本以獲得更好的可用性")
        print("2. 使用dependency:analyze檢查未使用的依賴")
        print("3. 考慮使用dependencyManagement統一管理版本")
        print("4. 對於企業環境，建議建立私有Maven倉庫")
        
        # 自動化腳本建議
        if essential_missing or plugin_missing:
            print(f"\n🔧 自動化解決腳本:")
            print("   創建以下腳本來檢查和下載缺失依賴:")
            
            script_content = "#!/bin/bash\n"
            script_content += "# 自動下載缺失依賴腳本\n\n"
            
            for dep_key in (essential_missing + plugin_missing)[:10]:
                dep_info = self.dependencies[dep_key]
                artifact_path = f"{dep_info['groupId'].replace('.', '/')}/{dep_info['artifactId']}/{dep_info['version']}"
                script_content += f"# 下載 {dep_key}\n"
                script_content += f"mkdir -p ~/.m2/repository/{artifact_path}\n"
                script_content += f"# wget https://repo1.maven.org/maven2/{artifact_path}/*.jar\n\n"
            
            script_file = self.target_repo / 'download-missing-deps.sh'
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script_content)
            print(f"   腳本已生成: {script_file}")
    
    def _find_similar_versions(self, group_id, artifact_id):
        """尋找類似可用版本"""
        similar_versions = []
        
        # 在來源倉庫中尋找相同artifact的其他版本
        group_path = group_id.replace('.', '/')
        artifact_dir = self.source_repo / group_path / artifact_id
        
        if artifact_dir.exists():
            for version_dir in artifact_dir.iterdir():
                if version_dir.is_dir() and version_dir.name[0].isdigit():
                    similar_versions.append(version_dir.name)
        
        return sorted(similar_versions, key=lambda v: [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', v)], reverse=True)[:5]
    
    def _create_report_data(self, missing_analysis):
        """創建詳細報告數據"""
        return {
            'timestamp': datetime.now().isoformat(),
            'project_info': {
                'path': str(self.project_path),
                'source_repo': str(self.source_repo),
                'target_repo': str(self.target_repo)
            },
            'statistics': {
                'total_dependencies': len(self.dependencies),
                'active_dependencies': len([d for d in self.dependencies.values() if not d.get('excluded', False)]),
                'copied_dependencies': len(self.dependencies) - len(self.missing_dependencies),
                'missing_dependencies': len(self.missing_dependencies),
                'excluded_dependencies': len([d for d in self.dependencies.values() if d.get('excluded', False)])
            },
            'scope_distribution': {
                scope: len([d for d in self.dependencies.values() 
                           if d.get('scope') == scope and not d.get('excluded', False)])
                for scope in set(d.get('scope', 'compile') for d in self.dependencies.values())
            },
            'missing_analysis': missing_analysis,
            'all_dependencies': {
                dep_key: {
                    'info': dep_info,
                    'chains': self.dependency_chains.get(dep_key, []),
                    'status': 'missing' if dep_key in self.missing_dependencies else 'copied'
                }
                for dep_key, dep_info in self.dependencies.items()
            },
            'failed_copies_detail': self.failed_copies
        }
    
    def create_offline_settings_xml(self):
        """建立離線環境的settings.xml"""
        settings_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 
                              http://maven.apache.org/xsd/settings-1.0.0.xsd">
    
    <localRepository>{self.target_repo}</localRepository>
    <offline>true</offline>
    
    <mirrors>
        <mirror>
            <id>local-repo</id>
            <name>Local Repository</name>
            <url>file://{self.target_repo}</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>
    
    <profiles>
        <profile>
            <id>offline</id>
            <repositories>
                <repository>
                    <id>local-repo</id>
                    <name>Local Repository</name>
                    <url>file://{self.target_repo}</url>
                    <layout>default</layout>
                    <releases>
                        <enabled>true</enabled>
                        <updatePolicy>never</updatePolicy>
                        <checksumPolicy>ignore</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>true</enabled>
                        <updatePolicy>never</updatePolicy>
                        <checksumPolicy>ignore</checksumPolicy>
                    </snapshots>
                </repository>
            </repositories>
            <pluginRepositories>
                <pluginRepository>
                    <id>local-repo</id>
                    <name>Local Repository</name>
                    <url>file://{self.target_repo}</url>
                    <layout>default</layout>
                    <releases>
                        <enabled>true</enabled>
                        <updatePolicy>never</updatePolicy>
                        <checksumPolicy>ignore</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>true</enabled>
                        <updatePolicy>never</updatePolicy>
                        <checksumPolicy>ignore</checksumPolicy>
                    </snapshots>
                </pluginRepository>
            </pluginRepositories>
        </profile>
    </profiles>
    
    <activeProfiles>
        <activeProfile>offline</activeProfile>
    </activeProfiles>
</settings>'''
        
        settings_file = self.target_repo / 'settings.xml'
        with open(settings_file, 'w', encoding='utf-8') as f:
            f.write(settings_content)
        
        return settings_file

def main():
    parser = argparse.ArgumentParser(
        description='Maven依賴追蹤分析工具 - 詳細追蹤每個依賴的來源鏈'
    )
    parser.add_argument('project_path', help='Maven專案路徑')
    parser.add_argument('source_repo', help='來源Maven倉庫路徑')
    parser.add_argument('target_repo', help='目標Maven倉庫路徑')
    parser.add_argument('-v', '--verbose', action='store_true', help='顯示詳細日誌')
    parser.add_argument('-j', '--threads', type=int, default=4, help='並行處理執行緒數')
    parser.add_argument('--analyze-only', action='store_true', help='只分析不複製')
    parser.add_argument('--copy-missing-only', action='store_true', help='只複製之前分析出缺失的依賴')
    
    args = parser.parse_args()
    
    # 驗證路徑
    project_path = Path(args.project_path)
    source_repo = Path(args.source_repo)
    target_repo = Path(args.target_repo)
    
    if not project_path.exists():
        print(f"錯誤: 專案路徑不存在: {project_path}")
        return 1
    
    pom_file = project_path / 'pom.xml'
    if not pom_file.exists():
        print(f"錯誤: 在專案路徑中找不到pom.xml: {pom_file}")
        return 1
    
    if not args.analyze_only and not source_repo.exists():
        print(f"錯誤: 來源倉庫路徑不存在: {source_repo}")
        return 1
    
    try:
        print("Maven依賴追蹤分析工具")
        print("=" * 60)
        print(f"專案路徑: {project_path}")
        print(f"來源倉庫: {source_repo}")
        print(f"目標倉庫: {target_repo}")
        print(f"執行緒數: {args.threads}")
        print("-" * 60)
        
        # 建立追蹤器實例
        tracer = MavenDependencyTracer(
            project_path, source_repo, target_repo, args.verbose
        )
        
        # 步驟1: 分析依賴
        print("\n步驟 1: 深度分析專案依賴...")
        tracer.analyze_dependencies_with_tracing()
        
        if not tracer.dependencies:
            print("警告: 沒有找到任何依賴")
            return 1
        
        print(f"發現 {len(tracer.dependencies)} 個依賴")
        

        # 步驟2: 複製依賴（如果需要）
        if not args.analyze_only:
            print(f"\n步驟 2: 複製依賴到目標倉庫...")
            
            if args.copy_missing_only:
                # 從之前的報告中載入缺失依賴
                report_file = target_repo / 'dependency-analysis-report.json'
                if report_file.exists():
                    with open(report_file, 'r', encoding='utf-8') as f:
                        previous_report = json.load(f)
                    
                    missing_keys = previous_report.get('missing_analysis', {}).get('essential', [])
                    missing_keys.extend(previous_report.get('missing_analysis', {}).get('plugin', []))
                    
                    print(f"從之前報告中找到 {len(missing_keys)} 個需要重新嘗試的依賴")
                    
                    success_count = 0
                    for dep_key in missing_keys:
                        if tracer.copy_dependency_with_tracking(dep_key):
                            success_count += 1
                    
                    print(f"重新複製結果: {success_count}/{len(missing_keys)}")
                else:
                    print("找不到之前的分析報告，執行完整複製...")
                    success_count = tracer.copy_all_dependencies_with_tracking(args.threads)
            else:
                success_count = tracer.copy_all_dependencies_with_tracking(args.threads)
            
            total_active = len([d for d in tracer.dependencies.values() if not d.get('excluded', False)])
            print(f"複製完成: {success_count}/{total_active} 個依賴")
        else:
            print("跳過複製階段（僅分析模式）")
        
        # 步驟3: 生成詳細報告
        print(f"\n步驟 3: 生成詳細分析報告...")
        missing_analysis = tracer.generate_enhanced_report()
        
        # 步驟4: 創建離線settings.xml
        if not args.analyze_only:
            settings_file = tracer.create_offline_settings_xml()
            print(f"\n離線構建配置文件: {settings_file}")
        
        # 最終結果總結
        print(f"\n" + "=" * 60)
        print("任務完成總結")
        print("=" * 60)
        
        essential_missing = missing_analysis.get('essential', [])
        plugin_missing = missing_analysis.get('plugin', [])
        
        if not essential_missing and not plugin_missing:
            print("🎉 完美！所有關鍵依賴都已就緒")
            print("✅ 離線環境應該可以正常構建")
            
            if not args.analyze_only:
                print("\n🚀 下一步操作:")
                print("1. 使用生成的settings.xml進行離線構建")
                print("2. 執行: mvn -s settings.xml clean package --offline")
                print("3. 如果需要，可以打包整個倉庫目錄部署")
        else:
            critical_count = len(essential_missing) + len(plugin_missing)
            print(f"⚠️  發現 {critical_count} 個關鍵依賴缺失")
            print("❌ 離線環境可能無法正常構建")
            
            print(f"\n🔧 需要處理的關鍵依賴:")
            all_critical = essential_missing + plugin_missing
            for i, dep_key in enumerate(all_critical[:5], 1):
                dep_info = tracer.dependencies[dep_key]
                chains = tracer.dependency_chains.get(dep_key, [])
                
                print(f"\n{i}. {dep_key}:{dep_info.get('version', 'unknown')}")
                if chains and len(chains[0]) > 1:
                    print(f"   引入路徑: {' → '.join(chains[0])}")
                else:
                    print(f"   直接依賴")
                    
                # 檢查本地是否有類似版本
                similar = tracer._find_similar_versions(dep_info['groupId'], dep_info['artifactId'])
                if similar:
                    print(f"   可用版本: {', '.join(similar[:3])}")
            
            if len(all_critical) > 5:
                print(f"\n   ... 還有 {len(all_critical) - 5} 個依賴需要處理")
        
        # 提供具體的解決方案
        print(f"\n💡 問題解決指南:")
        
        if essential_missing:
            print("\n對於缺失的必要依賴:")
            print("1. 檢查Maven中央倉庫: https://search.maven.org/")
            print("2. 手動下載JAR文件到正確的倉庫路徑")
            print("3. 使用 mvn install:install-file 安裝本地JAR")
            print("4. 考慮替換為可用的類似依賴")
        
        if plugin_missing:
            print("\n對於缺失的Maven插件:")
            print("1. 更新Maven到最新版本")
            print("2. 在POM中明確指定插件版本")
            print("3. 從Maven插件倉庫手動下載")
        
        # 關於shiro-core:jakarta的特別說明
        if any('shiro-core' in dep_key and 'jakarta' in tracer.dependencies[dep_key].get('version', '') 
               for dep_key in essential_missing):
            print(f"\n🔍 關於 org.apache.shiro:shiro-core:jakarta:")
            print("   這可能是一個不存在的版本標識符")
            print("   建議檢查:")
            print("   1. 是否應該是具體的版本號（如 1.9.1, 1.10.0）")
            print("   2. 是否在dependencyManagement中正確定義")
            print("   3. 父POM是否正確設置了版本")
        
        return 0 if not essential_missing and not plugin_missing else 1
        
    except KeyboardInterrupt:
        print("\n\n任務被中斷")
        return 1
    except Exception as e:
        print(f"\n錯誤: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit(main())
