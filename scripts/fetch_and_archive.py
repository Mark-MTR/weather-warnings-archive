import hashlib
import json
import os
import sys
import time
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

# ---------- 配置 ----------
# 每个条目可以只写 url（默认 GET、json）
# 字典模式支持：method / headers / body / type:xml|json
APIS = {
    "szWarn_all": "https://weather.121.com.cn/data_cache/szWeather/warn/szWarn_all.json",
    "szAlarm": "https://weather.121.com.cn/data_cache/szWeather/alarm/szAlarm.json",
    "szImportantTips": "https://weather.121.com.cn/data_cache/szWeather/szImportantTips.json",
    "szWarnPre": "https://tf.121.com.cn/weather/typhoonWeb/lwsWarnpre.txt",
    "hk_swt": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=swt&lang=sc",
    "mo_specInfo_xml": {
        "url": "https://xml.dsmg.gov.mo/specInfo.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_specInfo2_xml": {
        "url": "https://xml.dsmg.gov.mo/specInfo2.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_specInfo3_xml": {
        "url": "https://xml.dsmg.gov.mo/specInfo3.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_specInfo4_xml": {
        "url": "https://xml.dsmg.gov.mo/specInfo4.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_SS_prob_xml": {
        "url": "https://xml.dsmg.gov.mo/SS_prob.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_TC_prob_xml": {
        "url": "https://xml.dsmg.gov.mo/TC_prob.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_hc_air_xml": {
        "url": "https://xml.dsmg.gov.mo/hc_air.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_tempDropAlert_xml": {
        "url": "https://xml.dsmg.gov.mo/tempDropAlert.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_temperatureAlert_xml": {
        "url": "https://xml.dsmg.gov.mo/temperatureAlert.xml",
        "method": "GET",
        "type": "xml",
    },
    "mo_rainstormWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/rainstormWarning.json",
    "mo_thunderstormWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/thunderstormWarning.json",
    "mo_stormsurgeWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/stormsurgeWarning.json",
    "mo_typhoonWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/typhoonWarning.json",
    "mo_monsoonWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/monsoonWarning.json",
    "mo_activeWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/activeWarning.json",
    "mo_invalidWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/invalidWarning.json",
    "mo_tsunamiWarning": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/tsunamiWarning.json",
    "mo_specialAlert": "https://cdn.dsmg.gov.mo/uploads/weather/zh-CN/specialAlert.json",
}

CACHE_DIR = ".cache"
CACHE_FILE = os.path.join(CACHE_DIR, "last_hash.json")
DATA_DIR = "data"
DEFAULT_HEADERS = {"User-Agent": "GitHub-Actions-Archive/1.0"}
REQUEST_TIMEOUT = 30


# ---------- JSON稳定哈希（原有逻辑） ----------
def stable_hash_json(content: str) -> str:
    try:
        data = json.loads(content)
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


# ---------- XML稳定哈希（新增） ----------
def stable_hash_xml(content: str) -> str:
    """
    XML版本：剔除时间类动态节点，生成稳定序列化文本求md5
    注意：xmlns命名空间、属性会保留；只删tag名匹配的动态节点
    """
    try:
        root = ET.fromstring(content)
        dynamic_tags = {"updatetime", "pubtime", "timestamp", "fetchtime", "生成时间"}

        def clean_node(node):
            # 递归清理子节点
            for child in list(node):
                clean_node(child)
                tag = child.tag.split("}")[-1].lower()  # 去掉namespace前缀
                if tag in dynamic_tags:
                    node.remove(child)

        clean_node(root)
        # 转成字符串，ET.tostring会保证顺序固定
        stable_raw = ET.tostring(root, encoding="utf-8", method="xml")
        return hashlib.md5(stable_raw).hexdigest()
    except Exception:
        # XML解析失败，退回到原始文本哈希
        return hashlib.md5(content.encode("utf-8")).hexdigest()


def compute_hash(content: str, data_type: str = "json") -> str:
    if data_type == "xml":
        return stable_hash_xml(content)
    else:
        return stable_hash_json(content)


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
    # 统一处理配置
    if isinstance(api_config, str):
        url = api_config
        method = "GET"
        headers = {}
        body = None
        data_type = "json"
    else:
        url = api_config["url"]
        method = api_config.get("method", "GET").upper()
        headers = api_config.get("headers", {})
        body = api_config.get("body", None)
        data_type = api_config.get("type", "json")

    req_headers = {**DEFAULT_HEADERS, **headers}

    try:
        if method == "GET":
            resp = requests.get(url, headers=req_headers, timeout=REQUEST_TIMEOUT)
        elif method == "POST":
            if body is not None:
                resp = requests.post(url, headers=req_headers, json=body, timeout=REQUEST_TIMEOUT)
            else:
                resp = requests.post(url, headers=req_headers, timeout=REQUEST_TIMEOUT)
        else:
            print(f"[错误] 不支持的方法 {method}，跳过 {api_name}", file=sys.stderr)
            return False
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        print(f"[错误] 抓取 {api_name} 失败: {e}", file=sys.stderr)
        return False

    new_hash = compute_hash(content, data_type)
    old_hash = cache.get(api_name, "")

    print(f"[哈希] {api_name}  旧: {old_hash if old_hash else '(空)'}  新: {new_hash}")

    if new_hash == old_hash:
        print(f"[跳过] {api_name} 无更新")
        return False

    now = datetime.now()
    dir_path = os.path.join(DATA_DIR, str(now.year), f"{now.month:02d}")
    os.makedirs(dir_path, exist_ok=True)

    timestamp = now.strftime("%Y%m%d_%H%M%S")
    # 根据类型选后缀
    if data_type == "xml":
        filename = f"{api_name}_{timestamp}.xml"
    else:
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
