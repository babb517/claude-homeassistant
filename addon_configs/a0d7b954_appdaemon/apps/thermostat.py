from __future__ import annotations

from typing import Any, List
from datetime import datetime, timedelta
from random import randint

import hassapi as hass

NUM_THREADS = 6


class Thermostat(hass.Hass):
    debug: bool

    heaters: List[str]
    cooling: List[str]
    thermostats: List[str]

    min: float
    max: float

    active_at_night: bool
    active_during_day: bool

    thread: int

    def dbg(self, message):
        if self.debug:
            self.log(message)
        pass

    def arg(self, name: str, default: Any):
        v = self.args.get(name, default)
        self.log(f'config: {name}: {v}')
        return v

    def initialize(self):
        self.debug = bool(self.arg("debug", False))
        self.heaters = self.listr(self.arg("heaters", []), True)
        self.cooling = self.listr(self.arg("cooling", []), True)
        self.thermostats = self.listr(self.arg("thermostats", []), True)
        self.active_at_night = bool(self.arg('active_at_night', True))
        self.active_during_day = bool(self.arg('active_during_day', True))
        self.turn_devices_off = bool(self.arg('turn_devices_off', True))
        self.min = float(self.arg('min', -100))
        self.max = float(self.arg('max', 200))

        self.run_minutely(self.tick, None)

    def tick(self, kwargs):
        # Enforce light state
        is_night = self.get_state("binary_sensor.dark_outside") == "on"

        should_heat = False
        should_cool = False

        if (is_night and self.active_at_night) or (not is_night and self.active_during_day):
            for e in self.thermostats:
                state = self.get_state(e, attribute="all")
                self.dbg(f"{e} state {state}")
                
                if float(state.get('state', 1000)) < self.min or float(state.get('temperature', 1000)) < self.min:
                    self.dbg(f"Turning on heat as {e} is under {self.min}")
                    should_heat = True
                elif state.get('Hvac action') == 'heating':
                    self.dbg(f"Turning on heat as {e} is heating")
                    should_heat = True
                    
                if float(state.get('state', 1000)) > self.max or float(state.get('temperature', 1000)) < self.max:
                    self.dbg(f"Turning on cooling as {e} is over {self.max}")
                    should_cool = True
                elif state.get('Hvac action') == 'cooling':
                    self.dbg(f"Turning on cooling as {e} is cooling")
                    should_cool = True

        else:
            self.dbg("Not active")

        self.dbg(f"should_heat = {should_heat}")
        self.dbg(f"should_cool = {should_cool}")
        
        for e in self.heaters:
            heat_on = self.get_state(e, 'state') == 'on'
            if heat_on and not should_heat and self.turn_devices_off:
                self.log(f'Turning off {e}')
                self.turn_off(e)
            elif not heat_on and should_heat:
                self.log(f'Turning on {e}')
                self.turn_on(e)
                
        for e in self.cooling:
            cool_on = self.get_state(e, 'state') == 'on'
            if cool_on and not should_cool and self.turn_devices_off:
                self.log(f'Turning off {e}')
                self.turn_off(e)
            elif not cool_on and should_cool:
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
