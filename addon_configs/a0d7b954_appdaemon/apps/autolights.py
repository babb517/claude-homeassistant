from __future__ import annotations

from typing import Any, List
from datetime import datetime, timedelta
from random import randint

import hassapi as hass

NUM_THREADS = 6


class AutoLights(hass.Hass):
    debug: bool

    lights: List[str]

    triggers: List[str]
    trigger_states: List[str]

    trigger_minutes: int
    trigger_during_day: bool
    trigger_level: float
    trigger_transition_seconds: int

    initial_minutes: int
    update_minutes: int
    dim_increment: float
    min_dim_level: float
    threshold_level: float
    dim_transition_seconds: int

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
        self.lights = self.listr(self.arg("lights", []), True)
        self.triggers = self.listr(self.arg("triggers", []), True)
        self.trigger_states = self.listr(self.arg('trigger_states', ['on']), False)

        self.trigger_minutes = int(self.arg("trigger_minutes", 10))
        self.trigger_during_day = bool(self.arg('trigger_during_day', False))
        self.trigger_level = float(self.arg("trigger_level", 1.0))
        self.trigger_transition_seconds = int(self.arg("trigger_transition_seconds", 0))

        self.initial_minutes = int(self.arg("initial_minutes", 30))
        self.update_minutes = int(self.arg("update_minutes", 15))
        self.dim_increment = float(self.arg("dim_increment", 0.2))
        self.min_dim_level = float(self.arg("min_dim_level", 0.0))
        self.dim_transition_seconds = int(self.arg("dim_transition_seconds", 30))

        self.threshold_level = float(self.arg("threshold_level", 0.1))

        self.states = {}

        self.listen_state(self.notify_trigger, self.triggers)
        self.listen_state(self.notify_light, self.lights)
        self.listen_state(self.notify_light, self.lights, atttribute='brightness')

        # Initial state
        for e in self.lights:
            state = self.get_entity(e).state
            self.notify_light(e, None, state, state, {})

        self.run_minutely(self.tick, None)

    def tick(self, kwargs):
        now = datetime.now()

        # update timing if the trigger is still active
        for entity in self.triggers:
            state = self.get_state(entity, 'state')
            self.notify_trigger(entity, None, state, state, {})

        # Ensure that we haven't missed any light events
        for e in self.lights:
            state = self.get_state(e, 'state')
            light_on = self.get_state(e, 'state') == 'on'
            if light_on != (e in self.states):
                self.notify_light(e, None, state, state, {})

        # Handle timeout
        for entity, state in list(self.states.items()):

            update_time = state.get('next_update_time', now)

            if now > update_time:
                cur = self.get_current_brightness(entity)
                if state.get('manual', True):
                    v = min(cur, max(self.min_dim_level, cur - self.dim_increment))
                    self.apply_brightness(entity, cur, v, self.dim_transition_seconds)
                    self.schedule_update(entity, self.update_minutes)
                else:
                    self.apply_brightness(entity, cur, 0, self.dim_transition_seconds)

    def can_trigger(self, entity, state):
        if state not in self.trigger_states:
            self.dbg(f'Ignoring trigger {entity} with {state} not in {self.trigger_states}')
        elif self.trigger_during_day:
            self.dbg(f'trigger_during_day {entity}')
            return True
        elif self.get_state("binary_sensor.dark_outside") == "on":
            self.dbg(f'night_time_trigger {entity} - dark_outside sensor is on')
            return True
        else:
            self.dbg(f'Ignoring trigger {entity}')
            return False

    def notify_trigger(self, entity, attribute, old, new, kwargs):
        if self.can_trigger(entity, new):
            for e in self.lights:
                current = self.get_current_brightness(e)
                self.apply_brightness(e, current, max(current, self.trigger_level), self.trigger_transition_seconds)
                self.schedule_update(e, self.trigger_minutes)

    def notify_light(self, entity, attribute, old, new, kwargs):

        now = datetime.now()
        update_time = self.states.get(entity, {}).get('last_update_time', now - timedelta(seconds=100))
        if update_time + timedelta(seconds=5) > now:
            self.dbg(f'Suppressing light event {entity}')
            return

        self.dbg(f'Light {entity} attribute {attribute} from {old} to {new}')

        if self.get_current_brightness(entity) == 0:
            self.untrack(entity)
        else:
            self.schedule_update(entity, self.initial_minutes, manual=True)

    def untrack(self, entity):
        if self.states.pop(entity, None):
            self.dbg(f'Untracking {entity}')
            pass

    def get_current_brightness(self, entity) -> float:
        current = self.get_state(entity, 'brightness', None)
        if current:
            return float(current) / 255.0
        else:
            # No dimming support
            return 1.0 if self.get_state(entity, 'state') == 'on' else 0.0

    def apply_brightness(self, entity: str, current: float, next: float, transition_seconds: int):

        vcur = int(round(current * 255.0))
        vnext = int(round(next * 255.0))

        if vcur == vnext:
            self.dbg(f'Brightness of {entity} is already {vnext}')
            return

        if vnext <= self.threshold_level:
            self.log(f'Turning off {entity} from {vcur}')
            self.turn_off(entity, transition=transition_seconds)
            self.untrack(entity)
        else:
            self.log(f'Setting brightness of {entity} from {vcur} to {vnext}')
            # self.call_service('adaptive_lighting/set_manual_control', entity=entity, manual_control='true')
            es = self.states.get(entity, {})
            es['last_update_time'] = datetime.now()
            self.states[entity] = es
            self.turn_on(entity, brightness=vnext, transition=transition_seconds)

    def schedule_update(self, entity: str, update_minutes: int, manual: bool = False):

        now = datetime.now()

        es = self.states.get(entity, {})

        update_time = es.get('next_update_time', now)
        update_time = max(update_time, now + timedelta(minutes=update_minutes))
        es['next_update_time'] = update_time
        if manual:
            es['manual'] = True

        self.dbg(f'Updating state {entity} to {es}')
        self.states[entity] = es

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
