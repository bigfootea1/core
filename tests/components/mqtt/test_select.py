"""The tests for mqtt select component."""
import copy
import json
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.components import mqtt, select
from homeassistant.components.mqtt.select import MQTT_SELECT_ATTRIBUTES_BLOCKED
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.setup import async_setup_component

from .test_common import (
    help_test_availability_when_connection_lost,
    help_test_availability_without_topic,
    help_test_custom_availability_payload,
    help_test_default_availability_payload,
    help_test_discovery_broken,
    help_test_discovery_removal,
    help_test_discovery_setup,
    help_test_discovery_update,
    help_test_discovery_update_attr,
    help_test_discovery_update_unchanged,
    help_test_encoding_subscribable_topics,
    help_test_entity_debug_info_message,
    help_test_entity_device_info_remove,
    help_test_entity_device_info_update,
    help_test_entity_device_info_with_connection,
    help_test_entity_device_info_with_identifier,
    help_test_entity_id_update_discovery_update,
    help_test_entity_id_update_subscriptions,
    help_test_publishing_with_custom_encoding,
    help_test_reloadable,
    help_test_setting_attribute_via_mqtt_json_message,
    help_test_setting_attribute_with_template,
    help_test_setting_blocked_attribute_via_mqtt_json_message,
    help_test_unique_id,
    help_test_unload_config_entry_with_platform,
    help_test_update_with_json_attrs_bad_json,
    help_test_update_with_json_attrs_not_dict,
)

from tests.common import async_fire_mqtt_message, mock_restore_cache
from tests.typing import MqttMockHAClientGenerator, MqttMockPahoClient

DEFAULT_CONFIG = {
    mqtt.DOMAIN: {
        select.DOMAIN: {
            "name": "test",
            "command_topic": "test-topic",
            "options": ["milk", "beer"],
        }
    }
}


@pytest.fixture(autouse=True)
def select_platform_only():
    """Only setup the select platform to speed up tests."""
    with patch("homeassistant.components.mqtt.PLATFORMS", [Platform.SELECT]):
        yield


async def test_run_select_setup(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test that it fetches the given payload."""
    topic = "test/select"
    await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "state_topic": topic,
                    "command_topic": topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    async_fire_mqtt_message(hass, topic, "milk")

    await hass.async_block_till_done()

    state = hass.states.get("select.test_select")
    assert state.state == "milk"

    async_fire_mqtt_message(hass, topic, "beer")

    await hass.async_block_till_done()

    state = hass.states.get("select.test_select")
    assert state.state == "beer"


async def test_value_template(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test that it fetches the given payload with a template."""
    topic = "test/select"
    await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "state_topic": topic,
                    "command_topic": topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                    "value_template": "{{ value_json.val }}",
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    async_fire_mqtt_message(hass, topic, '{"val":"milk"}')

    await hass.async_block_till_done()

    state = hass.states.get("select.test_select")
    assert state.state == "milk"

    async_fire_mqtt_message(hass, topic, '{"val":"beer"}')

    await hass.async_block_till_done()

    state = hass.states.get("select.test_select")
    assert state.state == "beer"

    async_fire_mqtt_message(hass, topic, '{"val": null}')

    await hass.async_block_till_done()

    state = hass.states.get("select.test_select")
    assert state.state == STATE_UNKNOWN


async def test_run_select_service_optimistic(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test that set_value service works in optimistic mode."""
    topic = "test/select"

    fake_state = State("select.test_select", "milk")
    mock_restore_cache(hass, (fake_state,))

    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "command_topic": topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                }
            }
        },
    )
    await hass.async_block_till_done()
    mqtt_mock = await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("select.test_select")
    assert state.state == "milk"
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.test_select", ATTR_OPTION: "beer"},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(topic, "beer", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("select.test_select")
    assert state.state == "beer"


async def test_run_select_service_optimistic_with_command_template(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test that set_value service works in optimistic mode and with a command_template."""
    topic = "test/select"

    fake_state = State("select.test_select", "milk")
    mock_restore_cache(hass, (fake_state,))

    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "command_topic": topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                    "command_template": '{"option": "{{ value }}"}',
                }
            }
        },
    )
    await hass.async_block_till_done()
    mqtt_mock = await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("select.test_select")
    assert state.state == "milk"
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.test_select", ATTR_OPTION: "beer"},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(
        topic, '{"option": "beer"}', 0, False
    )
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("select.test_select")
    assert state.state == "beer"


async def test_run_select_service(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test that set_value service works in non optimistic mode."""
    cmd_topic = "test/select/set"
    state_topic = "test/select"

    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "command_topic": cmd_topic,
                    "state_topic": state_topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                }
            }
        },
    )
    await hass.async_block_till_done()
    mqtt_mock = await mqtt_mock_entry_with_yaml_config()

    async_fire_mqtt_message(hass, state_topic, "beer")
    state = hass.states.get("select.test_select")
    assert state.state == "beer"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.test_select", ATTR_OPTION: "milk"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(cmd_topic, "milk", 0, False)
    state = hass.states.get("select.test_select")
    assert state.state == "beer"


async def test_run_select_service_with_command_template(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test that set_value service works in non optimistic mode and with a command_template."""
    cmd_topic = "test/select/set"
    state_topic = "test/select"

    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "command_topic": cmd_topic,
                    "state_topic": state_topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                    "command_template": '{"option": "{{ value }}"}',
                }
            }
        },
    )
    await hass.async_block_till_done()
    mqtt_mock = await mqtt_mock_entry_with_yaml_config()

    async_fire_mqtt_message(hass, state_topic, "beer")
    state = hass.states.get("select.test_select")
    assert state.state == "beer"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.test_select", ATTR_OPTION: "milk"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        cmd_topic, '{"option": "milk"}', 0, False
    )


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG])
async def test_availability_when_connection_lost(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability after MQTT disconnection."""
    await help_test_availability_when_connection_lost(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN
    )


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG])
async def test_availability_without_topic(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability without defined availability topic."""
    await help_test_availability_without_topic(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_default_availability_payload(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability by default payload with defined topic."""
    await help_test_default_availability_payload(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_custom_availability_payload(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability by custom payload with defined topic."""
    await help_test_custom_availability_payload(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_attribute_via_mqtt_json_message(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_via_mqtt_json_message(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_blocked_attribute_via_mqtt_json_message(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_blocked_attribute_via_mqtt_json_message(
        hass,
        mqtt_mock_entry_no_yaml_config,
        select.DOMAIN,
        DEFAULT_CONFIG,
        MQTT_SELECT_ATTRIBUTES_BLOCKED,
    )


async def test_setting_attribute_with_template(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_with_template(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_not_dict(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_not_dict(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        select.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_update_with_json_attrs_bad_json(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_bad_json(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        select.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_discovery_update_attr(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered MQTTAttributes."""
    await help_test_discovery_update_attr(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        select.DOMAIN,
        DEFAULT_CONFIG,
    )


@pytest.mark.parametrize(
    "hass_config",
    [
        {
            mqtt.DOMAIN: {
                select.DOMAIN: [
                    {
                        "name": "Test 1",
                        "state_topic": "test-topic",
                        "command_topic": "test-topic",
                        "unique_id": "TOTALLY_UNIQUE",
                        "options": ["milk", "beer"],
                    },
                    {
                        "name": "Test 2",
                        "state_topic": "test-topic",
                        "command_topic": "test-topic",
                        "unique_id": "TOTALLY_UNIQUE",
                        "options": ["milk", "beer"],
                    },
                ]
            }
        }
    ],
)
async def test_unique_id(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test unique id option only creates one select per unique_id."""
    await help_test_unique_id(hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN)


async def test_discovery_removal_select(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test removal of discovered select."""
    data = json.dumps(DEFAULT_CONFIG[mqtt.DOMAIN][select.DOMAIN])
    await help_test_discovery_removal(
        hass, mqtt_mock_entry_no_yaml_config, caplog, select.DOMAIN, data
    )


async def test_discovery_update_select(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered select."""
    config1 = {
        "name": "Beer",
        "state_topic": "test-topic",
        "command_topic": "test-topic",
        "options": ["milk", "beer"],
    }
    config2 = {
        "name": "Milk",
        "state_topic": "test-topic",
        "command_topic": "test-topic",
        "options": ["milk"],
    }

    await help_test_discovery_update(
        hass, mqtt_mock_entry_no_yaml_config, caplog, select.DOMAIN, config1, config2
    )


async def test_discovery_update_unchanged_select(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered select."""
    data1 = '{ "name": "Beer", "state_topic": "test-topic", "command_topic": "test-topic", "options": ["milk", "beer"]}'
    with patch(
        "homeassistant.components.mqtt.select.MqttSelect.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass,
            mqtt_mock_entry_no_yaml_config,
            caplog,
            select.DOMAIN,
            data1,
            discovery_update,
        )


@pytest.mark.no_fail_on_log_exception
async def test_discovery_broken(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of bad discovery message."""
    data1 = '{ "name": "Beer" }'
    data2 = '{ "name": "Milk", "state_topic": "test-topic", "command_topic": "test-topic", "options": ["milk", "beer"]}'

    await help_test_discovery_broken(
        hass, mqtt_mock_entry_no_yaml_config, caplog, select.DOMAIN, data1, data2
    )


async def test_entity_device_info_with_connection(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT select device registry integration."""
    await help_test_entity_device_info_with_connection(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_with_identifier(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT select device registry integration."""
    await help_test_entity_device_info_with_identifier(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_update(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test device registry update."""
    await help_test_entity_device_info_update(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_remove(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test device registry remove."""
    await help_test_entity_device_info_remove(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_subscriptions(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT subscriptions are managed when entity_id is updated."""
    await help_test_entity_id_update_subscriptions(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_discovery_update(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT discovery update when entity_id is updated."""
    await help_test_entity_id_update_discovery_update(
        hass, mqtt_mock_entry_no_yaml_config, select.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_debug_info_message(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT debug info."""
    await help_test_entity_debug_info_message(
        hass,
        mqtt_mock_entry_no_yaml_config,
        select.DOMAIN,
        DEFAULT_CONFIG,
        select.SERVICE_SELECT_OPTION,
        service_parameters={ATTR_OPTION: "beer"},
        command_payload="beer",
        state_payload="milk",
    )


@pytest.mark.parametrize("options", [["milk", "beer"], ["milk"], []])
async def test_options_attributes(
    hass: HomeAssistant,
    mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator,
    options,
) -> None:
    """Test options attribute."""
    topic = "test/select"
    await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "state_topic": topic,
                    "command_topic": topic,
                    "name": "Test select",
                    "options": options,
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("select.test_select")
    assert state.attributes.get(ATTR_OPTIONS) == options


async def test_mqtt_payload_not_an_option_warning(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mqtt_mock_entry_with_yaml_config: MqttMockHAClientGenerator,
) -> None:
    """Test warning for MQTT payload which is not a valid option."""
    topic = "test/select"
    await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                select.DOMAIN: {
                    "state_topic": topic,
                    "command_topic": topic,
                    "name": "Test Select",
                    "options": ["milk", "beer"],
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    async_fire_mqtt_message(hass, topic, "öl")

    await hass.async_block_till_done()

    assert (
        "Invalid option for select.test_select: 'öl' (valid options: ['milk', 'beer'])"
        in caplog.text
    )


@pytest.mark.parametrize(
    ("service", "topic", "parameters", "payload", "template"),
    [
        (
            select.SERVICE_SELECT_OPTION,
            "command_topic",
            {"option": "beer"},
            "beer",
            "command_template",
        ),
    ],
)
async def test_publishing_with_custom_encoding(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
    service: str,
    topic: str,
    parameters: dict[str, Any],
    payload: str,
    template: str | None,
) -> None:
    """Test publishing MQTT payload with different encoding."""
    domain = select.DOMAIN
    config = DEFAULT_CONFIG
    config[mqtt.DOMAIN][domain]["options"] = ["milk", "beer"]

    await help_test_publishing_with_custom_encoding(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        domain,
        config,
        service,
        topic,
        parameters,
        payload,
        template,
    )


async def test_reloadable(
    hass: HomeAssistant,
    mqtt_client_mock: MqttMockPahoClient,
) -> None:
    """Test reloading the MQTT platform."""
    domain = select.DOMAIN
    config = DEFAULT_CONFIG
    await help_test_reloadable(hass, mqtt_client_mock, domain, config)


@pytest.mark.parametrize(
    ("topic", "value", "attribute", "attribute_value"),
    [
        ("state_topic", "milk", None, "milk"),
        ("state_topic", "beer", None, "beer"),
    ],
)
async def test_encoding_subscribable_topics(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    topic: str,
    value: str,
    attribute: str | None,
    attribute_value: Any,
) -> None:
    """Test handling of incoming encoded payload."""
    config = copy.deepcopy(DEFAULT_CONFIG[mqtt.DOMAIN][select.DOMAIN])
    config["options"] = ["milk", "beer"]
    await help_test_encoding_subscribable_topics(
        hass,
        mqtt_mock_entry_no_yaml_config,
        select.DOMAIN,
        config,
        topic,
        value,
        attribute,
        attribute_value,
    )


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG])
async def test_setup_manual_entity_from_yaml(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test setup manual configured MQTT entity."""
    await mqtt_mock_entry_no_yaml_config()
    platform = select.DOMAIN
    assert hass.states.get(f"{platform}.test")


async def test_unload_entry(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
) -> None:
    """Test unloading the config entry."""
    domain = select.DOMAIN
    config = DEFAULT_CONFIG
    await help_test_unload_config_entry_with_platform(
        hass, mqtt_mock_entry_no_yaml_config, domain, config
    )


async def test_persistent_state_after_reconfig(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test of the state is persistent after reconfiguring the select options."""
    await mqtt_mock_entry_no_yaml_config()
    discovery_data = '{ "name": "Milk", "state_topic": "test-topic", "command_topic": "test-topic", "options": ["milk", "beer"]}'
    await help_test_discovery_setup(hass, SELECT_DOMAIN, discovery_data, "milk")

    # assign an initial state
    async_fire_mqtt_message(hass, "test-topic", "beer")
    state = hass.states.get("select.milk")
    assert state.state == "beer"
    assert state.attributes["options"] == ["milk", "beer"]

    # remove "milk" option
    discovery_data = '{ "name": "Milk", "state_topic": "test-topic", "command_topic": "test-topic", "options": ["beer"]}'
    await help_test_discovery_setup(hass, SELECT_DOMAIN, discovery_data, "milk")

    # assert the state persistent
    state = hass.states.get("select.milk")
    assert state.state == "beer"
    assert state.attributes["options"] == ["beer"]
