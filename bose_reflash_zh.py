# -*- coding: utf-8 -*-
"""
Bose Sport Earbuds（小鲨鱼一代，代号 revel，PID 0x402D）强制重刷官方固件脚本

原理：
  btu.bose.com 判断“是否需要更新”时，会把耳机当前版本号发给 Bose 云端
  (svc-naota-update-service) 询问。本脚本向云端申报一个旧版本号，云端就会返回
  官方最新固件的下载地址 / CRC / 大小，然后调用本机 Bose Updater 的
  updateUsingEndpointUrl 接口刷写。用的是 Bose 官方固件和官方 Updater，
  效果等同于“强制重新刷一遍当前版本”。

只用 Python 标准库，无需安装第三方包。
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

# ---- 默认常量（取自 btu.bose.com 页面脚本，启动时会尝试从页面重新读取） ----
BTU_URL = "https://btu.bose.com/"
UPDATER_BASE = "http://127.0.0.1:49312/updater"
DISCOVERY_URL = "https://services.api.bose.io"
X_API_KEY = "67616C617061676F732D5PKH1B5D0QZMGORWMXODFKJ13CWL4Q8YGJBZY19GCAL24F"

REVEL_PID = "16429"  # Bose Sport Earbuds
FAKE_VERSION = "1.0.0"  # 向云端申报的旧版本号
ORIGIN_HEADERS = {"Origin": "https://btu.bose.com", "Referer": "https://btu.bose.com/"}


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def refresh_constants():
    """从 btu.bose.com 当前页面脚本读取接口地址和 API Key，失败则用默认值。"""
    global UPDATER_BASE, DISCOVERY_URL, X_API_KEY
    try:
        html = http_get(BTU_URL)
        m = re.search(r'src="([^"]+\.js)"', html)
        js = http_get(urllib.parse.urljoin(BTU_URL, m.group(1)), timeout=60)
        for name in ("BOSE_UPDATER_BASE_URL", "SERVICE_DISCOVERY_URL", "X_API_KEY"):
            v = re.search(name + r'="([^"]+)"', js)
            if v:
                if name == "BOSE_UPDATER_BASE_URL":
                    UPDATER_BASE = v.group(1)
                elif name == "SERVICE_DISCOVERY_URL":
                    DISCOVERY_URL = v.group(1)
                else:
                    X_API_KEY = v.group(1)
        print("已从 btu.bose.com 读取最新接口参数")
    except Exception as e:
        print(f"读取 btu.bose.com 失败，使用内置参数（{e}）")


def updater(path, allow_error=False, **params):
    """调用本机 Bose Updater，解析 BoseUpdater.remoteCallback(token, data, error) 格式。"""
    url = f"{UPDATER_BASE}/{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    text = http_get(url, ORIGIN_HEADERS).strip()
    m = re.match(r"^[\w.]+\((.*)\);?$", text, re.S)
    if not m:
        raise RuntimeError(f"Updater 返回无法解析：{text[:200]}")
    _token, data, error = json.loads("[" + m.group(1) + "]")
    if allow_error:
        return data, error
    if error not in (0, "0", None, ""):
        raise RuntimeError(f"Updater 返回错误码：{error}")
    return data


def token():
    return "T" + format(int(time.time() * 1000), "x")[-12:]


def find_device(allow_any):
    # 充电盒刚连上或耳机不在盒里时，Updater 会返回 -1043/-1044/-1047 等组件错误，等待重试
    for i in range(24):
        devices, error = updater("getCurrentDevicesConnected", allow_error=True, pids="-1")
        if devices:
            break
        if i == 0:
            print(f"暂未检测到耳机（错误码 {error}），请确认：充电盒用 USB 连着电脑、"
                  "两只耳机都在盒里、盒盖打开。等待中…")
        time.sleep(5)
    else:
        sys.exit("2 分钟内没有检测到 Bose 耳机，请检查连接后重试。")
    if len(devices) > 1:
        sys.exit("检测到多个 Bose 设备，请只连接一个。")
    info = updater("getCurrentDeviceInformation", deviceID=devices[0]["ID"])
    print("\n=== 已连接设备 ===")
    for k in ("name", "serial", "version", "pid", "modelType", "useCloud", "isLatestVersion"):
        print(f"  {k:16}: {info.get(k)}")
    if info.get("pid") != REVEL_PID and not allow_any:
        sys.exit(f"\n该设备 PID={info.get('pid')} 不是 Bose Sport Earbuds（{REVEL_PID}）。"
                 "\n如确定要用于其他云端更新型号，加参数 --any-model（风险自负）。")
    if str(info.get("useCloud")) != "4":
        sys.exit("该设备不是云端更新型号（useCloud≠4），本脚本不适用。")
    return info


def query_firmware(info, fake_version):
    guid = updater("getGuid", deviceID=info["ID"])["guid"]
    guid = re.sub(r"(.{8})(.{4})(.{4})(.{4})(.{12})", r"\1-\2-\3-\4-\5", guid)
    disc = json.loads(http_get(f"{DISCOVERY_URL}/discovery/discover/product/{guid}"))
    base = disc["services"]["svc-naota-update-service"]["url"]
    q = urllib.parse.urlencode({
        "productID": guid,
        "productType": info["modelType"].lower(),
        "firmwareVersion": fake_version,
        "fields": "updateAvailable,baseUrl,versionInfo,deferrable,rollback,metadata",
    })
    fw = json.loads(http_get(f"{base}/update?{q}", {"x-api-key": X_API_KEY}))
    if str(fw.get("updateAvailable")).lower() != "true":
        sys.exit(f"云端没有返回固件：{fw}")
    meta = fw.get("metadata") or {}
    if not meta.get("CRC") or not meta.get("length"):
        sys.exit(f"云端返回的固件缺少 CRC/大小信息：{fw}")
    print("\n=== Bose 云端返回的官方固件 ===")
    print(f"  版本 : {fw['versionInfo']}")
    print(f"  地址 : {fw['baseUrl']}")
    print(f"  大小 : {meta['length']} 字节")
    print(f"  CRC  : {meta['CRC']}")
    return fw


def flash(info, fw):
    meta = fw["metadata"]
    updater("updateUsingEndpointUrl",
            deviceID=info["ID"],
            url=fw["baseUrl"],
            version=urllib.parse.quote(fw["versionInfo"], safe=""),
            fileCrc=meta["CRC"],
            fileSize=meta["length"],
            callback="BoseUpdater.remoteCallback",
            token=token())
    print("\n已开始刷写。全程约 40~60 分钟，期间不要拔线、不要合盖、不要让电脑休眠！\n")
    last, started, misses = None, False, 0
    while True:
        time.sleep(5)
        try:
            p = updater("getUpdateProgress", deviceID=info["ID"])
            misses = 0
        except Exception as e:
            misses += 1
            print(f"  （暂时读不到进度：{e}）")
            if misses >= 60:
                sys.exit("超过 5 分钟读不到进度，请查看 %TEMP%\\BoseUpdater.log")
            continue
        state, pct = p.get("state"), p.get("percentage")
        if state == "updating":
            started = True
        if (state, pct) != last:
            print(f"  {time.strftime('%H:%M:%S')}  状态={state}  进度={pct}%")
            last = (state, pct)
        if state == "finished":
            print("\n刷写完成！")
            return True
        if started and state not in ("updating", "finished"):
            print(f"\n刷写结束，最终状态={state}，请查看 %TEMP%\\BoseUpdater.log 确认结果。")
            return state == "idle"


def main():
    ap = argparse.ArgumentParser(description="Bose Sport Earbuds 强制重刷官方固件")
    ap.add_argument("--dry-run", action="store_true", help="只检测设备和查询固件，不刷写")
    ap.add_argument("--yes", action="store_true", help="跳过刷写前的确认提示")
    ap.add_argument("--fake-version", default=FAKE_VERSION, help="向云端申报的旧版本号（默认 1.0.0）")
    ap.add_argument("--any-model", action="store_true", help="允许非 Sport Earbuds 的云端更新型号（风险自负）")
    args = ap.parse_args()

    refresh_constants()
    try:
        updater("isUpdaterReady", callback="BoseUpdater.remoteCallback", token=token())
    except Exception as e:
        sys.exit(f"连不上本机 Bose Updater（{UPDATER_BASE}）：{e}\n"
                 "请先安装并运行 Bose Updater（打开一次 btu.bose.com 即会提示安装）。")

    info = find_device(args.any_model)
    fw = query_firmware(info, args.fake_version)
    if args.dry_run:
        print("\n[--dry-run] 只做检测，未刷写。")
        return
    if not args.yes:
        ans = input("\n确认刷写？请关闭浏览器里的 btu.bose.com 页面后输入 YES 继续：")
        if ans.strip() != "YES":
            print("已取消。")
            return
    flash(info, fw)
    try:
        info = updater("getCurrentDeviceInformation", deviceID=info["ID"])
        print(f"当前固件版本：{info.get('version')}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
