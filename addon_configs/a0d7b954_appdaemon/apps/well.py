from __future__ import annotations

from typing import Any, List
from datetime import datetime, timedelta
from random import randint
import math

import hassapi as hass

NUM_THREADS = 6

class Well(hass.Hass):
    debug: bool
    thread: int
    
    notification_service: List[str]
    notification_title: str
    notification_repeat_minutes: int
    
    power_sensor: str 
    period_duration_minutes: int
    usage_threshold_kwh: float
    
    explained_usage_switches: List[str]

    last_notification_time: any
    last_explained_time: any
    power_samples_kwh: list[float]
    
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
        self.debug = bool(self.arg("debug", False))
        self.thread = int(self.arg("thread", randint(0, NUM_THREADS - 1)))
        
        self.notification_service = self.listr(self.required_arg('notification_service'), False)
        self.notification_title = self.required_arg('notification_title')
        self.notification_repeat_minutes = self.required_arg('notification_repeat_minutes')
        
        self.power_sensor = self.required_arg('power_sensor', True)
        self.period_duration_minutes = int(self.required_arg('period_duration_minutes'))
        self.usage_threshold_kwh = float(self.required_arg('usage_threshold_kwh'))
        
        self.power_samples_kwh = [math.inf] * (self.period_duration_minutes + 1)
        self.next_sample_index = 0
        
        self.last_explained_time = datetime.now() - timedelta(minutes=self.period_duration_minutes+1)
        self.last_notification_time = datetime.now() - timedelta(minutes=self.notification_repeat_minutes+1)
        
        self.explained_usage_switches = self.listr(self.arg("triggers", []), True)

        self.set_app_pin(True)
        self.set_pin_thread(self.thread)

        self.notify('Well monitoring enabled.')
        self.tick(None)
        self.run_minutely(self.tick, None)

    def notify(self, message):
        for n in self.notification_service:
            self.dbg(f'Notifying {n} with message "{message}"')
            self.call_service(n, message=message, title=self.notification_title)

    def tick(self, kwargs):
        now = datetime.now()

        # Check if there's an explanation for usage
        for e in self.explained_usage_switches:
            if self.get_state(e, 'state') == 'on':
                self.dbg(f'Explained usage from {e} detected at {now}')
                self.last_explained_time = now
                
        
        current_sample = float(self.get_state(self.power_sensor, 'state'))
        begin_sample = self.power_samples_kwh[0]
        delta = current_sample - begin_sample
        self.dbg(f'Last explained usage {self.last_explained_time}')
        self.dbg(f'Last notification time {self.last_notification_time}')
        self.dbg(f'Period begin {begin_sample}, end {current_sample}, delta {delta}')
        
        # Update samples 
        n = len(self.power_samples_kwh)
        self.power_samples_kwh = [self.power_samples_kwh[(i + 1) % n] for i in range(0, n)]
        self.power_samples_kwh[n - 1] = current_sample
        self.dbg(f'New Power samples: {self.power_samples_kwh}')
        
        if now - self.last_explained_time < timedelta(minutes=self.period_duration_minutes):
            self.dbg('Water usage is explained, ignoring usage')
        elif delta > self.usage_threshold_kwh:
            if now - self.last_notification_time < timedelta(minutes=self.notification_repeat_minutes):
                self.dbg('Suppressed notification')
            else:
                self.last_notification_time = now
                self.notify('Detected high usage')

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
