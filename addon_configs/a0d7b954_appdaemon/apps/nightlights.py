from __future__ import annotations

from typing import Any, List
from datetime import datetime, timedelta
from random import randint

import hassapi as hass

NUM_THREADS = 6


class NightLights(hass.Hass):
    debug: bool

    lights: List[str]

    turn_off_during_day: bool
    turn_on_at_night: bool

    off_entity: str
    on_entity: str

    thread: int

    def dbg(self, message):
        if self.debug:
            self.log(message)
        pass

    def arg(self, name: str, default: Any, require_entity_exists: bool = False):
        v = self.args.get(name, default)
        self.log(f'config: {name}: {v}')

        if v and require_entity_exists and not self.entity_exists(v):
            raise AttributeError(f'Entity {v} does not exist')

        return v

    def initialize(self):
        self.debug = bool(self.arg("debug", False))
        self.lights = self.listr(self.arg("lights", []), True)
        self.turn_off_during_day = bool(self.arg('turn_off_during_day', True))
        self.turn_on_at_night = bool(self.arg('turn_on_at_night', False))
        self.off_entity = str(self.arg('off_entity', default="", require_entity_exists=True))
        self.on_entity = str(self.arg('on_entity', default="", require_entity_exists=True))

        self.thread = int(self.arg("thread", randint(0, NUM_THREADS - 1)))

        self.set_app_pin(True)
        self.set_pin_thread(self.thread)

        self.run_minutely(self.tick, None)

    def tick(self, kwargs):
        # Enforce light state
        is_night = self.now_is_between("sunset - 00:30:00", "sunrise + 00:30:00")
        for e in self.lights:
            light_on = self.get_state(e, 'state') == 'on'
            if self.off_entity and self.get_state(self.off_entity, 'state') == 'on':
                if light_on:
                    self.log(f'Turning off {e} due to {self.off_entity} override')
                    self.turn_off(e)
            elif self.on_entity and self.get_state(self.on_entity, 'state') == 'on':
                if not light_on:
                    self.log(f'Turning on {e} due to {self.on_entity} override')
                    self.turn_on(e)
            elif self.turn_off_during_day and not is_night:
                if light_on:
                    self.log(f'Turning off {e}')
                    self.turn_off(e)
            elif self.turn_on_at_night and is_night:
                if not light_on:
                    self.log(f'Turning on {e}')
                    self.turn_on(e)

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
