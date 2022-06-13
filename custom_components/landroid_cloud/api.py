"""Representing the Landroid Cloud API interface."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.util import slugify as util_slugify

from pyworxcloud import WorxCloud, exceptions

from .const import (
    DOMAIN,
    LOGLEVEL,
    UPDATE_SIGNAL,
    LandroidFeatureSupport,
)

from .utils.logger import LandroidLogger, LoggerType, LogLevel

LOGGER = LandroidLogger(__name__, LOGLEVEL)


class LandroidAPI:
    """Handle the API calls."""

    def __init__(
        self, hass: HomeAssistant, index: int, device: WorxCloud, entry: ConfigEntry
    ):
        """Set up device."""
        self.hass = hass
        self.entry_id = entry.entry_id
        self.data = entry.data
        self.options = entry.options
        self.device: WorxCloud = device["device"]
        self.index = index
        self.unique_id = entry.unique_id
        self.services = {}
        self.shared_options = {}
        self.device_id = None
        self.features = 0
        self.features_loaded = False

        self._last_state = self.device.online

        self.name = util_slugify(f"{self.device.name}")
        self.friendly_name = self.device.name

        self.config = {
            "email": hass.data[DOMAIN][entry.entry_id][CONF_EMAIL].lower(),
            "password": hass.data[DOMAIN][entry.entry_id][CONF_PASSWORD],
            "type": hass.data[DOMAIN][entry.entry_id][CONF_TYPE].lower(),
        }

        LOGGER.set_api(self)
        self.device.set_callback(self.receive_data)

    def check_features(self, features: int, callback=None) -> None:
        """Check supported features."""

        if self.device.partymode_capable:
            LOGGER.write(LoggerType.FEATURE_ASSESSMENT, "Party mode capable")
            features = features | LandroidFeatureSupport.PARTYMODE

        if self.device.ots_capable:
            LOGGER.write(LoggerType.FEATURE_ASSESSMENT, "OTS capable")
            features = (
                features | LandroidFeatureSupport.EDGECUT | LandroidFeatureSupport.OTS
            )

        if self.device.torque_capable:
            LOGGER.write(LoggerType.FEATURE_ASSESSMENT, "Torque capable")
            features = features | LandroidFeatureSupport.TORQUE

        self.features = features
        self.features_loaded = True

        if callback:
            callback()

    def receive_data(self):
        """Used as callback from API when data is received."""
        if not self._last_state and self.device.online:
            self._last_state = True
            self.hass.config_entries.async_reload(self.entry_id)

        LOGGER.write(LoggerType.DATA_UPDATE, "Received new data from API")
        dispatcher_send(self.hass, f"{UPDATE_SIGNAL}_{self.device.name}")

    async def async_refresh(self):
        """Try fetching data from cloud."""
        try:
            await self.hass.async_add_executor_job(self.device.update)
            # dispatcher_send(self.hass, f"{UPDATE_SIGNAL}_{self.device.name}")
        except exceptions.RequestError:
            LOGGER.write(
                LoggerType.API,
                "Request for %s was malformed.",
                self.config["email"],
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.AuthorizationError:
            LOGGER.write(
                LoggerType.API,
                "Unauthorized - please check your credentials for %s at Landroid Cloud",
                self.config["email"],
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.ForbiddenError:
            LOGGER.write(
                LoggerType.API,
                "Server rejected access for %s at Landroid Cloud - this might be "
                "temporary due to high numbers of API requests from this IP address.",
                self.config["email"],
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.NotFoundError:
            LOGGER.write(
                LoggerType.API,
                "Endpoint for %s was not found.",
                self.config["email"],
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.TooManyRequestsError:
            LOGGER.write(
                LoggerType.API,
                "Too many requests for %s at Landroid Cloud. IP address temporary banned.",
                self.config["email"],
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.InternalServerError:
            LOGGER.write(
                LoggerType.API,
                "Internal server error happend for the request to %s at Landroid Cloud.",
                self.config["email"],
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.ServiceUnavailableError:
            LOGGER.write(
                LoggerType.API,
                "Service at Landroid Cloud was unavailable.",
                log_level=LogLevel.ERROR,
            )
            return False
        except exceptions.APIException as ex:
            LOGGER.write(
                LoggerType.API,
                "%s",
                ex,
                log_level=LogLevel.ERROR,
            )
            return False
