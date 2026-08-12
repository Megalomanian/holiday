#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成都重庆行程 · 高德地图 API 助手
================================
需要：高德开放平台 Web服务 Key（免费申请，见 README 顶部说明）

用法：
  export AMAP_KEY=你的Key            # 或每行命令前加 AMAP_KEY=xxx
  python3 amap_planner.py --geocode 成都春熙路
  python3 amap_planner.py --route   春熙路 成都大熊猫繁育研究基地
  python3 amap_planner.py --transit 春熙路 成都东站
  python3 amap_planner.py --walk    解放碑 朝天门码头
  python3 amap_planner.py --itinerary        # 内置行程所有路段(驾车)，一键输出
  python3 amap_planner.py --list             # 列出内置行程点位
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://restapi.amap.com"

# 内置行程点位（对应《上海出发成都重庆五天四晚攻略.md》）
ITINERARY = {
    "成都段": ["成都双流国际机场", "成都大熊猫繁育研究基地", "春熙路", "青城山风景区", "宽窄巷子", "人民公园", "成都东站"],
    "重庆段": ["重庆北站", "解放碑", "李子坝轻轨站", "长江索道", "洪崖洞", "华生园金色蛋糕梦幻城堡", "重庆江北国际机场"],
}


def get_key():
    key = os.environ.get("AMAP_KEY")
    if not key:
        sys.exit("错误：未设置 AMAP_KEY 环境变量。\n请先 export AMAP_KEY=你的高德Web服务Key（申请见回复说明）")
    return key


def call(path, params, retries=6):
    params = dict(params)
    params["key"] = get_key()
    for attempt in range(retries):
        url = BASE + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "amap-planner/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("status") == "1":
            return data
        if data.get("infocode") == "10021":  # QPS 超限，稍等后重试
            time.sleep(1.5 * (attempt + 1))
            continue
        sys.exit(f"API 返回错误：{data.get('info')} ({data.get('infocode')})")
    sys.exit(f"API 返回错误：QPS 超限，重试 {retries} 次仍失败")
    return None


def geocode(address, city=None):
    """地址/地名 → 经纬度 (lng,lat)。优先 POI 关键字搜索（定位更准），失败回退地理编码。
    配额：地理编码 5000次/日；POI 搜索 100次/日（仅用于带城市提示的关键点位）"""
    if city:
        try:
            data = call("/v3/place/text", {"keywords": address, "city": city, "offset": 5, "extensions": "base"})
            pois = data.get("pois") or []
            if pois:
                # 优先选结果中名称/地址含目标城市的 POI，避免解析到外地同名地点
                pick = next((p for p in pois[:5] if city in p.get("name", "") + p.get("address", "")), pois[0])
                loc = pick["location"]
                lng, lat = loc.split(",")
                return lng, lat, pick.get("address", "")
        except SystemExit:
            pass  # POI 搜索失败则回退地理编码
    params = {"address": address}
    if city:
        params["city"] = city
    data = call("/v3/geocode/geo", params)
    gs = data.get("geocodes") or []
    if not gs:
        sys.exit(f"地理编码失败：找不到「{address}」")
    loc = gs[0]["location"]
    lng, lat = loc.split(",")
    return lng, lat, gs[0].get("formatted_address", "")


def driving(origin, destination, city=None):
    """驾车路径规划 → (距离km, 时长min)。配额：个人开发者 5000次/日"""
    o = geocode(origin, city)
    d = geocode(destination, city)
    data = call("/v3/direction/driving", {
        "origin": f"{o[0]},{o[1]}", "destination": f"{d[0]},{d[1]}",
        "extensions": "base", "strategy": 0,
    })
    path = data["route"]["paths"][0]
    return float(path["distance"]) / 1000.0, float(path["duration"]) / 60.0, o, d


def transit(origin, destination, city="成都"):
    """公交/地铁路径规划 → (距离km, 时长min, 换乘次数)。配额：个人开发者 5000次/日"""
    o = geocode(origin, city)
    d = geocode(destination, city)
    data = call("/v3/direction/transit/integrated", {
        "origin": f"{o[0]},{o[1]}", "destination": f"{d[0]},{d[1]}",
        "city": city, "cityd": city, "strategy": 0, "extensions": "base",
    })
    transits = data["route"].get("transits") or []
    if not transits:
        return None
    t = transits[0]
    return float(t["distance"]) / 1000.0, float(t["duration"]) / 60.0, len(t.get("segments", [])) - 1


def walking(origin, destination, city=None):
    """步行路径规划 → (距离km, 时长min)。配额：个人开发者 5000次/日"""
    o = geocode(origin, city)
    d = geocode(destination, city)
    data = call("/v3/direction/walking", {
        "origin": f"{o[0]},{o[1]}", "destination": f"{d[0]},{d[1]}",
        "extensions": "base",
    })
    path = data["route"]["paths"][0]
    return float(path["distance"]) / 1000.0, float(path["duration"]) / 60.0, o, d


def main():
    ap = argparse.ArgumentParser(description="高德地图 API 行程助手")
    ap.add_argument("--geocode", metavar="地点", help="地名转经纬度")
    ap.add_argument("--route", nargs=2, metavar=("起点", "终点"), help="驾车路线(距离/时长)")
    ap.add_argument("--transit", nargs=2, metavar=("起点", "终点"), help="公交/地铁路线(距离/时长/换乘)")
    ap.add_argument("--walk", nargs=2, metavar=("起点", "终点"), help="步行路线(距离/时长)")
    ap.add_argument("--itinerary", action="store_true", help="输出内置行程所有路段(驾车)")
    ap.add_argument("--list", action="store_true", help="列出内置行程点位")
    ap.add_argument("--city", metavar="城市", help="地理编码城市提示（如 成都/重庆），防止同名地名解析错")
    args = ap.parse_args()

    if args.list:
        for grp, pts in ITINERARY.items():
            print(f"[{grp}]")
            for p in pts:
                print("  " + p)
        return

    if args.geocode:
        lng, lat, addr = geocode(args.geocode)
        print(f"{args.geocode} → {lng},{lat}  ({addr})")
        return

    if args.route:
        a, b = args.route
        km, mins, o, d = driving(a, b, args.city)
        print(f"驾车 {a} → {b}")
        print(f"  距离 {km:.1f} km，预计 {mins:.0f} 分钟（理想路况）")
        print(f"  起({o[0]},{o[1]}) → 止({d[0]},{d[1]})")
        return

    if args.transit:
        a, b = args.transit
        city = args.city or ("重庆" if any(k in b + a for k in ["重庆", "李子坝", "洪崖洞", "索道"]) else "成都")
        r = transit(a, b, city)
        if r is None:
            print(f"公交 {a} → {b}：未找到方案")
        else:
            km, mins, trans = r
            print(f"公交/地铁 {a} → {b}：{km:.1f} km，约 {mins:.0f} 分钟，换乘 {trans} 次")
        return

    if args.walk:
        a, b = args.walk
        km, mins, o, d = walking(a, b, args.city)
        print(f"步行 {a} → {b}")
        print(f"  距离 {km:.1f} km，预计 {mins:.0f} 分钟")
        print(f"  起({o[0]},{o[1]}) → 止({d[0]},{d[1]})")
        return

    if args.itinerary:
        for grp, pts in ITINERARY.items():
            print(f"\n=== {grp} ===")
            for a, b in zip(pts, pts[1:]):
                try:
                    city = "重庆" if ("重庆" in a or "重庆" in b) else "成都"
                    km, mins, _, _ = driving(a, b, city)
                    print(f"  {a} → {b}：{km:.1f} km，约 {mins:.0f} 分钟")
                except Exception as e:
                    print(f"  {a} → {b}：失败（{e}）")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
