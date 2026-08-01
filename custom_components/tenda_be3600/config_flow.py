"""Config flow for Tenda BE3600."""

from __future__ import annotations

import socket
from typing import Any

import aiohttp
from aiohttp.resolver import ThreadedResolver
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD

from .api import (
    TendaApi,
    TendaAuthError,
    TendaConnectionError,
    TendaLockedError,
    TendaProtocolError,
    hash_password,
)
from .const import CONF_PASSWORD_DIGEST, DEFAULT_HOST, DOMAIN
from .coordinator import controller_sn


def _host(value: str) -> str:
    host = value.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
    return host


class TendaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Tenda BE3600 config flow."""

    VERSION = 1

    async def _validate(self, host: str, password: str) -> tuple[str, str]:
        digest = hash_password(password)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                family=socket.AF_INET, resolver=ThreadedResolver()
            )
        ) as session:
            api = TendaApi(session, host, digest)
            await api.async_login()
            snapshot = await api.async_get_snapshot()
        if not (unique_id := controller_sn(snapshot)):
            raise TendaProtocolError("No mesh controller in response")
        return digest, unique_id

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _host(user_input[CONF_HOST])
            try:
                digest, unique_id = await self._validate(
                    host, user_input[CONF_PASSWORD]
                )
            except TendaLockedError:
                errors["base"] = "locked"
            except TendaAuthError:
                errors["base"] = "invalid_auth"
            except TendaConnectionError:
                errors["base"] = "cannot_connect"
            except TendaProtocolError:
                errors["base"] = "unsupported_device"
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PASSWORD_DIGEST: digest}
                )
                return self.async_create_entry(
                    title="Tenda BE3600 Mesh",
                    data={CONF_HOST: host, CONF_PASSWORD_DIGEST: digest},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate a replacement administrator password."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                digest, unique_id = await self._validate(
                    entry.data[CONF_HOST], user_input[CONF_PASSWORD]
                )
            except TendaLockedError:
                errors["base"] = "locked"
            except TendaAuthError:
                errors["base"] = "invalid_auth"
            except TendaConnectionError:
                errors["base"] = "cannot_connect"
            except TendaProtocolError:
                errors["base"] = "unsupported_device"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                if unique_id != entry.unique_id:
                    errors["base"] = "wrong_router"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={CONF_PASSWORD_DIGEST: digest},
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
