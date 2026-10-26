"""Read the weekly schedule from a Navien NaviLink device. Read-only.

Usage:
    NAVIEN_USER=you@example.com NAVIEN_PASS=... python scripts/read_schedule.py [-v] [--status]

With --status, only the channel status is read; the schedule is not fetched or printed.
"""
import asyncio
import importlib.util
import json
import logging
import os
import sys
import time
from pathlib import Path

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "navien_water_heater"

# Load navien_api.py directly so we don't import the package __init__ (which needs Home Assistant).
spec = importlib.util.spec_from_file_location("navien_api", COMPONENT / "navien_api.py")
navien_api = importlib.util.module_from_spec(spec)
sys.modules["navien_api"] = navien_api
spec.loader.exec_module(navien_api)


async def main():
    user, password = os.environ.get("NAVIEN_USER"), os.environ.get("NAVIEN_PASS")
    if not user or not password:
        sys.exit("Set NAVIEN_USER and NAVIEN_PASS environment variables.")

    logging.basicConfig(level=logging.DEBUG if "-v" in sys.argv else logging.INFO)
    if "-v" not in sys.argv:
        # The AWS SDK logs signed URLs at DEBUG; keep it quiet unless asked.
        logging.getLogger("AWSIoTPythonSDK").setLevel(logging.WARNING)
    navilink = navien_api.NavilinkConnect(
        userId=user,
        passwd=password,
        aws_cert_path=str(COMPONENT / "cert" / "AmazonRootCA1.pem"),
    )
    try:
        channels = await navilink.start()
        if not channels:
            sys.exit("Could not get channel information from the heater (connection failed). "
                     "If another script or the app is connected, stop it and try again.")
        print(f"Connected. Channels: {list(channels)}")
        print(f"modelTypeCode={navilink.messages.model_type_code}")
        for number, channel in channels.items():
            info = channel.channel_info
            print(f"\nChannel {number}: weeklyScheduleType={info.get('weeklyScheduleType')} onDemandUse={info.get('onDemandUse')} (1 = hot button available)")
            print(f"  onDemandUseFlag (hot button active now)={channel.channel_status.get('onDemandUseFlag')}")
            if "--status" in sys.argv:
                # Full channel status as last polled, so runs with the schedule on/off can be diffed.
                status_file = Path(f"status-{int(time.time())}-ch{number}.json")
                status_file.write_text(json.dumps(channel.channel_status, indent=2, sort_keys=True))
                print(f"  Channel status saved to {status_file.resolve()}")
                interesting = ("powerStatus","weeklyControl","onDemandUseFlag","DHWSettingTemp","avgInletTemp","avgOutletTemp","recirculationUse","avgCalorie")
                print("  " + ", ".join(f"{k}={channel.channel_status.get(k)}" for k in interesting))
                unit = (channel.channel_status.get("unitInfo", {}).get("unitStatusList") or [{}])[0]
                print("  " + ", ".join(f"{k}={unit.get(k)}" for k in ("DHWFlowRate","gasInstantUsage","accumulatedGasUsage","currentInletTemp","currentOutletTemp")))
                continue  # status only: skip the schedule read, printout and backup
            schedule = await channel.get_weekly_schedule()
            if not schedule:
                print("  No schedule received (timed out or empty response).")
            print(json.dumps(schedule, indent=2))
            if schedule:
                # raw is the exact form the heater uses, so it can be written back unchanged later.
                backup = Path(f"schedule-backup-{int(time.time())}-ch{number}.json")
                backup.write_text(json.dumps({"parsed": schedule, "raw": channel.weekly_days_raw}, indent=2))
                print(f"Saved to {backup.resolve()}")
    finally:
        await navilink.disconnect()


asyncio.run(main())
