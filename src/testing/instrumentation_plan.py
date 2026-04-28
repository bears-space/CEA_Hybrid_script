"""Instrumentation recommendations and expected data schemas."""

from __future__ import annotations

from typing import Mapping

from src.testing.test_types import InstrumentationChannel, InstrumentationPlan, TestArticleDefinition


def _channel(
    name: str,
    sensor_type: str,
    units: str,
    sampling_rate_hz: float,
    location: str,
    required: bool,
    notes: list[str] | None = None,
) -> InstrumentationChannel:
    return InstrumentationChannel(
        channel_name=name,
        sensor_type=sensor_type,
        units=units,
        sampling_rate_hz=sampling_rate_hz,
        location_description=location,
        required_flag=required,
        notes=list(notes or []),
    )


def build_instrumentation_plans(
    testing_config: Mapping[str, object],
    articles: list[TestArticleDefinition],
) -> list[InstrumentationPlan]:
    """Generate core instrumentation expectations for each test article."""

    defaults = dict(testing_config.get("instrumentation_defaults", {}))
    hotfire_rate_hz = float(defaults.get("hotfire_sampling_rate_hz", 1000.0))
    coldflow_rate_hz = float(defaults.get("coldflow_sampling_rate_hz", 100.0))
    plans: list[InstrumentationPlan] = []
    for article in articles:
        channels: list[InstrumentationChannel]
        if article.article_type == "coupon":
            channels = [
                _channel("coupon_mass_kg", "mass", "kg", 1.0, "Coupon pre/post-test mass", True),
                _channel("coupon_density_kg_m3", "derived_property", "kg/m^3", 1.0, "Coupon density characterization", True),
                _channel("manufacturing_batch_id", "metadata", "-", 1.0, "Batch traceability", True),
            ]
        elif article.article_type == "coldflow_rig":
            channels = [
                _channel("time_s", "clock", "s", coldflow_rate_hz, "DAQ master clock", True),
                _channel("upstream_pressure_pa", "pressure", "Pa", coldflow_rate_hz, "Feed manifold upstream tap", True),
                _channel("injector_inlet_pressure_pa", "pressure", "Pa", coldflow_rate_hz, "Injector inlet tap", False),
                _channel("downstream_pressure_pa", "pressure", "Pa", coldflow_rate_hz, "Injector discharge / chamber surrogate tap", True),
                _channel("mass_flow_kg_s", "flow_meter", "kg/s", coldflow_rate_hz, "Primary flow measurement", True),
                _channel("fluid_temperature_k", "thermocouple", "K", coldflow_rate_hz, "Working fluid bulk temperature", True),
                _channel("valve_state", "valve_state", "-", coldflow_rate_hz, "Main valve timing and state", False),
            ]
        else:
            channels = [
                _channel("time_s", "clock", "s", hotfire_rate_hz, "DAQ master clock", True),
                _channel("chamber_pressure_pa", "pressure", "Pa", hotfire_rate_hz, "Primary chamber pressure tap", True),
                _channel("tank_pressure_pa", "pressure", "Pa", hotfire_rate_hz, "Tank pressure tap", True),
                _channel("injector_inlet_pressure_pa", "pressure", "Pa", hotfire_rate_hz, "Injector manifold tap", False),
                _channel("thrust_n", "load_cell", "N", hotfire_rate_hz, "Main thrust stand load cell", True),
                _channel("ignition_signal", "ignition_signal", "-", hotfire_rate_hz, "Ignition command or current signature", False),
                _channel("valve_state", "valve_state", "-", hotfire_rate_hz, "Valve timing and sequence logging", False),
                _channel("oxidizer_mass_flow_kg_s", "flow_meter", "kg/s", hotfire_rate_hz, "Oxidizer flow estimate or flow meter", False),
                _channel("tank_mass_kg", "tank_mass", "kg", max(hotfire_rate_hz / 10.0, 20.0), "Tank mass or scale", False),
                _channel("chamber_wall_temp_k", "thermocouple", "K", max(hotfire_rate_hz / 20.0, 10.0), "Representative wall-temperature indicator", False),
                _channel("video_event_marker", "high_speed_video", "-", 100.0, "Video or anomaly marker stream", False),
            ]
        required_core_channels = [channel.channel_name for channel in channels if channel.required_flag]
        optional_channels = [channel.channel_name for channel in channels if not channel.required_flag]
        plans.append(
            InstrumentationPlan(
                article_id=article.article_id,
                channels=channels,
                required_core_channels=required_core_channels,
                optional_channels=optional_channels,
                synchronization_notes=[
                    "All channels should share a common DAQ clock or documented synchronization reference.",
                    "Valve events and ignition commands should be timestamped on the same time basis as pressure and thrust.",
                ],
                data_file_expectations=[
                    "JSON datasets should provide a `time_series_channels` mapping with consistent-length arrays.",
                    "CSV datasets should provide one row per sample with standardized or mapped channel names.",
                ],
                notes=["This plan defines required data for model comparison and calibration, not test-stand control."],
            )
        )
    return plans
