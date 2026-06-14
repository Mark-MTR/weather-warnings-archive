import hashlib
import json
import os
import sys
import time
from datetime import datetime
import requests

# ---------- 配置 ----------
# 每个条目可以只写 url（默认 GET），也可以用字典指定 method / headers 等
APIS = {
    "szWarn_all": "https://weather.121.com.cn/data_cache/szWeather/warn/szWarn_all.json",
    "szAlarm": "https://weather.121.com.cn/data_cache/szWeather/alarm/szAlarm.json",
    "hk_swt": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=swt&lang=sc",
    # 澳门 API（全部使用 POST）
    "mo_specInfo": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=specInfo",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},   # 如有需要可填入请求体
    },
    "mo_specInfo2": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=specInfo2",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_specInfo3": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=specInfo3",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_specInfo4": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=specInfo4",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_rainstorm": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=rainstorm&lang=c",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_thunderstorm": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=thunderstorm&lang=c",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_monsoon": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=monsoon&lang=c",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_typhoon": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=typhoon&lang=c",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_stormsurge": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=stormsurge&lang=c",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_tsunami": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=tsunami&lang=c",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_temperatureAlert": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=temperatureAlert",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
    "mo_tempDropAlert": {
        "url": "https://new-api.smg.gov.mo/weather_v2?selection=tempDropAlert",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {},
    },
}

CACHE_DIR = ".cache"
CACHE_FILE = os.path.join(CACHE_DIR, "last_hash.json")
DATA_DIR = "data"
DEFAULT_HEADERS = {"User-Agent": "GitHub-Actions-Archive/1.0"}
REQUEST_TIMEOUT = 30  # 增加超时时间，因为澳门 API 可能响应稍慢


# ---------- 稳定哈希函数（剔除动态字段）----------
def stable_hash(content: str) -> str:
    """
    只对预警数据本体求哈希，忽略时间戳等元字段。
    可根据实际情况调整需要剔除的字段名。
    """
    try:
        data = json.loads(content)
        # 递归剔除常见的时间字段
        def remove_dynamic(obj):
            if isinstance(obj, dict):
                for key in list(obj.keys()):
                    if key.lower() in {"updatetime", "pubtime", "timestamp", "fetchtime", "生成时间"}:
                        del obj[key]
                    else:
                        remove_dynamic(obj[key])
            elif isinstance(obj, list):
                for item in obj:
                    remove_dynamic(item)
        remove_dynamic(data)
        stable_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(stable_str.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.md5(content.encode("utf-8")).hexdigest()


def compute_hash(text: str) -> str:
    """默认用 stable_hash，避免动态字段导致重复存档"""
    return stable_hash(text)


# ---------- 工具函数 ----------
def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache_dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_dict, f, indent=2)


def fetch_and_save(api_name, api_config, cache):
    """
    api_config 可以是字符串（url）或者包含 url/method/headers/body 的字典。
    返回：是否有任何文件被保存（bool）
    """
    # 统一处理配置格式
    if isinstance(api_config, str):
        url = api_config
        method = "GET"
        headers = {}
        body = None
    else:
        url = api_config["url"]
        method = api_config.get("method", "GET").upper()
        headers = api_config.get("headers", {})
        body = api_config.get("body", None)

    # 构造请求头，合并默认头
    req_headers = {**DEFAULT_HEADERS, **headers}

    try:
        if method == "GET":
            resp = requests.get(url, headers=req_headers, timeout=REQUEST_TIMEOUT)
        elif method == "POST":
            if body is not None:
                resp = requests.post(url, headers=req_headers, json=body, timeout=REQUEST_TIMEOUT)
            else:
                # 如果没有指定 body，但又是 POST，可能需要发空 body
                resp = requests.post(url, headers=req_headers, timeout=REQUEST_TIMEOUT)
        else:
            print(f"[错误] 不支持的方法 {method}，跳过 {api_name}", file=sys.stderr)
            return False

        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        print(f"[错误] 抓取 {api_name} 失败: {e}", file=sys.stderr)
        return False

    new_hash = compute_hash(content)
    old_hash = cache.get(api_name, "")

    print(f"[哈希] {api_name}  旧: {old_hash if old_hash else '(空)'}  新: {new_hash}")

    if new_hash == old_hash:
        print(f"[跳过] {api_name} 无更新")
        return False

    # 有更新，写入年月目录
    now = datetime.now()
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

    for api_name, api_config in APIS.items():
        if fetch_and_save(api_name, api_config, cache):
            any_updated = True

    if any_updated:
        save_cache(cache)
        print("检测到更新，已保存新文件并更新缓存。")
    else:
        print("所有 API 均无更新。")


if __name__ == "__main__":
    main()
