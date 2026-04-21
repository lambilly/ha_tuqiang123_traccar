"""Tuqiang123 to Traccar integration."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, CONF_DEVICES, CONF_TRACCAR_URL, CONF_DEVICE_PREFIX, CONF_UPDATE_INTERVAL
from .tuqiang123_fetcher import Tuqiang123Fetcher

_LOGGER = logging.getLogger(__name__)
PLATFORMS = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration."""
    config = entry.data
    username = config["username"]
    password = config["password"]
    devices = config["devices"]
    traccar_url = config[CONF_TRACCAR_URL].rstrip("/")
    prefix = config.get(CONF_DEVICE_PREFIX, "")
    interval = config.get(CONF_UPDATE_INTERVAL, 30)

    session = async_get_clientsession(hass)
    fetcher = Tuqiang123Fetcher(username, password)

    # Store for unload
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"remove_timer": None}

    async def forward_positions(*_):
        """Fetch and send positions to Traccar."""
        # Ensure login
        if not fetcher.userid:
            await hass.async_add_executor_job(fetcher.login)

        for imei in devices:
            try:
                pos = await hass.async_add_executor_job(fetcher.get_device_position, imei)
                if not pos:
                    continue

                device_id = f"{prefix}{imei}" if prefix else imei
                # Convert speed to knots for OsmAnd protocol
                speed_knots = pos["speed"] * 0.539957

                params = {
                    "id": device_id,
                    "lat": pos["latitude"],
                    "lon": pos["longitude"],
                    "timestamp": int(pos["timestamp"]),
                    "speed": speed_knots,
                    "bearing": pos["course"],
                }

                async with session.get(traccar_url + "/", params=params) as resp:
                    if resp.status == 200:
                        _LOGGER.debug("Device %s reported successfully", imei)
                    else:
                        _LOGGER.warning("Device %s report failed: HTTP %s", imei, resp.status)
            except Exception as e:
                _LOGGER.error("Error processing device %s: %s", imei, e)

    # Run immediately once
    await forward_positions()

    # Schedule periodic updates
    remove_timer = async_track_time_interval(hass, forward_positions, timedelta(seconds=interval))
    hass.data[DOMAIN][entry.entry_id]["remove_timer"] = remove_timer

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload the integration."""
    data = hass.data[DOMAIN].pop(entry.entry_id)
    if remove_timer := data.get("remove_timer"):
        remove_timer()
    return True