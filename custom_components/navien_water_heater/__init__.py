"""The Navien NaviLink Water Heater Integration."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
from .navien_api import (
    NavilinkConnect,
    NoResponseData
)
from .const import DOMAIN
import logging
import os
_LOGGER=logging.getLogger(__name__)

PLATFORMS: list[str] = ["water_heater","sensor","switch"]

SERVICE_GET_WEEKLY_SCHEDULE = "get_weekly_schedule"

async def _async_get_weekly_schedule(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Read the weekly schedule from every channel of every configured device."""
    result = {}
    for entry_id, navilink in hass.data.get(DOMAIN, {}).items():
        result[entry_id] = {
            str(number): await channel.get_weekly_schedule()
            for number, channel in navilink.channels.items()
        }
    return result

SERVICE_SET_WEEKLY_SCHEDULE = "set_weekly_schedule"
SET_WEEKLY_SCHEDULE_SCHEMA = vol.Schema({
    vol.Optional("channel"): vol.All(int, vol.Range(min=1)),
    vol.Optional("enabled"): bool,
    vol.Required("days"): [{
        vol.Required("day"): vol.All(int, vol.Range(min=1, max=7)),
        vol.Required("entries"): [{
            vol.Required("hour"): vol.All(int, vol.Range(min=0, max=23)),
            vol.Required("minute"): vol.All(int, vol.Range(min=0, max=59)),
            vol.Required("on"): bool,
        }],
    }],
})

async def _async_set_weekly_schedule(hass: HomeAssistant, call: ServiceCall) -> dict:
    """Replace the entries of the given days and return the schedule read back."""
    channels = [
        channel
        for navilink in hass.data.get(DOMAIN, {}).values()
        for number, channel in navilink.channels.items()
        if call.data.get("channel") in (None, number)
    ]
    if len(channels) != 1:
        raise HomeAssistantError(f"Expected exactly one matching channel, found {len(channels)}; set 'channel' to pick one")
    try:
        return await channels[0].set_weekly_schedule(call.data["days"], call.data.get("enabled"))
    except (ValueError, NoResponseData) as err:
        raise HomeAssistantError(str(err)) from err

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navien NaviLink Water Heater Integration from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    aws_path = hass.config.path() 
    subdirs = ['custom_components','navien_water_heater','cert']
    for subdir in subdirs:
        aws_path = os.path.join(aws_path,subdir)
    navilink = NavilinkConnect(userId=entry.data.get("username",""), passwd=entry.data.get("password",""), polling_interval=entry.data.get("polling_interval",15), device_index=entry.data.get("device_index",0), aws_cert_path=os.path.join(aws_path,"AmazonRootCA1.pem"))
    hass.data[DOMAIN][entry.entry_id] = navilink
    await navilink.start()    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.services.has_service(DOMAIN, SERVICE_GET_WEEKLY_SCHEDULE):
        async def get_weekly_schedule(call: ServiceCall) -> dict:
            return await _async_get_weekly_schedule(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_GET_WEEKLY_SCHEDULE, get_weekly_schedule, supports_response=SupportsResponse.ONLY)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_WEEKLY_SCHEDULE):
        async def set_weekly_schedule(call: ServiceCall) -> dict:
            return await _async_set_weekly_schedule(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_SET_WEEKLY_SCHEDULE, set_weekly_schedule, schema=SET_WEEKLY_SCHEDULE_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    navilink = hass.data[DOMAIN][entry.entry_id]
    await navilink.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_GET_WEEKLY_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_SET_WEEKLY_SCHEDULE)
    return unload_ok

