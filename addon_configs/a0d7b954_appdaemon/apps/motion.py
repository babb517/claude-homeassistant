from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from random import randint
from typing import Any, List, Optional

import hassapi as hass

NUM_THREADS = 6


class NotificationTime(Enum):
    never = 0
    always = 1
    night = 2
    day = 3


@dataclass
class Sensor:
    name: str
    entity: str
    icon: str
    critical: NotificationTime
    notify: NotificationTime
    notification_period: timedelta
    snapshot_period: timedelta

    last_notification_time: datetime
    last_snapshot_time: datetime

    def __init__(self, definition: dict, validate_entity):
        self.name = definition['name']
        self.entity = validate_entity(definition['entity'])
        self.icon = definition.get('icon', 'sfsymbols:notifications')
        self.critical = NotificationTime[definition.get('critical', 'never')]
        self.notify = NotificationTime[definition.get('notify', 'always')]
        self.notification_period = timedelta(minutes=int(definition['notification_period_minutes']))

        if 'snapshot_period_minutes' in definition:
            self.snapshot_period = timedelta(minutes=int(definition['snapshot_period_minutes']))
        else:
            self.snapshot_period = self.notification_period

        last_time = datetime.now() - max(self.notification_period, self.snapshot_period)
        self.last_notification_time = last_time
        self.last_snapshot_time = last_time


@dataclass
class Camera:
    name: str
    entity: str

    sensors: List[Sensor]

    def __init__(self, definition, validate_entity):
        self.name = definition['name']
        self.entity = validate_entity(definition['entity'])

        self.sensors = [Sensor(s, validate_entity) for s in definition['sensors']]


class Motion(hass.Hass):
    debug: bool
    thread: int

    notification_service: List[str]
    cameras: List[Camera]

    def dbg(self, message):
        if self.debug:
            self.log(message)
        pass

    def arg(self, name: str, default: Any):
        v = self.args.get(name, default)
        self.log(f'config: {name}: {v}')
        return v

    def required_arg(self, name: str, entities_exist: bool = False):
        v = self.args.get(name, None)
        if not v:
            raise Exception(f'Expected argument "{name}"')
        elif entities_exist and not self.entity_exists(v):
            raise Exception(f'Entity {v} does not exist')

        return v

    def initialize(self):

        def validate_entity(entity: str):
            if not self.entity_exists(entity):
                raise RuntimeError(f'Entity {entity} does not exist')
            return entity

        self.debug = bool(self.arg("debug", False))
        self.thread = int(self.arg("thread", randint(0, NUM_THREADS - 1)))
        self.notification_service = self.listr(self.required_arg('notification_service'), False)

        camera_configs = self.required_arg('cameras')
        self.cameras = [Camera(c, validate_entity) for c in camera_configs]

        self.dbg(self.cameras)

        for c in self.cameras:
            for sensor in c.sensors:
                self.dbg(f'Listening for events for {sensor.entity}')
                self.listen_state(self.motion, sensor.entity, new="on", camera=c, sensor=sensor)

    def motion(self, entity, attribute, old, new, cb_args):
        camera: Camera = cb_args["camera"]
        sensor: Sensor = cb_args["sensor"]
        now = datetime.now()

        if (now - sensor.last_notification_time) > sensor.notification_period and self.is_enabled(sensor.notify):
            self.notify(camera, sensor)
        elif (now - sensor.last_snapshot_time) > sensor.snapshot_period:
            self.snapshot(camera, sensor)
        else:
            self.dbg(f'Suppressing event {camera.name}, sensor {sensor}')

    internal_snapshot_path = '/config/www/camera_events'
    external_snapshot_path = '/local/camera_events'

    def snapshot(self, camera: Camera, sensor: Sensor, now: Optional[datetime] = None) -> str:
        self.dbg(f'Create snapshot for camera {camera.name}, sensor {sensor.name}')

        if not now:
            now = datetime.now()

        sensor.last_snapshot_time = now
        time_str = now.strftime("%h %d %I:%M:%S %p")

        camera_path = os.path.join(f'{camera.name} Images', f'{sensor.name} - {time_str}.jpg')
        sensor_path = os.path.join(f'{sensor.name} Images', f'{camera.name} - {time_str}.jpg')

        internal_camera_path = os.path.join(self.internal_snapshot_path, camera_path)
        self.dbg(f'Snapshotting {camera.name} to {internal_camera_path}')
        self.call_service(
            service='camera/snapshot',
            entity_id=camera.entity,
            filename=internal_camera_path
        )

        # Create a symlink to power alternate galleries
        internal_sensor_path = os.path.join(self.internal_snapshot_path, sensor_path)
        os.makedirs(os.path.dirname(internal_sensor_path), exist_ok=True)
        os.symlink(internal_camera_path, internal_sensor_path)

        return os.path.join(self.external_snapshot_path, camera_path)

    def is_enabled(self, nt: NotificationTime):
        if nt == NotificationTime.always:
            return True
        elif nt == NotificationTime.night:
            return self.get_state("binary_sensor.dark_outside") == "on"
        elif nt == NotificationTime.day:
            return self.get_state("binary_sensor.dark_outside") == "off"
        else:
            return False

    def notify(self, camera: Camera, sensor: Sensor):
        self.dbg(f'Notifying for camera {camera.name}, sensor {sensor.name}')
        now = datetime.now()
        sensor.last_notification_time = now

        external = self.snapshot(camera, sensor, now)

        is_critical = self.is_enabled(sensor.critical)

        for n in self.notification_service:
            message = f'{camera.name} detected {sensor.name}'
            self.dbg(f'Notifying {n} with message "{message}"')
            self.call_service(
                service=n,
                message=message,
                title='Motion Event',
                data={
                    'notification_icon': sensor.icon,
                    'url': external,
                    'entity_id': camera.entity,
                    'attachment': {
                        'content-type': 'video'
                    },
                    'push': {
                        'category': 'camera',
                        'sound': {
                            'critical': '1' if is_critical else '0',
                            'volume': '0.0' if is_critical else '0.0',
                            'name': 'default'
                        }
                    }
                }
            )

    def listr(self, list_or_string: list[str] | set[str] | str | Any, entities_exist: bool) -> list[str]:

        entity_list: list[str] = []

        if isinstance(list_or_string, str):
            entity_list.append(list_or_string)
        elif isinstance(list_or_string, (list, set)):
            entity_list += list_or_string
        elif list_or_string:
            self.log(f"{list_or_string} is of type {type(list_or_string)} and not 'Union[List[str], Set[str], str]'")

        if entities_exist:
            return list(filter(self.entity_exists, entity_list))
        else:
            return entity_list
