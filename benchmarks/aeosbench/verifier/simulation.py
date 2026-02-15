"""BSK-based simulation environment for AEOS-Bench verifier.

Direct port of constellation/environments/basilisk/basilisk_satellite.py
and constellation/environments/basilisk/basilisk_environment.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from Basilisk.architecture import messaging
from Basilisk.architecture.messaging import VehicleConfigMsg, VehicleConfigMsgPayload
from Basilisk.fswAlgorithms.locationPointing import locationPointing
from Basilisk.fswAlgorithms.mrpFeedback import mrpFeedback
from Basilisk.fswAlgorithms.rwMotorTorque import rwMotorTorque
from Basilisk.simulation.eclipse import Eclipse
from Basilisk.simulation.groundLocation import GroundLocation
from Basilisk.simulation.groundMapping import GroundMapping
from Basilisk.simulation.ReactionWheelPower import ReactionWheelPower
from Basilisk.simulation.reactionWheelStateEffector import ReactionWheelStateEffector
from Basilisk.simulation.simpleBattery import SimpleBattery
from Basilisk.simulation.simpleNav import SimpleNav
from Basilisk.simulation.simplePowerSink import SimplePowerSink
from Basilisk.simulation.simpleSolarPanel import SimpleSolarPanel
from Basilisk.simulation.spacecraft import HubEffector, Spacecraft
from Basilisk.utilities import orbitalMotion, unitTestSupport
from Basilisk.utilities.simIncludeGravBody import gravBodyFactory, spiceInterface
from Basilisk.utilities.simIncludeRW import rwFactory
from Basilisk.utilities.SimulationBaseClass import SimBaseClass

from .constants import (
    IDENTITY_MATRIX_3,
    INTERVAL,
    MU_EARTH,
    RADIUS_EARTH,
    TIMESTAMP,
    UNIT_VECTOR_Z,
)
from .models import Constellation, Satellite, TaskSet


def sec2nano(seconds: float) -> int:
    """Convert seconds to nanoseconds (Basilisk time unit)."""
    return int(seconds * 1e9)


def datetime2basilisk(date_object: datetime) -> str:
    """Convert datetime to Basilisk format string."""
    return date_object.strftime("%Y %b %d %H:%M:%S.%f (UTC)")


def str2datetime(standard_time: str) -> datetime:
    """Turn standard format('YYYYMMDDhhmmss') into datetime."""
    return datetime.strptime(standard_time, "%Y%m%d%H%M%S")


def lla2pcpf(
    lla_position: tuple[float, float, float],
    planet_spherical_radius: float = RADIUS_EARTH,
) -> list[float]:
    """Lat/Long/Alt coordinate -> planet-centered planet-fixed coordinate.

    Args:
        lla_position: [rad] Position in (latitude, longitude, altitude).
        planet_spherical_radius: [m] Planetary equatorial radius.

    Returns:
        pcpf_position: [m] Position in planet-centered planet-fixed frame.
    """
    lat, lon, alt = lla_position
    # Spherical Earth model (eccentricity = 0)
    n_val = planet_spherical_radius
    pcpf_position = [
        (n_val + alt) * np.cos(lat) * np.cos(lon),
        (n_val + alt) * np.cos(lat) * np.sin(lon),
        (n_val + alt) * np.sin(lat),
    ]
    return pcpf_position


class BSKSatellite:
    """BSK satellite wrapper with all modules.

    Mirrors constellation/environments/basilisk/basilisk_satellite.py
    """

    def __init__(
        self,
        simulator: SimBaseClass,
        process: Any,
        grav_body_factory: gravBodyFactory,
        spice_object: spiceInterface,
        satellite: Satellite,
    ) -> None:
        self._id = satellite.id
        self._orbit_id = satellite.orbit_id

        # Create task
        self._task_name = f"task-{self._id}"
        task_timestep = sec2nano(INTERVAL)
        process.addTask(simulator.CreateNewTask(self._task_name, task_timestep))

        self.setup_models(simulator, satellite)
        self.connect_messages(grav_body_factory, spice_object)

        # Custom variables
        self._sensor_type = satellite.sensor.type
        self._reaction_wheels = satellite.reaction_wheels

    def setup_models(self, simulator: SimBaseClass, satellite: Satellite) -> None:
        """Create all BSK modules for this satellite."""
        self._spacecraft = self._setup_spacecraft(satellite)
        simulator.AddModelToTask(self._task_name, self._spacecraft)

        self._eclipse = self._setup_eclipse()
        simulator.AddModelToTask(self._task_name, self._eclipse)

        self._solar_panel = self._setup_solar_panel(satellite)
        simulator.AddModelToTask(self._task_name, self._solar_panel)

        self._power_sink = self._setup_power_sink(satellite)
        simulator.AddModelToTask(self._task_name, self._power_sink)

        self._battery = self._setup_battery(satellite)
        simulator.AddModelToTask(self._task_name, self._battery)

        self._simple_navigation = self._setup_simple_navigation()
        simulator.AddModelToTask(self._task_name, self._simple_navigation)

        self._pointing_location = self._setup_pointing_location()
        simulator.AddModelToTask(self._task_name, self._pointing_location)

        self._pointing_guide = self._setup_pointing_guide()
        simulator.AddModelToTask(self._task_name, self._pointing_guide)

        self._ground_mapping = self._setup_ground_mapping(satellite)
        simulator.AddModelToTask(self._task_name, self._ground_mapping)

        self._rw_factory = self._setup_rw_factory(satellite)
        # NOTE: rw_factory not added to task (just creates RWs)

        self._mrp_control = self._setup_mrp_control(satellite)
        simulator.AddModelToTask(self._task_name, self._mrp_control)

        self._rw_motor_torque = self._setup_rw_motor_torque()
        simulator.AddModelToTask(self._task_name, self._rw_motor_torque)

        self._rw_state_effector = self._setup_rw_state_effector()
        simulator.AddModelToTask(self._task_name, self._rw_state_effector)

        self._rw_power_list = self._setup_rw_power_list(satellite)
        for rw_power in self._rw_power_list:
            simulator.AddModelToTask(self._task_name, rw_power)

    def _setup_spacecraft(self, satellite: Satellite) -> Spacecraft:
        """Setup spacecraft hub with initial state."""
        spacecraft = Spacecraft()
        spacecraft.ModelTag = f"spacecraft-{self._id}"
        hub: HubEffector = spacecraft.hub

        # Convert orbital elements to position/velocity
        r_CN_N, v_CN_N = self._compute_rv(satellite)
        hub.r_CN_NInit = r_CN_N
        hub.v_CN_NInit = v_CN_N

        # Mass and inertia
        hub.mHub = satellite.mass
        hub.r_BcB_B = np.reshape(satellite.center_of_mass, (-1, 1))
        # Inertia must be a flat list/tuple of 9 elements for np2EigenMatrix3d
        hub.IHubPntBc_B = unitTestSupport.np2EigenMatrix3d(list(satellite.inertia))
        hub.sigma_BNInit = np.reshape(satellite.mrp_attitude_bn, (-1, 1))

        return spacecraft

    def _compute_rv(
        self, satellite: Satellite
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute position/velocity from orbital elements."""
        orbit = satellite.orbit if hasattr(satellite, "orbit") else None
        if orbit is None:
            # Use orbit_id to look up in constellation
            raise ValueError("Satellite needs orbit reference")

        orbital_elements = orbitalMotion.ClassicElements()
        orbital_elements.e = orbit.eccentricity
        orbital_elements.a = orbit.semi_major_axis
        orbital_elements.i = np.radians(orbit.inclination)
        orbital_elements.Omega = np.radians(orbit.raan)
        orbital_elements.omega = np.radians(orbit.argument_of_perigee)
        orbital_elements.f = np.radians(satellite.true_anomaly)

        return orbitalMotion.elem2rv(MU_EARTH, orbital_elements)

    def _setup_eclipse(self) -> Eclipse:
        """Setup eclipse module."""
        eclipse = Eclipse()
        eclipse.ModelTag = f"eclipse-{self._id}"
        return eclipse

    def _setup_solar_panel(self, satellite: Satellite) -> SimpleSolarPanel:
        """Setup solar panel."""
        solar_panel = SimpleSolarPanel()
        solar_panel.ModelTag = f"solar_panel-{self._id}"
        sp = satellite.solar_panel
        solar_panel.setPanelParameters(
            sp.direction.tolist(), sp.area, sp.efficiency
        )
        return solar_panel

    def _setup_power_sink(self, satellite: Satellite) -> SimplePowerSink:
        """Setup power sink (sensor power consumption)."""
        power_sink = SimplePowerSink()
        power_sink.ModelTag = f"power_sink-{self._id}"
        power_sink.powerStatus = 1 if satellite.sensor.enabled else 0
        power_sink.nodePowerOut = -satellite.sensor.power
        return power_sink

    def _setup_battery(self, satellite: Satellite) -> SimpleBattery:
        """Setup battery."""
        battery = SimpleBattery()
        battery.ModelTag = f"battery-{self._id}"
        battery.storageCapacity = satellite.battery.capacity
        battery.storedCharge_Init = (
            satellite.battery.percentage * satellite.battery.capacity
        )
        return battery

    def _setup_simple_navigation(self) -> SimpleNav:
        """Setup simple navigation module."""
        simple_navigation = SimpleNav()
        simple_navigation.ModelTag = f"simple_navigation-{self._id}"
        return simple_navigation

    def _setup_pointing_location(self) -> GroundLocation:
        """Setup ground location for attitude pointing."""
        pointing_location = GroundLocation()
        pointing_location.ModelTag = f"pointing_location-{self._id}"
        pointing_location.planetRadius = RADIUS_EARTH
        pointing_location.minimumElevation = 0
        return pointing_location

    def _setup_pointing_guide(self) -> locationPointing:
        """Setup location pointing guidance."""
        pointing_guide = locationPointing()
        pointing_guide.ModelTag = f"pointing_guide-{self._id}"
        pointing_guide.pHat_B = UNIT_VECTOR_Z
        return pointing_guide

    def _setup_ground_mapping(self, satellite: Satellite) -> GroundMapping:
        """Setup ground mapping for visibility checking."""
        ground_mapping = GroundMapping()
        ground_mapping.ModelTag = f"ground_mapping-{self._id}"
        ground_mapping.minimumElevation = 0
        ground_mapping.maximumRange = 1e9
        ground_mapping.cameraPos_B = [0, 0, 0]
        ground_mapping.nHat_B = UNIT_VECTOR_Z
        ground_mapping.halfFieldOfView = np.radians(
            satellite.sensor.half_field_of_view
        )
        return ground_mapping

    def _setup_rw_factory(self, satellite: Satellite) -> rwFactory:
        """Setup reaction wheel factory and create wheels."""
        rw_factory = rwFactory()
        for i, reaction_wheel in enumerate(satellite.reaction_wheels):
            rw_factory.create(
                reaction_wheel.rw_type,
                reaction_wheel.direction.tolist(),
                maxMomentum=reaction_wheel.max_momentum,
                Omega=reaction_wheel.speed_init,
                RWModel=messaging.BalancedWheels,
                label=self._reaction_wheel_id(i),
            )
        return rw_factory

    def _setup_rw_motor_torque(self) -> rwMotorTorque:
        """Setup RW motor torque mapping."""
        rw_motor_torque = rwMotorTorque()
        rw_motor_torque.ModelTag = f"rw_motor_torque-{self._id}"
        rw_motor_torque.controlAxes_B = IDENTITY_MATRIX_3
        return rw_motor_torque

    def _setup_mrp_control(self, satellite: Satellite) -> mrpFeedback:
        """Setup MRP feedback control."""
        mrp_control = mrpFeedback()
        mrp_control.ModelTag = f"mrpFeedback-{self._id}"
        mrp_control.K = satellite.mrp_control.k
        mrp_control.Ki = satellite.mrp_control.ki
        mrp_control.P = satellite.mrp_control.p
        mrp_control.integralLimit = satellite.mrp_control.integral_limit

        # Create vehicle config message with inertia
        satellite_config_out = VehicleConfigMsgPayload()
        # Inertia is already a 9-element tuple
        satellite_config_out.ISCPntB_B = list(satellite.inertia)
        config_data_msg = VehicleConfigMsg()
        config_data_msg.write(satellite_config_out)
        mrp_control.vehConfigInMsg.subscribeTo(config_data_msg)
        self._config_data_msg = config_data_msg  # Prevent garbage collection

        return mrp_control

    def _setup_rw_state_effector(self) -> ReactionWheelStateEffector:
        """Setup RW state effector."""
        rw_state_effector = ReactionWheelStateEffector()
        rw_state_effector.ModelTag = f"rw_state_effector-{self._id}"
        return rw_state_effector

    def _setup_rw_power_list(
        self, satellite: Satellite
    ) -> list[ReactionWheelPower]:
        """Setup power models for each reaction wheel."""
        rw_power_list: list[ReactionWheelPower] = []
        for i, reaction_wheel in enumerate(satellite.reaction_wheels):
            rw_power = ReactionWheelPower()
            rw_power.ModelTag = f"rw_power-{self._id}-{i}"
            rw_power.basePowerNeed = reaction_wheel.power
            rw_power.mechToElecEfficiency = reaction_wheel.efficiency
            rw_power_list.append(rw_power)
        return rw_power_list

    def connect_messages(
        self,
        grav_body_factory: gravBodyFactory,
        spice_object: spiceInterface,
    ) -> None:
        """Connect all message subscriptions between modules."""
        earth_state = spice_object.planetStateOutMsgs[0]
        sun_state = spice_object.planetStateOutMsgs[1]

        # grav_factory
        grav_body_factory.addBodiesTo(self._spacecraft)

        # eclipse
        self._eclipse.addSpacecraftToModel(self._spacecraft.scStateOutMsg)
        self._eclipse.addPlanetToModel(earth_state)
        self._eclipse.sunInMsg.subscribeTo(sun_state)

        # solar_panel
        self._solar_panel.stateInMsg.subscribeTo(self._spacecraft.scStateOutMsg)
        self._solar_panel.sunEclipseInMsg.subscribeTo(
            self._eclipse.eclipseOutMsgs[0]
        )
        self._solar_panel.sunInMsg.subscribeTo(sun_state)

        # battery
        self._battery.addPowerNodeToModel(self._solar_panel.nodePowerOutMsg)
        self._battery.addPowerNodeToModel(self._power_sink.nodePowerOutMsg)
        for rw_power in self._rw_power_list:
            self._battery.addPowerNodeToModel(rw_power.nodePowerOutMsg)

        # simple_navigation
        self._simple_navigation.scStateInMsg.subscribeTo(
            self._spacecraft.scStateOutMsg
        )

        # pointing_location
        self._pointing_location.planetInMsg.subscribeTo(earth_state)
        self._pointing_location.addSpacecraftToModel(
            self._spacecraft.scStateOutMsg
        )

        # pointing_guide
        self._pointing_guide.scAttInMsg.subscribeTo(
            self._simple_navigation.attOutMsg
        )
        self._pointing_guide.scTransInMsg.subscribeTo(
            self._simple_navigation.transOutMsg
        )
        self._pointing_guide.locationInMsg.subscribeTo(
            self._pointing_location.currentGroundStateOutMsg
        )

        # ground_mapping
        self._ground_mapping.scStateInMsg.subscribeTo(
            self._spacecraft.scStateOutMsg
        )
        self._ground_mapping.planetInMsg.subscribeTo(earth_state)

        # rw_factory - add RWs to spacecraft
        self._rw_factory.addToSpacecraft(
            self._spacecraft.ModelTag,
            self._rw_state_effector,
            self._spacecraft,
        )

        # mrp_control
        # Store as instance variable to prevent garbage collection
        self._rw_params_message = self._rw_factory.getConfigMessage()
        self._mrp_control.guidInMsg.subscribeTo(
            self._pointing_guide.attGuidOutMsg
        )
        self._mrp_control.rwParamsInMsg.subscribeTo(self._rw_params_message)
        self._mrp_control.rwSpeedsInMsg.subscribeTo(
            self._rw_state_effector.rwSpeedOutMsg
        )

        # rw_motor_torque
        self._rw_motor_torque.vehControlInMsg.subscribeTo(
            self._mrp_control.cmdTorqueOutMsg
        )
        self._rw_motor_torque.rwParamsInMsg.subscribeTo(self._rw_params_message)
        self._rw_state_effector.rwMotorCmdInMsg.subscribeTo(
            self._rw_motor_torque.rwMotorTorqueOutMsg
        )

        # rw_power_list
        for rw_power, rw_out_message in zip(
            self._rw_power_list,
            self._rw_state_effector.rwOutMsgs,
        ):
            rw_power.rwStateInMsg.subscribeTo(rw_out_message)

    def toggle(self) -> None:
        """Toggle sensor on/off."""
        self._power_sink.powerStatus = 1 - self._power_sink.powerStatus

    def guide_attitude(self, target_location: tuple[float, float] | None) -> None:
        """Set attitude target location.

        Args:
            target_location: (lat_deg, lon_deg) or None to point at origin.
        """
        if target_location is None:
            self._pointing_location.specifyLocationPCPF([[0.0], [0.0], [0.0]])
        else:
            self._pointing_location.specifyLocation(
                np.radians(target_location[0]),
                np.radians(target_location[1]),
                0,
            )

    def _reaction_wheel_id(self, index: int) -> str:
        """Generate reaction wheel ID string."""
        return f"{index}RW{self._id}"

    @property
    def id(self) -> int:
        """Satellite ID."""
        return self._id

    @property
    def sensor_type(self) -> int:
        """Sensor type (0=VISIBLE, 1=NEAR_INFRARED)."""
        return self._sensor_type

    @property
    def is_sensor_enabled(self) -> bool:
        """Check if sensor is currently enabled."""
        return self._power_sink.powerStatus == 1

    @property
    def ground_mapping(self) -> GroundMapping:
        """Ground mapping module for visibility."""
        return self._ground_mapping


class BSKEnvironment:
    """BSK simulation environment for multiple satellites.

    Mirrors constellation/environments/basilisk/basilisk_environment.py
    """

    def __init__(
        self,
        constellation: Constellation,
        taskset: TaskSet,
        standard_time_init: str = TIMESTAMP,
    ) -> None:
        """Initialize BSK environment with all satellites.

        Args:
            constellation: Satellite constellation definition.
            taskset: Task set with target locations.
            standard_time_init: Initial timestamp string (YYYYMMDDhhmmss).
        """
        self._constellation = constellation
        self._taskset = taskset
        self._standard_time_init = standard_time_init

        # Create simulator
        simulator = SimBaseClass()
        task_name = "task_environment"
        process = simulator.CreateNewProcess("environment_process")
        process.addTask(simulator.CreateNewTask(task_name, sec2nano(INTERVAL)))

        # Setup gravity bodies
        grav_body_factory = gravBodyFactory()
        earth = grav_body_factory.createEarth()
        earth.isCentralBody = True
        grav_body_factory.createSun()

        # Setup SPICE
        date_object = str2datetime(standard_time_init)
        basilisk_time_init = datetime2basilisk(date_object)
        spice_object = grav_body_factory.createSpiceInterface(
            time=basilisk_time_init
        )
        spice_object.zeroBase = "Earth"
        simulator.AddModelToTask(task_name, spice_object)

        # Create satellites (sorted by ID for consistent ordering)
        bsk_satellites = []
        for satellite in sorted(constellation.satellites, key=lambda s: s.id):
            # Need to attach orbit data to satellite
            orbit = constellation.get_orbit(satellite.orbit_id)
            # Create a copy with orbit reference
            sat_with_orbit = self._attach_orbit(satellite, orbit)

            bsk_sat = BSKSatellite(
                simulator,
                process,
                grav_body_factory,
                spice_object,
                sat_with_orbit,
            )
            bsk_satellites.append(bsk_sat)

        # Register all tasks with each satellite's GroundMapping
        for bsk_sat in bsk_satellites:
            for task in taskset.tasks:
                lla_location = (
                    np.radians(task.coordinate[0]),
                    np.radians(task.coordinate[1]),
                    0,
                )
                pcpf_location = np.array(lla2pcpf(lla_location, RADIUS_EARTH))
                bsk_sat.ground_mapping.addPointToModel(pcpf_location)

        # Initialize simulation
        simulator.InitializeSimulation()
        simulator.ConfigureStopTime(0)  # Connect all messages
        simulator.ExecuteSimulation()

        self._simulator = simulator
        self._satellites = bsk_satellites
        self._spice_object = spice_object

    def _attach_orbit(self, satellite: Satellite, orbit: Any) -> Satellite:
        """Attach orbit data to satellite for RV computation."""
        # Create a new satellite with orbit attribute
        sat_dict = {
            "id": satellite.id,
            "orbit_id": satellite.orbit_id,
            "mass": satellite.mass,
            "inertia": satellite.inertia,
            "center_of_mass": satellite.center_of_mass,
            "solar_panel": satellite.solar_panel,
            "sensor": satellite.sensor,
            "battery": satellite.battery,
            "reaction_wheels": satellite.reaction_wheels,
            "mrp_control": satellite.mrp_control,
            "true_anomaly": satellite.true_anomaly,
            "mrp_attitude_bn": satellite.mrp_attitude_bn,
        }
        new_sat = Satellite(**sat_dict)
        new_sat.orbit = orbit  # type: ignore
        return new_sat

    def is_visible(self, taskset: TaskSet) -> np.ndarray:
        """Compute visibility matrix for current BSK state.

        Args:
            taskset: Task set to check visibility against.

        Returns:
            visibility: (n_sat, n_task) bool array.
        """
        n_sat = len(self._satellites)
        n_task = len(taskset.tasks)
        visibility = np.zeros((n_sat, n_task), dtype=bool)

        for sat_idx, satellite in enumerate(self._satellites):
            for task_idx, task in enumerate(taskset.tasks):
                access_message = satellite.ground_mapping.accessOutMsgs[task_idx]
                access = access_message.read().hasAccess
                state = satellite.is_sensor_enabled
                type_match = task.sensor_type == satellite.sensor_type
                visibility[sat_idx, task_idx] = access and state and type_match

        return visibility

    def take_actions(
        self, toggles: list[bool], target_locations: list[tuple[float, float] | None]
    ) -> None:
        """Apply actions to all satellites.

        Args:
            toggles: List of toggle commands per satellite.
            target_locations: List of target locations per satellite.
        """
        for satellite, toggle, target in zip(
            self._satellites, toggles, target_locations
        ):
            if toggle:
                satellite.toggle()
            satellite.guide_attitude(target)

    def step(self, time_nano: int) -> None:
        """Advance BSK simulation to specified time.

        Args:
            time_nano: Target time in nanoseconds.
        """
        self._simulator.ConfigureStopTime(time_nano)
        self._simulator.ExecuteSimulation()

    @property
    def satellites(self) -> list[BSKSatellite]:
        """List of BSK satellites."""
        return self._satellites

    @property
    def num_satellites(self) -> int:
        """Number of satellites."""
        return len(self._satellites)
