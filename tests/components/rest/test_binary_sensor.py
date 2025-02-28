"""The tests for the REST binary sensor platform."""

import asyncio
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from homeassistant import config as hass_config
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    CONTENT_TYPE_JSON,
    SERVICE_RELOAD,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import get_fixture_path


async def test_setup_missing_basic_config(hass: HomeAssistant) -> None:
    """Test setup with configuration missing required entries."""
    assert await async_setup_component(
        hass, Platform.BINARY_SENSOR, {"binary_sensor": {"platform": "rest"}}
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 0


async def test_setup_missing_config(hass: HomeAssistant) -> None:
    """Test setup with configuration missing required entries."""
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "localhost",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 0


@respx.mock
async def test_setup_failed_connect(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test setup when connection error occurs."""

    respx.get("http://localhost").mock(
        side_effect=httpx.RequestError("server offline", request=MagicMock())
    )
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 0
    assert "server offline" in caplog.text


@respx.mock
async def test_setup_timeout(hass: HomeAssistant) -> None:
    """Test setup when connection timeout occurs."""
    respx.get("http://localhost").mock(side_effect=asyncio.TimeoutError())
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "localhost",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 0


@respx.mock
async def test_setup_minimum(hass: HomeAssistant) -> None:
    """Test setup with minimum configuration."""
    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1


@respx.mock
async def test_setup_minimum_resource_template(hass: HomeAssistant) -> None:
    """Test setup with minimum configuration (resource_template)."""
    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource_template": "{% set url = 'http://localhost' %}{{ url }}",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1


@respx.mock
async def test_setup_duplicate_resource_template(hass: HomeAssistant) -> None:
    """Test setup with duplicate resources."""
    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "resource_template": "http://localhost",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 0


@respx.mock
async def test_setup_get(hass: HomeAssistant) -> None:
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
                "authentication": "basic",
                "username": "my username",
                "password": "my password",
                "headers": {"Accept": CONTENT_TYPE_JSON},
                "device_class": BinarySensorDeviceClass.PLUG,
            }
        },
    )

    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1

    state = hass.states.get("binary_sensor.foo")
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PLUG


@respx.mock
async def test_setup_get_template_headers_params(hass: HomeAssistant) -> None:
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(status_code=200, json={})
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {
                    "Accept": CONTENT_TYPE_JSON,
                    "User-Agent": "Mozilla/{{ 3 + 2 }}.0",
                },
                "params": {
                    "start": 0,
                    "end": "{{ 3 + 2 }}",
                },
            }
        },
    )
    await async_setup_component(hass, "homeassistant", {})
    await hass.async_block_till_done()

    assert respx.calls.last.request.headers["Accept"] == CONTENT_TYPE_JSON
    assert respx.calls.last.request.headers["User-Agent"] == "Mozilla/5.0"
    assert respx.calls.last.request.url.query == b"start=0&end=5"


@respx.mock
async def test_setup_get_digest_auth(hass: HomeAssistant) -> None:
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
                "authentication": "digest",
                "username": "my username",
                "password": "my password",
                "headers": {"Accept": CONTENT_TYPE_JSON},
            }
        },
    )

    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1


@respx.mock
async def test_setup_post(hass: HomeAssistant) -> None:
    """Test setup with valid configuration."""
    respx.post("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "POST",
                "value_template": "{{ value_json.key }}",
                "payload": '{ "device": "toaster"}',
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
                "authentication": "basic",
                "username": "my username",
                "password": "my password",
                "headers": {"Accept": CONTENT_TYPE_JSON},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1


@respx.mock
async def test_setup_get_off(hass: HomeAssistant) -> None:
    """Test setup with valid off configuration."""
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/json"},
        json={"dog": False},
    )
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.dog }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1

    state = hass.states.get("binary_sensor.foo")
    assert state.state == STATE_OFF


@respx.mock
async def test_setup_get_on(hass: HomeAssistant) -> None:
    """Test setup with valid on configuration."""
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/json"},
        json={"dog": True},
    )
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.dog }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1

    state = hass.states.get("binary_sensor.foo")
    assert state.state == STATE_ON


@respx.mock
async def test_setup_with_exception(hass: HomeAssistant) -> None:
    """Test setup with exception."""
    respx.get("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.dog }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1

    state = hass.states.get("binary_sensor.foo")
    assert state.state == STATE_OFF

    await async_setup_component(hass, "homeassistant", {})
    await hass.async_block_till_done()

    respx.clear()
    respx.get("http://localhost").mock(side_effect=httpx.RequestError)
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: ["binary_sensor.foo"]},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.foo")
    assert state.state == STATE_UNAVAILABLE


@respx.mock
async def test_reload(hass: HomeAssistant) -> None:
    """Verify we can reload reset sensors."""

    respx.get("http://localhost") % HTTPStatus.OK

    await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "rest",
                "method": "GET",
                "name": "mockrest",
                "resource": "http://localhost",
            }
        },
    )
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    assert len(hass.states.async_all("binary_sensor")) == 1

    assert hass.states.get("binary_sensor.mockrest")

    yaml_path = get_fixture_path("configuration.yaml", "rest")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(
            "rest",
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.mockreset") is None
    assert hass.states.get("binary_sensor.rollout")


@respx.mock
async def test_setup_query_params(hass: HomeAssistant) -> None:
    """Test setup with query params."""
    respx.get("http://localhost", params={"search": "something"}) % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        Platform.BINARY_SENSOR,
        {
            "binary_sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "params": {"search": "something"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("binary_sensor")) == 1


@respx.mock
async def test_entity_config(hass: HomeAssistant) -> None:
    """Test entity configuration."""

    config = {
        Platform.BINARY_SENSOR: {
            # REST configuration
            "platform": "rest",
            "method": "GET",
            "resource": "http://localhost",
            # Entity configuration
            "icon": "{{'mdi:one_two_three'}}",
            "picture": "{{'blabla.png'}}",
            "name": "{{'REST' + ' ' + 'Binary Sensor'}}",
            "unique_id": "very_unique",
        },
    }

    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(hass, Platform.BINARY_SENSOR, config)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert (
        entity_registry.async_get("binary_sensor.rest_binary_sensor").unique_id
        == "very_unique"
    )

    state = hass.states.get("binary_sensor.rest_binary_sensor")
    assert state.state == "off"
    assert state.attributes == {
        "entity_picture": "blabla.png",
        "friendly_name": "REST Binary Sensor",
        "icon": "mdi:one_two_three",
    }
