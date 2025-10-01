
# The entity being operated on
entity_id = data.get('entity_id')

# The action being performed
action = data.get('action')
# 'notify_on' - The light has been turned on manually
# 'notify_off' - The light has been turned off manually
# 'turn_on' - Automatically turn on the light
# 'tick' - Regular update

if action == 'tick':
  logger.error('got tick')
  

bright_minutes = int(data.get('bright_minutes', 1))
dim_minutes = int(data.get('dim_minutes', 0))

dim_time_entity_id = 'origin_dim_at.' + entity_id.replace('.', '_')
shutoff_time_entity_id = 'origin_shutoff_at.' + entity_id.replace('.', '_')

def get_time(eid):
  state = hass.states.get(eid)
  if not state:
    return None
  state = state.state
  if not state:
    return None
  return dt_util.parse_datetime(state)

current_dim_time = get_time(dim_time_entity_id)
current_shutoff_time = get_time(shutoff_time_entity_id)


light_data = {
  'entity_id' : entity_id,
  'brightness' : 100
}

current_state = hass.states.get(entity_id)
logger.error("Got state: " + str(current_state.as_dict()))

state = hass.states.get(origin_entity_id)
logger.error("Got origin state: " + str(state))
attrs = {}
if state:
  attrs = state.attributes.as_dict()

logger.error("Got attrs: " + str(attrs))

attrs['count'] = attrs.get('count', 0) + 1

hass.states.set(origin_entity_id, "state", attrs)

if current_state.state == 'on':
  hass.services.call('light', 'turn_off', {'entity_id' : entity_id }, False)
else:
  hass.services.call('light', 'turn_on', {'entity_id' : entity_id, 'brightness' : 200 }, False)
   

