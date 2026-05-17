import hashlib
import json
import os
import sys
import time
from datetime import datetime

import requests

# ---------- 配置 ----------
APIS = {
    "szWarn_all": "https://weather.121.com.cn/data_cache/szWeather/warn/szWarn_all.json",
    "szAlarm": "https://weather.121.com.cn/data_cache/szWeather/alarm/szAlarm.json",
    "hk_swt": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=swt&lang=sc",
}

CACHE_DIR = ".cache"
CACHE_FILE = os.path.join(CACHE_DIR, "last_hash.json")
DATA_DIR = "data"
REQUEST_HEADERS = {"User-Agent": "GitHub-Actions-Archive/1.0"}
REQUEST_TIMEOUT = 15  # 秒

# ---------- 工具函数 ----------
def load_cache():
    """读取上次的 hash 缓存，若不存在返回空字典"""
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache_dict):
    """保存 hash 缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_dict, f, indent=2)


def compute_hash(text: str) -> str:
    """计算文本内容的 MD5 哈希"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def fetch_and_save(api_name, url, cache):
    """
    抓取 API 数据，如果与上次哈希不同，则保存到 data/ 并更新缓存
    返回：是否有任何文件被保存（bool）
    """
    if '?' in url:
        url += f'&_t={int(time.time())}'
    else:
        url += f'?_t={int(time.time())}'
        
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        print(f"[错误] 抓取 {api_name} 失败: {e}", file=sys.stderr)
        return False

    new_hash = compute_hash(content)
    old_hash = cache.get(api_name, "")

    if new_hash == old_hash:
        print(f"[跳过] {api_name} 无更新")
        return False

    # 有更新，写入年月目录
    now = datetime.now()  # 使用东八区时间，需在环境中设置 TZ=Asia/Shanghai
    dir_path = os.path.join(DATA_DIR, str(now.year), f"{now.month:02d}")
    os.makedirs(dir_path, exist_ok=True)

    timestamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{api_name}_{timestamp}.json"
    filepath = os.path.join(dir_path, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    cache[api_name] = new_hash
    print(f"[存档] {filepath}")
    return True


def main():
    cache = load_cache()
    any_updated = False

    for api_name, url in APIS.items():
        if fetch_and_save(api_name, url, cache):
            any_updated = True

    if any_updated:
        save_cache(cache)
        print("检测到更新，已保存新文件并更新缓存。")
    else:
        print("所有 API 均无更新。")


if __name__ == "__main__":
    main()
