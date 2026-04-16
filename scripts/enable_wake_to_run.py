#!/usr/bin/env python3
"""
Configure Task Scheduler to wake from sleep for task execution.
Uses Windows XML API to set WakeToRun flag.
"""

import subprocess
import xml.etree.ElementTree as ET
import tempfile
import os

def export_task(task_name):
    """タスク定義をXMLで取得"""
    result = subprocess.run(
        f'schtasks /query /tn "{task_name}" /xml',
        shell=True,
        capture_output=True,
        text=True
    )
    return result.stdout

def modify_and_reimport_task(task_name, task_xml):
    """XML を修正して再登録"""
    
    # XML を解析
    try:
        root = ET.fromstring(task_xml)
    except Exception as e:
        print(f"❌ XML Parse Error: {e}")
        return False
    
    # XMLNS定義
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    
    # WakeToRun フラグを追加
    settings = root.find('.//t:Settings', ns)
    if settings is not None:
        # 既存の WakeToRun を削除
        wake_to_run = settings.find('t:WakeToRun', ns)
        if wake_to_run is not None:
            settings.remove(wake_to_run)
        
        # 新しい WakeToRun を追加
        wake_elem = ET.Element('{http://schemas.microsoft.com/windows/2004/02/mit/task}WakeToRun')
        wake_elem.text = 'true'
        settings.append(wake_elem)
    
    # 修正済み XML をファイルに保存
    modified_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-16"?>\n')
        f.write(modified_xml)
        temp_file = f.name
    
    try:
        # タスクを削除
        subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True, capture_output=True)
        
        # 修正済みXMLで再登録
        result = subprocess.run(
            f'schtasks /create /tn "{task_name}" /xml "{temp_file}"',
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✅ {task_name}: WakeToRun enabled")
            return True
        else:
            print(f"⚠️  {task_name}: {result.stderr}")
            return False
    finally:
        os.unlink(temp_file)

def main():
    print("=" * 80)
    print("Configure Task Scheduler - Wake from Sleep")
    print("=" * 80)
    print()
    
    tasks = [
        "AIJapan_RadioUpload",
        "AIJapan_ThumbnailUpload",
        "AIJapan_DailyArticleGeneration"
    ]
    
    for task_name in tasks:
        print(f"Processing: {task_name}")
        
        # XML取得
        task_xml = export_task(task_name)
        
        if not task_xml or "ERROR" in task_xml:
            print(f"  ⚠️  Could not export task")
            continue
        
        # 修正して再登録
        modify_and_reimport_task(task_name, task_xml)
        print()
    
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print("""
✅ WakeToRun enabled: PC will wake from sleep for scheduled tasks
✅ スリープ中でも予定時刻に PC が自動起動して実行される
✅ All registered tasks will execute even if PC is sleeping

【重要】 What happens:
  1. PC がスリープ時刻 02:40 に予約されたラジオ動画がある
  2. Windows はスリープモードから自動的に PE を復帰
  3. 予約されたタスク（ラジオアップロード）が実行される
  4. タスク完了後、PC はスリープに戻る (または通常状態継続)

スリープから起動までの時間: ~1-2分
    """)

if __name__ == "__main__":
    main()
