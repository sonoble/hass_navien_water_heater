"""Test writing the weekly schedule of a Navien NaviLink device.

Always reads the current schedule first and saves it to a backup file.

    python scripts/write_schedule.py            # no-op: write back the identical schedule
    python scripts/write_schedule.py --disable  # turn the schedule off (entries kept)
    python scripts/write_schedule.py --enable   # turn the schedule on

Credentials come from NAVIEN_USER / NAVIEN_PASS. Add -v for raw MQTT logging.
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
spec = importlib.util.spec_from_file_location("navien_api", COMPONENT / "navien_api.py")
navien_api = importlib.util.module_from_spec(spec)
sys.modules["navien_api"] = navien_api
spec.loader.exec_module(navien_api)


async def main():
    user, password = os.environ.get("NAVIEN_USER"), os.environ.get("NAVIEN_PASS")
    if not user or not password:
        sys.exit("Set NAVIEN_USER and NAVIEN_PASS environment variables.")
    logging.basicConfig(level=logging.DEBUG if "-v" in sys.argv else logging.INFO)
    # Keep the AWS SDK quiet unless asked; it logs signed URLs at DEBUG.
    if "-v" not in sys.argv:
        logging.getLogger("AWSIoTPythonSDK").setLevel(logging.WARNING)

    navilink = navien_api.NavilinkConnect(
        userId=user, passwd=password, aws_cert_path=str(COMPONENT / "cert" / "AmazonRootCA1.pem"))
    try:
        channels = await navilink.start()
        if not channels:
            sys.exit("Could not get channel information from the heater (connection failed). Nothing was written. "
                     "If another script or the app is connected, stop it and try again.")
        if len(channels) != 1:
            sys.exit(f"Expected one channel, found {list(channels)}")
        channel = next(iter(channels.values()))

        before = await channel.get_weekly_schedule()
        if not before:
            sys.exit("Could not read the current schedule; not writing anything.")
        backup = Path(f"schedule-backup-{int(time.time())}.json")
        backup.write_text(json.dumps({"parsed": before, "raw": channel.weekly_days_raw}, indent=2))
        print(f"Backed up current schedule to {backup}")

        if "--disable" in sys.argv:
            enabled = False
        elif "--enable" in sys.argv:
            enabled = True
        else:
            enabled = before["enabled"]
        print(f"Writing {'identical schedule' if enabled == before['enabled'] else 'new on/off state'} (enabled={enabled})")
        await navilink._write_weekly_schedule(channel.channel_number, enabled, channel.weekly_days_raw)

        after = channel.weekly_schedule
        print(f"weeklyControl in channel status: {channel.channel_status.get('weeklyControl')}")
        print("Entries unchanged:", after.get("days") == before["days"])
        print("Schedule enabled now:", after.get("enabled"))
    finally:
        await navilink.disconnect()


asyncio.run(main())
