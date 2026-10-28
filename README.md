# Bose Sport Earbuds – Force Reflash Official Firmware

English | [中文](使用方法.md)

> English script: `bose_reflash.py`; Chinese script: `bose_reflash_zh.py`. Both do exactly the same thing.

For **Bose Sport Earbuds** (Bose codename `revel`, USB product ID 16429 / 0x402D).
Typical use: after a battery replacement the earbuds flash red and white, or the two buds fail to authenticate/sync, and btu.bose.com only says "Your product is up to date" and refuses to update.

## How it works

To decide whether an update is needed, btu.bose.com sends the earbuds' firmware version to the Bose cloud.
This script reports an older version instead (1.0.0 by default), so the cloud returns the download URL, CRC and size of the **latest official firmware** (currently 2.0.7).
It then asks the **Bose Updater** running on your computer to flash it. Both the firmware and the flashing program are Bose's own, so the result is a complete reflash of the current version.

> Note: it can only flash the version the Bose cloud currently offers. It **cannot downgrade** to older versions.

## Requirements

1. Python 3 (https://www.python.org; on Windows tick "Add Python to PATH" during install). No third-party packages needed.
2. Bose Updater: open https://btu.bose.com in a browser and install it when prompted. Make sure the Bose icon is in the system tray.
3. Put both earbuds in the charging case, **keep the lid open**, and connect the case to the computer with a USB cable.
4. Recommended: hold the case's Bluetooth button for about 30 seconds to factory-reset the earbuds before connecting.

## Usage

Open a command prompt in this folder, then:

**Step 1: read-only check (no flashing)**

```
python bose_reflash.py --dry-run
```

This shows the device name, serial number and current version, plus the firmware information returned by the cloud. If you see `Bose Sport Earbuds` and a firmware version, everything is ready.

**Step 2: flash**

First **close every btu.bose.com browser tab**, then run:

```
python bose_reflash.py
```

Check the information, type `YES` (uppercase) and press Enter. Progress is printed every 5 seconds.

## Flashing stages (about 40–60 minutes)

| Progress | Stage |
|---|---|
| 1% → 60% | Download firmware and write it to the first earbud (slowest, ~35 min) |
| 61% → 99% | Validate, install, and sync the other earbud |
| 99% | Earbuds reboot, final confirmation |
| 100% / finished | Done |

**While flashing, never:** unplug the USB cable, close the case, take out the earbuds, quit Bose Updater, or let the computer sleep/shut down (don't close a laptop lid).

## Afterwards

1. Unplug the USB cable, put the earbuds back, close the lid for 10 seconds and open it again.
2. Check that the red/white flashing has stopped, then re-pair with your phone and test both earbuds.

## Options

| Option | Effect |
|---|---|
| `--dry-run` | Detect only, do not flash |
| `--yes` | Skip the YES confirmation |
| `--fake-version 1.0.0` | Older version reported to the cloud (normally leave as is) |
| `--any-model` | Allow other cloud-updated Bose models (untested, at your own risk) |

## Troubleshooting

- **Cannot reach the local Bose Updater**: make sure Bose Updater is running (tray icon), or open btu.bose.com once to start it.
- **No earbuds detected (error -1043 etc.)**: both earbuds must be in the case with the lid open; try another USB cable/port.
- **Flashing error**: check the log `%TEMP%\BoseUpdater.log` (type `%TEMP%` in the Explorer address bar) and search for `Programming was successful` or `Error`.
- If Bose changes the web endpoints, the script reads the latest settings from btu.bose.com automatically; if it still fails, the page script needs to be re-analyzed.

## Reference firmware

Official 2.0.7 as offered by the Bose cloud on 2026-10-28:

- Version `2.0.7-18670+fb87694`, 6,144,812 bytes, CRC32 `0X3A15D305`
- SHA-256 `2b1abec709151d3aecaf2106dc16f0d1bb86223376ae971fab61c073210e4367`

If `--dry-run` reports a different CRC, Bose has released a new version. The firmware file itself is Bose's copyright and is **not included** in this repository.

## License

The scripts and documentation in this repository are released under the [MIT License](LICENSE).
The license does not cover Bose firmware, Bose Updater, or any Bose trademarks, which remain the property of Bose Corporation.

## Disclaimer

This method is not provided or endorsed by Bose. Flashing carries a risk of damaging your device; use at your own risk.
Tested successfully on 2026-10-28 on a pair of Sport Earbuds that flashed red/white after a battery replacement (back to normal after reflashing 2.0.7).
