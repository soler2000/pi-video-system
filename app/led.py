_state={"enabled":False,"brightness":50,"color":"#ffffff","animation":"solid"}

def get_state():
    return dict(_state)

def apply_state(new):
    _state.update({k:v for k,v in new.items() if k in _state}); return True
