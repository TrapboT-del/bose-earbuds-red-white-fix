# -*- coding: utf-8 -*-
"""
Force-reflash official firmware on Bose Sport Earbuds (codename "revel", PID 0x402D)

How it works:
  To decide whether an update is needed, btu.bose.com sends the earbuds' current
  firmware version to the Bose cloud (svc-naota-update-service). This script reports
  an older version instead, so the cloud returns the download URL / CRC / size of the
  latest official firmware, then asks the local Bose Updater to flash it through its
  updateUsingEndpointUrl endpoint. Official firmware, official updater: the effect is
  a forced reflash of the current version.

Standard library only, no third-party packages required.
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

# ---- Defaults (taken from the btu.bose.com page script; refreshed from the page at startup) ----
BTU_URL = "https://btu.bose.com/"
UPDATER_BASE = "http://127.0.0.1:49312/updater"
DISCOVERY_URL = "https://services.api.bose.io"
X_API_KEY = "67616C617061676F732D5PKH1B5D0QZMGORWMXODFKJ13CWL4Q8YGJBZY19GCAL24F"

REVEL_PID = "16429"  # Bose Sport Earbuds
FAKE_VERSION = "1.0.0"  # older version reported to the cloud
ORIGIN_HEADERS = {"Origin": "https://btu.bose.com", "Referer": "https://btu.bose.com/"}


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def refresh_constants():
    """Read endpoint URLs and API key from the current btu.bose.com script; fall back to defaults."""
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
        print("Loaded current endpoint settings from btu.bose.com")
    except Exception as e:
        print(f"Could not read btu.bose.com, using built-in settings ({e})")


def updater(path, allow_error=False, **params):
    """Call the local Bose Updater and parse its BoseUpdater.remoteCallback(token, data, error) reply."""
    url = f"{UPDATER_BASE}/{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    text = http_get(url, ORIGIN_HEADERS).strip()
    m = re.match(r"^[\w.]+\((.*)\);?$", text, re.S)
    if not m:
        raise RuntimeError(f"Unrecognized Updater reply: {text[:200]}")
    _token, data, error = json.loads("[" + m.group(1) + "]")
    if allow_error:
        return data, error
    if error not in (0, "0", None, ""):
        raise RuntimeError(f"Updater returned error code: {error}")
    return data


def token():
    return "T" + format(int(time.time() * 1000), "x")[-12:]


def find_device(allow_any):
    # Right after the case is plugged in, or with the earbuds out of the case, the Updater
    # returns component errors such as -1043/-1044/-1047; wait and retry
    for i in range(24):
        devices, error = updater("getCurrentDevicesConnected", allow_error=True, pids="-1")
        if devices:
            break
        if i == 0:
            print(f"No earbuds detected yet (error {error}). Make sure the case is connected by USB, "
                  "both earbuds are in the case and the lid is open. Waiting...")
        time.sleep(5)
    else:
        sys.exit("No Bose earbuds detected within 2 minutes. Check the connection and try again.")
    if len(devices) > 1:
        sys.exit("More than one Bose device detected; connect only one.")
    info = updater("getCurrentDeviceInformation", deviceID=devices[0]["ID"])
    print("\n=== Connected device ===")
    for k in ("name", "serial", "version", "pid", "modelType", "useCloud", "isLatestVersion"):
        print(f"  {k:16}: {info.get(k)}")
    if info.get("pid") != REVEL_PID and not allow_any:
        sys.exit(f"\nThis device (PID={info.get('pid')}) is not Bose Sport Earbuds ({REVEL_PID})."
                 "\nTo use it on another cloud-updated model anyway, add --any-model (at your own risk).")
    if str(info.get("useCloud")) != "4":
        sys.exit("This device is not cloud-updated (useCloud != 4); this script does not apply.")
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
        sys.exit(f"The cloud did not offer any firmware: {fw}")
    meta = fw.get("metadata") or {}
    if not meta.get("CRC") or not meta.get("length"):
        sys.exit(f"Firmware returned by the cloud is missing CRC/size: {fw}")
    print("\n=== Official firmware offered by the Bose cloud ===")
    print(f"  Version : {fw['versionInfo']}")
    print(f"  URL     : {fw['baseUrl']}")
    print(f"  Size    : {meta['length']} bytes")
    print(f"  CRC     : {meta['CRC']}")
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
    print("\nFlashing started. It takes about 40-60 minutes. Do NOT unplug, close the lid "
          "or let the computer sleep!\n")
    last, started, misses = None, False, 0
    while True:
        time.sleep(5)
        try:
            p = updater("getUpdateProgress", deviceID=info["ID"])
            misses = 0
        except Exception as e:
            misses += 1
            print(f"  (progress temporarily unavailable: {e})")
            if misses >= 60:
                sys.exit("No progress for over 5 minutes; check %TEMP%\\BoseUpdater.log")
            continue
        state, pct = p.get("state"), p.get("percentage")
        if state == "updating":
            started = True
        if (state, pct) != last:
            print(f"  {time.strftime('%H:%M:%S')}  state={state}  progress={pct}%")
            last = (state, pct)
        if state == "finished":
            print("\nFlashing complete!")
            return True
        if started and state not in ("updating", "finished"):
            print(f"\nFlashing ended with state={state}; check %TEMP%\\BoseUpdater.log for the result.")
            return state == "idle"


def main():
    ap = argparse.ArgumentParser(description="Force-reflash official firmware on Bose Sport Earbuds")
    ap.add_argument("--dry-run", action="store_true", help="only detect the device and query firmware, do not flash")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt before flashing")
    ap.add_argument("--fake-version", default=FAKE_VERSION, help="older version reported to the cloud (default 1.0.0)")
    ap.add_argument("--any-model", action="store_true", help="allow cloud-updated models other than Sport Earbuds (at your own risk)")
    args = ap.parse_args()

    refresh_constants()
    try:
        updater("isUpdaterReady", callback="BoseUpdater.remoteCallback", token=token())
    except Exception as e:
        sys.exit(f"Cannot reach the local Bose Updater ({UPDATER_BASE}): {e}\n"
                 "Install and run Bose Updater first (opening btu.bose.com once will prompt you).")

    info = find_device(args.any_model)
    fw = query_firmware(info, args.fake_version)
    if args.dry_run:
        print("\n[--dry-run] Detection only, nothing was flashed.")
        return
    if not args.yes:
        ans = input("\nFlash now? Close any btu.bose.com browser tabs, then type YES to continue: ")
        if ans.strip() != "YES":
            print("Cancelled.")
            return
    flash(info, fw)
    try:
        info = updater("getCurrentDeviceInformation", deviceID=info["ID"])
        print(f"Current firmware version: {info.get('version')}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
